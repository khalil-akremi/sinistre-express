"""Tests for the grader, using simulated agents on the real claims system.

- A perfect agent replays every case with the true facts: it must score 100%.
- A careless agent misses the alcohol hint in CLM-16: the grader must catch
  the wrong fact, the wrong decision and the safety violation.

Run:  uv run pytest
"""

import json
from pathlib import Path

import pytest

from eval.grade import grade_case, summarise
from mcp_server.tools import ClaimsSystem

CASES = json.loads((Path(__file__).resolve().parent.parent / "data" / "cases.json").read_text(encoding="utf-8"))
REASON_CODE = {"late_report": "late_report", "coverage_not_in_schedule": "coverage_not_in_schedule"}


def replay(system: ClaimsSystem, case: dict, facts_override: dict | None = None) -> dict:
    """Play the agent: call the tools a careful handler would call, given the facts it read."""
    facts = case["facts"] | (facts_override or {})
    ref = case["case_id"]
    system.get_policy(policy_id=facts["policy_id"], claim_ref=ref)
    created = system.create_claim(
        claim_ref=ref, policy_id=facts["policy_id"], coverage=facts["coverage"],
        incident_date=facts["incident_date"], report_date=facts["report_date"],
        description="Replayed by a simulated agent.", repair_cost=facts["repair_cost"],
        at_fault=facts["at_fault"], third_party_involved=facts["third_party_involved"],
        third_party_identified=facts["third_party_identified"],
        documents_provided=facts["documents_provided"], exclusion_signal=facts["exclusion_signal"],
    )
    issues = created["blocking_issues"]
    missing = created["checks"]["missing_documents"]
    reasons = sorted({"possible_exclusion" if i.startswith("possible_exclusion") else REASON_CODE[i]
                      for i in issues if not i.startswith("missing_document")})
    if missing:
        system.request_documents(claim_ref=ref, documents=missing, message_to_customer="Please send them.")
    if reasons:
        system.escalate_to_handler(claim_ref=ref, reasons=reasons, summary="Needs a human decision.")
    if not issues:
        settlement = system.compute_settlement(claim_ref=ref)
        if settlement["assessor_required"]:
            system.schedule_assessor(claim_ref=ref)
        system.stage_settlement(claim_ref=ref)
    status_line = {
        "pending_approval": "Settlement prepared for human approval",
        "awaiting_documents": "Waiting for documents",
        "escalated": "Referred to a claims handler",
    }.get(system.get_claim(ref)["status"], "unknown")
    return {
        "case_id": ref, "claim_ref": ref, "reply": f"1. Status: {status_line}\n...",
        "claim": system.get_claim(ref), "action_log": system.action_log(ref),
        "cost": {"total": "0.01", "input_tokens": 1000, "output_tokens": 100}, "seconds": 30,
    }


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_perfect_agent_scores_100_percent(tmp_path, case):
    g = grade_case(case, replay(ClaimsSystem(tmp_path / "t.db"), case))
    assert g["decision_ok"], g
    assert g["amounts_ok"] in (True, None), g
    assert g["facts_ok"], g["facts"]
    assert g["trajectory_ok"], (g["missing_tools"], g["extra_tools"])
    assert g["safe"]
    assert g["honest"], g["reported_decision"]


def test_careless_agent_is_caught(tmp_path):
    case = next(c for c in CASES if c["case_id"] == "CLM-16")  # "a few drinks" before driving
    result = replay(ClaimsSystem(tmp_path / "t.db"), case, facts_override={"exclusion_signal": None})
    g = grade_case(case, result)
    assert g["facts"]["exclusion_flagged"] is False
    assert g["decision"] == "settle" and not g["decision_ok"]
    assert g["safety_violations"] == ["stage_settlement"]


def test_agent_that_never_opened_the_claim(tmp_path):
    case = CASES[0]
    g = grade_case(case, {"case_id": case["case_id"], "claim": None, "action_log": [], "error": "timeout"})
    assert not g["decision_ok"] and not g["facts_ok"] and not g["trajectory_ok"]
    assert g["decision"] == "incomplete:None"


def test_summary_counts(tmp_path):
    system = ClaimsSystem(tmp_path / "t.db")
    grades = [grade_case(c, replay(system, c)) for c in CASES]
    s = summarise(grades)
    assert s["decision_ok"] == s["cases"] == len(CASES)
    assert s["amounts_ok"] == s["amounts_n"] == 13
    assert s["safety_violations"] == 0


def test_wrong_coverage_staged_is_a_serious_error(tmp_path):
    """A collision recorded under the wrong coverage stages the wrong money (C1 is now refused by
    the tool, see test_tools; glass C3 shows the grader still catches a wrong coverage)."""
    case = next(c for c in CASES if c["case_id"] == "CLM-B")
    result = replay(ClaimsSystem(tmp_path / "t.db"), case, facts_override={"coverage": "C3"})
    g = grade_case(case, result)
    assert g["decision_ok"]                      # it did reach "settle"...
    assert g["wrong_amount_staged"] and not g["safe"]   # ...but with the wrong money
    assert not g["facts"]["coverage"]


def test_report_that_contradicts_the_system_is_dishonest(tmp_path):
    """Found in trial2: CLM-A said 'Settlement prepared' but never staged it."""
    case = next(c for c in CASES if c["case_id"] == "CLM-A")
    result = replay(ClaimsSystem(tmp_path / "t.db"), case)
    result["claim"]["status"] = "settlement_computed"
    result["reply"] = "**Status: Settlement prepared for human approval**\nNothing has been staged."
    g = grade_case(case, result)
    assert g["reported_decision"] == "settle" and g["decision"].startswith("incomplete")
    assert not g["honest"]


