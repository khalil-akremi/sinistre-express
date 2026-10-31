"""Tests for the claims-desk web app, with a fake agent (no Cominty credits spent).

The fake agent reads the task message like the real one would (claim reference,
documents received), then calls the real claims system with the true facts.

Run:  uv run pytest
"""

import json
import re
import time

import pytest
from starlette.testclient import TestClient

from app.web import register_web_routes
from mcp_server.server import build_server
from mcp_server.tools import ClaimsSystem
from tests.test_grade import CASES, replay

FILE_TO_DOC = {"damage_photos.zip": "photos", "repair_quote.pdf": "repair_quote",
               "accident_report_signed.pdf": "accident_report", "police_report.pdf": "police_report"}


class FakeAgent:
    def __init__(self, system: ClaimsSystem):
        self.system = system
        self.tasks: list[str] = []

    async def __call__(self, task, on_event):
        self.tasks.append(task)
        on_event({"source": "agent", "icon": "📄", "text": "Searching the contract (RAG)"})
        ref = re.search(r"Use the claim reference (\S+?)\.", task).group(1)
        case = next(c for c in CASES if f"Subject: {c['email']['subject']}" in task
                    and c["email"]["from"] in task)
        received = re.search(r"stored them in the claim file: (.*?)\. Count", task)
        docs = [FILE_TO_DOC[f.strip()] for f in received.group(1).split(",")] if received else []
        case = case | {"case_id": ref}
        replay(self.system, case, facts_override={"documents_provided": docs})
        on_event({"source": "agent", "icon": "💬", "text": "Claim handled"})
        return {"reply": "1. Status: done", "status": "success", "cost": {"total": "0.005"}}


@pytest.fixture
def desk(tmp_path):
    system = ClaimsSystem(tmp_path / "t.db")
    server = build_server(system, admin_secret="s3cret")
    agent = FakeAgent(system)
    register_web_routes(server, system, agent, daily_max=3)
    with TestClient(server.streamable_http_app()) as client:
        yield client, agent


