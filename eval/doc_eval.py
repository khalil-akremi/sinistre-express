"""Document evaluation: can the agent get the facts right when they are only in the documents?

Run:  uv run python -m eval.doc_eval --label v1          (6 claims, about €0.08)
      uv run python -m eval.doc_eval --label v1 --no-memory

Each claim in data/doc_cases.json comes with real PDFs (typed or scanned), uploaded
with the message. The email leaves the key facts out, so the facts the agent passes
to create_claim show what it actually read. Graded with the same grader as the main
evaluation (decision, amounts, facts field by field, trajectory, safety, honesty),
plus: did it open every document (read_file), and typed vs scanned accuracy.

By default memory is on, with the playbook's commercial-vehicle rule (as on the live
demo), so DOC-02 must be referred: the van appears only in the accident report.
Finished runs are kept and skipped if you run the same label again.
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
from core.task import build_task
from eval.grade import grade_case

ROOT = Path(__file__).resolve().parent.parent
DOC_CASES_FILE = ROOT / "data" / "doc_cases.json"
FILE_KIND = {"repair_quote.pdf": "quote", "accident_report_signed.pdf": "report", "police_report.pdf": "police"}


def expected_for(case: dict, memory: bool) -> dict:
    """Without memory the agent cannot know the van rule: DOC-02 must then be settled."""
    exp = case["expected"]
    if memory or "settlement_without_rule" not in exp:
        return case
    s = exp["settlement_without_rule"]
    actions = ["get_policy", "create_claim", "compute_settlement"] + \
        (["schedule_assessor"] if s["assessor_required"] else []) + ["stage_settlement"]
    return case | {"expected": {"decision": "settle", "expected_actions": actions, "forbidden_actions": [],
                                "missing_documents": [], "escalation_reasons": [], "settlement": s}}


async def run_one(client, agent_id: str, case: dict, claim_ref: str, max_steps: int,
                  capabilities, namespace: str | None) -> dict:
    from eval.run_eval import run_agent

    ids = [(await client.chat.upload_file(ROOT / f)).id for f in case["email"]["files"]]
    return await run_agent(client, agent_id, build_task(case["email"], claim_ref, memory_namespace=namespace),
                           max_steps, capabilities, file_ids=ids)


async def main_async(args: argparse.Namespace) -> None:
    from cominty_sdk import AgentCapabilities, AsyncCominty, MemoryCapability

    from app.memory import ComintyMemory
    from eval.generate_documents import VAN_RULE
    from eval.run_eval import DEFAULT_SERVER, check_admin_access, fetch_snapshot, wake_server

    load_dotenv(ROOT / ".env")
    agent_id = clean_secret(os.environ["COMINTY_AGENT_ID"])
    secret = os.environ["MCP_SECRET_TOKEN"].strip()
    server = os.environ.get("SINISTRE_SERVER_URL", DEFAULT_SERVER).strip().rstrip("/")
    memory = not args.no_memory
    cases = json.loads(DOC_CASES_FILE.read_text(encoding="utf-8"))
    if args.cases:
        cases = [c for c in cases if c["case_id"] in set(args.cases)]
    run_dir = ROOT / "runs" / f"docs-{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Document evaluation '{args.label}': {len(cases)} claims, memory {'on' if memory else 'off'}")
    wake_server(server)
    check_admin_access(server, secret)

    namespace = f"docs-{args.label}"
    if memory and not any(run_dir.glob("DOC-*.json")):
        store = ComintyMemory(namespace)
        await store.reset()
        await store.teach(VAN_RULE)
        print(f"Memory namespace {namespace}: playbook with the commercial-vehicle rule")
    capabilities = AgentCapabilities(memory=MemoryCapability(activation="always", namespace=namespace)
                                     if memory else MemoryCapability(activation="never"))

    async with AsyncCominty(api_token=clean_secret(os.environ.get("COMINTY_API_KEY")),
                            user_id=clean_secret(os.environ.get("COMINTY_USER_ID"))) as client:
        for i, case in enumerate(cases, 1):
            path = run_dir / f"{case['case_id']}.json"
            if path.exists() and not json.loads(path.read_text(encoding="utf-8")).get("error"):
                print(f"[{i}/{len(cases)}] {case['case_id']}: already run, skipped")
                continue
            claim_ref = f"DOCS-{args.label}-{case['case_id']}"
            record = {"case_id": case["case_id"], "claim_ref": claim_ref, "memory": memory}
            started = time.monotonic()
            try:
                record |= await asyncio.wait_for(
                    run_one(client, agent_id, case, claim_ref, args.max_steps, capabilities,
                            namespace if memory else None), timeout=300)
            except Exception as exc:  # noqa: BLE001
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["seconds"] = round(time.monotonic() - started, 1)
            record["claim"], record["action_log"], record["snapshot_error"] = fetch_snapshot(server, secret, claim_ref)
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            status = (record["claim"] or {}).get("status")
            print(f"[{i}/{len(cases)}] {case['case_id']}: {status}  €{float((record.get('cost') or {}).get('total') or 0):.4f}"
                  + (f"  ERROR {record['error']}" if record.get("error") else ""))

    report = render(cases, run_dir, memory)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)


def grade_dir(cases: list[dict], run_dir: Path, memory: bool) -> list[dict]:
    rows = []
    for case in cases:
        path = run_dir / f"{case['case_id']}.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        g = grade_case(expected_for(case, memory), record)
        reads = sum(1 for e in record.get("cominty_tool_events") or []
                    if e["name"] == "read_file" and e["status"] == "success")
        g |= {"skill": case["skill"], "files": len(case["email"]["files"]), "reads": reads,
              "scanned": bool(case["scanned"])}
        rows.append(g)
    return rows


def render(cases: list[dict], run_dir: Path, memory: bool) -> str:
    rows = grade_dir(cases, run_dir, memory)
    if not rows:
        return "No results yet.\n"
    n = len(rows)
    mark = lambda ok: "✅" if ok else ("—" if ok is None else "❌")  # noqa: E731

    def field_rate(group: list[dict]) -> str:
        values = [v for g in group for v in g["facts"].values()]
        return f"{sum(values)}/{len(values)}" if values else "-"

    typed = [g for g in rows if not g["scanned"]]
    scanned = [g for g in rows if g["scanned"]]
    lines = [
        f"# Document evaluation ({'memory on, commercial-vehicle rule in the playbook' if memory else 'memory off'})",
        "",
        "| | Result |",
        "|---|---|",
        f"| Right decision | {sum(g['decision_ok'] for g in rows)}/{n} |",
        f"| All facts right (create_claim inputs) | {sum(g['facts_ok'] for g in rows)}/{n} |",
        f"| Fact fields right, typed PDFs | {field_rate(typed)} |",
        f"| Fact fields right, scanned PDFs (OCR) | {field_rate(scanned)} |",
        f"| Opened every document (read_file) | {sum(g['reads'] >= g['files'] for g in rows)}/{n} |",
        f"| Safety violations / wrong amount staged | {sum(not g['safe'] for g in rows)} |",
        f"| Honest status line | {sum(g['honest'] for g in rows)}/{n} |",
        f"| Average cost, time per claim | €{sum(g['cost_eur'] for g in rows) / n:.4f}, "
        f"{sum(g['seconds'] for g in rows) / n:.0f} s |",
        "",
        "| Claim | Tests whether the agent can… | Decision | Facts | Amounts | Docs opened | Cost |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in rows:
        wrong = [f for f, ok in g["facts"].items() if not ok]
        lines.append(
            f"| {g['case_id']}{' (scan)' if g['scanned'] else ''} | {g['skill']} | "
            f"{mark(g['decision_ok'])} {g['decision']} | {mark(g['facts_ok'])}{' ' + ', '.join(wrong) if wrong else ''} | "
            f"{mark(g['amounts_ok'])} | {g['reads']}/{g['files']} | €{g['cost_eur']:.4f} |")
    lines += ["", "Small sample (6 claims): it shows what the agent can and cannot read, not a precise rate."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default=time.strftime("%m%d-%H%M"))
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--no-memory", action="store_true")
    parser.add_argument("--report-only", action="store_true", help="re-grade saved results, no agent runs")
    args = parser.parse_args()
    if args.report_only:
        cases = json.loads(DOC_CASES_FILE.read_text(encoding="utf-8"))
        run_dir = ROOT / "runs" / f"docs-{args.label}"
        print(render(cases, run_dir, memory=not args.no_memory))
        return
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
