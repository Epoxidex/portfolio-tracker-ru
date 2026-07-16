"""Синхронизация операций из T-Invest API → таблица transactions.

Использует постраничный GetOperationsByCursor и дедупликацию по note='op:<id>'.
Импортирует: buy, sell, coupon, dividend и внешние вводы/выводы денег.
Пропускает: налоги, комиссии (они уже внутри payment), service-операции.

Запуск: python -m app.cli sync-ops [--days N]
"""
from datetime import datetime, time, timezone, timedelta
from .. import config
from ..models import Instrument, Transaction
from .tinvest import find_or_create_instrument
from .tinvest_client import make_client

_KIND_MAP = {
    "OPERATION_TYPE_BUY":            "buy",
    "OPERATION_TYPE_BUY_CARD":       "buy",
    "OPERATION_TYPE_BUY_MARGIN":     "buy",
    "OPERATION_TYPE_DELIVERY_BUY":   "buy",
    "OPERATION_TYPE_SELL":           "sell",
    "OPERATION_TYPE_SELL_CARD":      "sell",
    "OPERATION_TYPE_SELL_MARGIN":    "sell",
    "OPERATION_TYPE_DELIVERY_SELL":  "sell",
    "OPERATION_TYPE_COUPON":         "coupon",
    "OPERATION_TYPE_DIVIDEND":       "dividend",
    "OPERATION_TYPE_INPUT":          "topup",
    "OPERATION_TYPE_OUTPUT":         "withdrawal",
    "OPERATION_TYPE_INPUT_SWIFT":    "topup",
    "OPERATION_TYPE_OUTPUT_SWIFT":   "withdrawal",
    "OPERATION_TYPE_INPUT_ACQUIRING": "topup",
    "OPERATION_TYPE_OUTPUT_ACQUIRING": "withdrawal",
    "OPERATION_TYPE_BOND_REPAYMENT": "sell",        # погашение = продажа по номиналу
    "OPERATION_TYPE_BOND_REPAYMENT_FULL": "sell",
}


def _q2f(q):
    if q is None:
        return 0.0
    try:
        return q.units + q.nano / 1e9
    except AttributeError:
        return float(q)


def sync_operations(db, days_back=365):
    """Подтягивает операции из T-Invest за последние days_back дней.

    Дубликаты определяются по note='op:<id>'.
    Уже засеянные транзакции (без такого note) не затрагиваются.
    """
    if not config.TINVEST_TOKEN:
        return {"ok": False, "error": "TINVEST_TOKEN не задан"}
    try:
        from t_tech.invest import GetOperationsByCursorRequest, OperationState
    except ImportError:
        return {"ok": False, "error": "pip install t-tech-investments (см. requirements.txt)"}

    # Уже импортированные op-id
    existing_ids = {
        tx.note.split(":", 1)[1]
        for tx in db.query(Transaction).filter(Transaction.note.like("op:%")).all()
    }

    # FIGI → Instrument
    instrument_map = {}
    for instrument in db.query(Instrument).all():
        if instrument.figi:
            instrument_map[instrument.figi] = instrument
        uid = (instrument.meta or {}).get("tinvest_uid")
        if uid:
            instrument_map[uid] = instrument

    imported, skipped = [], 0

    with make_client(config.TINVEST_TOKEN) as client:
        accounts = client.users.get_accounts().accounts
        acc_id = config.TINVEST_ACCOUNT_ID or (accounts[0].id if accounts else "")
        if not acc_id:
            return {"ok": False, "error": "нет счетов в T-Invest"}

        from_ = datetime.now(timezone.utc) - timedelta(days=days_back)
        if config.PORTFOLIO_TRACKING_START_DATE:
            configured_start = datetime.combine(
                config.PORTFOLIO_TRACKING_START_DATE,
                time.min,
                tzinfo=timezone.utc,
            )
            from_ = max(from_, configured_start)
        to = datetime.now(timezone.utc)

        try:
            ops = []
            cursor = ""
            seen_cursors = set()
            while True:
                response = client.operations.get_operations_by_cursor(
                    GetOperationsByCursorRequest(
                        account_id=acc_id,
                        from_=from_,
                        to=to,
                        cursor=cursor,
                        limit=1000,
                        state=OperationState.OPERATION_STATE_EXECUTED,
                        without_commissions=True,
                        without_trades=True,
                        without_overnights=True,
                    )
                )
                ops.extend(response.items)
                if not response.has_next:
                    break
                next_cursor = response.next_cursor
                if not next_cursor or next_cursor in seen_cursors:
                    raise RuntimeError("T-Invest вернул повторяющийся курсор операций")
                seen_cursors.add(next_cursor)
                cursor = next_cursor
        except Exception as e:
            return {"ok": False, "error": str(e)}

        for op in ops:
            op_id = op.id
            if op_id in existing_ids:
                skipped += 1
                continue

            operation_type = getattr(op, "operation_type", None) or getattr(op, "type", None)
            operation_name = getattr(operation_type, "name", str(operation_type or ""))
            kind = _KIND_MAP.get(operation_name)
            if kind is None:
                continue

            payment = _q2f(op.payment)
            if payment == 0:
                continue

            qty = abs(_q2f(getattr(op, "quantity_done", None) or getattr(op, "quantity", None)))
            price = _q2f(getattr(op, "price", None))
            commission = abs(_q2f(getattr(op, "commission", None)))
            figi = getattr(op, "figi", "") or ""
            instrument_uid = getattr(op, "instrument_uid", "") or ""
            instrument_ref = figi or instrument_uid
            inst = instrument_map.get(figi) or instrument_map.get(instrument_uid)
            if inst is None and instrument_ref:
                # Инструмента ещё нет в БД (новая покупка) или у операции
                # другой класс FIGI, чем у портфеля — резолвим/создаём.
                inst = find_or_create_instrument(client, instrument_ref, db)
                if inst is not None:
                    if figi:
                        instrument_map[figi] = inst
                    if instrument_uid:
                        instrument_map[instrument_uid] = inst
            if inst is not None:
                meta = dict(inst.meta or {})
                meta["source"] = "tinvest"
                if instrument_uid:
                    meta["tinvest_uid"] = instrument_uid
                inst.meta = meta
            op_date = op.date.date() if hasattr(op.date, "date") else op.date

            tx = Transaction(
                ts=op_date,
                instrument_id=inst.id if inst else None,
                kind=kind,
                quantity=round(qty, 4),
                price=round(price, 4),
                amount=round(payment, 2),
                commission=round(commission, 4),
                note=f"op:{op_id}",
            )
            db.add(tx)
            imported.append({
                "id": op_id,
                "date": op_date.isoformat(),
                "kind": kind,
                "name": inst.name if inst else (instrument_ref or "—"),
                "amount": round(payment, 2),
            })

    db.commit()
    return {
        "ok": True,
        "imported": len(imported),
        "skipped": skipped,
        "ops": imported,
        "tracking_start": (
            config.PORTFOLIO_TRACKING_START_DATE.isoformat()
            if config.PORTFOLIO_TRACKING_START_DATE else None
        ),
    }
