"""Generate the Reviewer's test set: prepared claims, half with a planted mistake.

Run:  uv run python -m eval.generate_review_cases

Each file is a real claim prepared with our claims system (in a temporary
database), exactly as the Handler agent would leave it: payment staged,
waiting for a person. 8 files contain a mistake a careless agent could make;
8 are correct. A good Reviewer raises concerns on the first group and
approves the second. Writes data/review_cases.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mcp_server.tools import ClaimsSystem

ROOT = Path(__file__).resolve().parent.parent

# (review id, source claim, mistake or None, field the mistake is in, changed facts)
PLAN = [
    ("R-01", "DOC-04", "Took the email's rough amount (€900) instead of the written quote (€1,640).",
     "repair_cost", {"repair_cost": 900}),
    ("R-02", "DOC-01", "Recorded the policyholder as not at fault; the signed report says he is.",
     "at_fault", {"at_fault": False}),
    ("R-03", "DOC-05", "Accepted a repair quote made out to another person and another car.",
     "documents_provided", {"documents_provided": ["photos", "repair_quote"], "repair_cost": 980}),
    ("R-04", "DOC-02", "Ignored the playbook: the other vehicle is a company van, the claim should be referred.",
     "decision", {}),
    ("R-05", "CLM-16", "Missed a possible exclusion: the customer says he had a few drinks before driving.",
     "exclusion_signal", {"exclusion_signal": None}),
    ("R-06", "CLM-15", "Recorded a wrong report date, hiding a late report (9 days after the incident).",
     "report_date", {"report_date": "2026-10-03"}),
    ("R-07", "CLM-05", "Recorded the other driver as not identified, so the not-at-fault waiver was lost.",
     "third_party_identified", {"third_party_identified": False}),
    ("R-08", "DOC-03", "Recorded a windscreen claim as collision (C2) instead of glass (C3).",
     "coverage", {"coverage": "C2"}),
    ("R-09", "DOC-01", None, None, {}),
    ("R-10", "DOC-03", None, None, {}),
    ("R-11", "DOC-04", None, None, {}),
    ("R-12", "DOC-06", None, None, {}),
    ("R-13", "CLM-B", None, None, {}),
    ("R-14", "CLM-08", None, None, {}),
    ("R-15", "CLM-01", None, None, {}),
    ("R-16", "CLM-06", None, None, {}),
]


def prepare(system: ClaimsSystem, ref: str, facts: dict) -> tuple[dict, dict, dict]:
    """Prepare and stage a payment like the Handler agent; return (policy, create_claim inputs, claim)."""
    policy = system.get_policy(policy_id=facts["policy_id"], claim_ref=ref)
    created = {k: facts[k] for k in ("policy_id", "coverage", "incident_date", "report_date", "repair_cost",
                                     "at_fault", "third_party_involved", "third_party_identified",
                                     "documents_provided", "exclusion_signal")}
    system.create_claim(claim_ref=ref, description="Prepared by the handler agent.", **created)
    settlement = system.compute_settlement(claim_ref=ref)
    if settlement["assessor_required"]:
        system.schedule_assessor(claim_ref=ref)
    system.stage_settlement(claim_ref=ref)
    return policy, created, system.get_claim(ref)


def main() -> None:
    sources = {c["case_id"]: c for name in ("cases.json", "doc_cases.json")
               for c in json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))}
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        system = ClaimsSystem(Path(tmp) / "review.db")
        for review_id, source_id, mistake, field, changes in PLAN:
            source = sources[source_id]
            facts = {k: v for k, v in source["facts"].items() if k != "ungraded"} | changes
            policy, created, claim = prepare(system, review_id, facts)
            out.append({"review_id": review_id, "source_case": source_id, "mistake": mistake, "field": field,
                        "expected_verdict": "concerns" if mistake else "approve",
                        "email": source["email"], "policy": policy, "created": created, "claim": claim})
            print(f"{review_id}  {source_id:7} payout €{claim['payout']:>6}  "
                  f"{'MISTAKE: ' + mistake if mistake else 'correct'}")
    (ROOT / "data" / "review_cases.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
