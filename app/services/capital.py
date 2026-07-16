"""External-capital accounting shared by portfolio, cash, and history views.

"Invested" means money added from outside the portfolio. Trades, coupons,
deposit settlements, and reinvestment are internal cash movements. Older local
rows and incomplete broker history have no explicit top-up operation, so the
smallest cash injection needed to fund their recorded outflows is inferred.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from .. import config
from ..models import Instrument, Transaction


_ASSET_CASH_KINDS = {
    "buy", "sell", "coupon", "dividend", "interest", "fx_buy", "fx_sell",
}
_INTERNAL_CASH_MARKERS = (
    ":rub-to-deposit", ":deposit-to-rub",
    ":rub-to-currency", ":currency-to-rub",
    ":rub-to-security", ":security-to-rub",
)


def _is_rub_cash(tx: Transaction) -> bool:
    inst = tx.instrument
    return bool(inst and inst.kind == "currency" and inst.currency == "RUB")


def _is_internal_cash(tx: Transaction) -> bool:
    note = tx.note or ""
    return any(marker in note for marker in _INTERNAL_CASH_MARKERS)


def _is_broker_operation(tx: Transaction) -> bool:
    return (tx.note or "").startswith("op:")


def _is_legacy_manual_asset_flow(tx: Transaction) -> bool:
    """Rows created before the cash ledger represented outside money directly."""
    note = tx.note or ""
    return bool(
        tx.instrument
        and not _is_rub_cash(tx)
        and tx.kind in _ASSET_CASH_KINDS
        and not note.startswith("op:")
        and not note.startswith("audit:")
    )


def _flow_amount(tx: Transaction) -> float:
    amount = float(tx.amount or 0)
    if tx.kind == "topup":
        return abs(amount)
    if tx.kind == "withdrawal":
        return -abs(amount)
    return amount


def _run_pool(
    rows: list[Transaction],
    *,
    external_cash_predicate,
) -> dict[str, Any]:
    """Run a dated cash pool and infer only cash that recorded history lacks."""
    by_day: dict[date, list[Transaction]] = defaultdict(list)
    for tx in rows:
        by_day[tx.ts].append(tx)

    cash = 0.0
    contributed = 0.0
    withdrawn = 0.0
    inferred = 0.0
    events: list[tuple[date, float]] = []

    for day in sorted(by_day):
        day_flow = 0.0
        for tx in by_day[day]:
            amount = _flow_amount(tx)
            day_flow += amount
            if external_cash_predicate(tx):
                if tx.kind == "topup":
                    value = abs(amount)
                    contributed += value
                    events.append((day, -value))
                elif tx.kind == "withdrawal":
                    value = abs(amount)
                    withdrawn += value
                    events.append((day, value))
        cash += day_flow
        if cash < -0.005:
            missing = -cash
            contributed += missing
            inferred += missing
            events.append((day, -missing))
            cash = 0.0
        elif abs(cash) < 0.005:
            cash = 0.0

    return {
        "cash": cash,
        "contributed": contributed,
        "withdrawn": withdrawn,
        "inferred": inferred,
        "events": events,
    }


def _manual_pool(
    db: Session,
    on: date | None,
    transactions: list[Transaction] | None = None,
) -> dict[str, Any]:
    rows = []
    source = transactions if transactions is not None else db.query(Transaction).all()
    for tx in source:
        if on and tx.ts > on:
            continue
        if _is_rub_cash(tx) or _is_legacy_manual_asset_flow(tx):
            rows.append(tx)

    def is_external(tx: Transaction) -> bool:
        return (
            _is_rub_cash(tx)
            and tx.kind in {"topup", "withdrawal"}
            and not _is_internal_cash(tx)
        )

    return _run_pool(rows, external_cash_predicate=is_external)


def _broker_pool(
    db: Session,
    on: date | None,
    transactions: list[Transaction] | None = None,
) -> dict[str, Any]:
    source = transactions if transactions is not None else db.query(Transaction).all()
    rows = [
        tx for tx in source
        if _is_broker_operation(tx) and (not on or tx.ts <= on)
    ]
    return _run_pool(
        rows,
        external_cash_predicate=lambda tx: tx.kind in {"topup", "withdrawal"},
    )


def manual_cash_balance(db: Session, *, on: date | None = None) -> float:
    """Manual RUB after explicit ledger rows and compatible legacy asset flows."""
    return round(_manual_pool(db, on)["cash"], 2)


def _current_broker_opening_estimate(
    db: Session,
    *,
    broker_cash_from_operations: float,
) -> float:
    """Conservative opening-capital estimate for history missing before tracking."""
    estimate = 0.0
    for inst in db.query(Instrument).filter(Instrument.kind.in_(("bond", "share", "etf"))).all():
        meta = inst.meta or {}
        if not meta.get("tinvest_position_synced"):
            continue
        broker_quantity = float(meta.get("tinvest_current_quantity", 0) or 0)
        if broker_quantity <= 0:
            continue
        imported_quantity = 0.0
        for tx in sorted(inst.transactions, key=lambda item: (item.ts, item.id or 0)):
            if not _is_broker_operation(tx):
                continue
            quantity = abs(float(tx.quantity or 0))
            if tx.kind == "buy":
                imported_quantity += quantity
            elif tx.kind == "sell":
                imported_quantity = max(0.0, imported_quantity - quantity)
        missing_quantity = max(0.0, broker_quantity - imported_quantity)
        average_price = float(meta.get("tinvest_average_price", 0) or 0)
        estimate += missing_quantity * average_price

    broker_cash = 0.0
    for inst in db.query(Instrument).filter(
        Instrument.kind == "currency", Instrument.currency == "RUB"
    ).all():
        meta = inst.meta or {}
        broker_cash += float(meta.get("broker_balance", meta.get("balance", 0)) or 0)
    estimate += max(0.0, broker_cash - max(0.0, broker_cash_from_operations))
    return estimate


def capital_summary(
    db: Session,
    *,
    on: date | None = None,
    include_current_broker_state: bool = False,
    _transactions: list[Transaction] | None = None,
) -> dict[str, Any]:
    """Gross external contributions, external withdrawals, and XIRR events."""
    manual = _manual_pool(db, on, _transactions)
    broker = _broker_pool(db, on, _transactions)
    contributed = manual["contributed"] + broker["contributed"]
    withdrawn = manual["withdrawn"] + broker["withdrawn"]
    inferred = manual["inferred"] + broker["inferred"]
    events = [*manual["events"], *broker["events"]]

    if include_current_broker_state:
        opening = _current_broker_opening_estimate(
            db,
            broker_cash_from_operations=broker["cash"],
        )
        if opening > 0.005:
            event_day = (
                config.PORTFOLIO_TRACKING_START_DATE
                or min((tx.ts for tx in db.query(Transaction).all()), default=on or date.today())
            )
            contributed += opening
            inferred += opening
            events.append((event_day, -opening))

    return {
        "contributed": round(contributed, 2),
        "withdrawn": round(withdrawn, 2),
        "net": round(contributed - withdrawn, 2),
        "inferred": round(inferred, 2),
        "events": sorted(events, key=lambda item: item[0]),
    }