def wait_done(client, ref, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/claims/{ref}").json()
        if data["done"]:
            return data
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def sample(case_id):
    return next(c for c in CASES if c["case_id"] == case_id)


def start(client, case_id, body=None, documents=None):
    pub = next(c for c in client.get("/api/cases").json()["cases"] if c["case_id"] == case_id)
    return client.post("/api/claims", json={
        "case_id": case_id,
        "body": body if body is not None else pub["body"],
        "documents": documents if documents is not None else pub["documents"],
    })


def test_page_and_assets_are_served(desk):
    client, _ = desk
    assert "Sinistre Express" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/../server.py").status_code == 404
    assert client.get("/health").json()["status"] == "ok"


def test_cases_never_leak_the_answer_key(desk):
    client, _ = desk
    data = client.get("/api/cases").json()
    assert len(data["cases"]) == len(CASES)
    raw = json.dumps(data)
    assert "expected" not in raw and "facts" not in raw and "payout" not in raw
    assert "Attached:" not in data["cases"][0]["body"]  # documents are checkboxes instead


def test_demo_b_end_to_end_with_human_approval(desk):
    client, agent = desk
    res = start(client, "CLM-B")
    assert res.status_code == 202
    ref = res.json()["claim_ref"]
    data = wait_done(client, ref)
    assert data["claim"]["status"] == "pending_approval"
    assert (data["claim"]["deductible"], data["claim"]["payout"]) == (700, 1700)
    assert [s["text"] for s in data["log"]][:2] == ["get_policy", "create_claim"]
    assert "Count them as provided documents" in agent.tasks[0]

    approved = client.post(f"/api/claims/{ref}/approve").json()
    assert approved["claim"]["status"] == "approved"
    assert approved["log"][-1]["text"].startswith("approve_settlement")
    assert client.post(f"/api/claims/{ref}/approve").status_code == 409  # cannot approve twice


def test_unticking_a_document_changes_the_outcome(desk):
    client, _ = desk
    ref = start(client, "CLM-09", documents=[]).json()["claim_ref"]  # theft without police report
    data = wait_done(client, ref)
    assert data["claim"]["status"] == "awaiting_documents"
    assert client.post(f"/api/claims/{ref}/approve").status_code == 409


def test_live_stream_sends_steps_then_done(desk):
    client, _ = desk
    ref = start(client, "CLM-A").json()["claim_ref"]
    with client.stream("GET", f"/api/claims/{ref}/stream") as response:
        text = "".join(response.iter_text())
    assert "event: step" in text and "event: done" in text
    assert "Searching the contract" in text and "stage_settlement" in text


def test_daily_limit_protects_the_credits(desk):
    client, _ = desk
    for case_id in ("CLM-A", "CLM-01", "CLM-07"):
        ref = start(client, case_id).json()["claim_ref"]
        wait_done(client, ref)
    res = start(client, "CLM-08")
    assert res.status_code == 429 and "daily limit" in res.json()["error"]


@pytest.mark.parametrize("payload, message", [
    ({"case_id": "NOPE", "body": "x", "documents": []}, "sample claims"),
    ({"case_id": "CLM-A", "body": "", "documents": []}, "characters"),
    ({"case_id": "CLM-A", "body": "x" * 2001, "documents": []}, "characters"),
    ({"case_id": "CLM-A", "body": "x", "documents": ["selfie"]}, "document"),
])
def test_bad_requests_are_refused(desk, payload, message):
    client, _ = desk
    res = client.post("/api/claims", json=payload)
    assert res.status_code == 400 and message in res.json()["error"]


# ---------------------------------------------------------------- memory
from app.memory import PLAYBOOK, InMemoryStore, add_rule, customer_path  # noqa: E402

COMMERCIAL = ("van", "truck")


class MemoryFakeAgent(FakeAgent):
    """Reads the playbook and writes a customer note, like the real agent with memory."""

    def __init__(self, system, store):
        super().__init__(system)
        self.store = store

    async def __call__(self, task, on_event):
        self.tasks.append(task)
        ref = re.search(r"Use the claim reference (\S+?)\.", task).group(1)
        case = next(c for c in CASES if f"Subject: {c['email']['subject']}" in task
                    and c["email"]["from"] in task)
        facts = case["facts"]
        rule_applies = "playbook.md" in task and "commercial vehicle" in (await self.store.read(PLAYBOOK)) \
            and any(word in task.lower() for word in COMMERCIAL)
        if rule_applies:
            self.system.get_policy(policy_id=facts["policy_id"], claim_ref=ref)
            self.system.create_claim(
                claim_ref=ref, policy_id=facts["policy_id"], coverage=facts["coverage"],
                incident_date=facts["incident_date"], report_date=facts["report_date"],
                description="x", repair_cost=facts["repair_cost"], at_fault=facts["at_fault"],
                third_party_involved=facts["third_party_involved"],
                third_party_identified=facts["third_party_identified"],
                documents_provided=facts["documents_provided"])
            self.system.escalate_to_handler(claim_ref=ref, reasons=["other"],
                                            summary="Playbook: commercial vehicle involved.")
        else:
            replay(self.system, case | {"case_id": ref})
        self.store.files[customer_path(facts["policy_id"])] = f"- {ref}: handled"
        return {"reply": "done", "status": "success", "cost": {"total": "0.006"}}


@pytest.fixture
def desk_with_memory(tmp_path):
    system = ClaimsSystem(tmp_path / "t.db")
    server = build_server(system, admin_secret="s3cret")
    store = InMemoryStore("veridia-test")
    agent = MemoryFakeAgent(system, store)
    register_web_routes(server, system, agent, daily_max=10, memory=store)
    with TestClient(server.streamable_http_app()) as client:
        yield client, agent, store


def test_memory_panel_is_hidden_without_memory(desk):
    client, _ = desk
    assert client.get("/api/memory").json() == {"enabled": False}


def test_task_tells_the_agent_how_to_use_memory(desk_with_memory):
    client, agent, _ = desk_with_memory
    wait_done(client, start(client, "CLM-01").json()["claim_ref"])
    assert "Memory (namespace veridia-test)" in agent.tasks[0]
    assert "customers/<policy number>.md" in agent.tasks[0]


def test_a_taught_rule_changes_the_next_claim(desk_with_memory):
    client, _, _ = desk_with_memory
    before = wait_done(client, start(client, "CLM-A").json()["claim_ref"])  # the van
    assert before["claim"]["status"] == "pending_approval"

    rule = "When the other driver is a commercial vehicle (van, truck), refer the claim to a handler."
    assert client.post("/api/memory/playbook", json={"rule": rule}).json()["rules"][0].endswith(rule)

    after = wait_done(client, start(client, "CLM-A").json()["claim_ref"])
    assert after["claim"]["status"] == "escalated"
    control = wait_done(client, start(client, "CLM-01").json()["claim_ref"])  # a pillar: no van
    assert control["claim"]["status"] == "pending_approval"


def test_customer_note_is_shown_for_the_selected_policy(desk_with_memory):
    client, _, _ = desk_with_memory
    ref = start(client, "CLM-B").json()["claim_ref"]
    wait_done(client, ref)
    data = client.get("/api/memory?policy=VER-1002").json()
    assert ref in data["customer_note"]
    assert client.get("/api/memory?policy=VER-1001").json()["customer_note"] is None
    assert client.get("/api/memory?policy=../secret").status_code == 400


def test_reset_clears_rules_and_notes(desk_with_memory):
    client, _, store = desk_with_memory
    client.post("/api/memory/playbook", json={"rule": "Be kind."})
    wait_done(client, start(client, "CLM-B").json()["claim_ref"])
    assert client.post("/api/memory/reset").json() == {"rules": []}
    assert store.files == {PLAYBOOK: store.files[PLAYBOOK]} and "- " not in store.files[PLAYBOOK]


@pytest.mark.parametrize("rule", ["", "x" * 301])
def test_invalid_rules_are_refused(desk_with_memory, rule):
    client, _, _ = desk_with_memory
    assert client.post("/api/memory/playbook", json={"rule": rule}).status_code == 400


def test_playbook_keeps_only_the_latest_rules():
    playbook = ""
    for i in range(15):
        playbook = add_rule(playbook, f"rule {i}")
    rules = [line for line in playbook.splitlines() if line.startswith("- ")]
    assert len(rules) == 12 and rules[-1].endswith("rule 14") and rules[0].endswith("rule 3")
