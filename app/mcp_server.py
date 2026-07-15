"""Local Model Context Protocol server for Portfolio Tracker."""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import config
from .dataio import DATABASE_MAINTENANCE_LOCK
from .db import SessionLocal
from .services import calendar as cal
from .services import ledger, portfolio, read_model, snapshots
from .services.operations import sync_operations
from .services.tinvest import fetch_prices


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
SYNC = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

mcp = FastMCP(
    "Portfolio Tracker RU",
    instructions=(
        "Локальный доступ к личному портфелю. Денежные значения — RUB, если не указано иначе. "
        "Write-tools вызывайте только после явного указания пользователя внести конкретную операцию; "
        "для гипотетических вопросов используйте только read-tools. Всегда передавайте новый request_id "
        "и confirm=true. Несколько связанных действий выполняйте одним apply_portfolio_actions: пакет "
        "атомарный и повтор с тем же request_id безопасен. Сделки T-Invest нельзя вносить вручную — "
        "используйте synchronize_tinvest. Это не брокерский, налоговый или инвестиционный совет."
    ),
)


def _methodology_text() -> str:
    path = Path(__file__).resolve().parent.parent / "docs" / "CALCULATIONS.md"
    return path.read_text(encoding="utf-8")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _write_actions(
    *,
    request_id: str,
    actions: list[dict[str, Any]],
    confirm: bool,
    create_snapshot: bool = True,
) -> dict[str, Any]:
    if confirm is not True:
        raise ValueError("confirm=true is required after explicit user approval")
    with DATABASE_MAINTENANCE_LOCK:
        with SessionLocal() as db:
            return ledger.apply_actions(
                db,
                request_id=request_id,
                actions=actions,
                create_snapshot=create_snapshot,
            )


@mcp.tool(annotations=READ_ONLY)
def get_data_status() -> dict[str, Any]:
    """Проверить готовность данных и безопасные настройки без токенов, ID счёта и путей."""
    with SessionLocal() as db:
        return read_model.data_status(db)


@mcp.tool(annotations=READ_ONLY)
def get_portfolio_overview() -> dict[str, Any]:
    """Получить полную текущую сводку: стоимость, вложения, P&L, XIRR, классы и позиции."""
    with SessionLocal() as db:
        result = portfolio.summary(db)
        goal = float(config.PORTFOLIO_GOAL)
        result["goal"] = {
            "target": goal,
            "remaining": round(max(0.0, goal - result["value"]), 2),
            "progress": round(result["value"] / goal, 6) if goal else None,
        }
        return result


