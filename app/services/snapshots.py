from datetime import date, datetime, timedelta
from .. import config
from ..models import Instrument, Snapshot, Transaction
from .portfolio import summary


MOSCOW_OFFSET = timedelta(hours=3)


def _portfolio_day(ts: datetime) -> date:
    """Календарный день портфеля в Москве для хранимого UTC timestamp."""
    return (ts + MOSCOW_OFFSET).date()


def _hist_day(row: dict) -> date:
    return date.fromisoformat(row.get("day") or row["ts"][:10])


def take_snapshot(db, source="auto"):
    s = summary(db)
    snap = Snapshot(
        ts=datetime.utcnow(),
        total_value=s["value"],
        total_invested=s["invested"],
        total_pnl=s["pnl"],
        income_received=s["income_received"],
        by_class=s["by_class"],
        by_instrument={p["name"]: p["value"] for p in s["positions"]},
        source=source,
    )
    db.add(snap)
    db.commit()
    return snap


def history(db, limit=2000):
    rows = db.query(Snapshot).order_by(Snapshot.ts).limit(limit).all()
    by_day = {}
    for r in rows:
        day = _portfolio_day(r.ts)
        if config.PORTFOLIO_TRACKING_START_DATE and day < config.PORTFOLIO_TRACKING_START_DATE:
            continue
        by_day[day.isoformat()] = r
    return [{
        "ts": r.ts.isoformat(),
        "day": _portfolio_day(r.ts).isoformat(),
        "value": r.total_value, "invested": r.total_invested,
        "pnl": r.total_pnl, "income": r.income_received,
        "by_class": r.by_class,
        "by_instrument": r.by_instrument or {},
    } for r in sorted(by_day.values(), key=lambda x: x.ts)]


def _instrument_changes(db, reference, current):
    """Return cash-flow-adjusted market changes between two snapshots.

    The portfolio headline and the leaders list intentionally share this path.
    Broker cost-basis corrections affect stored P&L, but they are not market
    movements and must not appear as period returns.
    """
    current_values = current.by_instrument or {}
    reference_values = reference.by_instrument or {}
    instruments = {i.name: i for i in db.query(Instrument).all()}
    flows = {}
    purchases = {}
    tx_rows = (db.query(Transaction)
               .filter(Transaction.instrument_id.isnot(None),
                       Transaction.ts > _portfolio_day(reference.ts),
                       Transaction.ts <= _portfolio_day(current.ts))
               .all())
    for tx in tx_rows:
        name = tx.instrument.name if tx.instrument else None
        if not name:
            continue
        amount = float(tx.amount or 0)
        flows[name] = flows.get(name, 0.0) + amount
        if tx.kind in {"buy", "fx_buy"} and amount < 0:
            purchases[name] = purchases.get(name, 0.0) - amount

    items = []
    base_total = 0.0
    for name in set(current_values) | set(reference_values):
        current_value = float(current_values.get(name, 0) or 0)
        reference_value = float(reference_values.get(name, 0) or 0)
        inst = instruments.get(name)
        if inst and inst.kind == "currency" and inst.currency == "RUB":
            continue
        change = current_value - reference_value + flows.get(name, 0.0)
        base_value = reference_value + purchases.get(name, 0.0)
        base_total += max(0.0, base_value)
        if abs(change) < 0.005:
            continue
        change_pct = change / base_value if base_value else None
        ticker = ""
        if inst:
            ticker = inst.ticker or (inst.currency if inst.kind == "currency" else "")
        items.append({
            "name": name,
            "ticker": ticker or name.split()[0],
            "kind": inst.kind if inst else "",
            "value": round(current_value, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 6) if change_pct is not None else None,
        })

    items.sort(key=lambda item: abs(item["change"]), reverse=True)
    return items, base_total


