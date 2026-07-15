import argparse
import json
from datetime import date, datetime

from . import config
from .db import init_db, SessionLocal
from .seed import seed as load_demo
from .dataio import backup_database, restore_database
from .services.snapshots import take_snapshot
from .services.tinvest import fetch_prices
from .services.banki import fetch_fx
from .services.operations import sync_operations
from .services.onboarding import add_currency_holding, create_deposit
from .services.repairs import repair_snapshot_cost_basis
from .services.tracking import (
    apply_tracking_cleanup, preview_tracking_cleanup, update_env_setting,
)
from .models import Instrument, Transaction


def _session():
    init_db()
    return SessionLocal()


def cmd_init(args):
    init_db(); print("db initialized")


def cmd_demo(args):
    if not args.replace:
        raise SystemExit("demo data replaces the current DB; pass --replace to confirm")
    db = _session()
    load_demo(db); print("synthetic demo data loaded"); db.close()


def cmd_backup(args):
    path = backup_database(args.output)
    print(f"backup created: {path}")


def cmd_restore(args):
    if not args.yes:
        raise SystemExit("restore replaces the active DB; stop the server and pass --yes to confirm")
    target, safety = restore_database(args.path)
    print(f"database restored: {target}")
    if safety:
        print(f"previous database backed up: {safety}")


def cmd_snapshot(args):
    db = _session()
    s = take_snapshot(db, source="cli")
    print(f"snapshot @ {s.ts}: value={s.total_value} pnl={s.total_pnl}")
    db.close()


