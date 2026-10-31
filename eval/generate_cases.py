"""Generate the synthetic world: customers, claims and the answer key.

Run:  uv run python -m eval.generate_cases

Writes:
- data/customers.json  the Policy Schedules (what each customer bought)
- data/cases.json      the claims: the customer email the agent receives,
                       the true facts, and the expected outcome

Everything is fictional. The expected outcome of each claim is computed by
core.rules, the same code the agent's MCP tool uses, so the answer key and
the product can never disagree.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

from core.rules import Claim, Coverage, Policy, expected_outcome

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

C1, C2, C3, C4 = Coverage.THIRD_PARTY, Coverage.COLLISION, Coverage.GLASS, Coverage.THEFT

# --- Policy Schedules --------------------------------------------------------
POLICIES = [
    Policy("VER-1001", "Claire Martin", "Peugeot 208 (2021)", 14000, date(2012, 5, 14), (C1, C2, C3, C4)),
    Policy("VER-1002", "Lucas Bernard", "Renault Clio (2023)", 16500, date(2024, 9, 2), (C1, C2, C3)),
    Policy("VER-1003", "Ines Haddad", "Toyota Yaris (2019)", 9000, date(2015, 3, 20), (C1, C2, C3, C4)),
    Policy("VER-1004", "Thomas Petit", "Volkswagen Golf (2020)", 15500, date(2008, 11, 1), (C1, C2)),
    Policy("VER-1005", "Sarah Lefebvre", "Citroen C3 (2014)", 2200, date(2010, 6, 30), (C1, C2, C3, C4)),
    Policy("VER-1006", "Yanis Moreau", "Dacia Sandero (2022)", 11000, date(2025, 1, 15), (C1, C2, C4)),
    Policy("VER-1007", "Emma Rousseau", "Tesla Model 3 (2023)", 32000, date(2011, 4, 8), (C1, C2, C3, C4)),
    Policy("VER-1008", "Hugo Garcia", "Fiat 500 (2018)", 6500, date(2019, 7, 22), (C1, C3)),
]
POLICY_BY_ID = {p.policy_id: p for p in POLICIES}

ALL_C2_DOCS = ("photos", "repair_quote")
ALL_C2_TP_DOCS = ("photos", "repair_quote", "accident_report")


@dataclass(frozen=True)
class Scenario:
    """One test case: the facts plus the customer's own words."""

    case_id: str
    title: str
    policy_id: str
    coverage: Coverage
    incident: date
    delay_days: int
    story: str  # what happened, in the customer's words
    repair_cost: int = 0
    at_fault: bool = True
    third_party_involved: bool = False
    third_party_identified: bool = False
    documents: tuple[str, ...] = ()
    exclusion_signal: str | None = None
    demo: bool = False


D = date(2026, 10, 1)


def day(n: int) -> date:
    return D + timedelta(days=n - 1)


