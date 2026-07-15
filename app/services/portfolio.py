from datetime import date, datetime
from collections import defaultdict
from ..models import Instrument, Transaction


# ---------- XIRR ----------
def _xnpv(rate, flows):
    t0 = min(d for d, _ in flows)
    return sum(a / (1 + rate) ** ((d - t0).days / 365.0) for d, a in flows)


def xirr(flows, guess=0.12):
    """flows: list[(date, amount)], amount знаковый. Метод Ньютона + бисекция-фолбэк."""
    flows = [(d, float(a)) for d, a in flows if a]
    if len(flows) < 2 or not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    rate = guess
    for _ in range(100):
        f = _xnpv(rate, flows)
        df = (_xnpv(rate + 1e-5, flows) - f) / 1e-5
        if abs(df) < 1e-12:
            break
        new = rate - f / df
        if new <= -0.999999:
            new = (rate - 0.999999) / 2
        if abs(new - rate) < 1e-8:
            return new
        rate = new
    lo, hi = -0.9999, 100.0
    flo, fhi = _xnpv(lo, flows), _xnpv(hi, flows)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = _xnpv(mid, flows)
        if abs(fm) < 1e-7:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


# ---------- вклад ----------
def deposit_value_from_meta(meta, on=None):
    """Accrued deposit value for the explicitly selected interest model.

    New deposits use either simple daily accrual or a nominal annual rate with
    monthly capitalization. Old rows without interest_mode retain the previous
    effective-annual calculation so an upgrade does not rewrite user history.
    """
    on = on or date.today()
    m = meta or {}
    principal = float(m.get("principal", 0))
    open_d = _d(m.get("open_date"))
    close_d = _d(m.get("close_date"))
    annual_rate = float(m.get("eff_rate", 0))
    if not (principal and open_d and annual_rate):
        return principal
    end = min(on, close_d) if close_d else on
    if end <= open_d:
        return principal

    mode = m.get("interest_mode")
    if mode == "simple":
        return principal * (1 + annual_rate * (end - open_d).days / 365.0)

    months = (end.year - open_d.year) * 12 + (end.month - open_d.month)
    months = max(0, months)
    while months > 0 and _add_months(open_d, months) > end:
        months -= 1
    while _add_months(open_d, months + 1) <= end:
        months += 1
    anchor = _add_months(open_d, months)
    remainder_days = max(0, (end - anchor).days)

    if mode == "monthly_capitalization":
        monthly_rate = annual_rate / 12.0
        balance = principal * (1 + monthly_rate) ** months
        return balance * (1 + annual_rate * remainder_days / 365.0)

    # Legacy deposits stored an effective annual rate without an interest mode.
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    return principal * (1 + monthly_rate) ** months * (
        1 + monthly_rate * remainder_days / 30.0
    )


def deposit_value(inst, on=None):
    return deposit_value_from_meta(inst.meta or {}, on)


def _moving_average_book(txs, buy_kind: str, sell_kind: str):
    """Return remaining quantity/cost and realized P&L using moving average cost."""
    quantity = 0.0
    cost = 0.0
    realized = 0.0
    for tx in sorted(txs, key=lambda item: (item.ts, item.id or 0)):
        tx_quantity = abs(float(tx.quantity or 0))
        if tx.kind == buy_kind and tx_quantity:
            purchase_cost = -float(tx.amount or 0)
            if purchase_cost <= 0:
                purchase_cost = float(tx.price or 0) * tx_quantity + float(tx.commission or 0)
            quantity += tx_quantity
            cost += purchase_cost
        elif tx.kind == sell_kind and tx_quantity and quantity > 0:
            matched = min(tx_quantity, quantity)
            average_cost = cost / quantity if quantity else 0
            released_cost = average_cost * matched
            proceeds = float(tx.amount or 0)
            if proceeds <= 0:
                proceeds = max(0.0, float(tx.price or 0) * tx_quantity - float(tx.commission or 0))
            if matched < tx_quantity:
                proceeds *= matched / tx_quantity
            realized += proceeds - released_cost
            quantity -= matched
            cost -= released_cost
    if abs(quantity) < 1e-9:
        quantity = 0.0
        cost = 0.0
    return quantity, cost, realized