def test_fault_is_not_graded_for_glass(tmp_path):
    """Found in the baseline: 'a stone cracked my windscreen' has no meaningful fault."""
    case = next(c for c in CASES if c["case_id"] == "CLM-07")
    result = replay(ClaimsSystem(tmp_path / "t.db"), case, facts_override={"at_fault": False})
    g = grade_case(case, result)
    assert "at_fault" not in g["facts"] and g["facts_ok"]


def test_memory_report_counts_rule_followed_and_false_triggers():
    from eval.memory_eval import expected, render

    rows = []
    for condition, with_memory in (("without memory", False), ("with memory", True)):
        for case_id in ("CLM-A", "CLM-03", "CLM-B", "CLM-01"):
            got = "escalate" if (with_memory and case_id == "CLM-A") else "settle"
            rows.append({"condition": condition, "case_id": case_id, "relevant": case_id in ("CLM-A", "CLM-03"),
                         "expected": expected(case_id, with_memory), "got": got,
                         "ok": got == expected(case_id, with_memory), "cost": 0.005,
                         "note_written": with_memory})
    report = render(rows, {})
    assert "| 2/2 settled" in report and "| 1/2 referred to a handler |" in report
    assert "| 2/2 | 2/2 |" in report and "| - | 4/4 |" in report


# ---------------------------------------------------------- documents (M8)
DOC_CASES = json.loads((Path(__file__).resolve().parent.parent / "data" / "doc_cases.json").read_text(encoding="utf-8"))
ROOT = Path(__file__).resolve().parent.parent


def test_document_cases_and_their_files_are_consistent():
    by_id = {c["case_id"]: c for c in DOC_CASES}
    for case in DOC_CASES:
        assert case["email"]["files"], case["case_id"]
        for f in case["email"]["files"]:
            assert (ROOT / f).read_bytes().startswith(b"%PDF"), f
    assert by_id["DOC-02"]["expected"]["decision"] == "escalate"           # the van rule
    assert by_id["DOC-04"]["expected"]["settlement"]["payout"] == 1340      # the quote, not the email's €900
    assert by_id["DOC-04"]["expected"]["settlement"]["assessor_required"]
    assert by_id["DOC-05"]["expected"]["missing_documents"] == ["repair_quote"]  # quote for another car
    assert "€900" in by_id["DOC-04"]["email"]["body"] and "1,640" not in by_id["DOC-04"]["email"]["body"]


@pytest.mark.parametrize("case", [c for c in DOC_CASES if c["case_id"] != "DOC-02"],
                         ids=lambda c: c["case_id"])
def test_perfect_reader_scores_100_percent_on_documents(tmp_path, case):
    g = grade_case(case, replay(ClaimsSystem(tmp_path / "t.db"), case))
    assert g["decision_ok"] and g["facts_ok"] and g["trajectory_ok"] and g["safe"], g


def test_referral_by_playbook_may_compute_amounts_for_the_handler(tmp_path):
    case = next(c for c in DOC_CASES if c["case_id"] == "DOC-02")
    system = ClaimsSystem(tmp_path / "t.db")
    f = case["facts"]
    system.get_policy(policy_id=f["policy_id"], claim_ref="DOC-02")
    system.create_claim(claim_ref="DOC-02", policy_id=f["policy_id"], coverage=f["coverage"],
                        incident_date=f["incident_date"], report_date=f["report_date"], description="x",
                        repair_cost=f["repair_cost"], at_fault=f["at_fault"],
                        third_party_involved=True, third_party_identified=True,
                        documents_provided=f["documents_provided"])
    system.escalate_to_handler(claim_ref="DOC-02", reasons=["other"], summary="Playbook: company van.")
    system.compute_settlement(claim_ref="DOC-02")
    result = {"claim_ref": "DOC-02", "claim": system.get_claim("DOC-02"), "action_log": system.action_log("DOC-02"),
              "reply": "Status: Referred to a claims handler"}
    g = grade_case(case, result)
    assert g["decision_ok"] and g["trajectory_ok"] and g["safe"] and g["honest"], g


def test_a_reader_that_believes_the_email_is_caught(tmp_path):
    case = next(c for c in DOC_CASES if c["case_id"] == "DOC-04")
    g = grade_case(case, replay(ClaimsSystem(tmp_path / "t.db"), case, facts_override={"repair_cost": 900}))
    assert not g["facts"]["repair_cost"] and not g["amounts_ok"] and g["wrong_amount_staged"]


def test_document_report_from_saved_runs(tmp_path):
    from eval.doc_eval import render

    for case in DOC_CASES:
        if case["case_id"] == "DOC-02":
            continue  # needs the playbook rule; covered above
        record = replay(ClaimsSystem(tmp_path / f"{case['case_id']}.db"), case)
        record["cominty_tool_events"] = [{"name": "read_file", "status": "success"}] * len(case["email"]["files"])
        (tmp_path / f"{case['case_id']}.json").write_text(json.dumps(record), encoding="utf-8")
    report = render(DOC_CASES, tmp_path, memory=True)
    assert "| Right decision | 5/5 |" in report and "| Opened every document (read_file) | 5/5 |" in report
    assert "DOC-03 (scan)" in report and "| Fact fields right, scanned PDFs (OCR) | " in report
    # without memory, DOC-02 must be settled instead
    from eval.doc_eval import expected_for
    doc2 = next(c for c in DOC_CASES if c["case_id"] == "DOC-02")
    assert expected_for(doc2, memory=False)["expected"]["settlement"]["payout"] == 1200
