"""T-Invest API: обновление цен бумаг и авторезолв FIGI.

get_portfolio → current_price уже в рублях (используем напрямую).
get_last_prices → цена в % номинала, поэтому price/100*nominal.
НКД из get_portfolio: current_nkd = рубли на одну бумагу.

Запуск: python -m app.cli fetch-prices
"""
from datetime import datetime, timezone
from .. import config
from ..models import Instrument, PriceHistory
from .tinvest_client import make_client


def _q2f(q):
    """Quotation/MoneyValue → float; None → 0.0."""
    if q is None:
        return 0.0
    try:
        return q.units + q.nano / 1e9
    except AttributeError:
        return float(q)


def _resolve_figis(client, insts, db):
    """Находит FIGI по ISIN или тикеру для инструментов без FIGI и сохраняет в БД."""
    need = [i for i in insts if not i.figi]
    if not need:
        return
    for inst in need:
        query = inst.isin or (inst.ticker.rstrip("@") if inst.ticker else "")
        if not query:
            continue
        try:
            res = client.instruments.find_instrument(query=query)
        except Exception as e:
            print(f"  FIGI search failed for {inst.name!r}: {e}")
            continue

        candidates = []
        for item in res.instruments:
            item_isin = getattr(item, "isin", "")
            item_ticker = getattr(item, "ticker", "")
            clean_ticker = inst.ticker.rstrip("@") if inst.ticker else ""
            if (inst.isin and item_isin == inst.isin) \
                    or (inst.isin and item_ticker == inst.isin) \
                    or (clean_ticker and item_ticker == clean_ticker):
                candidates.append(item.figi)
        # Предпочитаем TCS00… (основной класс инструмента), иначе первый кандидат
        figi = next((f for f in candidates if f.startswith("TCS00")), None) \
               or (candidates[0] if candidates else None)
        if not figi and len(res.instruments) == 1:
            figi = res.instruments[0].figi

        if figi:
            print(f"  FIGI resolved: {inst.name!r} -> {figi}")
            inst.figi = figi
    db.commit()


_SKIP_FIGI_PREFIX = ("EUR0",)          # не создавать инструменты для EUR-кэша

_TINVEST_KIND = {
    "bond": "bond", "share": "share", "etf": "etf",
    "INSTRUMENT_TYPE_BOND": "bond", "INSTRUMENT_TYPE_SHARE": "share",
    "INSTRUMENT_TYPE_ETF": "etf",
}


def _kind_from_item(item):
    """instrument_kind (enum или строка) → 'bond'|'share'|'etf'; None для валют/фьючерсов и пр."""
    raw = getattr(item, "instrument_kind", None)
    raw = getattr(raw, "name", None) or str(raw or "")
    raw = raw.rsplit(".", 1)[-1]
    return _TINVEST_KIND.get(raw) or _TINVEST_KIND.get(raw.lower())


def _mark_tinvest(inst, uid=""):
    meta = dict(inst.meta or {})
    meta["source"] = "tinvest"
    if uid:
        meta["tinvest_uid"] = uid
    inst.meta = meta


def find_or_create_instrument(client, figi, db):
    """FIGI операции → Instrument: точное совпадение, затем по ISIN/тикеру/имени
    (у операций и портфеля классы FIGI могут различаться: TCS00… vs TCS60…),
    иначе создаёт новый инструмент."""
    if not figi or figi == "RUB000UTSTOM" \
            or any(figi.startswith(p) for p in _SKIP_FIGI_PREFIX):
        return None
    inst = db.query(Instrument).filter(Instrument.figi == figi).first()
    if inst:
        _mark_tinvest(inst)
        return inst
    try:
        res = client.instruments.find_instrument(query=figi)
    except Exception as e:
        print(f"  FIGI lookup failed for {figi!r}: {e}")
        return None
    item = next((x for x in res.instruments if x.figi == figi), None) \
           or (res.instruments[0] if res.instruments else None)
    if not item:
        return None

    isin = getattr(item, "isin", "") or ""
    ticker = (getattr(item, "ticker", "") or "").rstrip("@")
    name = getattr(item, "name", "") or ""
    uid = getattr(item, "uid", "") or getattr(item, "instrument_uid", "") or ""
    for cand in db.query(Instrument).all():
        if (isin and cand.isin == isin) \
                or (ticker and (cand.ticker or "").rstrip("@") == ticker) \
                or (name and cand.name.lower() == name.lower()):
            _mark_tinvest(cand, uid)
            if getattr(item, "figi", ""):
                cand.figi = item.figi
            return cand

    kind = _kind_from_item(item)
    if kind is None:
        return None
    inst = Instrument(
        kind=kind, name=name or figi,
        ticker=getattr(item, "ticker", "") or "",
        isin=isin, figi=figi, currency="RUB",
        nominal=1000.0 if kind == "bond" else 0.0,
        meta={"source": "tinvest", "tinvest_uid": uid} if uid else {"source": "tinvest"},
    )
    db.add(inst)
    db.flush()
    print(f"  Auto-created from operation: {kind} {inst.name!r} ({figi})")
    return inst


