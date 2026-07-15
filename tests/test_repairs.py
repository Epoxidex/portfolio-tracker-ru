from datetime import date, datetime

from app.models import Instrument, Snapshot, Transaction
from app.services.repairs import repair_snapshot_cost_basis


def _class_row(invested, value, pnl):
    return {
        "invested": invested,
        "value": value,
        "pnl": pnl,
        "pnl_pct": round(pnl / invested, 4),
    }


def test_snapshot_cost_basis_repair_is_previewable_idempotent_and_scoped(db):
    bond = Instrument(kind="bond", name="Bond", currency="RUB")
    fund = Instrument(kind="etf", name="Fund", currency="RUB")
    db.add_all([bond, fund])
    db.flush()
    db.add_all([
        Transaction(
            ts=date(2026, 7, 1), instrument_id=bond.id,
            kind="buy", quantity=1, amount=-1_000,
        ),
        Transaction(
            ts=date(2026, 7, 2), instrument_id=fund.id,
            kind="buy", quantity=2, amount=-500,
        ),
    ])
    untouched = Snapshot(
        ts=datetime(2026, 7, 13, 12), total_value=1_550,
        total_invested=1_500, total_pnl=50, income_received=0,
        by_class={
            "Облигации": _class_row(1_000, 1_020, 20),
            "Фонды": _class_row(500, 530, 30),
        },
        by_instrument={"Bond": 1_020, "Fund": 530}, source="test",
    )
    damaged = Snapshot(
        ts=datetime(2026, 7, 14, 12), total_value=1_570,
        total_invested=1_600, total_pnl=-30, income_received=0,
        by_class={
            "Облигации": _class_row(1_099, 1_030, -69),
            "Фонды": _class_row(501, 540, 39),
        },
        by_instrument={"Bond": 1_030, "Fund": 540}, source="test",
    )
    db.add_all([untouched, damaged])
    db.commit()

    preview = repair_snapshot_cost_basis(db, date(2026, 7, 14), apply=False)
    db.refresh(damaged)

    assert preview["changed"] == 1
    assert preview["snapshots"][0]["invested_before"] == 1_600
    assert preview["snapshots"][0]["invested_after"] == 1_500
    assert damaged.total_invested == 1_600

    applied = repair_snapshot_cost_basis(db, date(2026, 7, 14), apply=True)
    db.refresh(untouched)
    db.refresh(damaged)

    assert applied["changed"] == 1
    assert untouched.total_invested == 1_500
    assert damaged.total_invested == 1_500
    assert damaged.total_pnl == 70
    assert damaged.by_class["Облигации"]["invested"] == 1_000
    assert damaged.by_class["Облигации"]["pnl"] == 30
    assert damaged.by_class["Фонды"]["invested"] == 500
    assert damaged.by_class["Фонды"]["pnl"] == 40

    repeated = repair_snapshot_cost_basis(db, date(2026, 7, 14), apply=True)
    assert repeated["changed"] == 0

