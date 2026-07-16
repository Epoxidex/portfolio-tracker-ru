from app.services.operations import _KIND_MAP


def test_tinvest_cash_inputs_and_outputs_are_external_capital_operations():
    assert _KIND_MAP["OPERATION_TYPE_INPUT"] == "topup"
    assert _KIND_MAP["OPERATION_TYPE_OUTPUT"] == "withdrawal"
    assert _KIND_MAP["OPERATION_TYPE_INPUT_SWIFT"] == "topup"
    assert _KIND_MAP["OPERATION_TYPE_OUTPUT_SWIFT"] == "withdrawal"


def test_background_tinvest_job_imports_operations_before_prices(monkeypatch):
    from app import main

    calls = []

    class FakeDb:
        def close(self):
            calls.append("close")

    monkeypatch.setattr(main.config, "TINVEST_TOKEN", "configured")
    monkeypatch.setattr(main, "SessionLocal", FakeDb)
    monkeypatch.setattr(
        main,
        "sync_operations",
        lambda db, days_back: calls.append(("operations", days_back)) or {"ok": True},
    )
    monkeypatch.setattr(main, "fetch_prices", lambda db: calls.append("prices") or {"ok": True})

    main._job_fetch()

    assert calls == [("operations", 30), "prices", "close"]