def _auto_create(client, portfolio_positions, db):
    """Создаёт Instrument для позиций портфеля, которых ещё нет в БД.

    Проверяет и по ФИГИ, и по имени — чтобы не дублировать ETF/фонды,
    у которых в портфеле другой класс ФИГИ (TCS80… vs TCSM…).
    При совпадении по имени обновляет ФИГИ существующего инструмента.
    """
    all_insts = db.query(Instrument).all()
    existing_figis = {i.figi for i in all_insts if i.figi}
    existing_names = {i.name.lower(): i for i in all_insts}
    created = []

    for pos in portfolio_positions:
        figi = pos.figi
        if not figi or figi in existing_figis:
            continue
        if any(figi.startswith(p) for p in _SKIP_FIGI_PREFIX):
            continue
        try:
            res = client.instruments.find_instrument(query=figi)
        except Exception:
            continue
        item = next((x for x in res.instruments if x.figi == figi), None)
        if not item and res.instruments:
            item = res.instruments[0]
        if not item:
            continue

        item_name = item.name or figi
        # Если инструмент с таким именем уже есть — только обновляем ФИГИ
        existing = existing_names.get(item_name.lower())
        if existing:
            print(f"  Updated FIGI for {existing.name!r}: {existing.figi!r} -> {figi!r}")
            existing.figi = figi
            _mark_tinvest(
                existing,
                getattr(item, "uid", "") or getattr(item, "instrument_uid", "") or "",
            )
            existing_figis.add(figi)
            continue

        kind = _kind_from_item(item)
        if kind is None:          # валюта/фьючерс и пр. — не создаём
            continue
        inst = Instrument(
            kind=kind, name=item_name,
            ticker=getattr(item, "ticker", "") or "",
            isin=getattr(item, "isin", "") or "",
            figi=figi, currency="RUB",
            nominal=1000.0 if kind == "bond" else 0.0,
            meta={
                "source": "tinvest",
                "tinvest_uid": (
                    getattr(item, "uid", "")
                    or getattr(item, "instrument_uid", "")
                    or ""
                ),
            },
        )
        db.add(inst)
        existing_figis.add(figi)
        existing_names[item_name.lower()] = inst
        created.append(item_name)
        print(f"  Auto-created: {kind} {item_name!r} ({figi})")

    db.commit()
    return created


def _sync_portfolio_state(db, insts, portfolio_by_figi):
    """Persist broker-authoritative current quantities for T-Invest securities."""
    synced_at = datetime.now(timezone.utc).isoformat()
    for inst in insts:
        current = portfolio_by_figi.get(inst.figi)
        imported = any((tx.note or "").startswith("op:") for tx in inst.transactions)
        meta = dict(inst.meta or {})
        if current is not None:
            meta.update({
                "source": "tinvest",
                "tinvest_position_synced": True,
                "tinvest_position_synced_at": synced_at,
                "tinvest_current_quantity": round(_q2f(current.quantity), 8),
                "tinvest_average_price": round(
                    _q2f(getattr(current, "average_position_price", None)), 8
                ),
                "tinvest_expected_yield": round(
                    _q2f(getattr(current, "expected_yield", None)), 8
                ),
            })
            inst.meta = meta
        elif meta.get("source") == "tinvest" or imported:
            meta.update({
                "source": "tinvest",
                "tinvest_position_synced": True,
                "tinvest_position_synced_at": synced_at,
                "tinvest_current_quantity": 0.0,
                "tinvest_average_price": 0.0,
                "tinvest_expected_yield": 0.0,
            })
            inst.meta = meta
    db.commit()


def _save_price_history(db, insts_updated):
    """Записывает текущую цену в price_history для каждого обновлённого инструмента."""
    now = datetime.utcnow()
    for inst in insts_updated:
        if inst.last_price:
            db.add(PriceHistory(instrument_id=inst.id, ts=now, price=inst.last_price))
    db.commit()