@mcp.tool(annotations=READ_ONLY)
def list_positions(
    kind: str | None = None,
    query: str | None = None,
    sort_by: str = "value",
    descending: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """Получить активные позиции с фильтрацией и пагинацией.

    kind: bond, share, etf, currency или deposit.
    sort_by: name, kind, qty, invested, value, income, pnl или pnl_pct.
    """
    with SessionLocal() as db:
        return read_model.list_positions(
            db, kind=kind, query=query, sort_by=sort_by,
            descending=descending, limit=limit, offset=offset,
        )


@mcp.tool(annotations=READ_ONLY)
def list_instruments(
    kind: str | None = None,
    query: str | None = None,
    active_only: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """Получить справочник инструментов, включая закрытые позиции и полные метаданные."""
    with SessionLocal() as db:
        return read_model.list_instruments(
            db, kind=kind, query=query, active_only=active_only,
            limit=limit, offset=offset,
        )


@mcp.tool(annotations=READ_ONLY)
def get_instrument(
    identifier: str,
    transaction_limit: int = 100,
    price_limit: int = 200,
) -> dict[str, Any]:
    """Получить карточку инструмента, позицию, операции и цены.

    identifier принимает id, id:<номер>, тикер, ISIN, FIGI или точное название.
    """
    with SessionLocal() as db:
        return read_model.instrument_details(
            db, identifier, transaction_limit=transaction_limit, price_limit=price_limit,
        )


@mcp.tool(annotations=READ_ONLY)
def list_transactions(
    date_from: str | None = None,
    date_to: str | None = None,
    kind: str | None = None,
    instrument: str | None = None,
    query: str | None = None,
    descending: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """Получить денежные потоки и операции с точными фильтрами.

    Даты задаются как YYYY-MM-DD. kind: buy, sell, coupon, dividend, interest,
    fx_buy или fx_sell. instrument принимает те же идентификаторы, что get_instrument.
    """
    with SessionLocal() as db:
        return read_model.list_transactions(
            db, date_from=date_from, date_to=date_to, kind=kind,
            instrument=instrument, query=query, descending=descending,
            limit=limit, offset=offset,
        )


@mcp.tool(annotations=READ_ONLY)
def get_portfolio_history(
    date_from: str | None = None,
    date_to: str | None = None,
    granularity: str = "daily",
    limit: int = 2000,
) -> dict[str, Any]:
    """Получить историю снимков портфеля.

    granularity=daily возвращает последний снимок московского дня,
    granularity=raw возвращает все сохранённые снимки.
    """
    with SessionLocal() as db:
        return read_model.portfolio_history(
            db, date_from=date_from, date_to=date_to,
            granularity=granularity, limit=limit,
        )


@mcp.tool(annotations=READ_ONLY)
def get_price_history(
    instrument: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    days: int | None = 90,
    limit_per_instrument: int = 2000,
) -> dict[str, Any]:
    """Получить историю цен одного или всех инструментов.

    Явный date_from имеет приоритет над относительным окном days.
    """
    with SessionLocal() as db:
        return read_model.price_history(
            db, instrument=instrument, date_from=date_from, date_to=date_to,
            days=days, limit_per_instrument=limit_per_instrument,
        )


@mcp.tool(annotations=READ_ONLY)
def get_returns(period: str = "monthly") -> dict[str, Any]:
    """Получить скорректированную на покупки/продажи доходность.

    period: daily, monthly или yearly. Ответ также содержит day/week/month/YTD.
    """
    if period not in {"daily", "monthly", "yearly"}:
        raise ValueError("period must be daily, monthly or yearly")
    with SessionLocal() as db:
        return snapshots.compute_returns(db, period=period)


@mcp.tool(annotations=READ_ONLY)
def get_change_leaders(period: str = "day") -> dict[str, Any]:
    """Получить вклад инструментов в изменение портфеля за day, week или month."""
    if period not in {"day", "week", "month"}:
        raise ValueError("period must be day, week or month")
    with SessionLocal() as db:
        return snapshots.compute_leaders(db, period=period)


@mcp.tool(annotations=READ_ONLY)
def get_payment_calendar(months_ahead: int = 24, include_past: bool = False) -> dict[str, Any]:
    """Получить купоны, дивиденды, проценты и погашения на горизонте до 120 месяцев."""
    if months_ahead < 1 or months_ahead > 120:
        raise ValueError("months_ahead must be between 1 and 120")
    with SessionLocal() as db:
        items = cal.calendar(db, months_ahead=months_ahead, include_past=include_past)
        return {"items": items, "returned": len(items), "months_ahead": months_ahead}


@mcp.tool(annotations=READ_ONLY)
def get_passive_income() -> dict[str, Any]:
    """Получить оценочный годовой и среднемесячный пассивный доход по текущим позициям."""
    with SessionLocal() as db:
        return cal.passive_income(db)


@mcp.tool(annotations=READ_ONLY)
def get_rub_cash() -> dict[str, float]:
    """Получить рублёвый остаток: отдельно T-Invest, ручной ledger и общую сумму."""
    with SessionLocal() as db:
        return ledger.rub_cash_balance(db)


@mcp.tool(annotations=READ_ONLY)
def get_lifetime_results() -> dict[str, Any]:
    """Получить записанные купоны, дивиденды, проценты и реализованный P&L, включая закрытые активы."""
    with SessionLocal() as db:
        return portfolio.realized_results(db)


@mcp.tool(annotations=READ_ONLY)
def get_pending_reconciliations(as_of: str | None = None) -> dict[str, Any]:
    """Найти завершившиеся вклады и облигации, которые нужно закрыть или синхронизировать."""
    from datetime import date as _date

    on = _date.fromisoformat(as_of) if as_of else None
    with SessionLocal() as db:
        return ledger.pending_reconciliations(db, on=on)


@mcp.tool(annotations=READ_ONLY)
def search_portfolio(query: str, limit: int = 50) -> dict[str, Any]:
    """Искать одновременно по инструментам, активным позициям и операциям."""
    with SessionLocal() as db:
        return read_model.search(db, query, limit=limit)


@mcp.tool(annotations=READ_ONLY)
def get_portfolio_context(
    recent_transactions: int = 50,
    history_days: int = 365,
    calendar_months: int = 24,
) -> dict[str, Any]:
    """Получить единый пакет контекста для комплексного анализа портфеля.

    Включает статус, текущую сводку, доходы, календарь, доходность, лидеров,
    последние операции и дневную историю. Для точечных вопросов выбирайте узкие tools.
    """
    with SessionLocal() as db:
        return read_model.portfolio_context(
            db, recent_transactions=recent_transactions,
            history_days=history_days, calendar_months=calendar_months,
        )


@mcp.tool(annotations=READ_ONLY)
def get_calculation_methodology() -> dict[str, str]:
    """Получить полные правила расчётов и известные ограничения точности."""
    return {"format": "markdown", "text": _methodology_text()}


@mcp.tool(annotations=READ_ONLY)
def get_data_dictionary() -> dict[str, Any]:
    """Получить словарь сущностей, полей, единиц измерения и допустимых типов."""
    return {
        "base_currency": "RUB",
        "conventions": {
            "money": "RUB unless a field explicitly names another currency",
            "rates": "decimal fractions; 0.18 means 18%",
            "dates": "ISO 8601; portfolio days use Europe/Moscow calendar dates",
            "transaction_amount": "signed cash flow: purchases are negative, receipts are positive",
            "pnl_pct": "decimal fraction; multiply by 100 for percent",
        },
        "instrument_kinds": {
            "bond": "облигация", "share": "акция", "etf": "фонд",
            "currency": "валюта или рублёвый остаток", "deposit": "банковский вклад",
        },
        "transaction_kinds": {
            "buy": "покупка ценной бумаги", "sell": "продажа ценной бумаги",
            "coupon": "купон", "dividend": "дивиденд", "interest": "процент по вкладу",
            "fx_buy": "покупка валюты", "fx_sell": "продажа валюты",
            "topup": "поступление в рублёвый остаток",
            "withdrawal": "списание из рублёвого остатка",
        },
        "entities": {
            "instrument": [
                "id", "kind", "name", "ticker", "isin", "figi", "currency",
                "nominal", "last_price", "nkd", "price_updated_at", "meta",
            ],
            "position": [
                "qty", "invested", "value", "income", "unrealized", "realized",
                "pnl", "pnl_pct", "last_price", "nkd",
            ],
            "transaction": [
                "date", "instrument_id", "kind", "quantity", "price", "amount",
                "commission", "note",
            ],
            "snapshot": [
                "ts", "value", "invested", "pnl", "income", "by_class",
                "by_instrument", "source",
            ],
            "price_point": ["ts", "price"],
            "calendar_event": ["date", "instrument", "type", "amount", "ticker"],
        },
        "instrument_identifiers": ["numeric id", "id:<number>", "ticker", "ISIN", "FIGI", "exact name"],
        "accuracy_note": (
            "Dashboard estimates use floating-point numbers and incomplete broker-operation "
            "coverage; read portfolio://methodology before financial conclusions."
        ),
    }


@mcp.tool(annotations=WRITE)
def top_up_rub_cash(
    request_id: str,
    amount_rub: float,
    date: str,
    confirm: bool,
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Записать внешнее пополнение рублёвого остатка. date: YYYY-MM-DD."""
    return _write_actions(
        request_id=request_id,
        actions=[{"type": "cash_topup", "amount_rub": amount_rub, "date": date, "note": note}],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def withdraw_rub_cash(
    request_id: str,
    amount_rub: float,
    date: str,
    confirm: bool,
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Записать внешний вывод рублей; операция отклоняется при недостаточном остатке."""
    return _write_actions(
        request_id=request_id,
        actions=[{"type": "cash_withdrawal", "amount_rub": amount_rub, "date": date, "note": note}],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def open_deposit_with_cash(
    request_id: str,
    name: str,
    principal: float,
    open_date: str,
    close_date: str,
    annual_rate_pct: float,
    confirm: bool,
    interest_mode: str = "simple",
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Открыть вклад за счёт RUB.

    interest_mode: simple или monthly_capitalization. Сумма атомарно списывается
    из рублей и появляется во вкладе; при недостатке RUB ничего не меняется.
    """
    return _write_actions(
        request_id=request_id,
        actions=[{
            "type": "open_deposit", "name": name, "principal": principal,
            "open_date": open_date, "close_date": close_date,
            "annual_rate_pct": annual_rate_pct, "interest_mode": interest_mode,
            "note": note,
        }],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def settle_deposit_to_rub(
    request_id: str,
    instrument: str,
    settled_on: str,
    confirm: bool,
    actual_payout_rub: float | None = None,
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Закрыть вклад и зачислить выплату в RUB.

    После даты окончания actual_payout_rub можно пропустить — будет использована
    расчётная сумма. Для досрочного закрытия фактическая выплата обязательна.
    """
    return _write_actions(
        request_id=request_id,
        actions=[{
            "type": "settle_deposit", "instrument": instrument,
            "settled_on": settled_on, "actual_payout_rub": actual_payout_rub,
            "note": note,
        }],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def buy_manual_currency(
    request_id: str,
    code: str,
    quantity: float,
    total_cost_rub: float,
    traded_on: str,
    confirm: bool,
    current_rate: float | None = None,
    name: str = "",
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Купить ручную валюту за RUB; total_cost_rub — вся фактически списанная сумма."""
    return _write_actions(
        request_id=request_id,
        actions=[{
            "type": "buy_currency", "code": code, "quantity": quantity,
            "total_cost_rub": total_cost_rub, "traded_on": traded_on,
            "current_rate": current_rate, "name": name, "note": note,
        }],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def sell_manual_currency(
    request_id: str,
    code: str,
    quantity: float,
    total_proceeds_rub: float,
    traded_on: str,
    confirm: bool,
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Продать ручную валюту и зачислить чистую фактическую выручку в RUB."""
    return _write_actions(
        request_id=request_id,
        actions=[{
            "type": "sell_currency", "code": code, "quantity": quantity,
            "total_proceeds_rub": total_proceeds_rub, "traded_on": traded_on,
            "note": note,
        }],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def buy_manual_security(
    request_id: str,
    instrument: str,
    quantity: float,
    total_cost_rub: float,
    traded_on: str,
    confirm: bool,
    commission: float = 0,
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Купить вручную учитываемую бумагу за RUB; для T-Invest tool намеренно запрещён."""
    return _write_actions(
        request_id=request_id,
        actions=[{
            "type": "buy_security", "instrument": instrument, "quantity": quantity,
            "total_cost_rub": total_cost_rub, "traded_on": traded_on,
            "commission": commission, "note": note,
        }],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def sell_manual_security(
    request_id: str,
    instrument: str,
    quantity: float,
    total_proceeds_rub: float,
    traded_on: str,
    confirm: bool,
    commission: float = 0,
    note: str = "",
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Продать вручную учитываемую бумагу в RUB; для T-Invest tool намеренно запрещён."""
    return _write_actions(
        request_id=request_id,
        actions=[{
            "type": "sell_security", "instrument": instrument, "quantity": quantity,
            "total_proceeds_rub": total_proceeds_rub, "traded_on": traded_on,
            "commission": commission, "note": note,
        }],
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=WRITE)
def apply_portfolio_actions(
    request_id: str,
    actions: list[dict[str, Any]],
    confirm: bool,
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """Атомарно применить до 50 связанных действий.

    Поддерживаемые type: cash_topup, cash_withdrawal, open_deposit,
    settle_deposit, buy_currency, sell_currency, buy_security, sell_security.
    Если любое действие невалидно, весь пакет откатывается. Повтор с тем же
    request_id не дублирует данные. Предпочтительный tool для фраз вроде
    «внёс 50 000 ₽ и сразу открыл на них вклад».
    """
    return _write_actions(
        request_id=request_id,
        actions=actions,
        confirm=confirm,
        create_snapshot=create_snapshot,
    )


@mcp.tool(annotations=SYNC)
def synchronize_tinvest(days: int = 3650, confirm: bool = False) -> dict[str, Any]:
    """Обновить локальную БД из read-only T-Invest: операции, позиции, RUB, цены и снимок.

    Tool ничего не покупает и не продаёт у брокера, но изменяет локальную базу.
    """
    if confirm is not True:
        raise ValueError("confirm=true is required after explicit user approval")
    if days < 1 or days > 36500:
        raise ValueError("days must be between 1 and 36500")
    with DATABASE_MAINTENANCE_LOCK:
        with SessionLocal() as db:
            with redirect_stdout(sys.stderr):
                operations = sync_operations(db, days_back=days)
                if not operations.get("ok"):
                    return operations
                prices = fetch_prices(db)
            if not prices.get("ok"):
                return prices
            snapshot = snapshots.take_snapshot(db, source="mcp-tinvest-sync")
            return {
                "ok": True,
                "imported": operations.get("imported", 0),
                "skipped": operations.get("skipped", 0),
                "prices_updated": len(prices.get("updated", [])),
                "warnings": prices.get("warnings", []),
                "snapshot": snapshot.ts.isoformat(),
            }


@mcp.resource("portfolio://status", mime_type="application/json")
def status_resource() -> str:
    """Безопасный статус источников и наполнения базы."""
    return _json(get_data_status())


@mcp.resource("portfolio://summary", mime_type="application/json")
def summary_resource() -> str:
    """Полная текущая сводка портфеля."""
    return _json(get_portfolio_overview())


@mcp.resource("portfolio://positions", mime_type="application/json")
def positions_resource() -> str:
    """Все активные позиции."""
    return _json(list_positions(limit=2000))


@mcp.resource("portfolio://income", mime_type="application/json")
def income_resource() -> str:
    """Оценка пассивного дохода."""
    return _json(get_passive_income())


@mcp.resource("portfolio://cash", mime_type="application/json")
def cash_resource() -> str:
    """Рублёвый остаток по брокерской и ручной части."""
    return _json(get_rub_cash())


@mcp.resource("portfolio://lifetime-results", mime_type="application/json")
def lifetime_results_resource() -> str:
    """Записанный доход и реализованный результат, включая закрытые позиции."""
    return _json(get_lifetime_results())


@mcp.resource("portfolio://reconciliations", mime_type="application/json")
def reconciliations_resource() -> str:
    """Завершившиеся активы, ожидающие явного закрытия или синхронизации."""
    return _json(get_pending_reconciliations())


@mcp.resource("portfolio://methodology", mime_type="text/markdown")
def methodology_resource() -> str:
    """Правила финансовых расчётов и ограничения данных."""
    return _methodology_text()


@mcp.resource("portfolio://data-dictionary", mime_type="application/json")
def data_dictionary_resource() -> str:
    """Сущности, поля, единицы измерения и допустимые типы."""
    return _json(get_data_dictionary())


@mcp.resource("portfolio://instrument/{identifier}", mime_type="application/json")
def instrument_resource(identifier: str) -> str:
    """Карточка инструмента по id, тикеру, ISIN, FIGI или точному названию."""
    return _json(get_instrument(identifier))


@mcp.prompt()
def analyze_portfolio(focus: str = "risk, allocation, performance and upcoming cash flows") -> str:
    """Шаблон комплексного анализа портфеля на основе MCP-данных."""
    return (
        "Проанализируй локальный портфель. Сначала вызови get_portfolio_context, "
        f"затем при необходимости уточни данные узкими tools. Фокус: {focus}. "
        "Отделяй факты от выводов, объясняй финансовые термины простыми словами, "
        "учитывай methodology и не выдавай результат за налоговый или брокерский отчёт."
    )


@mcp.prompt()
def explain_change(period: str = "month") -> str:
    """Шаблон объяснения изменения стоимости портфеля."""
    return (
        f"Объясни изменение портфеля за {period}. Используй get_change_leaders и "
        "get_returns, проверь полноту опорного периода и отличай рыночное движение "
        "от покупок, продаж и выплат."
    )


def main() -> None:
    """Run the local server over MCP stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
