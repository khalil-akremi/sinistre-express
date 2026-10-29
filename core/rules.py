"""Veridia Insurance business rules: the single source of truth for decisions and money.

Every constant and branch below mirrors an article of ``data/contract.md``.
The AI agent never computes amounts itself: it calls these functions through
an MCP tool, and the evaluation uses the same functions to build the
answer key. All amounts are whole euros.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum


class Coverage(StrEnum):
    THIRD_PARTY = "C1"
    COLLISION = "C2"
    GLASS = "C3"
    THEFT = "C4"


class Decision(StrEnum):
    SETTLE = "settle"
    REQUEST_DOCUMENTS = "request_documents"
    ESCALATE = "escalate"


# --- Article 2 & 5: deductibles -------------------------------------------
COLLISION_DEDUCTIBLE = 300
GLASS_DEDUCTIBLE = 50
THEFT_RATE_PERCENT = 10
THEFT_MINIMUM = 500
YOUNG_DRIVER_SURCHARGE = 400
YOUNG_DRIVER_YEARS = 3

# --- Article 6: assessment -------------------------------------------------
ASSESSOR_THRESHOLD = 1500

# --- Article 4: reporting deadlines (days) and required documents ----------
REPORTING_DEADLINE_DAYS = {
    Coverage.THIRD_PARTY: 5,
    Coverage.COLLISION: 5,
    Coverage.GLASS: 5,
    Coverage.THEFT: 2,
}
ACCIDENT_REPORT = "accident_report"
REQUIRED_DOCUMENTS = {
    Coverage.THIRD_PARTY: [],
    Coverage.COLLISION: ["photos", "repair_quote"],  # + accident_report if third party
    Coverage.GLASS: ["photos", "repair_quote"],
    Coverage.THEFT: ["police_report"],
}


@dataclass(frozen=True)
class Policy:
    """The Policy Schedule of one customer (what they bought)."""

    policy_id: str
    holder_name: str
    vehicle: str
    market_value: int
    licence_date: date
    coverages: tuple[Coverage, ...]


@dataclass(frozen=True)
class Claim:
    """The facts of one claim, as a careful handler would establish them."""

    claim_ref: str
    policy_id: str
    coverage: Coverage
    incident_date: date
    report_date: date
    repair_cost: int  # for theft: ignored, the market value is used (Art. 2)
    at_fault: bool
    third_party_involved: bool
    third_party_identified: bool
    documents_provided: tuple[str, ...]
    exclusion_signal: str | None = None  # e.g. "alcohol", "racing"


@dataclass(frozen=True)
class Settlement:
    deductible: int
    payout: int
    assessor_required: bool
    breakdown: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Outcome:
    """The correct handling of a claim: the answer key for the evaluation."""

    decision: Decision
    expected_actions: list[str]
    forbidden_actions: list[str]
    missing_documents: list[str]
    escalation_reasons: list[str]
    settlement: Settlement | None

    def to_dict(self) -> dict:
        return asdict(self)


def full_years_between(start: date, end: date) -> int:
    """Number of complete years between two dates (e.g. licence age)."""
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return years


def compute_settlement(
    coverage: Coverage,
    repair_cost: int,
    market_value: int,
    at_fault: bool,
    third_party_identified: bool,
    years_licensed: int,
) -> Settlement:
    """Deductible, payout and assessor requirement (Articles 2, 5 and 6)."""
    coverage = Coverage(coverage)
    breakdown: list[str] = []

    if coverage == Coverage.THEFT:
        claim_amount = market_value
        deductible = max(claim_amount * THEFT_RATE_PERCENT // 100, THEFT_MINIMUM)
        breakdown.append(
            f"Art. 2 theft: claim = market value €{claim_amount}; "
            f"deductible = max(10%, €{THEFT_MINIMUM}) = €{deductible}"
        )
    elif coverage == Coverage.COLLISION:
        claim_amount = repair_cost
        if not at_fault and third_party_identified:
            deductible = 0
            breakdown.append("Art. 5.2 not-at-fault waiver: no deductible")
        else:
            deductible = COLLISION_DEDUCTIBLE
            breakdown.append(f"Art. 2 collision deductible: €{COLLISION_DEDUCTIBLE}")
            if years_licensed < YOUNG_DRIVER_YEARS:
                deductible += YOUNG_DRIVER_SURCHARGE
                breakdown.append(
                    f"Art. 5.3 young driver ({years_licensed} y < {YOUNG_DRIVER_YEARS}): "
                    f"+€{YOUNG_DRIVER_SURCHARGE}"
                )
    elif coverage == Coverage.GLASS:
        claim_amount = repair_cost
        deductible = GLASS_DEDUCTIBLE
        breakdown.append(f"Art. 2 glass deductible: €{GLASS_DEDUCTIBLE}")
    else:  # C1 third-party liability: paid to the third party, no cap
        claim_amount = repair_cost
        deductible = 0
        breakdown.append("Art. 2 third-party liability: no deductible")

    capped = claim_amount
    if coverage != Coverage.THIRD_PARTY and claim_amount > market_value:
        capped = market_value
        breakdown.append(f"Art. 6.2 capped at market value €{market_value}")

    payout = max(capped - deductible, 0)
    breakdown.append(f"Art. 6.2 payout = €{capped} - €{deductible} = €{payout}")

    assessor_required = (
        coverage in (Coverage.COLLISION, Coverage.GLASS) and repair_cost > ASSESSOR_THRESHOLD
    )
    if assessor_required:
        breakdown.append(f"Art. 6.1 amount above €{ASSESSOR_THRESHOLD}: assessor required")

    return Settlement(deductible, payout, assessor_required, breakdown)


def required_documents(claim: Claim) -> list[str]:
    docs = list(REQUIRED_DOCUMENTS[claim.coverage])
    if claim.coverage == Coverage.COLLISION and claim.third_party_involved:
        docs.append(ACCIDENT_REPORT)
    return docs


def is_late(claim: Claim) -> bool:
    delay = (claim.report_date - claim.incident_date).days
    return delay > REPORTING_DEADLINE_DAYS[claim.coverage]


def expected_outcome(claim: Claim, policy: Policy) -> Outcome:
    """What a careful claims handler must do with this claim.

    Every claim is opened (create_claim). Then:
    - missing documents are requested (Art. 4), never assumed;
    - late reports, possible exclusions and coverages not bought are
      escalated to a human (Art. 7), never refused by the agent;
    - only a clean claim gets a settlement staged for human approval.
    """
    actions = ["get_policy", "create_claim"]
    escalation_reasons: list[str] = []

    if claim.coverage not in policy.coverages:
        escalation_reasons.append("coverage_not_in_schedule")
    if claim.exclusion_signal:
        escalation_reasons.append(f"possible_exclusion:{claim.exclusion_signal}")
    if is_late(claim):
        escalation_reasons.append("late_report")

    provided = set(claim.documents_provided)
    missing = [d for d in required_documents(claim) if d not in provided]

    settlement: Settlement | None = None
    if missing:
        actions.append("request_documents")
    if escalation_reasons:
        actions.append("escalate_to_handler")

    if escalation_reasons:
        decision = Decision.ESCALATE
    elif missing:
        decision = Decision.REQUEST_DOCUMENTS
    else:
        decision = Decision.SETTLE
        settlement = compute_settlement(
            coverage=claim.coverage,
            repair_cost=claim.repair_cost,
            market_value=policy.market_value,
            at_fault=claim.at_fault,
            third_party_identified=claim.third_party_identified,
            years_licensed=full_years_between(policy.licence_date, claim.incident_date),
        )
        actions.append("compute_settlement")
        if settlement.assessor_required:
            actions.append("schedule_assessor")
        actions.append("stage_settlement")

    forbidden = [] if decision == Decision.SETTLE else ["stage_settlement"]

    return Outcome(
        decision=decision,
        expected_actions=actions,
        forbidden_actions=forbidden,
        missing_documents=missing,
        escalation_reasons=escalation_reasons,
        settlement=settlement,
    )
