"""Robustness and consistency of the Handler agent.

Run:  uv run python -m eval.robustness --label v1                  (both experiments, ~44 runs, ~€0.30)
      uv run python -m eval.robustness --label v1 --only paraphrase
      uv run python -m eval.robustness --label v1 --only repeat --repeats 5

1. Paraphrase robustness: 6 claims, each rewritten 4 ways (eval/paraphrases.py:
   formal, casual with typos, rambling with relative dates, other number formats).
   The facts are the same, so the decision and amounts must be the same.
2. Repeated runs: the same 4 claims run 5 times each, unchanged. An agent is not
   deterministic: how often does it decide the same way, record the same facts,
   and how much do cost, time and the number of steps vary?

Graded with the same grader as the main evaluation (eval/grade.py). Memory is off,
as in the main evaluation. Finished runs are kept: re-running the same label resumes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

from eval.grade import grade_case
from eval.paraphrases import PARAPHRASES

ROOT = Path(__file__).resolve().parent.parent
REPEAT_CASES = ["CLM-B", "CLM-06", "CLM-14", "CLM-16"]  # settle, threshold, missing document, exclusion
STYLES = ["formal", "casual", "rambling", "formats"]


def paraphrase_cases(cases: dict) -> list[dict]:
    out = []
    for case_id, variants in PARAPHRASES.items():
        base = cases[case_id]
        attached = base["email"]["attachments"]
        for style in STYLES:
            body = variants[style] + (f"\n\nAttached: {', '.join(attached)}" if attached else "")
            out.append(base | {"case_id": f"{case_id}_{style}", "base": case_id, "style": style,
                               "email": base["email"] | {"body": body}})
    return out


def repeat_cases(cases: dict, repeats: int) -> list[dict]:
    return [cases[c] | {"case_id": f"{c}_r{i}", "base": c, "run": i}
            for c in REPEAT_CASES for i in range(1, repeats + 1)]


def load_grades(run_dir: Path, cases: list[dict]) -> list[dict]:
    grades = []
    for case in cases:
        path = run_dir / f"{case['case_id']}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            created = next((e["arguments"] for e in record.get("action_log") or []
                            if e["tool"] == "create_claim" and e["ok"]), None)
            grades.append(grade_case(case, record) | {"base": case["base"], "style": case.get("style"),
                                                      "created": created})
    return grades


def render_paraphrase(grades: list[dict]) -> list[str]:
    if not grades:
        return []
    n = len(grades)
    lines = ["## 1. Same claim, written differently", "",
             f"Right decision: **{sum(g['decision_ok'] for g in grades)}/{n}** · "
             f"right amounts: {sum(bool(g['amounts_ok']) for g in grades if g['amounts_ok'] is not None)}/"
             f"{sum(1 for g in grades if g['amounts_ok'] is not None)} · "
             f"all facts right: {sum(g['facts_ok'] for g in grades)}/{n} · "
             f"safety violations: {sum(not g['safe'] for g in grades)}", "",
             "| Claim (expected) | " + " | ".join(STYLES) + " |", "|---|" + "---|" * len(STYLES)]
    for base in PARAPHRASES:
        row = {g["style"]: g for g in grades if g["base"] == base}
        if not row:
            continue
        expected = next(iter(row.values()))["expected_decision"]
        cells = []
        for style in STYLES:
            g = row.get(style)
            if g is None:
                cells.append("·")
                continue
            wrong = [f for f, ok in g["facts"].items() if not ok]
            mark = "✅" if g["decision_ok"] and g["amounts_ok"] is not False else "❌ " + g["decision"]
            cells.append(mark + (f" (fact: {', '.join(wrong)})" if wrong else ""))
        lines.append(f"| {base} ({expected}) | " + " | ".join(cells) + " |")
    by_style = {s: [g for g in grades if g["style"] == s] for s in STYLES}
    lines += ["", "Per style: " + " · ".join(
        f"{s} {sum(g['decision_ok'] and g['facts_ok'] for g in gs)}/{len(gs)} fully right" for s, gs in by_style.items() if gs)]
    return lines


def render_repeat(grades: list[dict]) -> list[str]:
    if not grades:
        return []
    lines = ["## 2. Same claim, run several times", "",
             "| Claim (expected) | Decisions | Same facts every run | Steps (min–max) | Cost (mean ± sd) | Time (min–max) |",
             "|---|---|---|---|---|---|"]
    for base in REPEAT_CASES:
        gs = [g for g in grades if g["base"] == base]
        if not gs:
            continue
        decisions = {}
        for g in gs:
            decisions[g["decision"]] = decisions.get(g["decision"], 0) + 1
        facts = {json.dumps({k: (g["created"] or {}).get(k) for k in g["facts"]}, sort_keys=True) for g in gs}
        costs = [g["cost_eur"] for g in gs]
        steps = [g["tool_calls"] for g in gs]
        secs = [g["seconds"] for g in gs]
        sd = statistics.stdev(costs) if len(costs) > 1 else 0
        lines.append(f"| {base} ({gs[0]['expected_decision']}) | "
                     + ", ".join(f"{d} ×{k}" for d, k in decisions.items())
                     + f" | {'yes' if len(facts) == 1 else f'no ({len(facts)} versions)'} | "
                     f"{min(steps)}–{max(steps)} | €{statistics.mean(costs):.4f} ± {sd:.4f} | "
                     f"{min(secs):.0f}–{max(secs):.0f} s |")
    same = sum(g["decision_ok"] for g in grades)
    lines += ["", f"Right decision on {same}/{len(grades)} repeated runs."]
    return lines


async def main_async(args: argparse.Namespace) -> None:
    from eval.run_eval import DEFAULT_SERVER, check_admin_access, run_cases, wake_server

    load_dotenv(ROOT / ".env")
    agent_id = os.environ["COMINTY_AGENT_ID"].strip()
    secret = os.environ["MCP_SECRET_TOKEN"].strip()
    server = os.environ.get("SINISTRE_SERVER_URL", DEFAULT_SERVER).strip().rstrip("/")
    cases = {c["case_id"]: c for c in json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))}
    run_dir = ROOT / "runs" / f"robust-{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    para = paraphrase_cases(cases) if args.only in (None, "paraphrase") else []
    rep = repeat_cases(cases, args.repeats) if args.only in (None, "repeat") else []
    if args.cases:  # e.g. --cases CLM-B_formats CLM-06  (a base id selects all its variants)
        keep = lambda c: c["case_id"] in args.cases or c["base"] in args.cases  # noqa: E731
        para, rep = [c for c in para if keep(c)], [c for c in rep if keep(c)]
    print(f"Robustness '{args.label}': {len(para)} rewritten claims, {len(rep)} repeated runs")
    wake_server(server)
    check_admin_access(server, secret)
    await run_cases(para + rep, run_dir, server, secret, agent_id, f"RB{args.label}", args.max_steps)
    report = render(run_dir, cases, args.repeats)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)


def render(run_dir: Path, cases: dict, repeats: int) -> str:
    lines = ["# Robustness and consistency", ""]
    lines += render_paraphrase(load_grades(run_dir, paraphrase_cases(cases)))
    lines += [""] + render_repeat(load_grades(run_dir, repeat_cases(cases, repeats)))
    lines += ["", "Small samples: they show how stable the agent is, not precise rates."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default=time.strftime("%m%d-%H%M"))
    parser.add_argument("--only", choices=["paraphrase", "repeat"])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--cases", nargs="*", help="only these runs, e.g. CLM-B_formats CLM-06")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    if args.report_only:
        cases = {c["case_id"]: c for c in json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))}
        print(render(ROOT / "runs" / f"robust-{args.label}", cases, args.repeats))
        return
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
