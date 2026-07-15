"""Atomic local portfolio mutations and the combined RUB cash ledger."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import Instrument, Snapshot, Transaction
from . import portfolio


class LedgerConflict(ValueError):
    """The requested mutation conflicts with the current portfolio state."""


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,79}$")
_SECURITY_KINDS = {"bond", "share", "etf"}
_ACTION_TYPES = {
    "cash_topup", "cash_withdrawal", "open_deposit", "settle_deposit",
    "buy_currency", "sell_currency", "buy_security", "sell_security",
}


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return number


def _number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _day(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _request_id(value: str) -> str:
    value = value.strip()
    if not _REQUEST_ID.fullmatch(value):
        raise ValueError(
            "request_id must be 8-80 characters using letters, digits, dot, colon, underscore or dash"
        )
    return value


def _safe_note(marker: str, note: str = "") -> str:
    note = " ".join(note.strip().split())[:200]
    return f"{marker} | {note}" if note else marker


def _resolve_instrument(db: Session, identifier: str | int) -> Instrument | None:
    raw = str(identifier).strip()
    numeric = raw[3:] if raw.lower().startswith("id:") else raw
    if numeric.isdigit():
        found = db.get(Instrument, int(numeric))
        if found:
            return found
    lowered = raw.lower()
    found = db.query(Instrument).filter(or_(
        Instrument.name == raw,
        func.lower(Instrument.ticker) == lowered,
        func.lower(Instrument.isin) == lowered,
        func.lower(Instrument.figi) == lowered,
        func.lower(Instrument.name) == lowered,
    )).first()
    if found:
        return found
    return next(
        (instrument for instrument in db.query(Instrument).all()
         if instrument.name.casefold() == raw.casefold()),
        None,
    )


def get_or_create_rub_cash(db: Session) -> Instrument:
    instrument = (
        db.query(Instrument)
        .filter(Instrument.kind == "currency", Instrument.currency == "RUB")
        .order_by((Instrument.figi == "RUB000UTSTOM").desc(), Instrument.id)
        .first()
    )
    if instrument is None:
        instrument = Instrument(
            kind="currency",
            name="Рубли (RUB)",
            ticker="RUB",
            currency="RUB",
            last_price=1.0,
            meta={"manual": True, "broker_balance": 0.0},
        )
        db.add(instrument)
        db.flush()
    return instrument


def rub_cash_balance(db: Session) -> dict[str, float]:
    instruments = db.query(Instrument).filter(
        Instrument.kind == "currency", Instrument.currency == "RUB"
    ).all()
    broker = 0.0
    manual = 0.0
    for instrument in instruments:
        meta = instrument.meta or {}
        broker += float(meta.get("broker_balance", meta.get("balance", 0)) or 0)
        manual += sum(
            float(tx.amount or 0)
            for tx in instrument.transactions
            if tx.kind in {"topup", "withdrawal"}
        )
    return {
        "broker": round(broker, 2),
        "manual": round(manual, 2),
        "total": round(broker + manual, 2),
    }


def pending_reconciliations(db: Session, *, on: date | None = None) -> dict[str, Any]:
    """Assets whose contractual maturity needs an explicit local reconciliation."""
    on = on or date.today()
    active_by_id = {row["id"]: row for row in portfolio.positions(db, on=on)}
    items = []
    for instrument in db.query(Instrument).all():
        meta = instrument.meta or {}
        if instrument.kind == "deposit" and meta.get("status") != "closed":
            raw_close = meta.get("close_date")
            if raw_close and _day(raw_close, "close_date") <= on:
                payout = portfolio.deposit_value(instrument, on)
                items.append({
                    "instrument_id": instrument.id,
                    "name": instrument.name,
                    "kind": "deposit",
                    "maturity_date": raw_close,
                    "status": "awaiting_settlement",
                    "estimated_payout_rub": round(payout, 2),
                    "recommended_tool": "settle_deposit_to_rub",
                })
        elif instrument.kind == "bond" and instrument.id in active_by_id:
            raw_maturity = meta.get("maturity")
            if raw_maturity and _day(raw_maturity, "maturity") <= on:
                broker_managed = meta.get("source") == "tinvest"
                items.append({
                    "instrument_id": instrument.id,
                    "name": instrument.name,
                    "ticker": instrument.ticker,
                    "kind": "bond",
                    "maturity_date": raw_maturity,
                    "status": "awaiting_broker_sync" if broker_managed else "awaiting_manual_settlement",
                    "recommended_tool": "synchronize_tinvest" if broker_managed else "sell_manual_security",
                })
    items.sort(key=lambda item: (item["maturity_date"], item["name"]))
    return {"as_of": on.isoformat(), "items": items, "total": len(items)}


def _change_cash(
    db: Session,
    *,
    amount: float,
    on: date,
    marker: str,
    note: str = "",
) -> dict[str, float]:
    amount = _number(amount, "cash amount")
    before = rub_cash_balance(db)
    if amount < 0 and before["manual"] + amount < -0.005:
        raise LedgerConflict(
            f"insufficient manual RUB cash: available {before['manual']:.2f}, required {-amount:.2f}; "
            "T-Invest cash is broker-managed and cannot fund a manual asset directly"
        )
    instrument = get_or_create_rub_cash(db)
    db.add(Transaction(
        ts=on,
        instrument_id=instrument.id,
        kind="topup" if amount >= 0 else "withdrawal",
        quantity=round(abs(amount), 2),
        price=1.0,
        amount=round(amount, 2),
        note=_safe_note(marker, note),
    ))
    db.flush()
    return rub_cash_balance(db)


def _deposit_duplicate(db: Session, name: str, opened_on: date) -> None:
    for existing in db.query(Instrument).filter(Instrument.kind == "deposit").all():
        meta = existing.meta or {}
        if existing.name.casefold() == name.casefold() and meta.get("open_date") == opened_on.isoformat():
            raise LedgerConflict(
                f"deposit {name!r} with opening date {opened_on.isoformat()} already exists"
            )


def _open_deposit(db: Session, action: dict[str, Any], marker: str) -> dict[str, Any]:
    name = str(action.get("name", "")).strip()
    principal = _positive(action.get("principal"), "principal")
    opened_on = _day(action.get("open_date"), "open_date")
    closes_on = _day(action.get("close_date"), "close_date")
    rate = _number(action.get("annual_rate_pct"), "annual_rate_pct")
    mode = action.get("interest_mode", "simple")
    if not name:
        raise ValueError("name must not be empty")
    if closes_on <= opened_on:
        raise ValueError("close_date must be after open_date")
    if not 0 <= rate <= 100:
        raise ValueError("annual_rate_pct must be between 0 and 100")
    if mode not in {"simple", "monthly_capitalization"}:
        raise ValueError("interest_mode must be simple or monthly_capitalization")
    _deposit_duplicate(db, name, opened_on)
    _change_cash(
        db, amount=-principal, on=opened_on,
        marker=f"{marker}:rub-to-deposit", note=str(action.get("note", "")),
    )
    instrument = Instrument(
        kind="deposit",
        name=name,
        currency="RUB",
        meta={
            "principal": principal,
            "open_date": opened_on.isoformat(),
            "close_date": closes_on.isoformat(),
            "eff_rate": rate / 100,
            "interest_mode": mode,
            "status": "active",
        },
    )
    db.add(instrument)
    db.flush()
    db.add(Transaction(
        ts=opened_on,
        instrument_id=instrument.id,
        kind="buy",
        quantity=1,
        amount=-round(principal, 2),
        note=_safe_note(f"{marker}:deposit-opened", str(action.get("note", ""))),
    ))
    db.flush()
    estimate = portfolio.deposit_value(instrument, closes_on)
    return {
        "type": "open_deposit",
        "instrument_id": instrument.id,
        "name": instrument.name,
        "principal": round(principal, 2),
        "estimated_payout": round(estimate, 2),
        "estimated_interest": round(estimate - principal, 2),
    }


def _settle_deposit(db: Session, action: dict[str, Any], marker: str) -> dict[str, Any]:
    identifier = action.get("instrument")
    instrument = _resolve_instrument(db, identifier)
    if not instrument or instrument.kind != "deposit":
        raise ValueError(f"deposit not found: {identifier}")
    meta = dict(instrument.meta or {})
    if meta.get("status") == "closed":
        raise LedgerConflict(f"deposit is already closed: {instrument.name}")
    settled_on = _day(action.get("settled_on"), "settled_on")
    closes_on = _day(meta.get("close_date"), "close_date")
    actual = action.get("actual_payout_rub")
    if settled_on < closes_on and actual is None:
        raise ValueError("actual_payout_rub is required for an early deposit closure")
    estimated = portfolio.deposit_value(instrument, settled_on)
    payout = _positive(actual if actual is not None else estimated, "actual_payout_rub")
    principal = _positive(meta.get("principal"), "principal")
    result = round(payout - principal, 2)
    db.add(Transaction(
        ts=settled_on,
        instrument_id=instrument.id,
        kind="sell",
        quantity=1,
        amount=round(principal, 2),
        note=_safe_note(f"{marker}:deposit-principal", str(action.get("note", ""))),
    ))
    if abs(result) >= 0.005:
        db.add(Transaction(
            ts=settled_on,
            instrument_id=instrument.id,
            kind="interest",
            quantity=0,
            amount=result,
            note=_safe_note(f"{marker}:deposit-result", str(action.get("note", ""))),
        ))
    meta.update({
        "status": "closed",
        "closed_on": settled_on.isoformat(),
        "actual_payout": round(payout, 2),
        "settlement_estimated": actual is None,
    })
    instrument.meta = meta
    _change_cash(
        db, amount=payout, on=settled_on,
        marker=f"{marker}:deposit-to-rub", note=str(action.get("note", "")),
    )
    return {
        "type": "settle_deposit",
        "instrument_id": instrument.id,
        "name": instrument.name,
        "payout": round(payout, 2),
        "profit": result,
        "used_estimate": actual is None,
    }


def _currency(db: Session, code: str) -> Instrument | None:
    return db.query(Instrument).filter(
        Instrument.kind == "currency", Instrument.currency == code
    ).first()


def _buy_currency(db: Session, action: dict[str, Any], marker: str) -> dict[str, Any]:
    code = str(action.get("code", "")).strip().upper()
    if len(code) != 3 or not code.isascii() or not code.isalpha() or code == "RUB":
        raise ValueError("code must be a non-RUB three-letter currency code")
    quantity = _positive(action.get("quantity"), "quantity")
    total_cost = _positive(action.get("total_cost_rub"), "total_cost_rub")
    traded_on = _day(action.get("traded_on"), "traded_on")
    rate = total_cost / quantity
    _change_cash(
        db, amount=-total_cost, on=traded_on,
        marker=f"{marker}:rub-to-currency", note=str(action.get("note", "")),
    )
    instrument = _currency(db, code)
    if instrument is None:
        instrument = Instrument(
            kind="currency",
            name=str(action.get("name", "")).strip() or f"{code} cash",
            ticker=code,
            currency=code,
            last_price=float(action.get("current_rate") or rate),
            meta={"manual": True, "source": "manual"},
        )
        db.add(instrument)
        db.flush()
    elif (instrument.meta or {}).get("source") == "tinvest":
        raise LedgerConflict(f"{code} is broker-managed; synchronize T-Invest instead")
    else:
        if action.get("current_rate") is not None:
            instrument.last_price = _positive(action["current_rate"], "current_rate")
        elif not instrument.last_price:
            instrument.last_price = rate
    db.add(Transaction(
        ts=traded_on,
        instrument_id=instrument.id,
        kind="fx_buy",
        quantity=round(quantity, 8),
        price=round(rate, 8),
        amount=-round(total_cost, 2),
        note=_safe_note(f"{marker}:currency-bought", str(action.get("note", ""))),
    ))
    return {
        "type": "buy_currency", "instrument_id": instrument.id, "code": code,
        "quantity": round(quantity, 8), "total_cost_rub": round(total_cost, 2),
        "rate": round(rate, 8),
    }


def _sell_currency(db: Session, action: dict[str, Any], marker: str) -> dict[str, Any]:
    code = str(action.get("code", "")).strip().upper()
    instrument = _currency(db, code)
    if instrument is None or code == "RUB":
        raise ValueError(f"currency not found: {code}")
    if (instrument.meta or {}).get("source") == "tinvest":
        raise LedgerConflict(f"{code} is broker-managed; synchronize T-Invest instead")
    quantity = _positive(action.get("quantity"), "quantity")
    proceeds = _positive(action.get("total_proceeds_rub"), "total_proceeds_rub")
    traded_on = _day(action.get("traded_on"), "traded_on")
    held, cost, _ = portfolio._moving_average_book(
        instrument.transactions, "fx_buy", "fx_sell"
    )
    if quantity - held > 1e-8:
        raise LedgerConflict(f"insufficient {code}: available {held:.8f}, requested {quantity:.8f}")
    released_cost = cost / held * quantity if held else 0.0
    realized = proceeds - released_cost
    rate = proceeds / quantity
    db.add(Transaction(
        ts=traded_on,
        instrument_id=instrument.id,
        kind="fx_sell",
        quantity=round(quantity, 8),
        price=round(rate, 8),
        amount=round(proceeds, 2),
        note=_safe_note(f"{marker}:currency-sold", str(action.get("note", ""))),
    ))
    _change_cash(
        db, amount=proceeds, on=traded_on,
        marker=f"{marker}:currency-to-rub", note=str(action.get("note", "")),
    )
    return {
        "type": "sell_currency", "instrument_id": instrument.id, "code": code,
        "quantity": round(quantity, 8), "total_proceeds_rub": round(proceeds, 2),
        "rate": round(rate, 8), "released_cost": round(released_cost, 2),
        "realized_pnl": round(realized, 2),
    }


def _manual_security(db: Session, identifier: Any) -> Instrument:
    instrument = _resolve_instrument(db, identifier)
    if not instrument or instrument.kind not in _SECURITY_KINDS:
        raise ValueError(f"security not found: {identifier}")
    imported = any((tx.note or "").startswith("op:") for tx in instrument.transactions)
    if (instrument.meta or {}).get("source") == "tinvest" or imported:
        raise LedgerConflict(
            f"{instrument.name} is managed by T-Invest; record the trade at the broker and synchronize"
        )
    return instrument


def _security_trade(db: Session, action: dict[str, Any], marker: str, *, sell: bool) -> dict[str, Any]:
    instrument = _manual_security(db, action.get("instrument"))
    quantity = _positive(action.get("quantity"), "quantity")
    field = "total_proceeds_rub" if sell else "total_cost_rub"
    total = _positive(action.get(field), field)
    commission = _number(action.get("commission", 0), "commission")
    if commission < 0:
        raise ValueError("commission cannot be negative")
    traded_on = _day(action.get("traded_on"), "traded_on")
    before_qty, before_cost, _ = portfolio._moving_average_book(
        instrument.transactions, "buy", "sell"
    )
    if sell and quantity - before_qty > 1e-8:
        raise LedgerConflict(
            f"insufficient {instrument.ticker or instrument.name}: "
            f"available {before_qty:.8f}, requested {quantity:.8f}"
        )
    if sell:
        released_cost = before_cost / before_qty * quantity if before_qty else 0.0
        realized = total - released_cost
        cash_amount = total
        tx_amount = total
        kind = "sell"
    else:
        released_cost = 0.0
        realized = 0.0
        cash_amount = -total
        tx_amount = -total
        kind = "buy"
    _change_cash(
        db, amount=cash_amount, on=traded_on,
        marker=f"{marker}:{'security-to-rub' if sell else 'rub-to-security'}",
        note=str(action.get("note", "")),
    )
    price = total / quantity
    db.add(Transaction(
        ts=traded_on,
        instrument_id=instrument.id,
        kind=kind,
        quantity=round(quantity, 8),
        price=round(price, 8),
        amount=round(tx_amount, 2),
        commission=round(commission, 2),
        note=_safe_note(
            f"{marker}:security-{'sold' if sell else 'bought'}",
            str(action.get("note", "")),
        ),
    ))
    instrument.last_price = round(price, 8)
    meta = dict(instrument.meta or {})
    meta.setdefault("source", "manual")
    instrument.meta = meta
    result = {
        "type": f"{'sell' if sell else 'buy'}_security",
        "instrument_id": instrument.id,
        "name": instrument.name,
        "quantity": round(quantity, 8),
        field: round(total, 2),
        "price": round(price, 8),
    }
    if sell:
        result.update({
            "released_cost": round(released_cost, 2),
            "realized_pnl": round(realized, 2),
        })
    return result


def _cash_action(db: Session, action: dict[str, Any], marker: str, *, withdrawal: bool) -> dict[str, Any]:
    amount = _positive(action.get("amount_rub"), "amount_rub")
    on = _day(action.get("date"), "date")
    balance = _change_cash(
        db,
        amount=-amount if withdrawal else amount,
        on=on,
        marker=f"{marker}:external-{'withdrawal' if withdrawal else 'topup'}",
        note=str(action.get("note", "")),
    )
    return {
        "type": "cash_withdrawal" if withdrawal else "cash_topup",
        "amount_rub": round(amount, 2),
        "cash": balance,
    }


def _apply_action(db: Session, action: dict[str, Any], marker: str) -> dict[str, Any]:
    action_type = action.get("type")
    if action_type not in _ACTION_TYPES:
        raise ValueError(f"unsupported action type: {action_type}")
    if action_type == "cash_topup":
        return _cash_action(db, action, marker, withdrawal=False)
    if action_type == "cash_withdrawal":
        return _cash_action(db, action, marker, withdrawal=True)
    if action_type == "open_deposit":
        return _open_deposit(db, action, marker)
    if action_type == "settle_deposit":
        return _settle_deposit(db, action, marker)
    if action_type == "buy_currency":
        return _buy_currency(db, action, marker)
    if action_type == "sell_currency":
        return _sell_currency(db, action, marker)
    if action_type == "buy_security":
        return _security_trade(db, action, marker, sell=False)
    return _security_trade(db, action, marker, sell=True)


def _add_snapshot(db: Session, source: str) -> Snapshot:
    result = portfolio.summary(db)
    snapshot = Snapshot(
        ts=datetime.now(timezone.utc).replace(tzinfo=None),
        total_value=result["value"],
        total_invested=result["invested"],
        total_pnl=result["pnl"],
        income_received=result["income_received"],
        by_class=result["by_class"],
        by_instrument={row["name"]: row["value"] for row in result["positions"]},
        source=source,
    )
    db.add(snapshot)
    return snapshot


def apply_actions(
    db: Session,
    *,
    request_id: str,
    actions: list[dict[str, Any]],
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Apply a user-confirmed action batch as one database transaction."""
    request_id = _request_id(request_id)
    if not actions:
        raise ValueError("actions cannot be empty")
    if len(actions) > 50:
        raise ValueError("a batch cannot contain more than 50 actions")
    prefix = f"audit:{request_id}:"
    if db.query(Transaction).filter(Transaction.note.like(prefix + "%")).first():
        return {
            "ok": True,
            "already_applied": True,
            "request_id": request_id,
            "cash": rub_cash_balance(db),
        }
    try:
        results = []
        for index, original in enumerate(actions):
            action = dict(original)
            marker = f"{prefix}{index}:{action.get('type', 'unknown')}"
            results.append(_apply_action(db, action, marker))
            db.flush()
        snapshot = _add_snapshot(db, source="ledger") if create_snapshot else None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "ok": True,
        "already_applied": False,
        "request_id": request_id,
        "actions": results,
        "cash": rub_cash_balance(db),
        "snapshot": snapshot.ts.isoformat() if snapshot else None,
    }
