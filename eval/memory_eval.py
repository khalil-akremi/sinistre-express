"""Memory experiment: does a rule taught by a handler change the agent's next claims?

Usage:  uv run python -m eval.memory_eval --label v1

Runs the same claims twice:
- without memory: memory turned off for the conversation;
- with memory: a fresh namespace whose playbook holds one handler rule:
  "commercial vehicle involved -> refer to a handler" (company practice, not in the contract).

Expected: with memory, the van and truck claims are referred to a handler and
the control claims are still settled; without memory, everything is settled.
It also checks that the agent wrote a note for each customer.
About 12 agent runs (~€0.10).
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
from app.memory import ComintyMemory, customer_path
from core.task import build_task

ROOT = Path(__file__).resolve().parent.parent
RULE = ("When the other driver is a commercial vehicle (van, truck, lorry, delivery vehicle), "
        "refer the claim to a handler so Veridia can recover the money from their insurer.")
RELEVANT = ["CLM-A", "CLM-03"]                     # a van, a delivery truck
CONTROLS = ["CLM-B", "CLM-01", "CLM-02", "CLM-05"]  # cars, a pillar, a car door
STATUS_TO_DECISION = {"pending_approval": "settle", "awaiting_documents": "request_documents",
                      "escalated": "escalate"}


def expected(case_id: str, with_memory: bool) -> str:
    return "escalate" if with_memory and case_id in RELEVANT else "settle"


async def main_async(label: str, max_steps: int) -> None:
    from cominty_sdk import AgentCapabilities, AsyncCominty, MemoryCapability

    from eval.run_eval import DEFAULT_SERVER, check_admin_access, http_get_json, run_agent, wake_server

    load_dotenv(ROOT / ".env")
    agent_id = clean_secret(os.environ["COMINTY_AGENT_ID"])
    secret = os.environ["MCP_SECRET_TOKEN"].strip()
    server = os.environ.get("SINISTRE_SERVER_URL", DEFAULT_SERVER).strip().rstrip("/")
    namespace = f"memeval-{label}"
    out_dir = ROOT / "runs" / f"memory-{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = {c["case_id"]: c for c in json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))}

    wake_server(server)
    check_admin_access(server, secret)
    store = ComintyMemory(namespace)
    print(f"Preparing memory namespace {namespace} with one playbook rule")
    await store.reset()
    await store.teach(RULE)

    rows = []
    async with AsyncCominty(api_token=clean_secret(os.environ.get("COMINTY_API_KEY")),
                            user_id=clean_secret(os.environ.get("COMINTY_USER_ID"))) as client:
        for with_memory in (False, True):
            condition = "with memory" if with_memory else "without memory"
            caps = AgentCapabilities(memory=MemoryCapability(activation="always", namespace=namespace)
                                     if with_memory else MemoryCapability(activation="never"))
            for case_id in RELEVANT + CONTROLS:
                ref = f"MEM-{label}-{'W' if with_memory else 'N'}-{case_id}"
                task = build_task(cases[case_id]["email"], ref, memory_namespace=namespace if with_memory else None)
                started = time.monotonic()
                try:
                    result = await asyncio.wait_for(run_agent(client, agent_id, task, max_steps, caps), 300)
                    error = None
                except Exception as exc:  # noqa: BLE001
                    result, error = {}, f"{type(exc).__name__}: {exc}"
                snapshot = http_get_json(f"{server}/admin/{secret}/claims/{ref}")
                status = (snapshot["claim"] or {}).get("status")
                got = STATUS_TO_DECISION.get(status, f"incomplete:{status}")
                row = {"condition": condition, "case_id": case_id, "claim_ref": ref,
                       "relevant": case_id in RELEVANT, "expected": expected(case_id, with_memory),
                       "got": got, "ok": got == expected(case_id, with_memory), "error": error,
                       "cost": float(((result.get("cost") or {}).get("total")) or 0),
                       "seconds": round(time.monotonic() - started, 1),
                       "reply": result.get("reply"), "action_log": snapshot["action_log"]}
                rows.append(row)
                print(f"[{condition}] {case_id}: {got} (expected {row['expected']}) €{row['cost']:.4f}"
                      + (f" ERROR {error}" if error else ""))

    # Did the agent write a note for each customer it handled with memory?
    notes = {}
    for case_id in RELEVANT + CONTROLS:
        policy = cases[case_id]["facts"]["policy_id"]
        notes[case_id] = await store.read(customer_path(policy))
    with_rows = [r for r in rows if r["condition"] == "with memory"]
    for r in with_rows:
        r["note_written"] = bool(notes[r["case_id"]] and r["claim_ref"] in notes[r["case_id"]])

    (out_dir / "results.json").write_text(json.dumps({"rule": RULE, "namespace": namespace, "rows": rows,
                                                      "notes": notes}, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    report = render(rows, notes)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)


def render(rows: list[dict], notes: dict) -> str:
    def part(condition: str, relevant: bool) -> tuple[int, int]:
        group = [r for r in rows if r["condition"] == condition and r["relevant"] == relevant]
        return sum(r["ok"] for r in group), len(group)

    def avg_cost(condition: str) -> float:
        group = [r for r in rows if r["condition"] == condition]
        return sum(r["cost"] for r in group) / len(group) if group else 0

    w_rel, w_rel_n = part("with memory", True)
    w_ctl, w_ctl_n = part("with memory", False)
    n_rel, n_rel_n = part("without memory", True)
    n_ctl, n_ctl_n = part("without memory", False)
    with_rows = [r for r in rows if r["condition"] == "with memory"]
    written = sum(r.get("note_written", False) for r in with_rows)
    lines = [
        "# Memory experiment",
        "",
        f"Playbook rule taught by a handler: *{RULE}*",
        "",
        "| | Without memory | With memory |",
        "|---|---|---|",
        f"| Van/truck claims handled as expected | {n_rel}/{n_rel_n} settled (the agent cannot know the rule) "
        f"| {w_rel}/{w_rel_n} referred to a handler |",
        f"| Control claims still settled (no false trigger) | {n_ctl}/{n_ctl_n} | {w_ctl}/{w_ctl_n} |",
        f"| Customer notes written | - | {written}/{len(with_rows)} |",
        f"| Average cost per claim | €{avg_cost('without memory'):.4f} | €{avg_cost('with memory'):.4f} |",
        "",
        "| Condition | Case | Expected | Got | |",
        "|---|---|---|---|---|",
        *[f"| {r['condition']} | {r['case_id']} | {r['expected']} | {r['got']} | {'✅' if r['ok'] else '❌'} |"
          for r in rows],
        "",
        "Small sample: indicative, not a precise rate.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default=time.strftime("%m%d-%H%M"))
    parser.add_argument("--max-steps", type=int, default=25)
    args = parser.parse_args()
    asyncio.run(main_async(args.label, args.max_steps))


if __name__ == "__main__":
    main()
