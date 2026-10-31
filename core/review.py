"""The Reviewer: a second, independent agent that checks a prepared payment.

The Handler agent prepares a claim; before a person can approve the payment,
the Reviewer re-reads the sources (customer email, attached documents, the
contract, the playbook) and checks the facts the Handler recorded and the
decision to pay.

Design choices
- Read-only: the Reviewer has no claims-system tools. It returns a verdict only.
- Independent: it does not see the Handler's report or reasoning, only what
  the Handler recorded in the system, so it cannot be anchored by it.
- It checks the facts, not the arithmetic: amounts are computed by tested code
  from the facts, so a wrong amount always comes from a wrong fact or a wrong
  decision to pay.
- It runs on a different model provider than the Handler, so the two are less
  likely to make the same mistake.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

FACT_LABELS = {
    "policy_id": "policy number", "coverage": "coverage (C1 third party, C2 collision, C3 glass, C4 theft)",
    "incident_date": "incident date", "report_date": "date the claim was reported (email date)",
    "repair_cost": "repair cost in EUR", "at_fault": "policyholder at fault",
    "third_party_involved": "a third party was involved", "third_party_identified": "the third party is identified",
    "documents_provided": "documents counted as provided", "exclusion_signal": "possible exclusion flagged",
}

REVIEW_TASK = """You are the Veridia claims reviewer. Another agent prepared the claim below and staged a \
payment. A person will approve or refuse it after reading your review. You cannot change anything.

Check it against the sources: the customer email, the attached documents (open each one with read_file), \
the Veridia contract (search it) and the handler playbook.

1. Each recorded fact against the email and the documents: dates, coverage, repair cost (the total \
including VAT on the quote, contract Article 1), fault, third party involved and identified, documents \
counted as provided (each must belong to this policyholder and vehicle), any sign of an exclusion.
2. Whether the claim should be paid at all: reporting deadline, exclusions, coverage in the Policy \
Schedule, required documents, playbook rules. A playbook rule that says to refer a claim to a handler \
means the claim must not be paid automatically: if such a rule applies, that is a concern. Apply a \
playbook rule only when the email or the documents state the facts that trigger it.
Do not redo the arithmetic: the claims system computes the amounts from the recorded facts.

Answer with JSON only. Give one check for EVERY recorded fact listed below (use its key as "field"), \
then one check of the decision to pay. Set "match" to false only for a specific difference you can point \
to in a source:
{{"checks": [{{"field": "repair_cost", "recorded": "...", "sources_say": "...", "match": true or false, \
"evidence": "where you saw it"}}, ...one per fact...],
 "payment": {{"should_be_paid": true or false, "evidence": "deadline, exclusions, coverage, documents, playbook"}},
 "summary": "one sentence for the person approving"}}

--- Customer email received on {date} ---
From: {sender}
Subject: {subject}

{body}
--- End of email ---

{attachments}

Policy Schedule (from the claims system): {policy}

Handler playbook: {playbook}

Facts recorded by the handler agent:
{facts}

Result in the claims system: status {status}; deductible €{deductible}; payout €{payout}; \
assessor required: {assessor}{assessor_date}."""


def build_review_task(email: dict, policy: dict, created: dict, claim: dict, playbook_rules: list[str]) -> str:
    files = [Path(f).name for f in email.get("files") or []]
    parts = []
    if files:
        parts.append(f"Attached documents (open them): {', '.join(files)}.")
    if email.get("attachments"):
        parts.append(f"Also stored by the mailroom (cannot be opened, count as received): {', '.join(email['attachments'])}.")
    facts = "\n".join(f"- {k} ({FACT_LABELS[k]}): {json.dumps(created.get(k))}" for k in FACT_LABELS)
    return REVIEW_TASK.format(
        date=email["date"], sender=email["from"], subject=email["subject"], body=email["body"],
        attachments=" ".join(parts) or "No attachment.",
        policy=json.dumps({k: policy.get(k) for k in ("policy_id", "holder_name", "vehicle", "market_value_eur",
                                                      "licence_date", "coverages")}, ensure_ascii=False),
        playbook="; ".join(playbook_rules) if playbook_rules else "no rules.",
        facts=facts, status=claim.get("status"), deductible=claim.get("deductible"),
        payout=claim.get("payout"), assessor="yes" if claim.get("assessor_required") else "no",
        assessor_date=f" (booked {claim['assessor_date']})" if claim.get("assessor_date") else "",
    )


def parse_verdict(text: str | None) -> dict:
    """Turn the Reviewer's checks into a verdict. The model reads; this code decides.

    - any fact check with "match": false, or "should_be_paid": false -> concerns
    - a fact left unchecked -> concerns (the review is incomplete)
    - anything unreadable -> concerns: when in doubt, a person looks
    (The older {"verdict", "issues"} format is still accepted.)
    """
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    unreadable = {"verdict": "concerns", "issues": [], "checks": [], "unreadable": True,
                  "summary": "The review could not be read; check the claim manually."}
    if not isinstance(data, dict):
        return unreadable
    summary = str(data.get("summary") or "")

    if isinstance(data.get("checks"), list):
        checks = [c for c in data["checks"] if isinstance(c, dict) and "field" in c]
        issues = [{"field": c["field"], "recorded": c.get("recorded"), "should_be": c.get("sources_say"),
                   "evidence": c.get("evidence", "")} for c in checks if c.get("match") is False]
        payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
        if payment.get("should_be_paid") is False:
            issues.append({"field": "payment decision", "recorded": "payment staged", "should_be": "not paid",
                           "evidence": payment.get("evidence", "")})
        unchecked = [f for f in FACT_LABELS if f not in {c["field"] for c in checks}]
        if unchecked:
            issues.append({"field": "review incomplete", "recorded": ", ".join(unchecked),
                           "should_be": "checked", "evidence": "the Reviewer did not check these facts"})
        return {"verdict": "concerns" if issues else "approve", "issues": issues, "checks": checks,
                "summary": summary, "unreadable": False}

    if data.get("verdict") not in ("approve", "concerns"):
        return unreadable
    issues = [i for i in data.get("issues") or [] if isinstance(i, dict)]
    return {"verdict": "concerns" if issues else data["verdict"], "issues": issues, "checks": [],
            "summary": summary, "unreadable": False}


def created_inputs(action_log: list[dict]) -> dict | None:
    """The facts the handler recorded: inputs of the first successful create_claim."""
    return next((e["arguments"] for e in action_log if e["tool"] == "create_claim" and e["ok"]), None)
