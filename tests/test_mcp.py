import sys
from datetime import date
from pathlib import Path

import anyio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from app.mcp_server import mcp
from app.models import Instrument, Transaction


def _portfolio_fixture(db):
    instrument = Instrument(
        kind="share",
        name="Тестовая акция",
        ticker="TEST",
        currency="RUB",
        last_price=125,
    )
    db.add(instrument)
    db.flush()
    db.add(Transaction(
        ts=date(2026, 7, 1),
        instrument_id=instrument.id,
        kind="buy",
        quantity=10,
        price=100,
        amount=-1000,
        note="test fixture",
    ))
    db.commit()


def test_mcp_exposes_complete_read_only_catalog(db):
    _portfolio_fixture(db)

    async def scenario():
        async with create_connected_server_and_client_session(mcp) as session:
            tools = (await session.list_tools()).tools
            names = {tool.name for tool in tools}
            assert {
                "get_data_status", "get_portfolio_overview", "list_positions",
                "list_instruments", "get_instrument", "list_transactions",
                "get_portfolio_history", "get_price_history", "get_returns",
                "get_change_leaders", "get_payment_calendar", "get_passive_income",
                "search_portfolio", "get_portfolio_context",
                "get_calculation_methodology", "get_data_dictionary",
                "get_rub_cash", "get_lifetime_results", "top_up_rub_cash",
                "get_pending_reconciliations",
                "withdraw_rub_cash", "open_deposit_with_cash",
                "settle_deposit_to_rub", "buy_manual_currency",
                "sell_manual_currency", "buy_manual_security",
                "sell_manual_security", "apply_portfolio_actions",
                "set_bond_coupon_schedule",
                "synchronize_tinvest",
            } <= names
            read_tools = [tool for tool in tools if tool.name.startswith("get_") or tool.name.startswith("list_") or tool.name == "search_portfolio"]
            write_tools = [tool for tool in tools if tool.name in {
                "top_up_rub_cash", "withdraw_rub_cash", "open_deposit_with_cash",
                "settle_deposit_to_rub", "buy_manual_currency", "sell_manual_currency",
                "buy_manual_security", "sell_manual_security", "apply_portfolio_actions",
                "set_bond_coupon_schedule",
                "synchronize_tinvest",
            }]
            assert all(tool.annotations.readOnlyHint is True for tool in read_tools)
            assert all(tool.annotations.readOnlyHint is False for tool in write_tools)
            assert all(tool.annotations.destructiveHint is False for tool in tools)

            result = await session.call_tool("get_portfolio_overview", {})
            assert result.isError is False
            assert result.structuredContent["value"] == 1250
            assert result.structuredContent["positions"][0]["ticker"] == "TEST"

            filtered = await session.call_tool(
                "list_transactions", {"instrument": "TEST", "kind": "buy"},
            )
            assert filtered.isError is False
            assert filtered.structuredContent["total"] == 1
            assert filtered.structuredContent["items"][0]["amount"] == -1000

            resources = (await session.list_resources()).resources
            uris = {str(resource.uri) for resource in resources}
            assert "portfolio://summary" in uris
            assert "portfolio://methodology" in uris
            assert "portfolio://data-dictionary" in uris
            assert "portfolio://cash" in uris
            assert "portfolio://lifetime-results" in uris
            assert "portfolio://reconciliations" in uris

    anyio.run(scenario)


def test_portable_entry_point_works_outside_project_directory(tmp_path):
    entry_point = Path(__file__).resolve().parents[1] / "mcp_server.py"

    async def scenario():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(entry_point)],
            cwd=tmp_path,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert "get_portfolio_overview" in names

    anyio.run(scenario)


def test_mcp_status_never_exposes_secret_values_or_paths(db):
    _portfolio_fixture(db)

    async def scenario():
        async with create_connected_server_and_client_session(mcp) as session:
            result = await session.call_tool("get_data_status", {})
            serialized = str(result.structuredContent).lower()
            assert "token" not in serialized
            assert "account_id" not in serialized
            assert "test.db" not in serialized

    anyio.run(scenario)


def test_mcp_write_tool_requires_confirmation_and_is_idempotent(db):
    async def scenario():
        async with create_connected_server_and_client_session(mcp) as session:
            arguments = {
                "request_id": "mcp-write-test-001",
                "amount_rub": 1_000,
                "date": "2026-07-15",
                "confirm": False,
            }
            rejected = await session.call_tool("top_up_rub_cash", arguments)
            assert rejected.isError is True

            arguments["confirm"] = True
            applied = await session.call_tool("top_up_rub_cash", arguments)
            repeated = await session.call_tool("top_up_rub_cash", arguments)
            cash = await session.call_tool("get_rub_cash", {})

            assert applied.isError is False
            assert applied.structuredContent["already_applied"] is False
            assert repeated.structuredContent["already_applied"] is True
            assert cash.structuredContent["manual"] == 1_000

    anyio.run(scenario)
