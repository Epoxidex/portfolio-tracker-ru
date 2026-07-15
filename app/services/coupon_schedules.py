"""Exact user-supplied bond coupon schedules."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import MutationRequest, Transaction
from .read_model import resolve_instrument


class CouponScheduleConflict(ValueError):
    """The schedule mutation conflicts with existing portfolio state."""


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,79}$")


def _request_id(value: str) -> str:
    value = value.strip()
    if not _REQUEST_ID.fullmatch(value):
        raise ValueError(
            "request_id must be 8-80 characters using letters, digits, "
            "dot, colon, underscore or dash"
        )
    return value


def _day(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return number


def _normalize_payments(payments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(payments) > 500:
        raise ValueError("payments cannot contain more than 500 coupon dates")
    normalized: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(payments):
        if not isinstance(raw, dict):
            raise ValueError(f"payments[{index}] must be an object")
        payment_date = _day(raw.get("payment_date"), f"payments[{index}].payment_date")
        amount = _positive(
            raw.get("coupon_per_unit_rub"),
            f"payments[{index}].coupon_per_unit_rub",
        )
        key = payment_date.isoformat()
        if key in normalized:
            raise ValueError(f"duplicate coupon payment date: {key}")
        normalized[key] = {
            "payment_date": key,
            "coupon_per_unit_rub": round(amount, 8),
        }
    return [normalized[key] for key in sorted(normalized)]


def set_coupon_schedule(
    db: Session,
    *,
    request_id: str,
    instrument: str | int,
    payments: list[dict[str, Any]],
    mode: str = "replace",
    maturity_date: str | date | None = None,
    nominal_per_unit_rub: float | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Replace or upsert an exact RUB coupon schedule as one idempotent mutation."""
    request_id = _request_id(request_id)
    previous = db.get(MutationRequest, request_id)
    if previous:
        if previous.action_type != "set_bond_coupon_schedule":
            raise CouponScheduleConflict(
                f"request_id {request_id!r} was already used for {previous.action_type}"
            )
        result = dict(previous.result or {})
        result["already_applied"] = True
        return result
    audit_prefix = f"audit:{request_id}:"
    if db.query(Transaction).filter(Transaction.note.like(audit_prefix + "%")).first():
        raise CouponScheduleConflict(
            f"request_id {request_id!r} was already used for a portfolio action"
        )
    if mode not in {"replace", "upsert"}:
        raise ValueError("mode must be replace or upsert")

    bond = resolve_instrument(db, instrument)
    if not bond or bond.kind != "bond":
        raise ValueError(f"bond not found: {instrument}")
    incoming = _normalize_payments(payments)
    if mode == "upsert" and not incoming:
        raise ValueError("upsert requires at least one coupon payment")

    meta = dict(bond.meta or {})
    if mode == "upsert":
        existing = _normalize_payments(list(meta.get("coupon_schedule") or []))
        by_date = {row["payment_date"]: row for row in existing}
        by_date.update({row["payment_date"]: row for row in incoming})
        schedule = [by_date[key] for key in sorted(by_date)]
    else:
        schedule = incoming

    maturity = _day(maturity_date, "maturity_date") if maturity_date is not None else None
    if maturity and schedule and schedule[-1]["payment_date"] > maturity.isoformat():
        raise ValueError("coupon payment date cannot be later than maturity_date")
    nominal = (
        _positive(nominal_per_unit_rub, "nominal_per_unit_rub")
        if nominal_per_unit_rub is not None else None
    )

    meta["coupon_schedule"] = schedule
    meta["coupon_schedule_source"] = "manual"
    meta["coupon_schedule_updated_at"] = datetime.now(timezone.utc).isoformat()
    meta["coupon_schedule_request_id"] = request_id
    clean_note = " ".join(note.strip().split())[:200]
    if clean_note:
        meta["coupon_schedule_note"] = clean_note
    else:
        meta.pop("coupon_schedule_note", None)
    if maturity:
        meta["maturity"] = maturity.isoformat()
    if nominal is not None:
        bond.nominal = round(nominal, 8)
        meta["nominal"] = round(nominal, 8)
    bond.meta = meta

    result = {
        "ok": True,
        "already_applied": False,
        "request_id": request_id,
        "instrument_id": bond.id,
        "instrument": bond.name,
        "ticker": bond.ticker,
        "mode": mode,
        "coupon_count": len(schedule),
        "first_payment_date": schedule[0]["payment_date"] if schedule else None,
        "last_payment_date": schedule[-1]["payment_date"] if schedule else None,
        "maturity_date": meta.get("maturity"),
        "nominal_per_unit_rub": bond.nominal,
    }
    db.add(MutationRequest(
        request_id=request_id,
        action_type="set_bond_coupon_schedule",
        result=result,
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result
