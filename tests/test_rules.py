"""Tests for the business rules: one test per article of the contract.

Run:  uv run pytest
"""

from datetime import date

import pytest

from core.rules import (
    Claim,
    Coverage,
    Decision,
    Policy,
    compute_settlement,
    expected_outcome,
    full_years_between,
)

C2, C3, C4 = Coverage.COLLISION, Coverage.GLASS, Coverage.THEFT


def settle(coverage, repair=1000, value=10000, at_fault=True, tp_identified=False, years=10):
    return compute_settlement(coverage, repair, value, at_fault, tp_identified, years)


# --- Article 2 & 5: deductibles ----------------------------------------------
def test_collision_standard_deductible():
    s = settle(C2, repair=900)
    assert (s.deductible, s.payout) == (300, 600)


def test_not_at_fault_waiver():
    s = settle(C2, repair=1200, at_fault=False, tp_identified=True)
    assert (s.deductible, s.payout) == (0, 1200)


def test_waiver_needs_identified_third_party():
    s = settle(C2, repair=1200, at_fault=False, tp_identified=False)
    assert s.deductible == 300


def test_young_driver_surcharge():
    s = settle(C2, repair=2400, years=2)
    assert (s.deductible, s.payout) == (700, 1700)


def test_waiver_also_removes_young_driver_surcharge():
    s = settle(C2, repair=1100, at_fault=False, tp_identified=True, years=1)
    assert s.deductible == 0


def test_glass_deductible():
    assert settle(C3, repair=480).payout == 430


@pytest.mark.parametrize("value, deductible", [(32000, 3200), (9000, 900), (2200, 500)])
def test_theft_ten_percent_with_minimum(value, deductible):
    s = settle(C4, value=value)
    assert (s.deductible, s.payout) == (deductible, value - deductible)


# --- Article 6: cap and assessor ---------------------------------------------
def test_payout_capped_at_market_value():
    s = settle(C2, repair=2600, value=2200)
    assert s.payout == 2200 - 300


def test_payout_never_negative():
    assert settle(C2, repair=200).payout == 0


@pytest.mark.parametrize("repair, required", [(1500, False), (1501, True)])
def test_assessor_threshold_is_strictly_above_1500(repair, required):
    assert settle(C2, repair=repair).assessor_required is required


def test_no_assessor_for_theft():
    assert settle(C4, value=32000).assessor_required is False


def test_licence_years_counts_complete_years():
    assert full_years_between(date(2024, 9, 2), date(2026, 9, 1)) == 1
    assert full_years_between(date(2024, 9, 2), date(2026, 9, 2)) == 2


# --- Articles 4 & 7: decisions -------------------------------------------------
POLICY = Policy("P1", "Test", "Car", 10000, date(2010, 1, 1), (Coverage.THIRD_PARTY, C2, C4))


def claim(**overrides):
    base = dict(
        claim_ref="T", policy_id="P1", coverage=C2,
        incident_date=date(2026, 10, 1), report_date=date(2026, 10, 2),
        repair_cost=900, at_fault=True, third_party_involved=False,
        third_party_identified=False, documents_provided=("photos", "repair_quote"),
    )
    return Claim(**(base | overrides))


def test_clean_claim_is_settled_and_staged():
    o = expected_outcome(claim(), POLICY)
    assert o.decision == Decision.SETTLE
    assert o.expected_actions[-1] == "stage_settlement"
    assert o.forbidden_actions == []


def test_missing_document_is_requested_not_settled():
    o = expected_outcome(claim(documents_provided=("repair_quote",)), POLICY)
    assert o.decision == Decision.REQUEST_DOCUMENTS
    assert o.missing_documents == ["photos"]
    assert "stage_settlement" in o.forbidden_actions


def test_accident_report_required_when_third_party_involved():
    o = expected_outcome(claim(third_party_involved=True, third_party_identified=True), POLICY)
    assert o.missing_documents == ["accident_report"]


@pytest.mark.parametrize("overrides, reason", [
    (dict(report_date=date(2026, 10, 9)), "late_report"),
    (dict(exclusion_signal="alcohol"), "possible_exclusion:alcohol"),
    (dict(coverage=C3), "coverage_not_in_schedule"),
])
def test_escalations_never_refuse(overrides, reason):
    o = expected_outcome(claim(**overrides), POLICY)
    assert o.decision == Decision.ESCALATE
    assert reason in o.escalation_reasons
    assert "stage_settlement" in o.forbidden_actions
    assert o.settlement is None


def test_theft_deadline_is_two_days():
    on_time = claim(coverage=C4, report_date=date(2026, 10, 3), documents_provided=("police_report",))
    late = claim(coverage=C4, report_date=date(2026, 10, 4), documents_provided=("police_report",))
    assert expected_outcome(on_time, POLICY).decision == Decision.SETTLE
    assert expected_outcome(late, POLICY).escalation_reasons == ["late_report"]
