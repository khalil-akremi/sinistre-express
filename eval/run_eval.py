"""Run the evaluation: send test claims to the Cominty agent, fetch what it did, grade.

Usage:
    uv run python -m eval.run_eval                          # all 23 cases
    uv run python -m eval.run_eval --cases CLM-A CLM-B      # a few cases
    uv run python -m eval.run_eval --label haiku-v1         # name the run
    uv run python -m eval.run_eval --label trial --refetch  # re-read results only (no agent calls, free)

Results go to runs/eval-<label>/ (one JSON per case, then report.md).
Re-running with the same label resumes: cases whose agent run already
finished are skipped (their server snapshot is fetched again if it failed).
Each agent run spends credits (about €0.01 with a small model).

Needs in .env: COMINTY_API_KEY, COMINTY_USER_ID, COMINTY_AGENT_ID,
MCP_SECRET_TOKEN, and optionally SINISTRE_SERVER_URL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from cominty_sdk import AsyncCominty, events
from eval.grade import grade_run

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "data" / "cases.json"
DEFAULT_SERVER = "https://sinistre-express.onrender.com"
INTEGRATION_ID = "veridia_claims"
CASE_TIMEOUT_S = 300


def build_task(case: dict, claim_ref: str) -> str:
    """Only the customer email is given; the facts and answers stay hidden."""
    email = case["email"]
    return (
        f'<use agent="{INTEGRATION_ID}"/>\n'
        f"New claim to handle in the Veridia claims system. Use the claim reference {claim_ref}.\n\n"
        f"--- Customer email received on {email['date']} ---\n"
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n\n"
        f"{email['body']}\n"
        f"--- End of email ---"
    )


def http_get_json(url: str, timeout: float = 90) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (our own server)
        return json.loads(response.read().decode("utf-8"))


def wake_server(server: str) -> None:
    """Free hosting sleeps; one request wakes it (can take up to a minute)."""
    print(f"Waking {server} ...", end=" ", flush=True)
    for attempt in range(4):
        try:
            http_get_json(server + "/")
            print("ok")
            return
        except Exception:  # noqa: BLE001
            time.sleep(10 * (attempt + 1))
    raise SystemExit("The claims server does not answer. Check Render.")


def check_admin_access(server: str, secret: str) -> None:
    """Fail fast, before spending credits, if the snapshot endpoint is unreachable."""
    try:
        http_get_json(f"{server}/admin/{secret}/claims/__access_check__")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(
                "Cannot read results from the claims server (404).\n"
                "- Is the latest code deployed on Render (status Live)?\n"
                "- Is MCP_SECRET_TOKEN in .env exactly the same as on Render?"
            ) from None
        raise


def fetch_snapshot(server: str, secret: str, claim_ref: str) -> tuple[dict | None, list, str | None]:
    """What the agent actually did, from our server's database."""
    try:
        snapshot = http_get_json(f"{server}/admin/{secret}/claims/{claim_ref}")
        return snapshot["claim"], snapshot["action_log"], None
    except Exception as exc:  # noqa: BLE001
        return None, [], f"snapshot failed: {exc}"


async def run_agent(client: AsyncCominty, agent_id: str, task: str, max_steps: int) -> dict:
    run = await client.chat.start(agent_id=agent_id, message=task, max_steps=max_steps)
    cost, tool_events = None, []
    async with run:
        async for event in run:
            if isinstance(event, events.ToolCall) and event.status != "running":
                tool_events.append({"name": event.data.name, "status": event.status,
                                    "error": getattr(event.data, "error", None)})
            elif isinstance(event, events.Result):
                cost = event.data.cost
        reply = await run.result()
    return {
        "status": str(reply.status),
        "reply": reply.content,
        "questions": [q.model_dump(mode="json") for q in (reply.questions or [])],
        "thread_id": str(reply.thread_id),
        "cost": cost.model_dump(mode="json") if cost is not None else None,
        "cominty_tool_events": tool_events,
    }


