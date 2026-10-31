"""Tests through the real MCP protocol, the same way Cominty will call us.

An in-memory MCP client connects to our server: same messages, no network.

Run:  uv run pytest
"""

import asyncio
import json

import pytest

from mcp.client.client import Client
from mcp_server.server import build_server
from mcp_server.tools import ClaimsSystem

EXPECTED_TOOLS = {
    "get_policy", "create_claim", "compute_settlement", "request_documents",
    "escalate_to_handler", "schedule_assessor", "stage_settlement",
}


@pytest.fixture
def server(tmp_path):
    return build_server(ClaimsSystem(tmp_path / "test.db"))


def run(coro):
    return asyncio.run(coro)


def result_data(result) -> dict:
    return json.loads(result.content[0].text)


def test_menu_has_exactly_our_seven_tools(server):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools

    tools = run(go())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert all(t.description for t in tools), "every tool needs a description for the agent"


def test_there_is_no_approve_tool(server):
    async def go():
        async with Client(server) as client:
            return {t.name for t in (await client.list_tools()).tools}

    assert not any("approve" in name for name in run(go()))


def test_full_demo_b_through_mcp(server):
    claim = {
        "claim_ref": "CLM-B", "policy_id": "VER-1002", "coverage": "C2",
        "incident_date": "2026-10-14", "report_date": "2026-10-15",
        "description": "Lane change collision, at fault.", "repair_cost": 2400,
        "at_fault": True, "third_party_involved": True, "third_party_identified": True,
        "documents_provided": ["photos", "repair_quote", "accident_report"],
    }

    async def go():
        async with Client(server) as client:
            created = await client.call_tool("create_claim", claim)
            settlement = await client.call_tool("compute_settlement", {"claim_ref": "CLM-B"})
            await client.call_tool("schedule_assessor", {"claim_ref": "CLM-B"})
            staged = await client.call_tool("stage_settlement", {"claim_ref": "CLM-B"})
            return created, settlement, staged

    created, settlement, staged = run(go())
    assert not created.is_error and result_data(created)["blocking_issues"] == []
    assert result_data(settlement)["payout_eur"] == 1700
    assert result_data(staged)["status"] == "pending_approval"


def test_refusal_message_reaches_the_agent(server):
    async def go():
        async with Client(server) as client:
            return await client.call_tool("compute_settlement", {"claim_ref": "UNKNOWN"})

    result = run(go())
    assert result.is_error
    assert "Open it first with create_claim" in result.content[0].text


def test_missing_argument_rejected_by_schema(server):
    async def go():
        async with Client(server) as client:
            return await client.call_tool("get_policy", {"policy_id": "VER-1001", "claim_ref": "T-1"}), \
                await client.call_tool("schedule_assessor", {})

    ok, missing_arg = run(go())
    assert not ok.is_error
    assert missing_arg.is_error


def test_admin_snapshot_requires_the_secret(tmp_path):
    from starlette.testclient import TestClient

    system = ClaimsSystem(tmp_path / "test.db")
    system.get_policy(policy_id="VER-1004", claim_ref="T-9")
    app = build_server(system, admin_secret="s3cret").streamable_http_app()
    with TestClient(app) as client:
        assert client.get("/admin/wrong/claims/T-9").status_code == 404
        data = client.get("/admin/s3cret/claims/T-9").json()
    assert data["claim"] is None  # looked up, not opened yet
    assert [e["tool"] for e in data["action_log"]] == ["get_policy"]
