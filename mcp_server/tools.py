"""The claims system ("the kitchen"): the logic behind the 7 MCP tools.

Plain Python, no MCP and no AI here, so every tool can be tested on its own.
server.py only publishes these methods on the MCP "menu".

Design rule: the AI reads and judges, the code applies the rules.
- The agent extracts the facts from the customer's email and records them
  with create_claim.
- The code then checks deadlines, documents and coverage (core.rules), and
  computes every amount. The agent never does arithmetic.

Safety (defence in depth):
1. There is no approve tool: approve_settlement() exists for the human app
   only and is never published to the agent.
2. Tools refuse unsafe orders (e.g. staging a payment on a claim with a
   blocking issue) with a clear message telling the agent what to do instead.
3. Every call, including refused ones, is written to action_log.
"""

from __future__ import annotations

import functools
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from core import rules
from core.rules import Claim, Coverage
from mcp_server.db import connect, ensure_database

COVERAGE_NAMES = {
    "C1": "Third-party liability",
    "C2": "Collision damage",
    "C3": "Glass breakage",
    "C4": "Theft",
}
DOCUMENT_TYPES = ("photos", "repair_quote", "accident_report", "police_report")
ESCALATION_REASONS = (
    "late_report",
    "possible_exclusion",
    "coverage_not_in_schedule",
    "other",
)
ASSESSOR_DELAY_DAYS = 3


