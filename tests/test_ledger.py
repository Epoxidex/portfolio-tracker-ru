from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Instrument, Snapshot, Transaction
from app.services.ledger import (
    LedgerConflict, apply_actions, pending_reconciliations, rub_cash_balance,
)
from app.services.onboarding import create_deposit
from app.services.portfolio import positions, realized_results, summary
from app.services.snapshots import history
from app.services.tinvest import _sync_rub_balance


def test_topup_and_deposit_open_as_one_atomic_batch(db):
    result = apply_actions(
        db,
        request_id="test-deposit-open-001",
        actions=[
            {"type": "cash_topup", "amount_rub": 50_000, "date": "2026-07-15"},
            {
                "type": "open_deposit",
                "name": "Вклад на год",
                "principal": 50_000,
                "open_date": "2026-07-15",
                "close_date": "2027-07-15",
                "annual_rate_pct": 12,
                "interest_mode": "monthly_capitalization",
            },
        ],
    )

    assert result["ok"] is True
    assert result["cash"]["total"] == 0
    assert db.query(Instrument).filter(Instrument.kind == "deposit").count() == 1
    deposit = db.query(Instrument).filter(Instrument.kind == "deposit").one()
    assert deposit.meta["interest_mode"] == "monthly_capitalization"
    assert db.query(Snapshot).count() == 1
    assert summary(db, on=date(2026, 7, 15))["value"] == 50_000


def test_action_batch_is_idempotent(db):
    arguments = {
        "request_id": "test-idempotency-001",
        "actions": [{"type": "cash_topup", "amount_rub": 10_000, "date": "2026-07-15"}],
    }
    first = apply_actions(db, **arguments)
    second = apply_actions(db, **arguments)

    assert first["already_applied"] is False
    assert second["already_applied"] is True
    assert rub_cash_balance(db)["total"] == 10_000
    assert db.query(Transaction).filter(Transaction.kind == "topup").count() == 1
    assert db.query(Snapshot).count() == 1


def test_invalid_later_action_rolls_back_entire_batch(db):
    with pytest.raises(LedgerConflict, match="insufficient manual RUB"):
        apply_actions(
            db,
            request_id="test-atomic-rollback-001",
            actions=[
                {"type": "cash_topup", "amount_rub": 10_000, "date": "2026-07-15"},
                {
                    "type": "open_deposit",
                    "name": "Слишком большой вклад",
                    "principal": 20_000,
                    "open_date": "2026-07-15",
                    "close_date": "2027-07-15",
                    "annual_rate_pct": 10,
                },
            ],
        )

    assert db.query(Instrument).count() == 0
    assert db.query(Transaction).count() == 0
    assert db.query(Snapshot).count() == 0


def test_currency_sale_moves_value_to_rub_and_keeps_realized_result(db):
    result = apply_actions(
        db,
        request_id="test-currency-cycle-001",
        actions=[
            {"type": "cash_topup", "amount_rub": 10_000, "date": "2026-07-01"},
            {
                "type": "buy_currency", "code": "USD", "quantity": 100,
                "total_cost_rub": 9_000, "traded_on": "2026-07-02", "current_rate": 95,
            },
            {
                "type": "sell_currency", "code": "USD", "quantity": 100,
                "total_proceeds_rub": 10_000, "traded_on": "2026-07-10",
            },
        ],
    )

    sale = result["actions"][2]
    assert sale["realized_pnl"] == 1_000
    assert result["cash"]["total"] == 11_000
    assert not any(row["currency"] == "USD" for row in positions(db))
    lifetime = realized_results(db)
    assert lifetime["realized_pnl"] == 1_000
    assert summary(db)["value"] == 11_000


def test_matured_deposit_settlement_closes_asset_and_credits_rub(db):
    result = apply_actions(
        db,
        request_id="test-deposit-settle-001",
        actions=[
            {"type": "cash_topup", "amount_rub": 100_000, "date": "2025-01-01"},
            {
                "type": "open_deposit", "name": "Завершённый вклад",
                "principal": 100_000, "open_date": "2025-01-01",
                "close_date": "2026-01-01", "annual_rate_pct": 10,
                "interest_mode": "simple",
            },
            {
                "type": "settle_deposit", "instrument": "Завершённый вклад",
                "settled_on": "2026-01-01",
            },
        ],
    )

    settlement = result["actions"][2]
    assert settlement["payout"] == 110_000
    assert settlement["profit"] == 10_000
    assert settlement["used_estimate"] is True
    assert result["cash"]["total"] == 110_000
    assert not any(row["kind"] == "deposit" for row in positions(db))
    deposit = db.query(Instrument).filter(Instrument.kind == "deposit").one()
    assert deposit.meta["status"] == "closed"
    assert realized_results(db)["income"] == 10_000
    assert pending_reconciliations(db, on=date(2026, 7, 1))["total"] == 0


