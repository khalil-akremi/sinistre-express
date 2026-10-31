"""Tests for the claims system, without any AI.

We play the agent ourselves: first a good agent (demo cases A, B, C), then a
bad agent that tries unsafe actions, to check the system blocks them.

Run:  uv run pytest
"""

import pytest

from mcp_server.tools import ClaimsSystem, ToolRefused


@pytest.fixture
def system(tmp_path):
    """A fresh claims system with an empty database for every test."""
    return ClaimsSystem(tmp_path / "test.db")


def open_claim(system, **overrides):
    facts = dict(
        claim_ref="T-1", policy_id="VER-1004", coverage="C2",
        incident_date="2026-10-03", report_date="2026-10-04",
        description="Hit a pillar while reversing.", repair_cost=900,
        at_fault=True, third_party_involved=False, third_party_identified=False,
        documents_provided=["photos", "repair_quote"], exclusion_signal=None,
    )
    return system.create_claim(**(facts | overrides))


# --------------------------------------------------------------- good agent
def test_get_policy(system):
    p = system.get_policy(policy_id="VER-1002", claim_ref="T-1")
    assert p["holder_name"] == "Lucas Bernard"
    assert p["licence_date"] == "2024-09-02"
    assert [c["code"] for c in p["coverages"]] == ["C1", "C2", "C3"]


def test_demo_a_not_at_fault(system):
    system.get_policy(policy_id="VER-1001", claim_ref="CLM-A")
    created = open_claim(
        system, claim_ref="CLM-A", policy_id="VER-1001", incident_date="2026-10-12",
        report_date="2026-10-14", repair_cost=1200, at_fault=False,
        third_party_involved=True, third_party_identified=True,
        documents_provided=["photos", "repair_quote", "accident_report"],
    )
    assert created["blocking_issues"] == []

    s = system.compute_settlement(claim_ref="CLM-A")
    assert (s["deductible_eur"], s["payout_eur"], s["assessor_required"]) == (0, 1200, False)

    staged = system.stage_settlement(claim_ref="CLM-A")
    assert staged["status"] == "pending_approval"


def test_demo_b_young_driver_with_assessor(system):
    open_claim(
        system, claim_ref="CLM-B", policy_id="VER-1002", incident_date="2026-10-14",
        report_date="2026-10-15", repair_cost=2400, at_fault=True,
        third_party_involved=True, third_party_identified=True,
        documents_provided=["photos", "repair_quote", "accident_report"],
    )
    s = system.compute_settlement(claim_ref="CLM-B")
    assert (s["deductible_eur"], s["payout_eur"], s["assessor_required"]) == (700, 1700, True)
    assert s["years_licensed_on_incident_date"] == 2

    # The assessor must be booked before the payment can be prepared
    with pytest.raises(ToolRefused, match="assessor"):
        system.stage_settlement(claim_ref="CLM-B")
    visit = system.schedule_assessor(claim_ref="CLM-B")
    assert visit["assessor_visit_date"] == "2026-10-18"
    assert system.stage_settlement(claim_ref="CLM-B")["status"] == "pending_approval"


def test_demo_c_theft_late_without_police_report(system):
    created = open_claim(
        system, claim_ref="CLM-C", policy_id="VER-1003", coverage="C4",
        incident_date="2026-10-15", report_date="2026-10-19", repair_cost=0,
        at_fault=False, documents_provided=[],
    )
    assert created["checks"]["reported_on_time"] is False
    assert created["checks"]["missing_documents"] == ["police_report"]
    assert created["blocking_issues"] == ["late_report", "missing_document:police_report"]

    system.request_documents(claim_ref="CLM-C", documents=["police_report"],
                             message_to_customer="Please send the police report.")
    out = system.escalate_to_handler(claim_ref="CLM-C", reasons=["late_report"],
                                     summary="Theft reported 4 days after discovery.")
    assert out["status"] == "escalated"
    assert system.get_claim("CLM-C")["status"] == "escalated"


def test_human_approval_is_the_last_step(system):
    open_claim(system)
    system.compute_settlement(claim_ref="T-1")
    system.stage_settlement(claim_ref="T-1")
    approved = system.approve_settlement("T-1", handler_name="Aziz")
    assert approved["status"] == "approved"


# ---------------------------------------------------------------- bad agent
def test_cannot_compute_settlement_with_blocking_issues(system):
    open_claim(system, exclusion_signal="alcohol")
    with pytest.raises(ToolRefused, match="blocking issues"):
        system.compute_settlement(claim_ref="T-1")


def test_cannot_stage_an_escalated_claim(system):
    open_claim(system, report_date="2026-10-20")  # late
    system.escalate_to_handler(claim_ref="T-1", reasons=["late_report"], summary="Late.")
    with pytest.raises(ToolRefused, match="Refused"):
        system.stage_settlement(claim_ref="T-1")


