"""Safe, reusable operations for first-time portfolio setup."""

from __future__ import annotations

import math
from datetime import date

from sqlalchemy.orm import Session

from ..models import Instrument, Transaction
from . import portfolio


class SetupConflict(ValueError):
    """Raised when a setup command would silently duplicate existing data."""


def _positive_number(value: float, field: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return number


def create_deposit(
    db: Session,
    *,
    name: str,
    principal: float,
    open_date: date,
    close_date: date,
    annual_rate_pct: float,
    interest_mode: str = "simple",
) -> dict:
    """Create a deposit and its opening cash flow in one transaction."""
    name = name.strip()
    principal = _positive_number(principal, "principal")
    annual_rate_pct = float(annual_rate_pct)
    if not name:
        raise ValueError("name must not be empty")
    if close_date <= open_date:
        raise ValueError("close_date must be after open_date")
    if not math.isfinite(annual_rate_pct) or not 0 <= annual_rate_pct <= 100:
        raise ValueError("annual_rate_pct must be between 0 and 100")
    if interest_mode not in {"simple", "monthly_capitalization"}:
        raise ValueError("interest_mode must be simple or monthly_capitalization")

    for existing in db.query(Instrument).filter(Instrument.kind == "deposit").all():
        meta = existing.meta or {}
        if (
            existing.name.casefold() == name.casefold()
            and meta.get("open_date") == open_date.isoformat()
        ):
            raise SetupConflict(
                f"deposit {name!r} with opening date {open_date.isoformat()} already exists"
            )

    meta = {
        "principal": principal,
        "open_date": open_date.isoformat(),
        "close_date": close_date.isoformat(),
        "eff_rate": annual_rate_pct / 100,
        "interest_mode": interest_mode,
    }
    inst = Instrument(kind="deposit", name=name, currency="RUB", meta=meta)
    try:
        db.add(inst)
        db.flush()
        db.add(Transaction(
            ts=open_date,
            instrument_id=inst.id,
            kind="buy",
            quantity=1,
            amount=-principal,
            note="deposit opened",
        ))
        db.flush()
        estimate = portfolio.deposit_value(inst, close_date) - principal
        db.commit()
        db.refresh(inst)
    except Exception:
        db.rollback()
        raise
    return {
        "ok": True,
        "id": inst.id,
        "estimated_interest": round(estimate, 2),
    }


def add_currency_holding(
    db: Session,
    *,
    code: str,
    quantity: float,
    invested_rub: float,
    acquired_on: date,
    name: str = "",
    rate_rub_per_unit: float | None = None,
    append: bool = False,
) -> dict:
    """Create or explicitly append a manual non-ruble currency holding."""
    code = code.strip().upper()
    if len(code) != 3 or not code.isascii() or not code.isalpha():
        raise ValueError("code must be a three-letter ISO-style currency code")
    if code == "RUB":
        raise ValueError("manual RUB cash is managed by the T-Invest balance import")
    quantity = _positive_number(quantity, "quantity")
    invested_rub = _positive_number(invested_rub, "invested_rub")
    if rate_rub_per_unit is not None:
        rate_rub_per_unit = _positive_number(rate_rub_per_unit, "rate_rub_per_unit")

    inst = (
        db.query(Instrument)
        .filter(Instrument.kind == "currency", Instrument.currency == code)
        .first()
    )
    if inst and inst.transactions and not append:
        raise SetupConflict(
            f"{code} already has transactions; pass append=True only for an additional purchase"
        )

    purchase_rate = invested_rub / quantity
    try:
        if inst is None:
            inst = Instrument(
                kind="currency",
                name=name.strip() or f"{code} cash",
                ticker=code,
                currency=code,
                last_price=rate_rub_per_unit or purchase_rate,
                meta={"manual": True},
            )
            db.add(inst)
            db.flush()
        else:
            if name.strip():
                inst.name = name.strip()
            if rate_rub_per_unit is not None or not inst.last_price:
                inst.last_price = rate_rub_per_unit or purchase_rate

        db.add(Transaction(
            ts=acquired_on,
            instrument_id=inst.id,
            kind="fx_buy",
            quantity=quantity,
            price=purchase_rate,
            amount=-invested_rub,
            note="manual currency opening balance" if not append else "manual currency purchase",
        ))
        db.commit()
        db.refresh(inst)
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "id": inst.id,
        "code": code,
        "quantity": quantity,
        "invested_rub": invested_rub,
        "current_rate": inst.last_price,
    }
