"""Tracking-window configuration and safe cleanup of imported history."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Instrument, PriceHistory, Snapshot, Transaction


_SECURITY_KINDS = {"bond", "share", "etf"}


def _is_imported(tx: Transaction) -> bool:
    return (tx.note or "").startswith("op:")


def preview_tracking_cleanup(db: Session, start_date: date) -> dict:
    """Describe the rows that a tracking-window reset would remove."""
    old_imported = [
        tx for tx in db.query(Transaction).all()
        if _is_imported(tx) and tx.ts < start_date
    ]
    removable_instruments = []
    for inst in db.query(Instrument).all():
        txs = list(inst.transactions)
        meta = inst.meta or {}
        broker_confirms_current = (
            meta.get("tinvest_position_synced")
            and float(meta.get("tinvest_current_quantity", 0) or 0) > 0
        )
        if (
            inst.kind in _SECURITY_KINDS
            and txs
            and not broker_confirms_current
            and all(_is_imported(tx) and tx.ts < start_date for tx in txs)
        ):
            removable_instruments.append(inst)

    removed_names = {inst.name for inst in removable_instruments}
    tainted_snapshots = []
    for snapshot in db.query(Snapshot).all():
        snapshot_day = (
            (snapshot.ts + timedelta(hours=3)).date() if snapshot.ts else start_date
        )
        names = set((snapshot.by_instrument or {}).keys())
        if snapshot_day < start_date or names.intersection(removed_names):
            tainted_snapshots.append(snapshot)

    return {
        "start_date": start_date.isoformat(),
        "imported_transactions": len(old_imported),
        "instruments": len(removable_instruments),
        "instrument_ids": [inst.id for inst in removable_instruments],
        "instrument_names": sorted(removed_names),
        "snapshots": len(tainted_snapshots),
        "snapshot_ids": [snapshot.id for snapshot in tainted_snapshots],
    }


def apply_tracking_cleanup(db: Session, start_date: date) -> dict:
    """Delete pre-window broker imports and snapshots made from phantom assets."""
    preview = preview_tracking_cleanup(db, start_date)
    instrument_ids = preview.pop("instrument_ids")
    snapshot_ids = preview.pop("snapshot_ids")

    try:
        old_imported_ids = [
            tx.id for tx in db.query(Transaction).all()
            if _is_imported(tx) and tx.ts < start_date
        ]

        if instrument_ids:
            db.query(PriceHistory).filter(
                PriceHistory.instrument_id.in_(instrument_ids)
            ).delete(synchronize_session=False)
            for inst in db.query(Instrument).filter(Instrument.id.in_(instrument_ids)).all():
                db.delete(inst)
            db.flush()

        if old_imported_ids:
            db.query(Transaction).filter(Transaction.id.in_(old_imported_ids)).delete(
                synchronize_session=False
            )

        if snapshot_ids:
            db.query(Snapshot).filter(Snapshot.id.in_(snapshot_ids)).delete(
                synchronize_session=False
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    preview["ok"] = True
    return preview


def update_env_setting(path: Path, key: str, value: str) -> None:
    """Atomically update one .env key without exposing or replacing other values."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    replaced = False
    output = []
    for line in lines:
        if line.strip().startswith(prefix):
            output.append(prefix + value)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append(prefix + value)

    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temp.write_text("\n".join(output) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