def cmd_doctor(args):
    """Print setup readiness without revealing credentials or local paths."""
    db = _session()
    try:
        report = {
            "database_ready": True,
            "tinvest_configured": bool(config.TINVEST_TOKEN),
            "tinvest_account_selected": bool(config.TINVEST_ACCOUNT_ID),
            "portfolio_goal_rub": config.PORTFOLIO_GOAL,
            "tracking_start_date": (
                config.PORTFOLIO_TRACKING_START_DATE.isoformat()
                if config.PORTFOLIO_TRACKING_START_DATE else None
            ),
            "fx_source": config.FX_RATE_SOURCE,
            "background_minutes": {
                "snapshot": config.SNAPSHOT_EVERY_MIN,
                "prices": config.FETCH_EVERY_MIN,
                "fx": config.FX_EVERY_MIN,
            },
            "data": {
                "instruments": db.query(Instrument).count(),
                "transactions": db.query(Transaction).count(),
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        db.close()


def cmd_add_deposit(args):
    db = _session()
    try:
        result = create_deposit(
            db,
            name=args.name,
            principal=args.principal,
            open_date=date.fromisoformat(args.open_date),
            close_date=date.fromisoformat(args.close_date),
            annual_rate_pct=args.rate,
            interest_mode=args.mode,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from None
    finally:
        db.close()


def cmd_add_currency(args):
    db = _session()
    try:
        result = add_currency_holding(
            db,
            code=args.code,
            quantity=args.quantity,
            invested_rub=args.invested,
            acquired_on=date.fromisoformat(args.date),
            name=args.name,
            rate_rub_per_unit=args.rate,
            append=args.append,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from None
    finally:
        db.close()


def cmd_tracking_start(args):
    try:
        start_date = date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit("error: --date must use YYYY-MM-DD") from None

    db = _session()
    try:
        if not args.apply:
            preview = preview_tracking_cleanup(db, start_date)
            print(json.dumps({
                "dry_run": True,
                "start_date": preview["start_date"],
                "would_delete": {
                    "imported_transactions": preview["imported_transactions"],
                    "instruments": preview["instruments"],
                    "snapshots": preview["snapshots"],
                },
            }, ensure_ascii=False, indent=2))
            return

        backup = backup_database(args.backup_output, prefix="before-tracking-start")
        result = apply_tracking_cleanup(db, start_date)
        update_env_setting(
            config.RUNTIME_SETTINGS_FILE,
            "PORTFOLIO_TRACKING_START_DATE",
            start_date.isoformat(),
        )
        config.PORTFOLIO_TRACKING_START_DATE = start_date
        snapshot = take_snapshot(db, source="tracking-reset")
        print(json.dumps({
            "ok": True,
            "start_date": start_date.isoformat(),
            "deleted": {
                "imported_transactions": result["imported_transactions"],
                "instruments": result["instruments"],
                "snapshots": result["snapshots"],
            },
            "backup": str(backup),
            "snapshot": snapshot.ts.isoformat(),
            "restart_required": True,
        }, ensure_ascii=False, indent=2))
    finally:
        db.close()


def cmd_repair_cost_basis(args):
    try:
        start_date = date.fromisoformat(args.from_date)
    except ValueError:
        raise SystemExit("error: --from-date must use YYYY-MM-DD") from None

    db = _session()
    try:
        if not args.apply:
            result = repair_snapshot_cost_basis(db, start_date, apply=False)
            result["dry_run"] = True
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        backup = backup_database(args.backup_output, prefix="before-cost-basis-repair")
        result = repair_snapshot_cost_basis(db, start_date, apply=True)
        result["backup"] = backup.name
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()


def cmd_fetch_prices(args):
    db = _session()
    print(json.dumps(fetch_prices(db), ensure_ascii=False, indent=2)); db.close()


def cmd_fetch_fx(args):
    db = _session()
    print(json.dumps(fetch_fx(db, source=args.source), ensure_ascii=False, indent=2)); db.close()


def cmd_sync_ops(args):
    db = _session()
    result = sync_operations(db, days_back=args.days)
    # Краткий вывод
    print(f"imported={result.get('imported', 0)}  skipped={result.get('skipped', 0)}")
    for op in result.get("ops", []):
        print(f"  {op['date']}  {op['kind']:8}  {op['name']:30}  {op['amount']:+.2f}")
    if result.get("error"):
        print(f"ERROR: {result['error']}")
    db.close()


def cmd_tx(args):
    """Быстро добавить транзакцию: app.cli tx --ticker DEMO --kind buy --qty 10 --amount -1000"""
    db = _session()
    inst = None
    if args.ticker:
        inst = db.query(Instrument).filter(
            (Instrument.ticker == args.ticker) | (Instrument.isin == args.ticker)).first()
    tx = Transaction(ts=datetime.strptime(args.ts, "%Y-%m-%d").date(),
                     instrument_id=inst.id if inst else None, kind=args.kind,
                     quantity=args.qty, price=args.price, amount=args.amount,
                     commission=args.commission, note=args.note)
    db.add(tx); db.commit()
    print(f"tx #{tx.id} added"); db.close()


def cmd_serve(args):
    import uvicorn
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


def build_parser():
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("doctor", help="show safe setup readiness").set_defaults(func=cmd_doctor)
    demo = sub.add_parser("demo", help="replace DB with synthetic demo data")
    demo.add_argument("--replace", action="store_true")
    demo.set_defaults(func=cmd_demo)

    backup = sub.add_parser("backup", help="create a consistent SQLite backup")
    backup.add_argument(
        "--output",
        default=None,
        help="output directory (default: backups beside the active database)",
    )
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", help="restore a SQLite backup")
    restore.add_argument("path", help="path to a .db backup")
    restore.add_argument("--yes", action="store_true", help="confirm replacing the active DB")
    restore.set_defaults(func=cmd_restore)

    deposit = sub.add_parser("add-deposit", help="add a manual bank deposit")
    deposit.add_argument("--name", required=True)
    deposit.add_argument("--principal", type=float, required=True)
    deposit.add_argument("--open-date", required=True, help="YYYY-MM-DD")
    deposit.add_argument("--close-date", required=True, help="YYYY-MM-DD")
    deposit.add_argument("--rate", type=float, required=True, help="annual percent, e.g. 18")
    deposit.add_argument(
        "--mode",
        choices=["simple", "monthly_capitalization"],
        default="simple",
    )
    deposit.set_defaults(func=cmd_add_deposit)

    currency = sub.add_parser("add-currency", help="add a manual foreign-currency holding")
    currency.add_argument("--code", required=True, help="three-letter code, e.g. USD")
    currency.add_argument("--quantity", type=float, required=True)
    currency.add_argument("--invested", type=float, required=True, help="historical cost in RUB")
    currency.add_argument("--date", required=True, help="acquisition date, YYYY-MM-DD")
    currency.add_argument("--name", default="")
    currency.add_argument("--rate", type=float, default=None, help="current RUB rate; optional")
    currency.add_argument(
        "--append",
        action="store_true",
        help="explicitly append a purchase when this currency already has transactions",
    )
    currency.set_defaults(func=cmd_add_currency)

    tracking = sub.add_parser(
        "tracking-start",
        help="preview or apply the earliest T-Invest tracking date",
    )
    tracking.add_argument("--date", required=True, help="YYYY-MM-DD")
    tracking.add_argument(
        "--apply",
        action="store_true",
        help="create a backup, trim older imports, and update .env",
    )
    tracking.add_argument(
        "--backup-output",
        default=None,
        help="backup directory (default: backups beside the active database)",
    )
    tracking.set_defaults(func=cmd_tracking_start)

    repair = sub.add_parser(
        "repair-cost-basis",
        help="preview or repair snapshot security cost basis from recorded operations",
    )
    repair.add_argument("--from-date", required=True, help="YYYY-MM-DD")
    repair.add_argument(
        "--apply",
        action="store_true",
        help="create a backup and apply the idempotent snapshot repair",
    )
    repair.add_argument(
        "--backup-output",
        default=None,
        help="backup directory (default: backups beside the active database)",
    )
    repair.set_defaults(func=cmd_repair_cost_basis)
    sub.add_parser("snapshot").set_defaults(func=cmd_snapshot)
    sub.add_parser("fetch-prices").set_defaults(func=cmd_fetch_prices)

    fx = sub.add_parser("fetch-fx")
    fx.add_argument("--source", choices=["bank_buy", "bank_sell", "cbr"], default=None,
                    help="переопределить FX_RATE_SOURCE из .env")
    fx.set_defaults(func=cmd_fetch_fx)

    ops = sub.add_parser("sync-ops")
    ops.add_argument("--days", type=int, default=365, help="глубина истории в днях")
    ops.set_defaults(func=cmd_sync_ops)

    t = sub.add_parser("tx")
    t.add_argument("--ts", required=True); t.add_argument("--ticker")
    t.add_argument("--kind", required=True)
    t.add_argument("--qty", type=float, default=0); t.add_argument("--price", type=float, default=0)
    t.add_argument("--amount", type=float, default=0); t.add_argument("--commission", type=float, default=0)
    t.add_argument("--note", default=""); t.set_defaults(func=cmd_tx)

    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true"); s.set_defaults(func=cmd_serve)
    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