SCENARIOS = [
    # ---- The three demo cases -------------------------------------------
    Scenario("CLM-A", "Demo A: not at fault, simple", "VER-1001", C2, day(12), 2,
             "A van ran a red light and hit the side of my car at the Rue de Rivoli crossing. "
             "The van driver, Mr. Dubois, admitted it was his fault and we both signed the accident report.",
             repair_cost=1200, at_fault=False, third_party_involved=True, third_party_identified=True,
             documents=ALL_C2_TP_DOCS, demo=True),
    Scenario("CLM-B", "Demo B: at fault, young driver, assessor", "VER-1002", C2, day(14), 1,
             "I misjudged the distance while changing lanes on the ring road and hit the car next to me. "
             "It was my fault. The other driver, Ms. Laurent, and I signed the accident report.",
             repair_cost=2400, at_fault=True, third_party_involved=True, third_party_identified=True,
             documents=ALL_C2_TP_DOCS, demo=True),
    Scenario("CLM-C", "Demo C: theft, late, no police report", "VER-1003", C4, day(15), 4,
             "My car was stolen from the street in front of my building. I was travelling and only "
             "had time to write to you now. I have not been to the police yet.",
             documents=(), demo=True),
    # ---- Clean settlements ------------------------------------------------
    Scenario("CLM-01", "At fault, single vehicle", "VER-1004", C2, day(3), 1,
             "While reversing out of a parking space I hit a concrete pillar. Nobody else was involved.",
             repair_cost=900, documents=ALL_C2_DOCS),
    Scenario("CLM-02", "At fault, young driver", "VER-1006", C2, day(4), 2,
             "I braked too late at a roundabout and hit the car in front of me. It was my fault; "
             "the other driver, Mr. Henry, and I filled in the accident report together.",
             repair_cost=1300, third_party_involved=True, third_party_identified=True,
             documents=ALL_C2_TP_DOCS),
    Scenario("CLM-03", "Not at fault, large repair", "VER-1007", C2, day(5), 1,
             "My car was parked when a delivery truck reversed into it. The truck driver, Mr. Costa, "
             "accepted responsibility and signed the accident report with me.",
             repair_cost=4800, at_fault=False, third_party_involved=True, third_party_identified=True,
             documents=ALL_C2_TP_DOCS),
    Scenario("CLM-04", "Repair above market value", "VER-1005", C2, day(6), 3,
             "I skidded on a wet road and went into a ditch. No other vehicle was involved.",
             repair_cost=2600, documents=ALL_C2_DOCS),
    Scenario("CLM-05", "Not at fault beats young driver", "VER-1006", C2, day(7), 1,
             "Someone opened their car door into my car as I drove past. The driver, Ms. Nguyen, "
             "admitted fault and signed the accident report.",
             repair_cost=1100, at_fault=False, third_party_involved=True, third_party_identified=True,
             documents=ALL_C2_TP_DOCS),
    Scenario("CLM-06", "Repair exactly at the assessor threshold", "VER-1004", C2, day(8), 2,
             "I hit the car in front of me in a traffic jam. My fault. Mr. Blanc and I signed the "
             "accident report.",
             repair_cost=1500, third_party_involved=True, third_party_identified=True,
             documents=ALL_C2_TP_DOCS),
    Scenario("CLM-07", "Glass breakage", "VER-1001", C3, day(9), 1,
             "A stone thrown up by a truck on the motorway cracked my windscreen.",
             repair_cost=480, documents=("photos", "repair_quote")),
    Scenario("CLM-08", "Glass breakage, small", "VER-1008", C3, day(10), 2,
             "My rear side window was smashed overnight. Nothing was taken from the car.",
             repair_cost=320, documents=("photos", "repair_quote")),
    Scenario("CLM-09", "Theft, high value", "VER-1007", C4, day(11), 1,
             "My car was stolen from a public car park last night. I filed a complaint at the police "
             "station this morning.",
             documents=("police_report",)),
    Scenario("CLM-10", "Theft, standard", "VER-1003", C4, day(16), 1,
             "My car disappeared from the supermarket car park. I went to the police the same day.",
             documents=("police_report",)),
    Scenario("CLM-11", "Theft, minimum deductible", "VER-1005", C4, day(17), 2,
             "My old car was stolen from my street. The police report is attached.",
             documents=("police_report",)),
    # ---- Missing documents ------------------------------------------------
    Scenario("CLM-12", "Missing photos", "VER-1004", C2, day(18), 1,
             "I scraped a low wall while parking. Nobody else involved. I forgot to take photos.",
             repair_cost=700, documents=("repair_quote",)),
    Scenario("CLM-13", "Missing repair quote", "VER-1001", C3, day(19), 1,
             "My windscreen cracked during a cold night. I will get a quote from the garage soon.",
             documents=("photos",)),
    Scenario("CLM-14", "Missing accident report", "VER-1007", C2, day(20), 2,
             "A motorbike scratched my car in slow traffic. The rider, Mr. Leroy, admitted it but we "
             "did not have an accident report form with us.",
             repair_cost=1250, at_fault=False, third_party_involved=True, third_party_identified=True,
             documents=ALL_C2_DOCS),
    # ---- Escalations -------------------------------------------------------
    Scenario("CLM-15", "Late report", "VER-1001", C2, day(2), 9,
             "I hit a bollard while parking. Nobody else was involved. "
             "I was too busy with work to report it earlier, sorry for the delay.",
             repair_cost=650, documents=ALL_C2_DOCS),
    Scenario("CLM-16", "Possible exclusion: alcohol", "VER-1004", C2, day(21), 1,
             "Coming back from a friend's birthday party, where I had a few drinks, I lost control "
             "and hit a fence. No one else was involved.",
             repair_cost=1800, documents=ALL_C2_DOCS, exclusion_signal="alcohol"),
    Scenario("CLM-17", "Possible exclusion: track day", "VER-1007", C2, day(22), 1,
             "I took my car to a track day at a racing circuit and hit the tyre barrier in a corner.",
             repair_cost=5200, documents=ALL_C2_DOCS, exclusion_signal="racing"),
    Scenario("CLM-18", "Coverage not bought: theft", "VER-1002", C4, day(23), 1,
             "My car was stolen from the train station car park. I filed a police report.",
             documents=("police_report",)),
    Scenario("CLM-19", "Coverage not bought: glass", "VER-1004", C3, day(24), 1,
             "A stone cracked my windscreen on the motorway.",
             repair_cost=450, documents=("photos", "repair_quote")),
    Scenario("CLM-20", "Late theft report", "VER-1006", C4, day(25), 3,
             "My car was stolen three days ago. I was in shock and only went to the police yesterday; "
             "the report is attached.",
             documents=("police_report",)),
]