def print_line(i: int, n: int, case: dict, record: dict) -> None:
    status = record["claim"]["status"] if record.get("claim") else "no claim"
    cost = (record.get("cost") or {}).get("total", "?")
    errors = " | ".join(e for e in (record.get("error"), record.get("snapshot_error")) if e)
    print(f"[{i}/{n}] {case['case_id']}: {status} (expected {case['expected']['decision']}) "
          f"€{cost} {record.get('seconds', 0)}s" + (f"  ERROR {errors}" if errors else ""))


def save(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def refetch(cases: list[dict], run_dir: Path, server: str, secret: str) -> None:
    """Re-read the server snapshot for every saved case. No agent call, no cost."""
    for i, case in enumerate(cases, 1):
        path = run_dir / f"{case['case_id']}.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("error") or "").strip().startswith("| snapshot failed"):
            record["error"] = None  # older format: the agent run itself had succeeded
        record["claim"], record["action_log"], record["snapshot_error"] = \
            fetch_snapshot(server, secret, record["claim_ref"])
        save(path, record)
        print_line(i, len(cases), case, record)


async def run_cases(cases: list[dict], run_dir: Path, server: str, secret: str,
                    agent_id: str, label: str, max_steps: int) -> None:
    async with AsyncCominty() as client:
        for i, case in enumerate(cases, 1):
            path = run_dir / f"{case['case_id']}.json"
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                if not record.get("error"):  # agent run finished: never pay twice
                    if record.get("snapshot_error"):
                        record["claim"], record["action_log"], record["snapshot_error"] = \
                            fetch_snapshot(server, secret, record["claim_ref"])
                        save(path, record)
                    print(f"[{i}/{len(cases)}] {case['case_id']}: already run, skipped")
                    continue

            claim_ref = f"{label}-{case['case_id']}"
            record = {"case_id": case["case_id"], "claim_ref": claim_ref, "label": label,
                      "agent_id": agent_id, "max_steps": max_steps}
            started = time.monotonic()
            try:
                record |= await asyncio.wait_for(
                    run_agent(client, agent_id, build_task(case, claim_ref), max_steps),
                    timeout=CASE_TIMEOUT_S,
                )
            except Exception as exc:  # noqa: BLE001  (record it and continue with the next case)
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["seconds"] = round(time.monotonic() - started, 1)
            record["claim"], record["action_log"], record["snapshot_error"] = \
                fetch_snapshot(server, secret, claim_ref)
            save(path, record)
            print_line(i, len(cases), case, record)


async def main_async(args: argparse.Namespace) -> None:
    load_dotenv(ROOT / ".env")
    agent_id = os.environ["COMINTY_AGENT_ID"]
    secret = os.environ["MCP_SECRET_TOKEN"].strip()
    server = os.environ.get("SINISTRE_SERVER_URL", DEFAULT_SERVER).strip().rstrip("/")

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if args.cases:
        cases = [c for c in cases if c["case_id"] in set(args.cases)]
    run_dir = ROOT / "runs" / f"eval-{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Evaluation '{args.label}': {len(cases)} cases -> {run_dir.relative_to(ROOT)}")
    wake_server(server)
    check_admin_access(server, secret)

    if args.refetch:
        refetch(cases, run_dir, server, secret)
    else:
        await run_cases(cases, run_dir, server, secret, agent_id, args.label, args.max_steps)

    summary = grade_run(run_dir)
    print(f"\nDecision {summary['decision_ok']}/{summary['cases']} | "
          f"amounts {summary['amounts_ok']}/{summary['amounts_n']} | "
          f"facts {summary['facts_ok']}/{summary['cases']} | "
          f"trajectory {summary['trajectory_ok']}/{summary['cases']} | "
          f"safety violations {summary['safety_violations']} | total €{summary['total_cost_eur']}")
    print(f"Report: {(run_dir / 'report.md').relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default=datetime.now().strftime("%m%d-%H%M"))
    parser.add_argument("--cases", nargs="*", help="case ids, e.g. CLM-A CLM-B (default: all)")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--refetch", action="store_true",
                        help="only re-read results from the server and re-grade (no agent calls)")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()