class ToolRefused(Exception):
    """An order the claims system will not execute. The message tells the
    agent why, and what to do instead."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolRefused(f"{field} must be a date in YYYY-MM-DD format, got {value!r}.") from None


def logged(func: Callable[..., dict]) -> Callable[..., dict]:
    """Write every call of a tool to action_log, whether it succeeds or not."""

    @functools.wraps(func)
    def wrapper(self: "ClaimsSystem", **kwargs: Any) -> dict:
        claim_ref = kwargs.get("claim_ref")
        try:
            result = func(self, **kwargs)
        except ToolRefused as exc:
            self._log(func.__name__, claim_ref, kwargs, ok=False, result={"error": str(exc)})
            raise
        self._log(func.__name__, claim_ref, kwargs, ok=True, result=result)
        return result

    return wrapper


class ClaimsSystem:
    """Veridia's claims system, backed by one SQLite file."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        ensure_database(self.db_path)

    # ------------------------------------------------------------------ helpers
    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def _log(self, tool: str, claim_ref: str | None, args: dict, ok: bool, result: dict) -> None:
        conn = self._conn()
        with conn:
            conn.execute(
                "INSERT INTO action_log (ts, claim_ref, tool, arguments, ok, result) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), claim_ref, tool, json.dumps(args, default=str), int(ok),
                 json.dumps(result, default=str)),
            )
        conn.close()

    def _policy_row(self, policy_id: str) -> sqlite3.Row:
        conn = self._conn()
        row = conn.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,)).fetchone()
        conn.close()
        if row is None:
            raise ToolRefused(f"Unknown policy number {policy_id!r}. Check the number in the customer's email.")
        return row

    def _claim_row(self, claim_ref: str) -> sqlite3.Row:
        conn = self._conn()
        row = conn.execute("SELECT * FROM claims WHERE claim_ref = ?", (claim_ref,)).fetchone()
        conn.close()
        if row is None:
            raise ToolRefused(f"Unknown claim {claim_ref!r}. Open it first with create_claim.")
        return row

    def _update_claim(self, claim_ref: str, **fields: Any) -> None:
        fields["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn = self._conn()
        with conn:
            conn.execute(f"UPDATE claims SET {sets} WHERE claim_ref = ?", (*fields.values(), claim_ref))
        conn.close()

    @staticmethod
    def _policy_from_row(row: sqlite3.Row) -> rules.Policy:
        return rules.Policy(
            policy_id=row["policy_id"],
            holder_name=row["holder_name"],
            vehicle=row["vehicle"],
            market_value=row["market_value"],
            licence_date=date.fromisoformat(row["licence_date"]),
            coverages=tuple(Coverage(c) for c in json.loads(row["coverages"])),
        )

    @staticmethod
    def _claim_from_row(row: sqlite3.Row) -> Claim:
        return Claim(
            claim_ref=row["claim_ref"],
            policy_id=row["policy_id"],
            coverage=Coverage(row["coverage"]),
            incident_date=date.fromisoformat(row["incident_date"]),
            report_date=date.fromisoformat(row["report_date"]),
            repair_cost=row["repair_cost"],
            at_fault=bool(row["at_fault"]),
            third_party_involved=bool(row["third_party_involved"]),
            third_party_identified=bool(row["third_party_identified"]),
            documents_provided=tuple(json.loads(row["documents_provided"])),
            exclusion_signal=row["exclusion_signal"],
        )

    # ------------------------------------------------------- tool 1: get_policy
    @logged
    def get_policy(self, *, policy_id: str, claim_ref: str) -> dict:
        # claim_ref links this lookup to its claim in the audit log.
        row = self._policy_row(policy_id)
        coverages = json.loads(row["coverages"])
        return {
            "policy_id": row["policy_id"],
            "holder_name": row["holder_name"],
            "vehicle": row["vehicle"],
            "market_value_eur": row["market_value"],
            "licence_date": row["licence_date"],
            "coverages": [{"code": c, "name": COVERAGE_NAMES[c]} for c in coverages],
        }

    # ----------------------------------------------------- tool 2: create_claim
    @logged
    def create_claim(
        self,
        *,
        claim_ref: str,
        policy_id: str,
        coverage: str,
        incident_date: str,
        report_date: str,
        description: str,
        repair_cost: int,
        at_fault: bool,
        third_party_involved: bool,
        third_party_identified: bool,
        documents_provided: list[str],
        exclusion_signal: str | None = None,
    ) -> dict:
        if coverage not in COVERAGE_NAMES:
            raise ToolRefused(f"coverage must be one of {list(COVERAGE_NAMES)}, got {coverage!r}.")
        if coverage == Coverage.THIRD_PARTY.value:
            # Found twice in evaluations (trial2, robustness v1): a collision with a named other
            # driver was recorded as C1, so a payment with no deductible was staged. This desk
            # only handles damage to the insured car; the tool refuses C1 instead of hoping.
            raise ToolRefused(
                "C1 (third-party liability) pays for damage the policyholder caused to OTHER people, and "
                "is handled by the liability team, not this desk. Claims here are for the insured car: "
                "use C2 for collision damage to the insured car (also when another driver is involved), "
                "C3 for glass, C4 for theft.")
        unknown_docs = [d for d in documents_provided if d not in DOCUMENT_TYPES]
        if unknown_docs:
            raise ToolRefused(f"Unknown document types {unknown_docs}. Allowed: {list(DOCUMENT_TYPES)}.")
        incident = _parse_date(incident_date, "incident_date")
        report = _parse_date(report_date, "report_date")
        if report < incident:
            raise ToolRefused("report_date cannot be before incident_date.")
        if repair_cost < 0:
            raise ToolRefused("repair_cost cannot be negative.")
        if third_party_identified and not third_party_involved:
            raise ToolRefused("third_party_identified requires third_party_involved to be true.")
        policy = self._policy_from_row(self._policy_row(policy_id))
        exclusion_signal = (exclusion_signal or "").strip() or None

        claim = Claim(
            claim_ref=claim_ref,
            policy_id=policy_id,
            coverage=Coverage(coverage),
            incident_date=incident,
            report_date=report,
            repair_cost=repair_cost,
            at_fault=at_fault,
            third_party_involved=third_party_involved,
            third_party_identified=third_party_identified,
            documents_provided=tuple(dict.fromkeys(documents_provided)),
            exclusion_signal=exclusion_signal,
        )

        # The deterministic checks (Articles 2, 3, 4 and 7)
        days_to_report = (report - incident).days
        deadline = rules.REPORTING_DEADLINE_DAYS[claim.coverage]
        on_time = not rules.is_late(claim)
        covered = claim.coverage in policy.coverages
        required = rules.required_documents(claim)
        missing = [d for d in required if d not in claim.documents_provided]

        blocking: list[str] = []
        if not covered:
            blocking.append("coverage_not_in_schedule")
        if exclusion_signal:
            blocking.append(f"possible_exclusion:{exclusion_signal}")
        if not on_time:
            blocking.append("late_report")
        blocking += [f"missing_document:{d}" for d in missing]

        conn = self._conn()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO claims (claim_ref, policy_id, coverage, incident_date, report_date, "
                    "description, repair_cost, at_fault, third_party_involved, third_party_identified, "
                    "documents_provided, exclusion_signal, status, blocking_issues, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (claim_ref, policy_id, coverage, incident.isoformat(), report.isoformat(),
                     description, repair_cost, int(at_fault), int(third_party_involved),
                     int(third_party_identified), json.dumps(list(claim.documents_provided)),
                     exclusion_signal, "open", json.dumps(blocking), _now(), _now()),
                )
        except sqlite3.IntegrityError:
            raise ToolRefused(f"Claim {claim_ref!r} already exists.") from None
        finally:
            conn.close()

        return {
            "claim_ref": claim_ref,
            "status": "open",
            "checks": {
                "coverage": f"{coverage} {COVERAGE_NAMES[coverage]}",
                "coverage_in_policy_schedule": covered,
                "days_to_report": days_to_report,
                "reporting_deadline_days": deadline,
                "reported_on_time": on_time,
                "required_documents": required,
                "missing_documents": missing,
                "possible_exclusion": exclusion_signal,
            },
            "blocking_issues": blocking,
        }

    # ----------------------------------------------- tool 3: compute_settlement
    @logged
    def compute_settlement(self, *, claim_ref: str) -> dict:
        row = self._claim_row(claim_ref)
        blocking = json.loads(row["blocking_issues"])
        if blocking:
            raise ToolRefused(
                f"Cannot compute a settlement for {claim_ref}: blocking issues {blocking}. "
                "Request missing documents with request_documents and/or refer the claim "
                "with escalate_to_handler."
            )
        claim = self._claim_from_row(row)
        policy = self._policy_from_row(self._policy_row(claim.policy_id))
        years = rules.full_years_between(policy.licence_date, claim.incident_date)
        s = rules.compute_settlement(
            coverage=claim.coverage,
            repair_cost=claim.repair_cost,
            market_value=policy.market_value,
            at_fault=claim.at_fault,
            third_party_identified=claim.third_party_identified,
            years_licensed=years,
        )
        # Computing the amounts must never un-escalate a claim: a referred claim
        # keeps "escalated" (so stage_settlement still refuses it) and the handler
        # still gets the figures. One atomic statement, like request_documents.
        conn = self._conn()
        with conn:
            conn.execute(
                "UPDATE claims SET deductible = ?, payout = ?, assessor_required = ?, updated_at = ?, "
                "status = CASE WHEN status = 'escalated' THEN 'escalated' ELSE 'settlement_computed' END "
                "WHERE claim_ref = ?",
                (s.deductible, s.payout, int(s.assessor_required), _now(), claim_ref),
            )
        conn.close()
        return {
            "claim_ref": claim_ref,
            "deductible_eur": s.deductible,
            "payout_eur": s.payout,
            "assessor_required": s.assessor_required,
            "years_licensed_on_incident_date": years,
            "calculation": s.breakdown,
        }

    # ------------------------------------------------ tool 4: request_documents
    @logged
    def request_documents(self, *, claim_ref: str, documents: list[str], message_to_customer: str) -> dict:
        self._claim_row(claim_ref)
        if not documents:
            raise ToolRefused("documents cannot be empty.")
        unknown = [d for d in documents if d not in DOCUMENT_TYPES]
        if unknown:
            raise ToolRefused(f"Unknown document types {unknown}. Allowed: {list(DOCUMENT_TYPES)}.")
        # One atomic statement: escalation always wins, whatever the order or timing
        # of the calls. (A read-then-write here lost escalations when the agent
        # called request_documents and escalate_to_handler in parallel.)
        conn = self._conn()
        with conn:
            conn.execute(
                "UPDATE claims SET requested_documents = ?, updated_at = ?, "
                "status = CASE WHEN status = 'escalated' THEN 'escalated' ELSE 'awaiting_documents' END "
                "WHERE claim_ref = ?",
                (json.dumps(documents), _now(), claim_ref),
            )
        conn.close()
        status = self._claim_row(claim_ref)["status"]
        return {
            "claim_ref": claim_ref,
            "status": status,
            "documents_requested": documents,
            "message_recorded": message_to_customer,
        }

    # ---------------------------------------------- tool 5: escalate_to_handler
    @logged
    def escalate_to_handler(self, *, claim_ref: str, reasons: list[str], summary: str) -> dict:
        self._claim_row(claim_ref)
        if not reasons:
            raise ToolRefused("reasons cannot be empty.")
        unknown = [r for r in reasons if r not in ESCALATION_REASONS]
        if unknown:
            raise ToolRefused(f"Unknown reasons {unknown}. Allowed: {list(ESCALATION_REASONS)}.")
        self._update_claim(
            claim_ref, status="escalated", escalation_reasons=json.dumps(reasons), handler_note=summary
        )
        return {
            "claim_ref": claim_ref,
            "status": "escalated",
            "reasons": reasons,
            "message": "Referred to a Veridia claims handler, who will decide. Do not settle this claim.",
        }

    # ------------------------------------------------- tool 6: schedule_assessor
    @logged
    def schedule_assessor(self, *, claim_ref: str) -> dict:
        row = self._claim_row(claim_ref)
        if row["status"] != "settlement_computed" or row["assessor_required"] is None:
            raise ToolRefused("Compute the settlement first with compute_settlement.")
        if not row["assessor_required"]:
            raise ToolRefused(
                f"No assessor needed for {claim_ref}: the repair cost is not above "
                f"€{rules.ASSESSOR_THRESHOLD} (Art. 6.1)."
            )
        visit = date.fromisoformat(row["report_date"]) + timedelta(days=ASSESSOR_DELAY_DAYS)
        self._update_claim(claim_ref, assessor_date=visit.isoformat())
        return {
            "claim_ref": claim_ref,
            "assessor_visit_date": visit.isoformat(),
            "message": "Independent assessor booked (Art. 6.1).",
        }

    # ------------------------------------------------- tool 7: stage_settlement
    @logged
    def stage_settlement(self, *, claim_ref: str) -> dict:
        row = self._claim_row(claim_ref)
        blocking = json.loads(row["blocking_issues"])
        if blocking or row["status"] in ("escalated", "awaiting_documents"):
            raise ToolRefused(
                f"Refused: {claim_ref} cannot be settled (status {row['status']}, "
                f"blocking issues {blocking}). Only clean claims can be staged for payment."
            )
        if row["status"] != "settlement_computed":
            raise ToolRefused("Compute the settlement first with compute_settlement.")
        if row["assessor_required"] and not row["assessor_date"]:
            raise ToolRefused("An assessor is required (Art. 6.1). Book one with schedule_assessor first.")
        self._update_claim(claim_ref, status="pending_approval")
        return {
            "claim_ref": claim_ref,
            "status": "pending_approval",
            "payout_eur": row["payout"],
            "deductible_eur": row["deductible"],
            "message": "Payment prepared. A human claims handler must approve it before it is paid.",
        }

    # -------------------------------------- for the human app only (NOT a tool)
    def approve_settlement(self, claim_ref: str, handler_name: str) -> dict:
        row = self._claim_row(claim_ref)
        if row["status"] != "pending_approval":
            raise ToolRefused(f"{claim_ref} is not pending approval (status {row['status']}).")
        self._update_claim(claim_ref, status="approved", approved_by=handler_name)
        self._log("approve_settlement (human)", claim_ref, {"handler_name": handler_name}, ok=True,
                  result={"status": "approved"})
        return {"claim_ref": claim_ref, "status": "approved", "approved_by": handler_name}

    def get_claim(self, claim_ref: str) -> dict:
        return dict(self._claim_row(claim_ref))

    def list_claims(self, since: str | None = None) -> list[dict]:
        """All claims (optionally created on or after `since`, ISO date), with the holder's name."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT c.*, p.holder_name FROM claims c JOIN policies p ON p.policy_id = c.policy_id "
            "WHERE c.created_at >= ? ORDER BY c.created_at", (since or "",)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def action_log(self, claim_ref: str | None = None) -> list[dict]:
        conn = self._conn()
        if claim_ref:
            rows = conn.execute(
                "SELECT * FROM action_log WHERE claim_ref = ? ORDER BY id", (claim_ref,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM action_log ORDER BY id").fetchall()
        conn.close()
        return [
            {**dict(r), "arguments": json.loads(r["arguments"]), "result": json.loads(r["result"]),
             "ok": bool(r["ok"])}
            for r in rows
        ]
