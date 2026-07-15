from datetime import date, datetime

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import Instrument, PriceHistory, Snapshot, Transaction
from app.services.tracking import apply_tracking_cleanup, preview_tracking_cleanup


def test_tracking_cleanup_removes_only_old_broker_history(db):
    stale = Instrument(
        kind="share", name="Closed before tracking", ticker="OLD", last_price=50,
        meta={"source": "tinvest"},
    )
    active = Instrument(
        kind="share", name="Active in window", ticker="NEW", last_price=100,
        meta={"source": "tinvest"},
    )
    manual = Instrument(
        kind="currency", name="Manual USD", currency="USD", last_price=90,
        meta={"manual": True},
    )
    db.add_all([stale, active, manual])
    db.flush()
    db.add_all([
        Transaction(
            ts=date(2025, 2, 1), instrument_id=stale.id, kind="buy",
            quantity=10, amount=-500, note="op:old",
        ),
        Transaction(
            ts=date(2025, 3, 1), instrument_id=active.id, kind="buy",
            quantity=1, amount=-80, note="op:active-old",
        ),
        Transaction(
            ts=date(2026, 4, 10), instrument_id=active.id, kind="buy",
            quantity=1, amount=-100, note="op:active-new",
        ),
        Transaction(
            ts=date(2025, 1, 10), instrument_id=manual.id, kind="fx_buy",
            quantity=100, amount=-8_000, note="manual opening balance",
        ),
        Transaction(
            ts=date(2025, 5, 1), instrument_id=None, kind="sell",
            quantity=10, amount=600, note="op:unresolved-sale",
        ),
    ])
    db.add(PriceHistory(instrument_id=stale.id, ts=datetime(2026, 1, 1), price=50))
    db.add_all([
        Snapshot(
            ts=datetime(2026, 3, 31, 20), by_instrument={"Manual USD": 9_000},
        ),
        Snapshot(
            ts=datetime(2026, 7, 1, 12),
            by_instrument={"Closed before tracking": 500, "Manual USD": 9_000},
        ),
        Snapshot(
            ts=datetime(2026, 7, 2, 12), by_instrument={"Manual USD": 9_000},
        ),
    ])
    db.commit()

    start = date(2026, 4, 1)
    preview = preview_tracking_cleanup(db, start)
    assert preview["imported_transactions"] == 3
    assert preview["instruments"] == 1
    assert preview["snapshots"] == 2

    result = apply_tracking_cleanup(db, start)
    assert result["ok"] is True
    assert db.query(Instrument).filter(Instrument.ticker == "OLD").count() == 0
    assert db.query(Instrument).filter(Instrument.ticker == "NEW").count() == 1
    assert db.query(Instrument).filter(Instrument.currency == "USD").count() == 1
    assert db.query(Transaction).filter(Transaction.note == "op:active-old").count() == 0
    assert db.query(Transaction).filter(Transaction.note == "op:active-new").count() == 1
    assert db.query(Transaction).filter(Transaction.note == "manual opening balance").count() == 1
    assert db.query(PriceHistory).count() == 0
    assert db.query(Snapshot).count() == 1


def test_tracking_start_uses_writable_runtime_settings(db, tmp_path, monkeypatch):
    settings = tmp_path / ".portfolio-settings.env"
    monkeypatch.setattr(config, "RUNTIME_SETTINGS_FILE", settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/settings/tracking-start",
            json={"start_date": "2026-04-01", "confirm": True},
        )

    assert response.status_code == 200
    assert settings.read_text(encoding="utf-8") == (
        "PORTFOLIO_TRACKING_START_DATE=2026-04-01\n"
    )