def test_cannot_stage_without_computing_first(system):
    open_claim(system)
    with pytest.raises(ToolRefused, match="compute_settlement"):
        system.stage_settlement(claim_ref="T-1")


def test_no_assessor_when_not_needed(system):
    open_claim(system, repair_cost=1500)
    system.compute_settlement(claim_ref="T-1")
    with pytest.raises(ToolRefused, match="No assessor needed"):
        system.schedule_assessor(claim_ref="T-1")


def test_coverage_not_bought_is_blocking(system):
    created = open_claim(system, coverage="C3")  # VER-1004 has no glass cover
    assert "coverage_not_in_schedule" in created["blocking_issues"]


@pytest.mark.parametrize("overrides, message", [
    (dict(policy_id="VER-9999"), "Unknown policy"),
    (dict(coverage="C9"), "coverage must be"),
    (dict(incident_date="03/10/2026"), "YYYY-MM-DD"),
    (dict(report_date="2026-10-01"), "before incident_date"),
    (dict(documents_provided=["selfie"]), "Unknown document"),
    (dict(third_party_identified=True), "third_party_involved"),
])
def test_bad_inputs_are_refused_with_a_clear_message(system, overrides, message):
    with pytest.raises(ToolRefused, match=message):
        open_claim(system, **overrides)


def test_duplicate_claim_is_refused(system):
    open_claim(system)
    with pytest.raises(ToolRefused, match="already exists"):
        open_claim(system)


def test_approve_is_impossible_before_staging(system):
    open_claim(system)
    with pytest.raises(ToolRefused, match="not pending approval"):
        system.approve_settlement("T-1", handler_name="Aziz")


# -------------------------------------------------------------- audit trail
def test_every_call_is_logged_including_refusals(system):
    open_claim(system, exclusion_signal="racing")
    with pytest.raises(ToolRefused):
        system.stage_settlement(claim_ref="T-1")
    log = system.action_log("T-1")
    assert [(e["tool"], e["ok"]) for e in log] == [("create_claim", True), ("stage_settlement", False)]
    assert "Refused" in log[1]["result"]["error"]
    assert log[0]["arguments"]["exclusion_signal"] == "racing"


@pytest.mark.parametrize("order", ["request_first", "escalate_first"])
def test_escalation_wins_whatever_the_order(system, order):
    """Found in trial3: parallel calls lost the escalation (race condition)."""
    open_claim(system, coverage="C4", report_date="2026-10-09", documents_provided=[])
    request = lambda: system.request_documents(  # noqa: E731
        claim_ref="T-1", documents=["police_report"], message_to_customer="Please send it.")
    escalate = lambda: system.escalate_to_handler(  # noqa: E731
        claim_ref="T-1", reasons=["late_report"], summary="Late theft report.")
    for call in ((request, escalate) if order == "request_first" else (escalate, request)):
        call()
    assert system.get_claim("T-1")["status"] == "escalated"


def test_parallel_request_and_escalate(system):
    """Fire both tools at the same time from two threads, many times."""
    from concurrent.futures import ThreadPoolExecutor

    for i in range(20):
        ref = f"P-{i}"
        open_claim(system, claim_ref=ref, coverage="C4", report_date="2026-10-09", documents_provided=[])
        with ThreadPoolExecutor(max_workers=2) as pool:
            pool.submit(system.request_documents, claim_ref=ref, documents=["police_report"],
                        message_to_customer="Please send it.")
            pool.submit(system.escalate_to_handler, claim_ref=ref, reasons=["late_report"], summary="Late.")
        assert system.get_claim(ref)["status"] == "escalated", ref


def test_computing_after_escalating_keeps_the_claim_escalated(system):
    """Found by the memory experiment (v2): the agent referred a clean claim because
    of a playbook rule, then computed the amounts for the handler. That call used to
    reset the status to settlement_computed, which would have let it be staged."""
    open_claim(system)  # a clean claim, no blocking issues
    system.escalate_to_handler(claim_ref="T-1", reasons=["other"], summary="Playbook rule.")
    s = system.compute_settlement(claim_ref="T-1")
    assert s["payout_eur"] == 600
    claim = system.get_claim("T-1")
    assert claim["status"] == "escalated" and claim["payout"] == 600  # figures kept for the handler
    with pytest.raises(ToolRefused, match="Refused"):
        system.stage_settlement(claim_ref="T-1")
    with pytest.raises(ToolRefused):
        system.schedule_assessor(claim_ref="T-1")



def test_c1_is_refused_with_a_way_to_correct_it(system):
    """Found twice (trial2, robustness v1): a collision with a named other driver recorded as C1
    staged €2,400 with no deductible instead of €1,700. The tool now refuses C1."""
    with pytest.raises(ToolRefused, match="use C2 for collision damage to the insured car"):
        open_claim(system, coverage="C1")
    assert open_claim(system, coverage="C2")["status"] == "open"  # the agent corrects itself