def _add_months(d0, n):
    y = d0.year + (d0.month - 1 + n) // 12
    mth = (d0.month - 1 + n) % 12 + 1
    import calendar
    day = min(d0.day, calendar.monthrange(y, mth)[1])
    return date(y, mth, day)


def _d(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    return datetime.strptime(v, "%Y-%m-%d").date()


# ---------- позиции и оценка ----------
def positions(db, on=None):
    on = on or date.today()
    out = []
    for inst in db.query(Instrument).all():
        txs = inst.transactions

        if inst.kind == "deposit":
            if (inst.meta or {}).get("status") == "closed":
                continue
            invested = sum(-t.amount for t in txs if t.kind == "buy")
            # A maturity date does not prove that money moved elsewhere. Keep a
            # matured deposit at its capped close-date value until the user
            # reconciles the real payout instead of silently dropping the asset.
            value = deposit_value(inst, on)
            income = sum(t.amount for t in txs if t.kind == "interest")
            out.append(_pos(inst, qty=1, invested=invested, value=value,
                            income=income, unrealized=value - invested, realized=0))
            continue

        if inst.kind == "currency":
            # RUB combines the broker-authoritative balance with the local cash ledger.
            if inst.currency == "RUB":
                meta = inst.meta or {}
                broker_balance = float(
                    meta.get("broker_balance", meta.get("balance", 0)) or 0
                )
                manual_balance = sum(
                    float(tx.amount or 0)
                    for tx in txs
                    if tx.kind in {"topup", "withdrawal"}
                )
                balance = broker_balance + manual_balance
                if balance <= 0:
                    continue
                out.append(_pos(inst, qty=round(balance, 2), invested=0,
                                value=round(balance, 2), income=0,
                                unrealized=0, realized=0))
                continue
            qty, invested, realized = _moving_average_book(txs, "fx_buy", "fx_sell")
            if qty <= 0:
                continue
            value = qty * inst.last_price
            out.append(_pos(inst, qty=qty, invested=invested, value=value,
                            income=0, unrealized=value - invested, realized=realized))
            continue

        # bond / share / etf
        meta = inst.meta or {}
        if meta.get("tinvest_position_synced"):
            qty = float(meta.get("tinvest_current_quantity", 0) or 0)
            if qty <= 0:
                continue
            dirty = inst.last_price + (inst.nkd if inst.kind == "bond" else 0)
            value = qty * dirty
            expected_yield = float(meta.get("tinvest_expected_yield", 0) or 0)
            average_price = float(meta.get("tinvest_average_price", 0) or 0)
            if value - expected_yield > 0:
                invested = value - expected_yield
                unrealized = expected_yield
            elif average_price > 0:
                invested = average_price * qty
                unrealized = value - invested
            else:
                _, invested, _ = _moving_average_book(txs, "buy", "sell")
                unrealized = value - invested
            income = sum(t.amount for t in txs if t.kind in ("coupon", "dividend"))
            out.append(_pos(inst, qty=qty, invested=invested, value=value,
                            income=income, unrealized=unrealized, realized=0))
            continue

        qty, invested, realized = _moving_average_book(txs, "buy", "sell")
        if qty <= 0:
            continue  # погашено или продано — скрываем из активных позиций
        dirty = inst.last_price + (inst.nkd if inst.kind == "bond" else 0)
        value = qty * dirty
        income = sum(t.amount for t in txs if t.kind in ("coupon", "dividend"))
        out.append(_pos(inst, qty=qty, invested=invested, value=value,
                        income=income, unrealized=value - invested, realized=realized))
    return out


def _pos(inst, qty, invested, value, income, unrealized, realized):
    pnl = unrealized + income + realized
    return {
        "id": inst.id, "kind": inst.kind, "name": inst.name,
        "ticker": inst.ticker, "isin": inst.isin, "currency": inst.currency,
        "qty": round(qty, 4), "invested": round(invested, 2), "value": round(value, 2),
        "income": round(income, 2), "unrealized": round(unrealized, 2),
        "realized": round(realized, 2), "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / invested, 4) if invested else 0,
        "last_price": inst.last_price, "nkd": inst.nkd, "nominal": inst.nominal,
        "meta": inst.meta or {},
    }


CLASS_RU = {"bond": "Облигации", "share": "Акции", "etf": "Фонды",
            "currency": "Валюта", "deposit": "Вклад"}


def summary(db, on=None):
    on = on or date.today()
    pos = positions(db, on)
    by_class = defaultdict(lambda: {"invested": 0.0, "value": 0.0, "pnl": 0.0})
    tot = {"invested": 0.0, "value": 0.0, "pnl": 0.0, "income": 0.0}
    for p in pos:
        c = CLASS_RU.get(p["kind"], p["kind"])
        by_class[c]["invested"] += p["invested"]
        by_class[c]["value"] += p["value"]
        by_class[c]["pnl"] += p["pnl"]
        for k in ("invested", "value", "pnl"):
            tot[k] += p[k]
        tot["income"] += p["income"]

    flows = []
    for t in db.query(Transaction).filter(Transaction.instrument_id.isnot(None)).all():
        if t.instrument and t.instrument.kind == "currency" and t.instrument.currency == "RUB":
            continue
        if t.amount:
            flows.append((t.ts, t.amount))
    # Ruble cash is excluded from the terminal XIRR value: security sales are
    # already positive flows. Including the same proceeds again as RUB balance
    # would double count them.
    terminal_value = sum(
        p["value"] for p in pos
        if not (p["kind"] == "currency" and p["currency"] == "RUB")
    )
    flows.append((on, terminal_value))
    r = xirr(flows)

    for c in by_class.values():
        c["pnl_pct"] = c["pnl"] / c["invested"] if c["invested"] else 0
        for k in ("invested", "value", "pnl"):
            c[k] = round(c[k], 2)
        c["pnl_pct"] = round(c["pnl_pct"], 4)
    from .snapshots import compute_streak
    streak = compute_streak(db)
    lifetime = realized_results(db)
    return {
        "as_of": on.isoformat(),
        "invested": round(tot["invested"], 2),
        "value": round(tot["value"], 2),
        "pnl": round(tot["pnl"], 2),
        "pnl_pct": round(tot["pnl"] / tot["invested"], 4) if tot["invested"] else 0,
        "income_received": round(tot["income"], 2),
        "xirr": round(r, 4) if r is not None else None,
        "streak": streak,
        "lifetime_results": lifetime,
        "by_class": dict(by_class),
        "positions": pos,
    }


def realized_results(db):
    """Recorded lifetime income and moving-average realized P&L.

    This is deliberately separate from headline current-position P&L. Imported
    broker history may be incomplete before the configured tracking boundary.
    """
    items = []
    realized_total = 0.0
    income_total = 0.0
    for inst in db.query(Instrument).all():
        if inst.kind == "currency" and inst.currency == "RUB":
            continue
        txs = list(inst.transactions)
        if inst.kind == "currency":
            quantity, _, realized = _moving_average_book(txs, "fx_buy", "fx_sell")
            income = 0.0
        elif inst.kind in {"bond", "share", "etf"}:
            quantity, _, realized = _moving_average_book(txs, "buy", "sell")
            income = sum(float(tx.amount or 0) for tx in txs if tx.kind in {"coupon", "dividend"})
        elif inst.kind == "deposit":
            quantity = 0.0 if (inst.meta or {}).get("status") == "closed" else 1.0
            realized = 0.0
            income = sum(float(tx.amount or 0) for tx in txs if tx.kind == "interest")
        else:
            continue
        if not realized and not income:
            continue
        realized_total += realized
        income_total += income
        items.append({
            "id": inst.id,
            "name": inst.name,
            "ticker": inst.ticker,
            "kind": inst.kind,
            "closed": quantity <= 1e-9,
            "realized_pnl": round(realized, 2),
            "income": round(income, 2),
            "total_result": round(realized + income, 2),
        })
    items.sort(key=lambda item: abs(item["total_result"]), reverse=True)
    return {
        "realized_pnl": round(realized_total, 2),
        "income": round(income_total, 2),
        "total": round(realized_total + income_total, 2),
        "items": items,
        "estimate": True,
        "limitation": "T-Invest results can be incomplete before the tracking start date",
    }