def compute_streak(db) -> int:
    """Consecutive snapshot days with positive cash-flow-adjusted movement."""
    rows = db.query(Snapshot).order_by(Snapshot.ts.desc()).limit(800).all()
    by_day: dict = {}
    for r in rows:
        day = _portfolio_day(r.ts)
        if day not in by_day:
            by_day[day] = r
    days = sorted(by_day.keys(), reverse=True)
    streak = 0
    for i in range(len(days) - 1):
        current = by_day[days[i]]
        reference = by_day[days[i + 1]]
        if current.by_instrument and reference.by_instrument:
            items, _ = _instrument_changes(db, reference, current)
            change = sum(item["change"] for item in items)
        else:
            change = current.total_pnl - reference.total_pnl
        if change > 0:
            streak += 1
        else:
            break
    return streak


def compute_returns(db, period: str = "monthly") -> dict:
    """Вычисляет доходность по периодам (daily/monthly/yearly) из снапшотов.

    Возвращает:
      points: список {label, change, pct, value}
      today: {change, pct}  — за сегодня (последний снапшот vs вчерашний)
      week:  {change, pct}  — от последнего снимка предыдущей недели
      month: {change, pct}  — от последнего снимка предыдущего месяца
      ytd:   {change, pct}  — с начала года
    """
    hist = history(db)  # one per day, sorted asc
    snapshot_by_ts = {
        row.ts.isoformat(): row
        for row in db.query(Snapshot).order_by(Snapshot.ts).all()
    }

    def _delta(a, b):
        """Cash-flow-adjusted market movement from snapshot ``a`` to ``b``."""
        if not a or not b or b.get("invested", 0) == 0:
            return {"change": None, "pct": None}
        if a.get("by_instrument") and b.get("by_instrument"):
            reference = snapshot_by_ts.get(a["ts"])
            current = snapshot_by_ts.get(b["ts"])
            if reference and current:
                items, base_total = _instrument_changes(db, reference, current)
                change = sum(item["change"] for item in items)
                pct = change / base_total if base_total else None
                return {
                    "change": round(change, 2),
                    "pct": round(pct, 6) if pct is not None else None,
                }
        # Backward compatibility for legacy snapshots without instrument detail.
        change = b["pnl"] - a["pnl"]
        pct = change / b["invested"]
        return {"change": round(change, 2), "pct": round(pct, 6)}

    # --- period points ---
    points = []
    if period == "daily":
        for i in range(1, len(hist)):
            d = _delta(hist[i - 1], hist[i])
            points.append({"label": _hist_day(hist[i]).isoformat(), **d, "value": hist[i]["value"]})

    elif period == "monthly":
        by_month: dict = {}
        for r in hist:
            ym = _hist_day(r).strftime("%Y-%m")
            if ym not in by_month:
                by_month[ym] = {"first": r, "last": r}
            else:
                by_month[ym]["last"] = r
        months = sorted(by_month)
        for i, ym in enumerate(months):
            l = by_month[ym]["last"]
            # сравниваем с последним снапшотом предыдущего месяца (если есть)
            prev = by_month[months[i - 1]]["last"] if i > 0 else by_month[ym]["first"]
            d = _delta(prev, l)
            points.append({"label": ym, **d, "value": l["value"]})

    elif period == "yearly":
        by_year: dict = {}
        for r in hist:
            y = str(_hist_day(r).year)
            if y not in by_year:
                by_year[y] = {"first": r, "last": r}
            else:
                by_year[y]["last"] = r
        years = sorted(by_year)
        for i, y in enumerate(years):
            l = by_year[y]["last"]
            prev = by_year[years[i - 1]]["last"] if i > 0 else by_year[y]["first"]
            d = _delta(prev, l)
            points.append({"label": y, **d, "value": l["value"]})

    # --- summary deltas ---
    last = hist[-1] if hist else None
    current_day = _hist_day(last) if last else None
    year_str = str(current_day.year) if current_day else ""

    if current_day:
        prev_day_target = current_day - timedelta(days=1)
        prev_day = next((r for r in reversed(hist[:-1]) if _hist_day(r) == prev_day_target), None)

        current_week_start = current_day - timedelta(days=current_day.weekday())
        prev_week_start = current_week_start - timedelta(days=7)
        prev_week_end = current_week_start - timedelta(days=1)
        week_ref = next((
            r for r in reversed(hist[:-1])
            if prev_week_start <= _hist_day(r) <= prev_week_end
        ), None)

        current_month_start = current_day.replace(day=1)
        prev_month_end = current_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        month_ref = next((
            r for r in reversed(hist[:-1])
            if prev_month_start <= _hist_day(r) <= prev_month_end
        ), None)
    else:
        prev_day = None
        week_ref = None
        month_ref = None

    delta_today = _delta(prev_day, last)
    delta_week = _delta(week_ref, last)
    delta_month = _delta(month_ref, last)

    # ytd: с конца прошлого года (последний снапшот года year_str-1);
    # фоллбэк — первый снапшот текущего года
    last_of_prev_year = next(
        (r for r in reversed(hist[:-1]) if str(_hist_day(r).year) < year_str), None
    )
    first_of_year = next((r for r in hist if str(_hist_day(r).year) == year_str), None)
    ref_ytd = last_of_prev_year or first_of_year
    delta_ytd = _delta(ref_ytd, last)

    return {
        "period": period,
        "points": points,
        "today": delta_today,
        "week": delta_week,
        "month": delta_month,
        "ytd": delta_ytd,
    }


