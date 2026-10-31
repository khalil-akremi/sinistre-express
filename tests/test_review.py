"""Tests for the Reviewer (second agent): task, verdict parsing, the app flow, the report."""

import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.web import register_web_routes
from core.review import build_review_task, parse_verdict
from mcp_server.server import build_server
from mcp_server.tools import ClaimsSystem
from tests.test_app import FakeAgent, start, wait_done

ROOT = Path(__file__).resolve().parent.parent
REVIEW_CASES = json.loads((ROOT / "data" / "review_cases.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------- verdicts
@pytest.mark.parametrize("text, verdict", [
    ('{"verdict": "approve", "issues": [], "summary": "All facts match."}', "approve"),
    ('Here is my review:\n```json\n{"verdict": "concerns", "issues": [{"field": "repair_cost"}], "summary": "x"}\n```',
     "concerns"),
    ('{"verdict": "approve", "issues": [{"field": "at_fault", "recorded": false}], "summary": "ok"}', "concerns"),
    ("I think it is fine.", "concerns"),          # unreadable -> a person must look
    ('{"verdict": "maybe"}', "concerns"),
    (None, "concerns"),
])
def test_verdicts_fail_safe(text, verdict):
    assert parse_verdict(text)["verdict"] == verdict


def test_review_task_has_the_sources_but_not_the_handlers_reasoning():
    case = next(c for c in REVIEW_CASES if c["review_id"] == "R-01")
    task = build_review_task(case["email"], case["policy"], case["created"], case["claim"], ["Vans go to a handler."])
    assert "around €900" in task                                  # the email
    assert "repair_quote.pdf" in task and "open them" in task     # the document to open
    assert "- repair_cost (repair cost in EUR): 900" in task      # what the handler recorded
    assert "Vans go to a handler." in task and "Emma" not in task
    assert "status pending_approval" in task and "payout €600" in task
    assert "Status:" not in task                                  # no handler report


def test_review_set_has_8_mistakes_and_8_correct_claims_all_staged():
    assert sum(1 for c in REVIEW_CASES if c["mistake"]) == 8
    assert sum(1 for c in REVIEW_CASES if not c["mistake"]) == 8
    assert all(c["claim"]["status"] == "pending_approval" for c in REVIEW_CASES)
    r1 = next(c for c in REVIEW_CASES if c["review_id"] == "R-01")
    r11 = next(c for c in REVIEW_CASES if c["review_id"] == "R-11")  # same claim, done right
    assert (r1["claim"]["payout"], r11["claim"]["payout"]) == (600, 1340)


# ------------------------------------------------------- the app flow
class FakeReviewer:
    def __init__(self, reply):
        self.reply, self.tasks, self.files = reply, [], []

    async def __call__(self, task, on_event, files=None):
        self.tasks.append(task)
        self.files.append(files)
        on_event({"source": "agent", "icon": "📎", "text": "Reading an attached document"})
        return {"reply": self.reply, "cost": {"total": "0.003"}}


def desk_with(reviewer, tmp_path):
    system = ClaimsSystem(tmp_path / "t.db")
    server = build_server(system, admin_secret="s3cret")
    register_web_routes(server, system, FakeAgent(system), daily_max=10, reviewer=reviewer)
    return TestClient(server.streamable_http_app())


CONCERNS = json.dumps({"verdict": "concerns", "summary": "Fault is wrong.",
                       "issues": [{"field": "at_fault", "recorded": False, "should_be": True, "evidence": "report"}]})


def test_reviewer_checks_a_staged_payment_and_concerns_need_an_override(tmp_path):
    reviewer = FakeReviewer(CONCERNS)
    with desk_with(reviewer, tmp_path) as client:
        ref = start(client, "CLM-B").json()["claim_ref"]
        data = wait_done(client, ref)
        assert data["review"]["verdict"] == "concerns" and data["review"]["issues"][0]["field"] == "at_fault"
        assert "Facts recorded by the handler agent" in reviewer.tasks[0]
        refused = client.post(f"/api/claims/{ref}/approve")
        assert refused.status_code == 409 and refused.json()["needs_override"]
        approved = client.post(f"/api/claims/{ref}/approve", json={"override": True}).json()
        assert approved["claim"]["status"] == "approved"
        assert "reviewer overridden" in approved["log"][-1]["detail"]


def test_reviewer_agreement_lets_the_person_approve(tmp_path):
    reviewer = FakeReviewer('{"verdict": "approve", "issues": [], "summary": "Facts match the sources."}')
    with desk_with(reviewer, tmp_path) as client:
        ref = start(client, "CLM-B").json()["claim_ref"]
        data = wait_done(client, ref)
        steps = [s["text"] for s in client.get(f"/api/claims/{ref}").json()["log"]]
        assert data["review"]["verdict"] == "approve" and "stage_settlement" in steps
        assert client.post(f"/api/claims/{ref}/approve").json()["claim"]["status"] == "approved"


def test_no_review_when_nothing_is_paid(tmp_path):
    reviewer = FakeReviewer(CONCERNS)
    with desk_with(reviewer, tmp_path) as client:
        data = wait_done(client, start(client, "CLM-C").json()["claim_ref"])  # theft, late: referred
        assert data["review"] is None and reviewer.tasks == []


def test_reviewer_receives_the_same_documents(tmp_path):
    from tests.test_grade import DOC_CASES, replay

    class DocHandler:
        async def __call__(self, task, on_event, files=None):
            ref = re.search(r"claim reference (\S+?)\.", task).group(1)
            replay(system, next(c for c in DOC_CASES if c["case_id"] == "DOC-03") | {"case_id": ref})
            return {"reply": "Status: Settlement prepared for human approval", "cost": None}

    reviewer = FakeReviewer('{"verdict": "approve", "issues": [], "summary": "ok"}')
    system = ClaimsSystem(tmp_path / "t.db")
    server = build_server(system, admin_secret="s3cret")
    register_web_routes(server, system, DocHandler(), daily_max=10, reviewer=reviewer)
    with TestClient(server.streamable_http_app()) as client:
        pub = next(c for c in client.get("/api/cases").json()["cases"] if c["case_id"] == "DOC-03")
        res = client.post("/api/claims", json={"case_id": "DOC-03", "body": pub["body"],
                                                "documents": ["photos"], "files": ["repair_quote.pdf"]})
        data = wait_done(client, res.json()["claim_ref"])
    assert data["claim"]["status"] == "pending_approval" and data["review"]["verdict"] == "approve"
    assert [f.name for f in reviewer.files[0]] == ["repair_quote.pdf"]
    assert "repair_quote.pdf" in reviewer.tasks[0] and "(repair cost in EUR): 1180" in reviewer.tasks[0]


def test_a_broken_reviewer_means_a_person_must_look(tmp_path):
    class Broken:
        async def __call__(self, task, on_event, files=None):
            raise TimeoutError("no answer")

    with desk_with(Broken(), tmp_path) as client:
        ref = start(client, "CLM-B").json()["claim_ref"]
        data = wait_done(client, ref)
        assert data["review"]["verdict"] == "concerns" and data["review"]["unreadable"]
        assert client.post(f"/api/claims/{ref}/approve").status_code == 409


# ------------------------------------------------------------ report
def test_review_report_counts_catches_and_false_alarms(tmp_path):
    from eval.review_eval import render

    for case in REVIEW_CASES:
        if case["mistake"]:
            reply = {"verdict": "concerns", "summary": f"Problem with {case['field']}",
                     "issues": [{"field": case["field"]}]} if case["review_id"] != "R-06" else \
                    {"verdict": "approve", "issues": [], "summary": "fine"}
        else:
            reply = {"verdict": "concerns" if case["review_id"] == "R-09" else "approve", "issues": [],
                     "summary": "x"}
        record = {"verdict": parse_verdict(json.dumps(reply)), "cost": {"total": "0.004"}, "seconds": 20}
        (tmp_path / f"{case['review_id']}.json").write_text(json.dumps(record), encoding="utf-8")
    report = render(REVIEW_CASES, tmp_path, "test")
    assert "| Planted mistakes caught | 7/8 |" in report
    assert "| False alarms on correct claims | 1/8 |" in report


# ------------------------------------------------- checks -> verdict (code decides)
from core.review import FACT_LABELS  # noqa: E402


def checks_reply(mismatch=None, paid=True, skip=None):
    checks = [{"field": f, "recorded": "x", "sources_say": "y" if f == mismatch else "x",
               "match": f != mismatch, "evidence": "email"} for f in FACT_LABELS if f != skip]
    return json.dumps({"checks": checks, "payment": {"should_be_paid": paid, "evidence": "ok"},
                       "summary": "Everything matches."})


def test_all_checks_match_means_approve():
    v = parse_verdict(checks_reply())
    assert v["verdict"] == "approve" and len(v["checks"]) == len(FACT_LABELS)


def test_one_mismatch_means_concerns_even_if_the_summary_says_fine():
    v = parse_verdict(checks_reply(mismatch="third_party_identified"))
    assert v["verdict"] == "concerns" and v["issues"][0]["field"] == "third_party_identified"


def test_should_not_be_paid_means_concerns():
    v = parse_verdict(checks_reply(paid=False))
    assert v["verdict"] == "concerns" and v["issues"][0]["field"] == "payment decision"


def test_a_fact_left_unchecked_means_concerns():
    v = parse_verdict(checks_reply(skip="at_fault"))
    assert v["verdict"] == "concerns" and v["issues"][0]["field"] == "review incomplete"
