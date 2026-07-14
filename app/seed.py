"""Synthetic demo data for screenshots and local experimentation.

The demo is never loaded automatically. It contains no real account, security,
transaction or portfolio data. Loading it replaces every row in the selected DB.
"""
from datetime import date, datetime, timedelta

from .db import SessionLocal, init_db
from .models import Instrument, PriceHistory, Snapshot, Transaction
from .services.snapshots import take_snapshot


def seed(db):
    today = date.today()

    db.query(PriceHistory).delete()
    db.query(Snapshot).delete()
    db.query(Transaction).delete()
    db.query(Instrument).delete()
    db.commit()

    fund = Instrument(
        kind="etf",
        name="Демо-фонд",
        ticker="DEMO",
        currency="RUB",
        last_price=112.40,
        meta={},
    )
    db.add(fund)
    db.flush()
    db.add(Transaction(
        ts=today - timedelta(days=90),
        instrument_id=fund.id,
        kind="buy",
        quantity=100,
        price=100,
        amount=-10_000,
        note="synthetic demo",
    ))

    deposit = Instrument(
        kind="deposit",
        name="Демо-вклад",
        currency="RUB",
        meta={
            "principal": 50_000,
            "open_date": (today - timedelta(days=45)).isoformat(),
            "close_date": (today + timedelta(days=135)).isoformat(),
            "eff_rate": 0.12,
            "interest_mode": "simple",
        },
    )
    db.add(deposit)
    db.flush()
    db.add(Transaction(
        ts=today - timedelta(days=45),
        instrument_id=deposit.id,
        kind="buy",
        quantity=1,
        amount=-50_000,
        note="synthetic demo",
    ))
    db.commit()

    for days_ago, value, invested, pnl in (
        (35, 60_250, 60_000, 250),
        (14, 61_050, 60_000, 1_050),
        (7, 61_320, 60_000, 1_320),
        (1, 61_500, 60_000, 1_500),
    ):
        day = today - timedelta(days=days_ago)
        db.add(Snapshot(
            ts=datetime.combine(day, datetime.min.time()).replace(hour=12),
            total_value=value,
            total_invested=invested,
            total_pnl=pnl,
            income_received=0,
            by_class={},
            by_instrument={"Демо-фонд": value - 50_000, "Демо-вклад": 50_000},
            source="synthetic-demo",
        ))
    db.commit()
    take_snapshot(db, source="synthetic-demo")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Replace the current DB with synthetic demo data")
    parser.add_argument("--replace", action="store_true", help="confirm destructive replacement")
    args = parser.parse_args()
    if not args.replace:
        parser.error("demo data replaces the current DB; pass --replace to confirm")

    init_db()
    with SessionLocal() as db:
        seed(db)
    print("synthetic demo data loaded")


if __name__ == "__main__":
    main()
