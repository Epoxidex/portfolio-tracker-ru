from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.models import Instrument, Snapshot, Transaction
from app.services.portfolio import deposit_value_from_meta, _moving_average_book, positions
from app.services.snapshots import compute_leaders, compute_returns, compute_streak
from app.services.tinvest import _sync_portfolio_state


def _tx(day, kind, quantity, amount, row_id):
    return SimpleNamespace(
        id=row_id,
        ts=date.fromisoformat(day),
        kind=kind,
        quantity=quantity,
        amount=amount,
        price=0,
        commission=0,
    )


def test_simple_deposit_uses_daily_accrual():
    meta = {
        "principal": 100_000,
        "open_date": "2026-01-01",
        "close_date": "2027-01-01",
        "eff_rate": 0.10,
        "interest_mode": "simple",
    }
    assert deposit_value_from_meta(meta, date(2027, 1, 1)) == pytest.approx(110_000)


def test_monthly_capitalization_matches_selected_model():
    meta = {
        "principal": 100_000,
        "open_date": "2026-01-01",
        "close_date": "2027-01-01",
        "eff_rate": 0.12,
        "interest_mode": "monthly_capitalization",
    }
    expected = 100_000 * (1 + 0.12 / 12) ** 12
    assert deposit_value_from_meta(meta, date(2027, 1, 1)) == pytest.approx(expected)


def test_legacy_deposit_keeps_effective_annual_behavior():
    meta = {
        "principal": 100_000,
        "open_date": "2026-01-01",
        "close_date": "2027-01-01",
        "eff_rate": 0.10,
    }
    assert deposit_value_from_meta(meta, date(2027, 1, 1)) == pytest.approx(110_000)


def test_matured_deposit_does_not_disappear_before_reconciliation(db):
    instrument = Instrument(
        kind="deposit",
        name="Matured deposit",
        currency="RUB",
        meta={
            "principal": 100_000,
            "open_date": "2025-01-01",
            "close_date": "2026-01-01",
            "eff_rate": 0.10,
            "interest_mode": "simple",
        },
    )
    db.add(instrument)
    db.flush()
    db.add(Transaction(
        ts=date(2025, 1, 1), instrument_id=instrument.id,
        kind="buy", quantity=1, amount=-100_000,
    ))
    db.commit()

    result = positions(db, on=date(2026, 7, 1))
    assert len(result) == 1
    assert result[0]["value"] == pytest.approx(110_000)


def test_broker_current_quantity_hides_stale_imported_position(db):
    current = Instrument(
        kind="share", name="Current", ticker="CUR", figi="FIGI-CUR",
        last_price=100, meta={},
    )
    stale = Instrument(
        kind="share", name="Stale", ticker="OLD", figi="FIGI-OLD",
        last_price=80, meta={"source": "tinvest"},
    )
    db.add_all([current, stale])
    db.flush()
    db.add_all([
        Transaction(
            ts=date(2026, 4, 2), instrument_id=current.id, kind="buy",
            quantity=2, amount=-220, note="op:current-buy",
        ),
        Transaction(
            ts=date(2025, 1, 2), instrument_id=stale.id, kind="buy",
            quantity=5, amount=-400, note="op:old-buy",
        ),
    ])
    db.commit()

    broker_position = SimpleNamespace(
        quantity=2.0,
        average_position_price=105.0,
        expected_yield=-10.0,
    )
    _sync_portfolio_state(db, [current, stale], {"FIGI-CUR": broker_position})

    result = positions(db)
    assert [row["ticker"] for row in result] == ["CUR"]
    assert result[0]["qty"] == 2
    assert result[0]["pnl"] == -10


def test_moving_average_cost_handles_sell_then_repurchase():
    txs = [
        _tx("2026-01-01", "buy", 10, -1_000, 1),
        _tx("2026-02-01", "sell", 5, 600, 2),
        _tx("2026-03-01", "buy", 5, -800, 3),
    ]
    quantity, remaining_cost, realized = _moving_average_book(txs, "buy", "sell")
    assert quantity == 10
    assert remaining_cost == pytest.approx(1_300)
    assert realized == pytest.approx(100)


def _snapshot(day, pnl, *, value=None, invested=1_000, by_instrument=None):
    return Snapshot(
        ts=datetime.fromisoformat(day + "T12:00:00"),
        total_value=value if value is not None else 1_000 + pnl,
        total_invested=invested,
        total_pnl=pnl,
        income_received=0,
        by_class={},
        by_instrument=by_instrument or {},
        source="test",
    )


def test_returns_use_last_snapshot_of_previous_calendar_period(db):
    db.add_all([
        _snapshot("2026-06-10", 30),
        _snapshot("2026-06-30", 40),
        _snapshot("2026-07-06", 60),
        _snapshot("2026-07-12", 70),
        _snapshot("2026-07-13", 100),
        _snapshot("2026-07-14", 150),
    ])
    db.commit()

    result = compute_returns(db, "daily")
    assert result["today"]["change"] == 50
    assert result["week"]["change"] == 80
    assert result["month"]["change"] == 110


def test_leaders_are_sorted_by_absolute_portfolio_impact(db):
    db.add_all([
        _snapshot("2026-07-12", 0, value=1_000, by_instrument={"A": 400, "B": 600}),
        _snapshot("2026-07-14", 0, value=1_000, by_instrument={"A": 450, "B": 570}),
    ])
    db.commit()

    result = compute_leaders(db, "week")
    assert result["complete"] is True
    assert [item["name"] for item in result["items"]] == ["A", "B"]
    assert [item["change"] for item in result["items"]] == [50, -30]


def test_returns_match_leaders_when_broker_cost_basis_changes(db):
    asset = Instrument(kind="share", name="Asset", ticker="AST", currency="RUB")
    cash = Instrument(kind="currency", name="Ruble cash", currency="RUB")
    db.add_all([asset, cash])
    db.add_all([
        _snapshot(
            "2026-07-13", 0, value=1_100, invested=1_000,
            by_instrument={"Asset": 1_000, "Ruble cash": 100},
        ),
        _snapshot(
            "2026-07-14", -483.03, value=1_316.61, invested=1_649.64,
            by_instrument={"Asset": 1_166.61, "Ruble cash": 150},
        ),
    ])
    db.commit()

    returns = compute_returns(db, "daily")
    leaders = compute_leaders(db, "day")

    assert returns["today"]["change"] == 166.61
    assert returns["today"]["pct"] == pytest.approx(0.16661)
    assert sum(item["change"] for item in leaders["items"]) == 166.61
    assert compute_streak(db) == 1
