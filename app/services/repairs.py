"""Auditable, idempotent repairs for derived portfolio history."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date

from ..models import Instrument, Snapshot
from .portfolio import CLASS_RU, _moving_average_book
from .snapshots import _portfolio_day


SECURITY_KINDS = {"bond", "share", "etf"}


def _recorded_security_costs(db, snapshot: Snapshot) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Return class costs supported by the operation ledger at snapshot time."""
    snapshot_names = set((snapshot.by_instrument or {}).keys())
    instruments = {
        instrument.name: instrument
        for instrument in db.query(Instrument).all()
        if instrument.kind in SECURITY_KINDS and instrument.name in snapshot_names
    }
    costs: dict[str, float] = defaultdict(float)
    unsupported: dict[str, list[str]] = defaultdict(list)
    day = _portfolio_day(snapshot.ts)

    for name, instrument in instruments.items():
        transactions = [tx for tx in instrument.transactions if tx.ts <= day]
        quantity, cost, _ = _moving_average_book(transactions, "buy", "sell")
        class_name = CLASS_RU[instrument.kind]
        if quantity <= 0 or cost <= 0:
            unsupported[class_name].append(name)
            continue
        costs[class_name] += cost

    return dict(costs), dict(unsupported)


def repair_snapshot_cost_basis(db, from_date: date, *, apply: bool = False) -> dict:
    """Repair stored security cost basis without recomputing historical prices.

    The snapshot already contains the market value captured at that moment. We
    replace only security-class ``invested`` values that can be fully supported
    by recorded buy/sell operations, and adjust P&L by the same opposite delta.
    Classes with incomplete operation history are reported and left untouched.
    """
    rows = db.query(Snapshot).order_by(Snapshot.ts).all()
    changes = []
    skipped = []

    for snapshot in rows:
        day = _portfolio_day(snapshot.ts)
        if day < from_date:
            continue
        class_costs, unsupported = _recorded_security_costs(db, snapshot)
        by_class = deepcopy(snapshot.by_class or {})
        class_changes = []
        invested_delta = 0.0
        pnl_delta = 0.0

        for class_name, new_cost in class_costs.items():
            if unsupported.get(class_name) or class_name not in by_class:
                continue
            entry = dict(by_class[class_name])
            old_cost = float(entry.get("invested", 0) or 0)
            new_cost = round(new_cost, 2)
            if abs(old_cost - new_cost) < 0.005:
                continue
            correction = old_cost - new_cost
            old_pnl = float(entry.get("pnl", 0) or 0)
            new_pnl = round(old_pnl + correction, 2)
            entry["invested"] = new_cost
            entry["pnl"] = new_pnl
            entry["pnl_pct"] = round(new_pnl / new_cost, 4) if new_cost else 0
            by_class[class_name] = entry
            invested_delta += new_cost - old_cost
            pnl_delta += correction
            class_changes.append({
                "class": class_name,
                "invested_before": round(old_cost, 2),
                "invested_after": new_cost,
            })

        if unsupported:
            skipped.append({"day": day.isoformat(), "classes": unsupported})
        if not class_changes:
            continue

        invested_before = round(float(snapshot.total_invested or 0), 2)
        pnl_before = round(float(snapshot.total_pnl or 0), 2)
        invested_after = round(invested_before + invested_delta, 2)
        pnl_after = round(pnl_before + pnl_delta, 2)
        changes.append({
            "snapshot_id": snapshot.id,
            "day": day.isoformat(),
            "invested_before": invested_before,
            "invested_after": invested_after,
            "pnl_before": pnl_before,
            "pnl_after": pnl_after,
            "classes": class_changes,
        })

        if apply:
            snapshot.total_invested = invested_after
            snapshot.total_pnl = pnl_after
            snapshot.by_class = by_class

    if apply:
        db.commit()

    return {
        "from_date": from_date.isoformat(),
        "applied": apply,
        "changed": len(changes),
        "snapshots": changes,
        "skipped": skipped,
    }
