"""The claims-desk web app: pages and API, added to the same server as MCP.

Routes
    GET  /                          the web page
    GET  /static/<file>             CSS and JavaScript
    GET  /api/cases                 sample claims (emails only, never the answers)
    GET  /documents/<case>/<file>   a sample document (PDF) the agent can read
    POST /api/claims                start the agent on an email -> {"claim_ref": ...}
    GET  /api/claims/<ref>/stream   live timeline (Server-Sent Events)
    GET  /api/claims/<ref>          claim record, agent reply, cost, audit log
    POST /api/claims/<ref>/approve  the human approval (the agent cannot do this);
                                    {"override": true} if the Reviewer raised concerns
    GET  /api/memory?policy=<id>    what the agent remembers: playbook rules, customer note
    POST /api/memory/playbook       a handler teaches the agent a rule
    POST /api/memory/reset          back to an empty playbook and no customer notes

The Cominty API key stays on the server. The browser only talks to these routes.
Every public run spends credits, so runs are rate-limited (one at a time,
a daily maximum).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse

from app.agent import AgentRunner
from app.memory import MAX_RULE_CHARS, PLAYBOOK, customer_path, rules_of
from core.review import build_review_task, created_inputs, parse_verdict
from core.task import build_task
from mcp.server.mcpserver import MCPServer
from mcp_server.tools import ClaimsSystem, ToolRefused

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
CASES_FILE = ROOT / "data" / "cases.json"
DOC_CASES_FILE = ROOT / "data" / "doc_cases.json"     # claims that come with real documents

DOC_FILES = {
    "photos": "damage_photos.zip",
    "repair_quote": "repair_quote.pdf",
    "accident_report": "accident_report_signed.pdf",
    "police_report": "police_report.pdf",
}
FILE_TO_DOC = {v: k for k, v in DOC_FILES.items()}
FILES_BY_SCAN = {"quote": "repair_quote.pdf", "report": "accident_report_signed.pdf", "police": "police_report.pdf"}
MAX_BODY_CHARS = 2000
POLICY_RE = re.compile(r"Policy number: (VER-\d{4})")
RUN_TIMEOUT_S = 360
STREAM_POLL_S = 0.7


# ------------------------------------------------------------- run state
@dataclass
class Run:
    claim_ref: str
    case_id: str
    started: float = field(default_factory=time.monotonic)
    events: list[dict] = field(default_factory=list)
    done: bool = False
    reply: str | None = None
    cost: dict | None = None
    error: str | None = None
    seconds: float | None = None
    email: dict | None = None
    files: list[Path] = field(default_factory=list)
    review_state: str = "none"          # none / running / done
    review: dict | None = None


@dataclass
class Limits:
    """Protects the credits behind a public demo link."""

    daily_max: int
    used_today: int = 0
    day: str = ""

    def try_take(self) -> bool:
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day, self.used_today = today, 0
        if self.used_today >= self.daily_max:
            return False
        self.used_today += 1
        return True


# ------------------------------------------------------------- helpers
def load_cases() -> list[dict]:
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if DOC_CASES_FILE.exists():
        cases += json.loads(DOC_CASES_FILE.read_text(encoding="utf-8"))
    return cases


def case_files(case: dict) -> dict[str, Path]:
    """Documents uploaded with this sample claim: file name -> path on disk."""
    return {Path(f).name: ROOT / f for f in case["email"].get("files") or []}


def public_case(case: dict) -> dict:
    """What the browser may see: the email and attachments, never the answer key."""
    email = case["email"]
    body = re.sub(r"\n+Attached:.*\Z", "", email["body"], flags=re.S).rstrip()
    policy = POLICY_RE.search(email["body"])
    return {
        "case_id": case["case_id"],
        "policy_id": policy.group(1) if policy else None,
        "title": case["title"],
        "demo": case.get("demo", False),
        "skill": case.get("skill"),
        "date": email["date"],
        "from": email["from"],
        "subject": email["subject"],
        "body": body,
        "documents": [FILE_TO_DOC[f] for f in email["attachments"]],
        "files": [{"name": name, "url": f"/documents/{case['case_id']}/{name}",
                   "scanned": any(name == FILES_BY_SCAN.get(k) for k in case.get("scanned", []))}
                  for name in case_files(case)],
    }


def make_email(case: dict, body: str, documents: list[str], files: list[str] = ()) -> dict:
    """Rebuild an email from a sample, the edited text, the ticked mailroom documents
    and the ticked files (documents uploaded with the message, which the agent reads)."""
    stored = [DOC_FILES[d] for d in documents]
    listed = list(files) + stored
    full_body = body.rstrip() + (f"\n\nAttached: {', '.join(listed)}" if listed else "")
    email = case["email"]
    return {"date": email["date"], "from": email["from"], "subject": email["subject"],
            "body": full_body, "attachments": stored, "files": list(files)}


def log_item(entry: dict) -> dict:
    """One audit-log entry from our MCP server -> one timeline item."""
    tool, args, result = entry["tool"], entry["arguments"], entry["result"]
    if not entry["ok"]:
        return {"source": "system", "icon": "⛔", "text": f"{tool} refused by the claims system",
                "detail": result.get("error", ""), "tool": tool, "ok": False}
    detail = ""
    if tool == "get_policy":
        detail = f"{result['holder_name']}, {result['vehicle']}, licence since {result['licence_date']}"
    elif tool == "create_claim":
        checks = result["checks"]
        bits = [f"{checks['coverage']}",
                "on time" if checks["reported_on_time"] else f"LATE ({checks['days_to_report']} days)"]
        if checks["missing_documents"]:
            bits.append("missing: " + ", ".join(checks["missing_documents"]))
        if checks["possible_exclusion"]:
            bits.append(f"possible exclusion: {checks['possible_exclusion']}")
        if not checks["coverage_in_policy_schedule"]:
            bits.append("coverage NOT in the policy")
        detail = "; ".join(bits)
    elif tool == "compute_settlement":
        detail = "; ".join(result["calculation"])
    elif tool == "request_documents":
        detail = "requested: " + ", ".join(result["documents_requested"])
    elif tool == "escalate_to_handler":
        detail = "reasons: " + ", ".join(result["reasons"])
    elif tool == "schedule_assessor":
        detail = f"visit on {result['assessor_visit_date']}"
    elif tool == "stage_settlement":
        detail = f"€{result['payout_eur']} pending human approval"
    elif tool.startswith("approve_settlement"):
        detail = f"approved by {args.get('handler_name', 'a human')}"
    return {"source": "system", "icon": "✅", "text": tool, "detail": detail, "tool": tool, "ok": True}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# --------------------------------------------------------------- routes
def register_web_routes(server: MCPServer, system: ClaimsSystem, runner: AgentRunner,
                        daily_max: int | None = None, memory=None, reviewer: AgentRunner | None = None
                        ) -> dict[str, Run]:
    """`memory` is a memory store (app.memory); None runs the demo without memory.
    `reviewer` is a second agent that checks every staged payment; None skips the review."""
    runs: dict[str, Run] = {}
    limits = Limits(daily_max if daily_max is not None else int(os.environ.get("DEMO_DAILY_LIMIT", "30")))
    teach_limits = Limits(int(os.environ.get("DEMO_TEACH_LIMIT", "20")))
    busy = asyncio.Lock()
    cases = {c["case_id"]: c for c in load_cases()}

    async def review(run: Run) -> None:
        """Second agent, read-only: checks a staged payment before a person can approve it."""
        log = system.action_log(run.claim_ref)
        created = created_inputs(log)
        policy = next((e["result"] for e in log if e["tool"] == "get_policy" and e["ok"]), None)
        if reviewer is None or created is None or policy is None:
            return
        run.review_state = "running"
        run.events.append({"source": "reviewer", "icon": "🔍",
                           "text": "A second agent (the Reviewer) is checking the prepared payment"})
        try:
            playbook = rules_of(await memory.read(PLAYBOOK)) if memory else []
            task = build_review_task(run.email, policy, created, system.get_claim(run.claim_ref), playbook)
            result = await asyncio.wait_for(
                reviewer(task, lambda item: run.events.append(item | {"source": "reviewer"}), files=run.files),
                timeout=RUN_TIMEOUT_S)
            run.review = parse_verdict(result.get("reply")) | {"cost": result.get("cost")}
        except Exception as exc:  # noqa: BLE001  (fail safe: no review means a person must look)
            run.review = {"verdict": "concerns", "issues": [], "unreadable": True,
                          "summary": f"The review could not run ({type(exc).__name__}); check the claim manually."}
        agrees = run.review["verdict"] == "approve"
        run.events.append({"source": "reviewer", "icon": "🟢" if agrees else "🟠",
                           "text": "Reviewer agrees with the payment" if agrees else "Reviewer raised concerns",
                           "detail": run.review["summary"]})
        run.review_state = "done"

    async def execute(run: Run, task: str, files: list[Path]) -> None:
        async with busy:
            try:
                result = await asyncio.wait_for(runner(task, run.events.append, files=files),
                                                timeout=RUN_TIMEOUT_S)
                run.reply, run.cost = result.get("reply"), result.get("cost")
                if system.get_claim(run.claim_ref)["status"] == "pending_approval":
                    await review(run)
            except Exception as exc:  # noqa: BLE001  (shown to the user, never crashes the server)
                run.error = f"{type(exc).__name__}: {exc}"
            finally:
                run.seconds = round(time.monotonic() - run.started, 1)
                run.done = True

    def claim_payload(ref: str) -> dict:
        try:
            claim = system.get_claim(ref)
        except ToolRefused:
            claim = None
        run = runs.get(ref)
        return {
            "claim_ref": ref,
            "claim": claim,
            "log": [log_item(e) for e in system.action_log(ref)],
            "reply": run.reply if run else None,
            "cost": run.cost if run else None,
            "error": run.error if run else None,
            "seconds": run.seconds if run else None,
            "review": run.review if run else None,
            "done": run.done if run else True,
        }

    @server.custom_route("/", methods=["GET"], include_in_schema=False)
    async def index(request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html")

    @server.custom_route("/static/{name}", methods=["GET"], include_in_schema=False)
    async def static(request: Request) -> Response:
        name = request.path_params["name"]
        path = STATIC_DIR / name
        if "/" in name or ".." in name or not path.is_file():
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(path)

    @server.custom_route("/documents/{case_id}/{name}", methods=["GET"], include_in_schema=False)
    async def document(request: Request) -> Response:
        case = cases.get(request.path_params["case_id"])
        path = case_files(case).get(request.path_params["name"]) if case else None
        if path is None or not path.is_file():  # only the sample documents, nothing else on disk
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(path, media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{path.name}"'})

    @server.custom_route("/api/cases", methods=["GET"], include_in_schema=False)
    async def list_cases(request: Request) -> Response:
        return JSONResponse({
            "cases": [public_case(c) for c in cases.values()],
            "runs_left_today": max(limits.daily_max - limits.used_today, 0)
            if limits.day == datetime.now(timezone.utc).date().isoformat() else limits.daily_max,
        })

    @server.custom_route("/api/claims", methods=["POST"], include_in_schema=False)
    async def start_claim(request: Request) -> Response:
        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"error": "Invalid JSON."}, status_code=400)
        case = cases.get(str(payload.get("case_id", "")))
        body = str(payload.get("body", "")).strip()
        documents = payload.get("documents", [])
        files = payload.get("files", [])
        if case is None:
            return JSONResponse({"error": "Choose one of the sample claims."}, status_code=400)
        if not body or len(body) > MAX_BODY_CHARS:
            return JSONResponse({"error": f"The email must be 1 to {MAX_BODY_CHARS} characters."},
                                status_code=400)
        if not isinstance(documents, list) or any(d not in DOC_FILES for d in documents):
            return JSONResponse({"error": "Unknown document type."}, status_code=400)
        available = case_files(case)
        if not isinstance(files, list) or any(f not in available for f in files):
            return JSONResponse({"error": "Unknown file for this claim."}, status_code=400)
        files = list(dict.fromkeys(files))
        if busy.locked():
            return JSONResponse({"error": "The agent is already handling a claim. Try again in a minute."},
                                status_code=429)
        if not limits.try_take():
            return JSONResponse({"error": "The demo's daily limit is reached. Please try again tomorrow."},
                                status_code=429)

        claim_ref = f"DEMO-{datetime.now(timezone.utc):%m%d%H%M%S}-{secrets.token_hex(2).upper()}"
        email = make_email(case, body, list(dict.fromkeys(documents)), files)
        run = Run(claim_ref=claim_ref, case_id=case["case_id"], email=email, files=[available[f] for f in files])
        runs[claim_ref] = run
        task = build_task(email, claim_ref, memory_namespace=memory.namespace if memory else None)
        asyncio.create_task(execute(run, task, run.files))
        return JSONResponse({"claim_ref": claim_ref}, status_code=202)

    @server.custom_route("/api/claims/{ref}", methods=["GET"], include_in_schema=False)
    async def get_claim(request: Request) -> Response:
        ref = request.path_params["ref"]
        if ref not in runs and not system.action_log(ref):
            return JSONResponse({"error": "Unknown claim."}, status_code=404)
        return JSONResponse(claim_payload(ref))

    @server.custom_route("/api/claims/{ref}/stream", methods=["GET"], include_in_schema=False)
    async def stream(request: Request) -> Response:
        ref = request.path_params["ref"]
        run = runs.get(ref)
        if run is None:
            return JSONResponse({"error": "Unknown claim."}, status_code=404)

        async def events():
            sent_agent, sent_log = 0, 0
            while True:
                for item in run.events[sent_agent:]:
                    yield sse("step", item)
                sent_agent = len(run.events)
                log = system.action_log(ref)
                for entry in log[sent_log:]:
                    yield sse("step", log_item(entry))
                sent_log = len(log)
                if run.done:
                    yield sse("done", claim_payload(ref))
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(STREAM_POLL_S)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @server.custom_route("/api/claims/{ref}/approve", methods=["POST"], include_in_schema=False)
    async def approve(request: Request) -> Response:
        ref = request.path_params["ref"]
        try:
            override = bool((await request.json()).get("override"))
        except (json.JSONDecodeError, ValueError, AttributeError):
            override = False
        run = runs.get(ref)
        if run and run.review_state == "running":
            return JSONResponse({"error": "The Reviewer is still checking this claim."}, status_code=409)
        if run and run.review and run.review["verdict"] == "concerns" and not override:
            return JSONResponse({"error": "The Reviewer raised concerns. Confirm to approve anyway.",
                                 "needs_override": True}, status_code=409)
        try:
            system.approve_settlement(ref, handler_name="Demo claims handler" + (" (reviewer overridden)" if override else ""))
        except ToolRefused as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return JSONResponse(claim_payload(ref))

    @server.custom_route("/api/memory", methods=["GET"], include_in_schema=False)
    async def read_memory(request: Request) -> Response:
        if memory is None:
            return JSONResponse({"enabled": False})
        policy = request.query_params.get("policy", "")
        if policy and not re.fullmatch(r"VER-\d{4}", policy):
            return JSONResponse({"error": "Unknown policy number."}, status_code=400)
        try:
            playbook = await memory.read(PLAYBOOK)
            note = await memory.read(customer_path(policy)) if policy else None
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"Memory is unavailable: {exc}"}, status_code=502)
        return JSONResponse({"enabled": True, "namespace": memory.namespace, "policy_id": policy or None,
                             "rules": rules_of(playbook), "customer_note": note})

    @server.custom_route("/api/memory/playbook", methods=["POST"], include_in_schema=False)
    async def teach(request: Request) -> Response:
        if memory is None:
            return JSONResponse({"error": "Memory is not enabled on this server."}, status_code=404)
        try:
            rule = str((await request.json()).get("rule", "")).strip()
        except (json.JSONDecodeError, ValueError, AttributeError):
            return JSONResponse({"error": "Invalid JSON."}, status_code=400)
        if not rule or len(rule) > MAX_RULE_CHARS:
            return JSONResponse({"error": f"A rule must be 1 to {MAX_RULE_CHARS} characters."}, status_code=400)
        if not teach_limits.try_take():
            return JSONResponse({"error": "The demo's daily limit for new rules is reached."}, status_code=429)
        try:
            playbook = await memory.teach(rule)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"Memory is unavailable: {exc}"}, status_code=502)
        return JSONResponse({"rules": rules_of(playbook)})

    @server.custom_route("/api/memory/reset", methods=["POST"], include_in_schema=False)
    async def reset_memory(request: Request) -> Response:
        if memory is None:
            return JSONResponse({"error": "Memory is not enabled on this server."}, status_code=404)
        if busy.locked():
            return JSONResponse({"error": "Wait until the agent has finished the current claim."}, status_code=409)
        try:
            await memory.reset()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"Memory is unavailable: {exc}"}, status_code=502)
        return JSONResponse({"rules": []})

    return runs
