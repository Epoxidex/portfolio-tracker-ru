from fastapi.testclient import TestClient

from app.main import app
from app.models import Instrument, Transaction


def test_react_preview_reports_when_build_is_missing(monkeypatch, tmp_path):
    from app import main as main_module

    monkeypatch.setattr(main_module, "REACT_DIST", tmp_path)
    with TestClient(main_module.app) as client:
        response = client.get("/react-preview/")
    assert response.status_code == 503
    assert "npm.cmd run build" in response.text


def test_status_never_exposes_token_or_database_path():
    with TestClient(app) as client:
        response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["tinvest"]["configured"] is False
    serialized = str(body).lower()
    assert "token" not in serialized
    assert "test.db" not in serialized


def test_deposit_is_created_atomically(db):
    payload = {
        "name": "Тестовый вклад",
        "principal": 200_000,
        "open_date": "2026-07-01",
        "close_date": "2027-01-01",
        "annual_rate_pct": 18,
        "interest_mode": "simple",
    }
    with TestClient(app) as client:
        response = client.post("/api/deposits", json=payload)
    assert response.status_code == 200
    assert response.json()["estimated_interest"] > 0
    db.expire_all()
    assert db.query(Instrument).count() == 2  # RUB cash ledger + deposit
    transactions = db.query(Transaction).order_by(Transaction.id).all()
    assert [(tx.kind, tx.amount) for tx in transactions] == [
        ("topup", 200_000),
        ("withdrawal", -200_000),
        ("buy", -200_000),
    ]


def test_invalid_deposit_does_not_leave_partial_rows(db):
    payload = {
        "name": "Некорректный вклад",
        "principal": 100_000,
        "open_date": "2026-07-01",
        "close_date": "2026-06-01",
        "annual_rate_pct": 18,
        "interest_mode": "simple",
    }
    with TestClient(app) as client:
        response = client.post("/api/deposits", json=payload)
    assert response.status_code == 422
    assert db.query(Instrument).count() == 0


def test_manual_currency_holding_is_created_with_cost_basis(db):
    payload = {
        "code": "usd",
        "quantity": 1_000,
        "invested_rub": 90_000,
        "acquired_on": "2026-01-15",
    }
    with TestClient(app) as client:
        response = client.post("/api/currencies", json=payload)
    assert response.status_code == 200
    assert response.json()["code"] == "USD"
    db.expire_all()
    instrument = db.query(Instrument).one()
    assert instrument.currency == "USD"
    assert instrument.last_price == 90
    tx = db.query(Transaction).one()
    assert tx.kind == "fx_buy"
    assert tx.quantity == 1_000
    assert tx.amount == -90_000


def test_manual_currency_duplicate_requires_explicit_append(db):
    payload = {
        "code": "CNY",
        "quantity": 2_000,
        "invested_rub": 24_000,
        "acquired_on": "2026-02-01",
    }
    with TestClient(app) as client:
        assert client.post("/api/currencies", json=payload).status_code == 200
        duplicate = client.post("/api/currencies", json=payload)
        payload["append"] = True
        appended = client.post("/api/currencies", json=payload)
    assert duplicate.status_code == 409
    assert appended.status_code == 200
    db.expire_all()
    assert db.query(Instrument).count() == 1
    assert db.query(Transaction).count() == 2
