from datetime import date

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from app.main import app
from app.mcp_server import mcp
from app.models import Instrument, MutationRequest, Transaction
from app.services import calendar as payment_calendar
from app.services.coupon_schedules import set_coupon_schedule
from app.services.ledger import LedgerConflict, apply_actions


def _bond(db, *, quantity=4):
    bond = Instrument(
        kind="bond",
        name="Тестовая облигация",
        ticker="BOND1",
        isin="RU000TEST001",
        figi="TCS00TESTBOND",
        currency="RUB",
        nominal=1_000,
        last_price=980,
        meta={"source": "tinvest", "tinvest_current_quantity": quantity},
    )
    db.add(bond)
    db.flush()
    db.add(Transaction(
        ts=date(2026, 7, 1),
        instrument_id=bond.id,
        kind="buy",
        quantity=quantity,
        price=970,
        amount=-(970 * quantity),
        note="op:test-bond-buy",
    ))
    db.commit()
    return bond


def test_exact_coupon_schedule_drives_calendar_and_redemption(db):
    bond = _bond(db, quantity=4)
    result = set_coupon_schedule(
        db,
        request_id="coupon-test-schedule-001",
        instrument="BOND1",
        payments=[
            {"payment_date": "2026-08-20", "coupon_per_unit_rub": 31.25},
            {"payment_date": "2026-11-20", "coupon_per_unit_rub": 32.50},
        ],
        maturity_date="2026-11-20",
        nominal_per_unit_rub=1_000,
    )

    assert result["coupon_count"] == 2
    assert bond.meta["source"] == "tinvest"
    events = payment_calendar.calendar(db, months_ahead=12, include_past=True)
    assert [(row["date"], row["type"], row["amount"]) for row in events] == [
        ("2026-08-20", "Купон", 125.0),
        ("2026-11-20", "Купон", 130.0),
        ("2026-11-20", "Погашение", 4_000.0),
    ]


def test_coupon_schedule_is_idempotent_and_upsert_replaces_same_date(db):
    bond = _bond(db)
    arguments = {
        "request_id": "coupon-test-idempotent-001",
        "instrument": "RU000TEST001",
        "payments": [
            {"payment_date": "2026-08-20", "coupon_per_unit_rub": 31.25},
        ],
    }
    first = set_coupon_schedule(db, **arguments)
    repeated = set_coupon_schedule(db, **arguments)
    updated = set_coupon_schedule(
        db,
        request_id="coupon-test-upsert-001",
        instrument="BOND1",
        mode="upsert",
        payments=[
            {"payment_date": "2026-08-20", "coupon_per_unit_rub": 40},
            {"payment_date": "2026-11-20", "coupon_per_unit_rub": 42},
        ],
    )

    db.refresh(bond)
    assert first["already_applied"] is False
    assert repeated["already_applied"] is True
    assert updated["coupon_count"] == 2
    assert bond.meta["coupon_schedule"] == [
        {"payment_date": "2026-08-20", "coupon_per_unit_rub": 40.0},
        {"payment_date": "2026-11-20", "coupon_per_unit_rub": 42.0},
    ]
    assert db.query(MutationRequest).count() == 2
    with pytest.raises(LedgerConflict, match="already used"):
        apply_actions(
            db,
            request_id="coupon-test-idempotent-001",
            actions=[{"type": "cash_topup", "amount_rub": 100, "date": "2026-07-15"}],
        )


def test_coupon_schedule_rejects_duplicate_dates_without_changing_bond(db):
    bond = _bond(db)
    with pytest.raises(ValueError, match="duplicate coupon payment date"):
        set_coupon_schedule(
            db,
            request_id="coupon-test-duplicate-001",
            instrument="BOND1",
            payments=[
                {"payment_date": "2026-08-20", "coupon_per_unit_rub": 31},
                {"payment_date": "2026-08-20", "coupon_per_unit_rub": 32},
            ],
        )
    db.refresh(bond)
    assert "coupon_schedule" not in bond.meta
    assert db.query(MutationRequest).count() == 0


def test_coupon_schedule_rest_endpoint(db):
    _bond(db, quantity=2)
    with TestClient(app) as client:
        response = client.put("/api/bonds/coupon-schedule", json={
            "request_id": "coupon-rest-test-001",
            "confirm": True,
            "instrument": "BOND1",
            "payments": [
                {"payment_date": "2026-09-01", "coupon_per_unit_rub": 25},
            ],
        })
        calendar_response = client.get("/api/calendar?months=12&past=true")

    assert response.status_code == 200
    assert response.json()["coupon_count"] == 1
    coupon = next(row for row in calendar_response.json() if row["type"] == "Купон")
    assert coupon["amount"] == 50


def test_mcp_can_set_exact_coupon_schedule(db):
    _bond(db, quantity=3)

    async def scenario():
        async with create_connected_server_and_client_session(mcp) as session:
            arguments = {
                "request_id": "coupon-mcp-test-001",
                "instrument": "BOND1",
                "payments": [
                    {"payment_date": "2026-09-15", "coupon_per_unit_rub": 20},
                    {"payment_date": "2026-12-15", "coupon_per_unit_rub": 22},
                ],
                "confirm": False,
            }
            rejected = await session.call_tool("set_bond_coupon_schedule", arguments)
            assert rejected.isError is True

            arguments["confirm"] = True
            applied = await session.call_tool("set_bond_coupon_schedule", arguments)
            repeated = await session.call_tool("set_bond_coupon_schedule", arguments)
            calendar_result = await session.call_tool(
                "get_payment_calendar", {"months_ahead": 12, "include_past": True},
            )

            assert applied.isError is False
            assert applied.structuredContent["coupon_count"] == 2
            assert repeated.structuredContent["already_applied"] is True
            coupons = [
                row for row in calendar_result.structuredContent["items"]
                if row["type"] == "Купон"
            ]
            assert [row["amount"] for row in coupons] == [60, 66]

    anyio.run(scenario)
