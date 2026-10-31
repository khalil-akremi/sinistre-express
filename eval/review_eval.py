"""Reviewer evaluation: does the second agent catch a careless Handler's mistakes?

Run:  uv run python -m eval.review_eval --label v1                    (16 files, ~€0.10)
      uv run python -m eval.review_eval --label haiku --agent-id <id>  (compare another model)

16 prepared claims (data/review_cases.json, see eval/generate_review_cases.py):
8 with a planted mistake, 8 correct. The Reviewer gets exactly what it gets in
the app (email, documents, Policy Schedule, playbook, recorded facts, result)
and returns approve / concerns.

    caught            mistakes flagged (out of 8)
    right problem     the flag points at the planted mistake, not something else
    false alarms      correct claims flagged (out of 8): each one costs a person's time
No claims system is involved: nothing is written anywhere.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from app.agent import clean_secret
from core.review import build_review_task, parse_verdict

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "data" / "review_cases.json"
VAN_RULE = ("When the other driver is a commercial vehicle (van, truck, lorry, delivery vehicle), "
            "refer the claim to a handler so Veridia can recover the money from their insurer.")
# words that show the Reviewer found the planted mistake (searched in its issues)
KEYWORDS = {
    "repair_cost": ("repair", "cost", "amount", "1,640", "1640", "1 640"),
    "at_fault": ("fault",),
    "documents_provided": ("document", "quote", "roche", "clio"),
    "decision": ("playbook", "van", "commercial", "refer"),
    "exclusion_signal": ("exclusion", "alcohol", "drink"),
    "report_date": ("report_date", "report date", "late", "deadline", "reported"),
    "third_party_identified": ("identified", "third"),
    "coverage": ("coverage", "glass", "c3"),
}


def right_problem(case: dict, verdict: dict) -> bool | None:
    if not case["mistake"]:
        return None
    text = json.dumps(verdict.get("issues") or [], ensure_ascii=False).lower() + " " + verdict.get("summary", "").lower()
    return verdict["verdict"] == "concerns" and any(k in text for k in KEYWORDS[case["field"]])


async def main_async(args: argparse.Namespace) -> None:
    from cominty_sdk import AgentCapabilities, AsyncCominty, MemoryCapability

    from eval.run_eval import run_agent

    load_dotenv(ROOT / ".env")
    agent_id = clean_secret(args.agent_id or os.environ.get("REVIEWER_AGENT_ID"))
    if not agent_id:
        raise SystemExit("Set REVIEWER_AGENT_ID in .env (or pass --agent-id).")
    all_cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    cases = [c for c in all_cases if not args.cases or c["review_id"] in set(args.cases)]
    run_dir = ROOT / "runs" / f"review-{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Reviewer evaluation '{args.label}' (agent {agent_id}): {len(cases)} prepared claims")
    caps = AgentCapabilities(memory=MemoryCapability(activation="never"))

    async with AsyncCominty(api_token=clean_secret(os.environ.get("COMINTY_API_KEY")),
                            user_id=clean_secret(os.environ.get("COMINTY_USER_ID"))) as client:
        for i, case in enumerate(cases, 1):
            path = run_dir / f"{case['review_id']}.json"
            if path.exists() and not args.redo and not json.loads(path.read_text(encoding="utf-8")).get("error"):
                print(f"[{i}/{len(cases)}] {case['review_id']}: already run, skipped")
                continue
            task = build_review_task(case["email"], case["policy"], case["created"], case["claim"], [VAN_RULE])
            record = {"review_id": case["review_id"], "agent_id": agent_id}
            started = time.monotonic()
            try:
                ids = [(await client.chat.upload_file(ROOT / f)).id for f in case["email"].get("files") or []]
                record |= await asyncio.wait_for(run_agent(client, agent_id, task, 12, caps, file_ids=ids), 300)
            except Exception as exc:  # noqa: BLE001
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["seconds"] = round(time.monotonic() - started, 1)
            record["verdict"] = parse_verdict(record.get("reply"))
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            ok = record["verdict"]["verdict"] == case["expected_verdict"]
            print(f"[{i}/{len(cases)}] {case['review_id']}: {record['verdict']['verdict']:8} "
                  f"(expected {case['expected_verdict']}) {'✅' if ok else '❌'}"
                  + (f"  ERROR {record['error']}" if record.get("error") else ""))

    report = render(all_cases, run_dir, args.label)  # always the whole set
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)


def render(cases: list[dict], run_dir: Path, label: str) -> str:
    rows = []
    for case in cases:
        path = run_dir / f"{case['review_id']}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            rows.append((case, record, record["verdict"]))
    if not rows:
        return "No results yet.\n"
    planted = [(c, r, v) for c, r, v in rows if c["mistake"]]
    clean = [(c, r, v) for c, r, v in rows if not c["mistake"]]
    caught = sum(v["verdict"] == "concerns" for _, _, v in planted)
    pointed = sum(bool(right_problem(c, v)) for c, _, v in planted)
    alarms = sum(v["verdict"] == "concerns" for _, _, v in clean)
    costs = [float(((r.get("cost") or {}).get("total")) or 0) for _, r, _ in rows]
    lines = [
        f"# Reviewer evaluation ({label})",
        "",
        "| | Result |",
        "|---|---|",
        f"| Planted mistakes caught | {caught}/{len(planted)} |",
        f"| … pointing at the right problem | {pointed}/{len(planted)} |",
        f"| False alarms on correct claims | {alarms}/{len(clean)} |",
        f"| Unreadable answers (counted as concerns) | {sum(v.get('unreadable', False) for _, _, v in rows)} |",
        f"| Average cost, time per review | €{sum(costs) / len(rows):.4f}, "
        f"{sum(r.get('seconds', 0) for _, r, _ in rows) / len(rows):.0f} s |",
        "",
        "| File | Planted mistake | Verdict | Right problem | Reviewer's summary |",
        "|---|---|---|---|---|",
    ]
    for case, _, v in rows:
        ok = v["verdict"] == case["expected_verdict"]
        rp = right_problem(case, v)
        lines.append(f"| {case['review_id']} ({case['source_case']}) | {case['mistake'] or 'none (correct claim)'} | "
                     f"{'✅' if ok else '❌'} {v['verdict']} | {'—' if rp is None else ('✅' if rp else '❌')} | "
                     f"{v.get('summary', '').replace('|', '/')[:160]} |")
    lines += ["", "Small sample (16 files): indicative, not a precise rate."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default=time.strftime("%m%d-%H%M"))
    parser.add_argument("--agent-id", help="reviewer agent to test (default: REVIEWER_AGENT_ID)")
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--redo", action="store_true", help="run the chosen files again even if already done")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