def test_reinvested_deposit_profit_does_not_increase_external_capital(db):
    first = create_deposit(
        db,
        name="Первоначальный вклад",
        principal=200_000,
        open_date=date(2025, 7, 16),
        close_date=date(2026, 7, 16),
        annual_rate_pct=5,
        interest_mode="simple",
    )
    assert first["external_topup"] == 200_000

    apply_actions(
        db,
        request_id="test-reinvest-settle-001",
        actions=[{
            "type": "settle_deposit",
            "instrument": "Первоначальный вклад",
            "settled_on": "2026-07-16",
            "actual_payout_rub": 210_000,
        }],
        create_snapshot=False,
    )
    second = create_deposit(
        db,
        name="Новый вклад 50",
        principal=50_000,
        open_date=date(2026, 7, 16),
        close_date=date(2027, 7, 16),
        annual_rate_pct=5,
    )
    third = create_deposit(
        db,
        name="Новый вклад 160",
        principal=160_000,
        open_date=date(2026, 7, 16),
        close_date=date(2027, 7, 16),
        annual_rate_pct=5,
    )

    result = summary(db, on=date(2026, 7, 16))
    assert second["external_topup"] == 0
    assert third["external_topup"] == 0
    assert result["invested"] == 200_000
    assert result["cost_basis"] == 210_000
    assert result["value"] == 210_000
    assert result["pnl"] == 10_000
    assert result["income_received"] == 10_000
    assert result["capital_inferred"] == 0
    assert history(db)[-1]["invested"] == 200_000
    assert rub_cash_balance(db)["manual"] == 0


def test_external_withdrawal_keeps_realized_profit_in_headline(db):
    create_deposit(
        db,
        name="Вклад для вывода",
        principal=200_000,
        open_date=date(2025, 7, 16),
        close_date=date(2026, 7, 16),
        annual_rate_pct=5,
    )
    apply_actions(
        db,
        request_id="test-withdraw-profit-001",
        actions=[
            {
                "type": "settle_deposit", "instrument": "Вклад для вывода",
                "settled_on": "2026-07-16", "actual_payout_rub": 210_000,
            },
            {"type": "cash_withdrawal", "amount_rub": 210_000, "date": "2026-07-16"},
        ],
        create_snapshot=False,
    )

    result = summary(db, on=date(2026, 7, 16))
    assert result["invested"] == 200_000
    assert result["external_withdrawals"] == 210_000
    assert result["value"] == 0
    assert result["pnl"] == 10_000


def test_legacy_deposit_reinvestment_uses_settlement_cash(db):
    legacy = Instrument(
        kind="deposit",
        name="Старый формат",
        currency="RUB",
        meta={
            "principal": 200_000,
            "open_date": "2025-07-16",
            "close_date": "2026-07-16",
            "eff_rate": 0.05,
            "interest_mode": "simple",
        },
    )
    db.add(legacy)
    db.flush()
    db.add(Transaction(
        ts=date(2025, 7, 16), instrument_id=legacy.id,
        kind="buy", quantity=1, amount=-200_000, note="deposit opened",
    ))
    db.commit()
    apply_actions(
        db,
        request_id="test-legacy-settle-001",
        actions=[{
            "type": "settle_deposit", "instrument": "Старый формат",
            "settled_on": "2026-07-16", "actual_payout_rub": 210_000,
        }],
        create_snapshot=False,
    )
    new = create_deposit(
        db,
        name="После старого",
        principal=210_000,
        open_date=date(2026, 7, 16),
        close_date=date(2027, 7, 16),
        annual_rate_pct=5,
    )

    result = summary(db, on=date(2026, 7, 16))
    assert new["external_topup"] == 0
    assert result["invested"] == 200_000
    assert result["value"] == 210_000
    assert result["pnl"] == 10_000