DOC_FILENAMES = {
    "photos": "damage_photos.zip",
    "repair_quote": "repair_quote.pdf",
    "accident_report": "accident_report_signed.pdf",
    "police_report": "police_report.pdf",
}


def render_email(s: Scenario, policy: Policy) -> dict:
    """The customer's email: the only thing the agent receives (plus files)."""
    report_date = s.incident + timedelta(days=s.delay_days)
    kind = {C2: "accident", C3: "broken glass", C4: "theft"}.get(s.coverage, "claim")
    lines = [
        "Hello Veridia,",
        "",
        f"I am writing to report {'an' if kind[0] in 'aeiou' else 'a'} {kind} that happened on {s.incident:%d %B %Y}.",
        s.story,
    ]
    if s.repair_cost and s.coverage in (C2, C3) and "repair_quote" in s.documents:
        lines.append(f"The garage quoted €{s.repair_cost:,} to repair my car.")
    lines += [
        "",
        "Kind regards,",
        policy.holder_name,
        f"Policy number: {policy.policy_id}",
    ]
    attachments = [DOC_FILENAMES[d] for d in s.documents]
    if attachments:
        lines += ["", "Attached: " + ", ".join(attachments)]
    return {
        "date": report_date.isoformat(),
        "from": policy.holder_name,
        "subject": f"Claim - {kind} - {policy.policy_id}",
        "body": "\n".join(lines),
        "attachments": attachments,
    }


def build_case(s: Scenario) -> dict:
    policy = POLICY_BY_ID[s.policy_id]
    claim = Claim(
        claim_ref=s.case_id,
        policy_id=s.policy_id,
        coverage=s.coverage,
        incident_date=s.incident,
        report_date=s.incident + timedelta(days=s.delay_days),
        repair_cost=s.repair_cost,
        at_fault=s.at_fault,
        third_party_involved=s.third_party_involved,
        third_party_identified=s.third_party_identified,
        documents_provided=s.documents,
        exclusion_signal=s.exclusion_signal,
    )
    return {
        "case_id": s.case_id,
        "title": s.title,
        "demo": s.demo,
        "email": render_email(s, policy),
        "facts": _jsonable(asdict(claim)),
        "expected": _jsonable(expected_outcome(claim, policy).to_dict()),
    }


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    customers = [_jsonable(asdict(p)) for p in POLICIES]
    cases = [build_case(s) for s in SCENARIOS]
    (DATA_DIR / "customers.json").write_text(json.dumps(customers, indent=2, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "cases.json").write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{len(customers)} customers, {len(cases)} cases written to {DATA_DIR}")
    for c in cases:
        e = c["expected"]
        s = e["settlement"]
        money = f"deductible €{s['deductible']}, payout €{s['payout']}" if s else "-"
        print(f"  {c['case_id']:7} {e['decision']:18} {money:34} {', '.join(e['escalation_reasons'] + e['missing_documents'])}")


if __name__ == "__main__":
    main()
