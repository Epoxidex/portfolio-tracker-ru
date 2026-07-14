from datetime import date
from dateutil.relativedelta import relativedelta
from .portfolio import positions, _d, _add_months, deposit_value_from_meta


def _step(ppy):
    return {1: 12, 2: 6, 4: 3, 12: 1}.get(int(ppy), 1)


def calendar(db, months_ahead=24, include_past=False):
    """Список будущих (и опц. прошлых) выплат: купоны, %вклада, погашения, дивиденды."""
    today = date.today()
    horizon = _add_months(today, months_ahead)
    ev = []
    for p in positions(db):
        m = p["meta"] or {}
        qty = p["qty"]
        if qty <= 0 and p["kind"] != "deposit":
            continue
        if p["kind"] == "bond":
            cpu = float(m.get("coupon_per_unit", 0))
            ppy = m.get("payments_per_year", 0)
            nxt = _d(m.get("next_coupon"))
            mat = _d(m.get("maturity"))
            if cpu and ppy and nxt and mat:
                step = _step(ppy)
                d = nxt
                while d < mat:
                    ev.append(_e(d, p["name"], "Купон", round(cpu * qty, 2), p["ticker"]))
                    d += relativedelta(months=step)
                ev.append(_e(mat, p["name"], "Купон", round(cpu * qty, 2), p["ticker"]))
                ev.append(_e(mat, p["name"], "Погашение", round(qty * (m.get("nominal") or p.get("nominal") or 1000), 2), p["ticker"]))
        elif p["kind"] == "deposit":
            open_d = _d(m.get("open_date")); close_d = _d(m.get("close_date"))
            eff = float(m.get("eff_rate", 0)); principal = float(m.get("principal", 0))
            if open_d and close_d and eff:
                mode = m.get("interest_mode")
                if mode == "simple":
                    interest = deposit_value_from_meta(m, close_d) - principal
                    ev.append(_e(close_d, p["name"], "Проценты", round(interest, 2), "ВКЛАД"))
                else:
                    period_start = open_d
                    period_number = 1
                    while period_start < close_d:
                        pay_d = _add_months(open_d, period_number)
                        period_end = min(pay_d, close_d)
                        interest = (
                            deposit_value_from_meta(m, period_end)
                            - deposit_value_from_meta(m, period_start)
                        )
                        ev.append(_e(period_end, p["name"], "Проценты", round(interest, 2), "ВКЛАД"))
                        period_start = period_end
                        period_number += 1
                ev.append(_e(close_d, p["name"], "Возврат вклада", round(principal, 2), "ВКЛАД"))
        elif p["kind"] == "share":
            dpy = float(m.get("div_per_unit", 0)); freq = int(m.get("div_per_year", 0))
            nxt = _d(m.get("next_div"))
            if dpy and freq and nxt:
                step = _step(freq); d = nxt
                for _ in range(freq * (months_ahead // 12 + 1)):
                    if d > horizon:
                        break
                    ev.append(_e(d, p["name"], "Дивиденд", round(dpy * qty, 2), p["ticker"]))
                    d += relativedelta(months=step)

    ev = [e for e in ev if (include_past or e["date"] >= today.isoformat()) and e["date"] <= horizon.isoformat()]
    ev.sort(key=lambda x: (x["date"], x["instrument"]))
    return ev


def _e(d, instrument, kind, amount, ticker):
    return {"date": d.isoformat(), "instrument": instrument, "type": kind,
            "amount": amount, "ticker": ticker}


def passive_income(db):
    """Годовой run-rate пассивного дохода по текущим позициям."""
    annual = 0.0
    detail = []
    for p in positions(db):
        m = p["meta"] or {}; qty = p["qty"]
        a = 0.0
        if p["kind"] == "bond" and qty > 0:
            a = float(m.get("coupon_per_unit", 0)) * int(m.get("payments_per_year", 0) or 0) * qty
        elif p["kind"] == "deposit":
            a = float(m.get("principal", 0)) * float(m.get("eff_rate", 0))
        elif p["kind"] == "share" and qty > 0:
            a = float(m.get("div_per_unit", 0)) * int(m.get("div_per_year", 0) or 0) * qty
        if a:
            detail.append({"name": p["name"], "annual": round(a, 2)})
            annual += a
    return {"annual": round(annual, 2), "monthly": round(annual / 12, 2), "detail": detail}