def fetch_prices(db):
    if not config.TINVEST_TOKEN:
        return {"ok": False, "error": "TINVEST_TOKEN не задан"}
    try:
        import t_tech.invest  # noqa: F401
    except ImportError:
        return {"ok": False, "error": "pip install t-tech-investments (см. requirements.txt)"}

    insts = [i for i in db.query(Instrument).all() if i.kind in ("bond", "share", "etf")]
    updated = []
    updated_objs = []
    warnings = []

    with make_client(config.TINVEST_TOKEN) as client:
        accounts = client.users.get_accounts().accounts
        acc_id = config.TINVEST_ACCOUNT_ID or (accounts[0].id if accounts else "")
        if not acc_id:
            return {"ok": False, "error": "нет счетов в T-Invest"}

        # 2. Портфель — цены и НКД
        portfolio_positions = []
        portfolio_by_figi = {}
        portfolio_loaded = False
        try:
            pf = client.operations.get_portfolio(account_id=acc_id)
            portfolio_positions = list(pf.positions)
            portfolio_by_figi = {p.figi: p for p in portfolio_positions}
            portfolio_loaded = True
        except Exception as e:
            warnings.append(f"get_portfolio: {e}")

        # 1. Авто-создание новых инструментов из портфеля
        if portfolio_loaded:
            _auto_create(client, portfolio_positions, db)
        # Перезагружаем список (могли добавиться новые)
        insts = [i for i in db.query(Instrument).all() if i.kind in ("bond", "share", "etf")]

        # 3. Резолв FIGI для инструментов без него
        _resolve_figis(client, insts, db)
        if portfolio_loaded:
            _sync_portfolio_state(db, insts, portfolio_by_figi)

        for inst in insts:
            if not inst.figi or inst.figi not in portfolio_by_figi:
                continue
            pos = portfolio_by_figi[inst.figi]
            inst.last_price = round(_q2f(pos.current_price), 4)
            if inst.kind == "bond":
                nkd = _q2f(getattr(pos, "current_nkd", None))
                if nkd:
                    inst.nkd = round(nkd, 4)
            inst.price_updated_at = datetime.utcnow()
            updated.append(inst.name)
            updated_objs.append(inst)

        # 4. Остальные с FIGI — через get_last_prices
        need_price = [
            i for i in insts
            if i.figi
            and i.name not in updated
            and not (
                (i.meta or {}).get("tinvest_position_synced")
                and float((i.meta or {}).get("tinvest_current_quantity", 0)) <= 0
            )
        ]
        if need_price:
            try:
                lp_resp = client.market_data.get_last_prices(
                    figi=[i.figi for i in need_price]
                )
                price_map = {x.figi: _q2f(x.price) for x in lp_resp.last_prices}
                for inst in need_price:
                    raw = price_map.get(inst.figi)
                    if raw is None or raw == 0:
                        continue
                    if inst.kind == "bond" and inst.nominal:
                        raw = raw / 100 * inst.nominal
                    inst.last_price = round(raw, 4)
                    inst.price_updated_at = datetime.utcnow()
                    updated.append(inst.name)
                    updated_objs.append(inst)
            except Exception as e:
                warnings.append(f"get_last_prices: {e}")

    # 5. Рублёвый баланс из портфеля (RUB000UTSTOM)
    if portfolio_loaded:
        _sync_rub_balance(client, portfolio_positions, db, acc_id)

    db.commit()
    _save_price_history(db, updated_objs)

    result: dict = {"ok": True, "updated": updated}
    if warnings:
        result["warnings"] = warnings
    return result


def _sync_rub_balance(client, portfolio_positions, db, acc_id):
    """Обновляет баланс рублей в T-Invest (RUB000UTSTOM) → инструмент 'Рубли (RUB)'."""
    rub_pos = next((p for p in portfolio_positions if p.figi == "RUB000UTSTOM"), None)
    if not rub_pos:
        return
    balance = round(_q2f(rub_pos.quantity), 2)

    rub_inst = db.query(Instrument).filter(
        Instrument.figi == "RUB000UTSTOM"
    ).first()
    if not rub_inst:
        rub_inst = db.query(Instrument).filter(
            Instrument.kind == "currency", Instrument.currency == "RUB"
        ).order_by(Instrument.id).first()
    if not rub_inst:
        rub_inst = Instrument(
            kind="currency", name="Рубли (RUB)", currency="RUB",
            ticker="RUB", figi="RUB000UTSTOM", last_price=1.0,
            meta={"balance": balance, "broker_balance": balance},
        )
        db.add(rub_inst)
        print(f"  Created: Рубли (RUB), balance={balance}")
    else:
        meta = dict(rub_inst.meta or {})
        meta["balance"] = balance
        meta["broker_balance"] = balance
        rub_inst.meta = meta
        rub_inst.figi = "RUB000UTSTOM"
        rub_inst.ticker = rub_inst.ticker or "RUB"
    db.commit()