def test_matured_deposit_is_reported_before_settlement(db):
    apply_actions(
        db,
        request_id="test-pending-deposit-001",
        actions=[
            {"type": "cash_topup", "amount_rub": 100_000, "date": "2025-01-01"},
            {
                "type": "open_deposit", "name": "Ожидает закрытия",
                "principal": 100_000, "open_date": "2025-01-01",
                "close_date": "2026-01-01", "annual_rate_pct": 10,
            },
        ],
    )

    pending = pending_reconciliations(db, on=date(2026, 7, 1))
    assert pending["total"] == 1
    assert pending["items"][0]["recommended_tool"] == "settle_deposit_to_rub"
    assert pending["items"][0]["estimated_payout_rub"] == 110_000


def test_early_deposit_settlement_requires_actual_payout(db):
    apply_actions(
        db,
        request_id="test-early-open-001",
        actions=[
            {"type": "cash_topup", "amount_rub": 100_000, "date": "2026-01-01"},
            {
                "type": "open_deposit", "name": "Досрочный",
                "principal": 100_000, "open_date": "2026-01-01",
                "close_date": "2027-01-01", "annual_rate_pct": 10,
            },
        ],
    )

    with pytest.raises(ValueError, match="actual_payout_rub"):
        apply_actions(
            db,
            request_id="test-early-close-001",
            actions=[{
                "type": "settle_deposit", "instrument": "Досрочный",
                "settled_on": "2026-06-01",
            }],
        )

    deposit = db.query(Instrument).filter(Instrument.kind == "deposit").one()
    assert deposit.meta["status"] == "active"


def test_manual_trade_is_rejected_for_tinvest_security(db):
    instrument = Instrument(
        kind="bond", name="Broker bond", ticker="BOND", currency="RUB",
        meta={"source": "tinvest"},
    )
    db.add(instrument)
    db.commit()

    with pytest.raises(LedgerConflict, match="managed by T-Invest"):
        apply_actions(
            db,
            request_id="test-broker-reject-001",
            actions=[{
                "type": "buy_security", "instrument": "BOND", "quantity": 1,
                "total_cost_rub": 1_000, "traded_on": "2026-07-15",
            }],
        )


def test_rub_position_combines_broker_and_manual_cash(db):
    rub = Instrument(
        kind="currency", name="Рубли", ticker="RUB", currency="RUB",
        figi="RUB000UTSTOM", last_price=1, meta={"broker_balance": 25_000},
    )
    db.add(rub)
    db.flush()
    db.add(Transaction(
        ts=date(2026, 7, 15), instrument_id=rub.id, kind="topup",
        quantity=5_000, price=1, amount=5_000,
    ))
    db.commit()

    cash = rub_cash_balance(db)
    assert cash == {"broker": 25_000, "manual": 5_000, "total": 30_000}
    rub_position = next(row for row in positions(db) if row["currency"] == "RUB")
    assert rub_position["value"] == 30_000


def test_tinvest_rub_sync_preserves_manual_ledger_without_duplicate(db):
    apply_actions(
        db,
        request_id="test-manual-rub-before-sync-001",
        actions=[{"type": "cash_topup", "amount_rub": 5_000, "date": "2026-07-15"}],
    )
    rub_position = SimpleNamespace(
        figi="RUB000UTSTOM",
        quantity=SimpleNamespace(units=25_000, nano=0),
    )

    _sync_rub_balance(None, [rub_position], db, "unused")

    assert db.query(Instrument).filter(Instrument.currency == "RUB").count() == 1
    assert rub_cash_balance(db) == {"broker": 25_000, "manual": 5_000, "total": 30_000}


def test_ledger_api_requires_confirmation_and_supports_currency_sale(db):
    with TestClient(app) as client:
        missing_confirmation = client.post("/api/ledger/cash/topup", json={
            "request_id": "api-topup-001",
            "amount_rub": 20_000,
            "date": "2026-07-15",
        })
        assert missing_confirmation.status_code == 422

        batch = client.post("/api/ledger/actions", json={
            "request_id": "api-currency-001",
            "confirm": True,
            "actions": [
                {"type": "cash_topup", "amount_rub": 20_000, "date": "2026-07-15"},
                {
                    "type": "buy_currency", "code": "USD", "quantity": 100,
                    "total_cost_rub": 9_000, "traded_on": "2026-07-15",
                },
                {
                    "type": "sell_currency", "code": "USD", "quantity": 50,
                    "total_proceeds_rub": 5_000, "traded_on": "2026-07-15",
                },
            ],
        })
        cash = client.get("/api/ledger/cash")
        realized = client.get("/api/ledger/realized")

    assert batch.status_code == 200
    assert batch.json()["actions"][2]["realized_pnl"] == 500
    assert cash.json()["total"] == 16_000
    assert realized.json()["realized_pnl"] == 500
