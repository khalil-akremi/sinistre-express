"""Send one test claim to the Cominty agent and watch it work live.

Usage:   uv run python scripts/run_claim.py CLM-B
         uv run python scripts/run_claim.py CLM-B --max-steps 20

Needs a .env file in the project root with:
    COMINTY_API_KEY=sk-cmt-...
    COMINTY_USER_ID=user_...
    COMINTY_AGENT_ID=nzAeZNNFr7yq

Each run spends credits. The result (events, reply, cost) is saved in runs/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from cominty_sdk import AsyncCominty, events

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "data" / "cases.json"
RUNS_DIR = ROOT / "runs"


def load_case(case_id: str) -> dict:
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    for case in cases:
        if case["case_id"] == case_id:
            return case
    raise SystemExit(f"Unknown case {case_id!r}. Available: {[c['case_id'] for c in cases]}")


def build_task(case: dict, claim_ref: str) -> str:
    """The message the agent receives: its task, the claim reference and the email.

    Only the email is given. The true facts and the expected outcome stay
    hidden: finding the facts is the agent's job.
    """
    email = case["email"]
    return (
        f"New claim to handle. Use the claim reference {claim_ref}.\n\n"
        f"--- Customer email received on {email['date']} ---\n"
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n\n"
        f"{email['body']}\n"
        f"--- End of email ---"
    )


def describe(event) -> str | None:
    """One readable line per progress event."""
    if isinstance(event, events.ToolCall):
        d = event.data
        icon = {"running": "🔧", "success": "✅", "error": "❌"}.get(event.status, "•")
        extra = f" — {d.error}" if getattr(d, "error", None) else ""
        return f"{icon} tool {d.name} [{event.status}]{extra}"
    if isinstance(event, events.LlmStep):
        return f"🧠 thinking: {event.data.description}"
    if isinstance(event, events.IntermediaryUpdate):
        return f"💬 {event.data.message}"
    if isinstance(event, events.SettingUpSandbox):
        return "📦 setting up sandbox"
    if isinstance(event, events.WaitingForStart):
        return "⏳ waiting for start"
    if isinstance(event, events.Result):
        return None  # printed separately
    return f"• {getattr(event, 'name', type(event).__name__)}"


def to_jsonable(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return str(obj)


async def run(case_id: str, max_steps: int) -> None:
    load_dotenv(ROOT / ".env")
    agent_id = os.environ.get("COMINTY_AGENT_ID")
    if not agent_id:
        raise SystemExit("COMINTY_AGENT_ID is missing from .env")

    case = load_case(case_id)
    claim_ref = f"{case_id}-{datetime.now():%m%d%H%M%S}"
    task = build_task(case, claim_ref)
    print(f"Case {case_id} ({case['title']}) -> claim reference {claim_ref}\n")

    log: list[dict] = []
    cost = None
    started = datetime.now()

    async with AsyncCominty() as client:
        run_handle = await client.chat.start(agent_id=agent_id, message=task, max_steps=max_steps)
        async with run_handle:
            async for event in run_handle:
                log.append({"name": getattr(event, "name", None), "status": getattr(event, "status", None),
                            "data": to_jsonable(getattr(event, "data", None))})
                line = describe(event)
                if line:
                    print(line)
                if isinstance(event, events.Result):
                    cost = event.data.cost
            reply = await run_handle.result()

    seconds = (datetime.now() - started).total_seconds()
    print("\n" + "=" * 70)
    print(reply.content)
    print("=" * 70)
    if reply.questions:
        print("\nThe agent asks:")
        for q in reply.questions:
            print(f"  ? {q.prompt}  options: {q.options}")
    if cost is not None:
        print(f"\nCost: €{cost.total}  (input {cost.input_tokens} tokens, "
              f"cached {cost.cached_tokens}, output {cost.output_tokens})")
    print(f"Time: {seconds:.0f}s   Status: {reply.status}")

    RUNS_DIR.mkdir(exist_ok=True)
    out = RUNS_DIR / f"{claim_ref}.json"
    out.write_text(json.dumps({
        "case_id": case_id,
        "claim_ref": claim_ref,
        "agent_id": agent_id,
        "max_steps": max_steps,
        "thread_id": str(reply.thread_id),
        "message_id": str(reply.id),
        "status": str(reply.status),
        "seconds": seconds,
        "cost": to_jsonable(cost) if cost is not None else None,
        "reply": reply.content,
        "questions": [to_jsonable(q) for q in (reply.questions or [])],
        "events": log,
        "expected": case["expected"],
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Saved to {out.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case_id", help="e.g. CLM-A, CLM-B, CLM-C, CLM-01 ...")
    parser.add_argument("--max-steps", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(run(args.case_id, args.max_steps))


if __name__ == "__main__":
    main()
