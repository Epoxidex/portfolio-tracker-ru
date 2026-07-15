"""Read-only query service shared by the REST API and MCP server."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import config
from ..models import Instrument, PriceHistory, Snapshot, Transaction
from . import calendar as cal
from . import portfolio, snapshots
from .git_backup import backup_status


INSTRUMENT_KINDS = {"bond", "share", "etf", "currency", "deposit"}
TRANSACTION_KINDS = {
    "buy", "sell", "coupon", "dividend", "interest", "fx_buy", "fx_sell",
    "topup", "withdrawal",
}
SORTABLE_POSITION_FIELDS = {
    "name", "kind", "qty", "invested", "value", "income", "pnl", "pnl_pct",
}


def _bounded_limit(value: int, *, maximum: int = 2000) -> int:
    if value < 1:
        raise ValueError("limit must be at least 1")
    return min(value, maximum)


def _offset(value: int) -> int:
    if value < 0:
        raise ValueError("offset cannot be negative")
    return value


def _date(value: str | date | None, field: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _date_window(date_from: str | date | None, date_to: str | date | None) -> tuple[date | None, date | None]:
    start = _date(date_from, "date_from")
    end = _date(date_to, "date_to")
    if start and end and start > end:
        raise ValueError("date_from cannot be later than date_to")
    return start, end


def _instrument_dict(inst: Instrument) -> dict[str, Any]:
    return {
        "id": inst.id,
        "kind": inst.kind,
        "name": inst.name,
        "ticker": inst.ticker,
        "isin": inst.isin,
        "figi": inst.figi,
        "currency": inst.currency,
        "nominal": inst.nominal,
        "last_price": inst.last_price,
        "nkd": inst.nkd,
        "price_updated_at": inst.price_updated_at.isoformat() if inst.price_updated_at else None,
        "meta": inst.meta or {},
    }


def _transaction_dict(tx: Transaction) -> dict[str, Any]:
    inst = tx.instrument
    return {
        "id": tx.id,
        "date": tx.ts.isoformat(),
        "ts": tx.ts.isoformat(),
        "instrument_id": tx.instrument_id,
        "instrument": inst.name if inst else None,
        "ticker": inst.ticker if inst else None,
        "isin": inst.isin if inst else None,
        "instrument_kind": inst.kind if inst else None,
        "kind": tx.kind,
        "quantity": tx.quantity,
        "price": tx.price,
        "amount": tx.amount,
        "commission": tx.commission,
        "note": tx.note,
    }


def resolve_instrument(db: Session, identifier: str | int) -> Instrument | None:
    """Resolve an instrument by numeric id, id:<n>, ticker, ISIN, FIGI, or exact name."""
    raw = str(identifier).strip()
    if not raw:
        return None
    numeric = raw[3:] if raw.lower().startswith("id:") else raw
    if numeric.isdigit():
        found = db.get(Instrument, int(numeric))
        if found:
            return found
    lowered = raw.lower()
    found = db.query(Instrument).filter(or_(
        Instrument.name == raw,
        func.lower(Instrument.ticker) == lowered,
        func.lower(Instrument.isin) == lowered,
        func.lower(Instrument.figi) == lowered,
        func.lower(Instrument.name) == lowered,
    )).first()
    if found:
        return found
    return next(
        (instrument for instrument in db.query(Instrument).all()
         if instrument.name.casefold() == raw.casefold()),
        None,
    )


def data_status(db: Session) -> dict[str, Any]:
    """Configuration and data readiness without secrets or local paths."""
    return {
        "tinvest": {
            "configured": bool(config.TINVEST_TOKEN),
            "account_selected": bool(config.TINVEST_ACCOUNT_ID),
        },
        "fx_source": config.FX_RATE_SOURCE,
        "portfolio_goal": config.PORTFOLIO_GOAL,
        "tracking_start_date": (
            config.PORTFOLIO_TRACKING_START_DATE.isoformat()
            if config.PORTFOLIO_TRACKING_START_DATE else None
        ),
        "background_jobs_minutes": {
            "snapshots": config.SNAPSHOT_EVERY_MIN,
            "tinvest_prices": config.FETCH_EVERY_MIN,
            "currency_rates": config.FX_EVERY_MIN,
        },
        "backups": backup_status(),
        "data": {
            "instruments": db.query(Instrument).count(),
            "transactions": db.query(Transaction).count(),
            "price_points": db.query(PriceHistory).count(),
            "snapshots": db.query(Snapshot).count(),
        },
    }


def list_positions(
    db: Session,
    *,
    kind: str | None = None,
    query: str | None = None,
    sort_by: str = "value",
    descending: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    if kind and kind not in INSTRUMENT_KINDS:
        raise ValueError(f"unsupported instrument kind: {kind}")
    if sort_by not in SORTABLE_POSITION_FIELDS:
        raise ValueError(f"unsupported sort field: {sort_by}")
    limit = _bounded_limit(limit)
    offset = _offset(offset)
    items = portfolio.positions(db)
    if kind:
        items = [item for item in items if item["kind"] == kind]
    if query:
        needle = query.casefold()
        items = [item for item in items if needle in " ".join((
            item.get("name", ""), item.get("ticker", ""), item.get("isin", ""),
            item.get("currency", ""), item.get("kind", ""),
        )).casefold()]
    items.sort(key=lambda item: (item.get(sort_by) is not None, item.get(sort_by)), reverse=descending)
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}


def list_instruments(
    db: Session,
    *,
    kind: str | None = None,
    query: str | None = None,
    active_only: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    if kind and kind not in INSTRUMENT_KINDS:
        raise ValueError(f"unsupported instrument kind: {kind}")
    limit = _bounded_limit(limit)
    offset = _offset(offset)
    q = db.query(Instrument)
    if kind:
        q = q.filter(Instrument.kind == kind)
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(or_(
            Instrument.name.ilike(pattern), Instrument.ticker.ilike(pattern),
            Instrument.isin.ilike(pattern), Instrument.figi.ilike(pattern),
            Instrument.currency.ilike(pattern),
        ))
    if active_only:
        active_ids = [item["id"] for item in portfolio.positions(db)]
        if not active_ids:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        q = q.filter(Instrument.id.in_(active_ids))
    total = q.count()
    rows = q.order_by(Instrument.kind, Instrument.name).offset(offset).limit(limit).all()
    return {"items": [_instrument_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def instrument_details(
    db: Session,
    identifier: str | int,
    *,
    transaction_limit: int = 100,
    price_limit: int = 200,
) -> dict[str, Any]:
    inst = resolve_instrument(db, identifier)
    if not inst:
        raise ValueError(f"instrument not found: {identifier}")
    transaction_limit = _bounded_limit(transaction_limit)
    price_limit = _bounded_limit(price_limit)
    txs = (db.query(Transaction).filter(Transaction.instrument_id == inst.id)
           .order_by(Transaction.ts.desc(), Transaction.id.desc()).limit(transaction_limit).all())
    prices = (db.query(PriceHistory).filter(PriceHistory.instrument_id == inst.id)
              .order_by(PriceHistory.ts.desc()).limit(price_limit).all())
    active = next((item for item in portfolio.positions(db) if item["id"] == inst.id), None)
    return {
        "instrument": _instrument_dict(inst),
        "active_position": active,
        "transactions": [_transaction_dict(tx) for tx in txs],
        "price_history": [
            {"ts": row.ts.isoformat(), "price": row.price}
            for row in reversed(prices)
        ],
        "returned": {"transactions": len(txs), "price_points": len(prices)},
    }


def list_transactions(
    db: Session,
    *,
    date_from: str | date | None = None,
    date_to: str | date | None = None,
    kind: str | None = None,
    instrument: str | int | None = None,
    query: str | None = None,
    descending: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to)
    if kind and kind not in TRANSACTION_KINDS:
        raise ValueError(f"unsupported transaction kind: {kind}")
    limit = _bounded_limit(limit)
    offset = _offset(offset)
    q = db.query(Transaction)
    if start:
        q = q.filter(Transaction.ts >= start)
    if end:
        q = q.filter(Transaction.ts <= end)
    if kind:
        q = q.filter(Transaction.kind == kind)
    if instrument is not None:
        inst = resolve_instrument(db, instrument)
        if not inst:
            raise ValueError(f"instrument not found: {instrument}")
        q = q.filter(Transaction.instrument_id == inst.id)
    if query:
        pattern = f"%{query.strip()}%"
        q = q.outerjoin(Instrument).filter(or_(
            Transaction.note.ilike(pattern), Transaction.kind.ilike(pattern),
            Instrument.name.ilike(pattern), Instrument.ticker.ilike(pattern),
            Instrument.isin.ilike(pattern),
        ))
    total = q.count()
    order = (Transaction.ts.desc(), Transaction.id.desc()) if descending else (Transaction.ts, Transaction.id)
    rows = q.order_by(*order).offset(offset).limit(limit).all()
    return {"items": [_transaction_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def portfolio_history(
    db: Session,
    *,
    date_from: str | date | None = None,
    date_to: str | date | None = None,
    granularity: str = "daily",
    limit: int = 2000,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to)
    if granularity not in {"daily", "raw"}:
        raise ValueError("granularity must be daily or raw")
    limit = _bounded_limit(limit, maximum=10000)
    if granularity == "daily":
        rows = snapshots.history(db, limit=10000)
        if start:
            rows = [row for row in rows if date.fromisoformat(row.get("day") or row["ts"][:10]) >= start]
        if end:
            rows = [row for row in rows if date.fromisoformat(row.get("day") or row["ts"][:10]) <= end]
        rows = rows[-limit:]
    else:
        q = db.query(Snapshot)
        if start:
            q = q.filter(Snapshot.ts >= datetime.combine(start, time.min) - timedelta(hours=3))
        if end:
            q = q.filter(Snapshot.ts < datetime.combine(end + timedelta(days=1), time.min) - timedelta(hours=3))
        raw = q.order_by(Snapshot.ts.desc()).limit(limit).all()
        rows = [{
            "ts": row.ts.isoformat(), "value": row.total_value,
            "invested": row.total_invested, "pnl": row.total_pnl,
            "income": row.income_received, "by_class": row.by_class or {},
            "by_instrument": row.by_instrument or {}, "source": row.source,
        } for row in reversed(raw)]
    return {"items": rows, "returned": len(rows), "granularity": granularity}


def price_history(
    db: Session,
    *,
    instrument: str | int | None = None,
    date_from: str | date | None = None,
    date_to: str | date | None = None,
    days: int | None = 90,
    limit_per_instrument: int = 2000,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to)
    if days is not None:
        if days < 1 or days > 36500:
            raise ValueError("days must be between 1 and 36500")
        if start is None:
            start = (end or date.today()) - timedelta(days=days)
    limit_per_instrument = _bounded_limit(limit_per_instrument, maximum=10000)
    instruments = [resolve_instrument(db, instrument)] if instrument is not None else db.query(Instrument).order_by(Instrument.name).all()
    if instrument is not None and not instruments[0]:
        raise ValueError(f"instrument not found: {instrument}")
    result = []
    for inst in instruments:
        q = db.query(PriceHistory).filter(PriceHistory.instrument_id == inst.id)
        if start:
            q = q.filter(PriceHistory.ts >= datetime.combine(start, time.min))
        if end:
            q = q.filter(PriceHistory.ts < datetime.combine(end + timedelta(days=1), time.min))
        rows = q.order_by(PriceHistory.ts.desc()).limit(limit_per_instrument).all()
        if rows:
            result.append({
                "id": inst.id, "name": inst.name, "ticker": inst.ticker,
                "kind": inst.kind, "currency": inst.currency,
                "history": [{"ts": row.ts.isoformat(), "price": row.price} for row in reversed(rows)],
            })
    return {"items": result, "instruments_returned": len(result)}


def search(db: Session, query: str, *, limit: int = 50) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query cannot be empty")
    limit = _bounded_limit(limit, maximum=500)
    return {
        "query": query,
        "instruments": list_instruments(db, query=query, limit=limit)["items"],
        "positions": list_positions(db, query=query, limit=limit)["items"],
        "transactions": list_transactions(db, query=query, limit=limit)["items"],
    }


def portfolio_context(
    db: Session,
    *,
    recent_transactions: int = 50,
    history_days: int = 365,
    calendar_months: int = 24,
) -> dict[str, Any]:
    if history_days < 1 or history_days > 36500:
        raise ValueError("history_days must be between 1 and 36500")
    if calendar_months < 1 or calendar_months > 120:
        raise ValueError("calendar_months must be between 1 and 120")
    recent_transactions = _bounded_limit(recent_transactions, maximum=1000)
    since = date.today() - timedelta(days=history_days)
    return {
        "status": data_status(db),
        "summary": portfolio.summary(db),
        "passive_income": cal.passive_income(db),
        "payment_calendar": cal.calendar(db, months_ahead=calendar_months),
        "returns": snapshots.compute_returns(db, period="monthly"),
        "leaders": {
            period: snapshots.compute_leaders(db, period=period)
            for period in ("day", "week", "month")
        },
        "recent_transactions": list_transactions(db, limit=recent_transactions)["items"],
        "history": portfolio_history(db, date_from=since, granularity="daily")["items"],
    }