def compute_leaders(db, period: str = "day") -> dict:
    """Возвращает вклад инструментов в изменение стоимости портфеля.

    Размер плитки строится по абсолютному вкладу позиции в результат портфеля,
    а цвет — по процентному изменению. Покупки и продажи исключаются из результата,
    выплаты включаются; поэтому новая покупка не выглядит как огромный рыночный рост.
    Опорная точка — последний снимок предыдущего дня, календарной недели или месяца.
    """
    if period not in {"day", "week", "month"}:
        period = "day"

    rows = db.query(Snapshot).order_by(Snapshot.ts).all()
    if len(rows) < 2:
        return {"period": period, "from": None, "to": None, "items": [], "complete": False}

    # Один (последний) снимок на день, чтобы внутридневные обновления не искажали окно.
    by_day = {}
    for row in rows:
        by_day[_portfolio_day(row.ts)] = row
    days = sorted(by_day)
    usable_days = [day for day in days if by_day[day].by_instrument]
    if len(usable_days) < 2:
        return {"period": period, "from": None, "to": None, "items": [], "complete": False}
    current = by_day[usable_days[-1]]

    current_day = _portfolio_day(current.ts)
    if period == "day":
        period_start = period_end = current_day - timedelta(days=1)
    elif period == "week":
        current_week_start = current_day - timedelta(days=current_day.weekday())
        period_start = current_week_start - timedelta(days=7)
        period_end = current_week_start - timedelta(days=1)
    else:
        current_month_start = current_day.replace(day=1)
        period_end = current_month_start - timedelta(days=1)
        period_start = period_end.replace(day=1)

    reference_days = [day for day in usable_days[:-1] if period_start <= day <= period_end]
    reference = by_day[reference_days[-1]] if reference_days else None
    complete = reference is not None

    if reference is None:
        return {
            "period": period, "from": None, "to": current.ts.isoformat(),
            "reference_period": {"from": period_start.isoformat(), "to": period_end.isoformat()},
            "items": [], "complete": False,
        }

    items, _ = _instrument_changes(db, reference, current)
    total_impact = sum(abs(item["change"]) for item in items)
    for item in items:
        item["impact_pct"] = round(abs(item["change"]) / total_impact, 6) if total_impact else 0

    return {
        "period": period,
        "from": reference.ts.isoformat(),
        "to": current.ts.isoformat(),
        "reference_period": {"from": period_start.isoformat(), "to": period_end.isoformat()},
        "complete": complete,
        "items": items,
    }
