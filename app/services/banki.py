"""Курсы валют (CNY/USD) с bankiros.ru + официальный курс ЦБ РФ.

Страница bankiros.ru/bank/<slug>/currency содержит 4 таблицы:
  0 — курс банка (2 столбца с ценами)
  1 — официальный курс ЦБ РФ
  2 — курс МосБиржи (обычно прочерки)
  3 — лучшие курсы среди банков Москвы

Логика: max(col1, col2) = bank_sell (что банк берёт с клиента),
         min(col1, col2) = bank_buy  (что банк платит клиенту).
Пользователь продаёт валюту → получает bank_buy.

fetch_fx(db, source) обновляет last_price валютных позиций.
source: "bank_buy" | "bank_sell" | "cbr" (default из config.FX_RATE_SOURCE).
"""
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
from .. import config
from ..models import Instrument, PriceHistory

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

# Порядок валют в таблицах bankiros.ru (Table 0, 1, 2, 3 — все одинаковые строки)
_ROW_ORDER = ["USD", "EUR", "CNY", "GBP", "CHF", "TRY", "AED"]


def _num(s):
    """Извлекает первое вещественное число из строки вида '77.0611+1.4264'."""
    m = re.search(r"\d+[.,]\d+", str(s).replace(",", "."))
    return float(m.group().replace(",", ".")) if m else None


def _fetch_bankiros():
    """Возвращает {currency: {"buy": float, "sell": float}} из bankiros.ru."""
    try:
        r = requests.get(config.BANKIROS_URL, headers=_HEADERS, timeout=20)
        r.encoding = "utf-8"
        r.raise_for_status()
    except Exception as e:
        return {}, f"bankiros.ru недоступен: {e}"

    soup = BeautifulSoup(r.text, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return {}, "таблицы не найдены"

    # Table 0: курс банка.
    # Строки: [currency_code, value1, value2]
    result = {}
    table = tables[0]
    for row in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
        if len(cells) < 3:
            continue
        code = cells[0].upper()
        # Нормализуем: "10 TRY" → "TRY"
        code = code.split()[-1] if " " in code else code
        if code not in ("USD", "EUR", "CNY", "GBP", "CHF", "TRY", "AED"):
            continue
        v1, v2 = _num(cells[1]), _num(cells[2])
        if v1 is None or v2 is None:
            continue
        result[code] = {
            "bank_buy":  round(min(v1, v2), 4),   # bank платит клиенту (клиент продаёт)
            "bank_sell": round(max(v1, v2), 4),   # bank берёт с клиента (клиент покупает)
        }

    return result, None


def _fetch_cbr():
    """Возвращает {currency: rate} с официального курса ЦБ РФ."""
    try:
        r = requests.get("https://www.cbr.ru/scripts/XML_daily.asp", timeout=10)
        root = ET.fromstring(r.content)
    except Exception as e:
        return {}, f"cbr.ru: {e}"

    rates = {}
    for v in root.findall("Valute"):
        code = v.find("CharCode").text
        val_text = v.find("Value").text.replace(",", ".")
        nom = int(v.find("Nominal").text)
        rates[code] = round(float(val_text) / nom, 4)
    return rates, None


def _bank_name() -> str:
    """Извлекает название банка из BANKIROS_URL для отображения в UI."""
    import re as _re
    m = _re.search(r"/bank/([^/]+)/", config.BANKIROS_URL)
    slug = m.group(1) if m else ""
    _MAP = {"kamkombank": "Камкомбанк", "sberbank": "Сбербанк",
            "vtb": "ВТБ", "alfabank": "Альфа-Банк", "tinkoff": "Т-Банк"}
    return _MAP.get(slug, slug)


def fetch_fx(db, source: str | None = None):
    """Обновляет last_price валютных позиций.

    source: "bank_buy" | "bank_sell" | "cbr" — переопределяет config.FX_RATE_SOURCE.
    """
    source = source or config.FX_RATE_SOURCE

    if source == "cbr":
        bank_rates, bank_err = {}, None
        cbr_rates, cbr_err = _fetch_cbr()
        if cbr_err:
            return {"ok": False, "error": cbr_err, "source": source}
    else:
        bank_rates, bank_err = _fetch_bankiros()
        cbr_rates, cbr_err = {}, None
        if bank_err:
            return {"ok": False, "error": bank_err, "source": source}

    # Объединяем в один словарь со всеми источниками
    all_rates: dict[str, dict] = {}
    for code in set(list(bank_rates.keys()) + list(cbr_rates.keys())):
        all_rates[code] = {
            "bank_buy":  bank_rates.get(code, {}).get("bank_buy"),
            "bank_sell": bank_rates.get(code, {}).get("bank_sell"),
            "cbr":       cbr_rates.get(code),
        }

    updated = {}
    for inst in db.query(Instrument).filter(Instrument.kind == "currency").all():
        code = inst.currency.upper()
        r = all_rates.get(code)
        if not r:
            continue
        price = r.get(source)
        if price:
            inst.last_price = price
            inst.price_updated_at = datetime.utcnow()
            updated[code] = price

    db.commit()

    # Пишем историю цен для валютных позиций
    now = datetime.utcnow()
    for inst in db.query(Instrument).filter(Instrument.kind == "currency").all():
        if inst.last_price:
            db.add(PriceHistory(instrument_id=inst.id, ts=now, price=inst.last_price))
    db.commit()

    source_label = {"bank_buy": f"{_bank_name()} — покупает у вас",
                    "bank_sell": f"{_bank_name()} — продаёт вам",
                    "cbr": "ЦБ РФ (официальный)"}.get(source, source)
    result: dict = {"ok": True, "source": source, "source_label": source_label,
                    "bank": _bank_name(), "rates": all_rates, "updated": updated}
    return result
