"""Make the daily claims report from your PC, against the live server's claims. (~€0.02-0.05)

Run:  uv run python -m scripts.make_report                     (today's claims, UTC)
      uv run python -m scripts.make_report --since 2026-10-31

Reads the claims from the live server (read-only admin endpoint), asks a built-in
Cominty agent (Chat + Spreadsheet skill, no claims-system access) to build the Excel
report, then checks the workbook against the claims. Saves everything in runs/report-<date>/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from app.agent import ComintyReportRunner
from core.report import (build_report_task, claim_rows, report_filename, summarise, to_csv, verify_briefing,
                         verify_workbook)

ROOT = Path(__file__).resolve().parent.parent


async def main_async(since: str) -> None:
    from eval.run_eval import DEFAULT_SERVER, check_admin_access, http_get_json, wake_server

    load_dotenv(ROOT / ".env")
    secret = os.environ["MCP_SECRET_TOKEN"].strip()
    server = os.environ.get("SINISTRE_SERVER_URL", DEFAULT_SERVER).strip().rstrip("/")
    wake_server(server)
    check_admin_access(server, secret)
    claims = http_get_json(f"{server}/admin/{secret}/claims?since={since}")["claims"]
    if not claims:
        raise SystemExit(f"No claims on the server since {since}. Send a few claims on the website first.")
    rows = claim_rows(claims)
    print(f"{len(rows)} claims since {since}. Our figures: {json.dumps(summarise(rows), ensure_ascii=False)}")

    out = ROOT / "runs" / f"report-{since}"
    out.mkdir(parents=True, exist_ok=True)
    csv_name = f"veridia-claims-{since}.csv"
    (out / csv_name).write_text(to_csv(rows), encoding="utf-8")
    result = await ComintyReportRunner()(build_report_task(since, rows, csv_name), csv_name, to_csv(rows),
                                         lambda e: print(f"  {e['icon']} {e['text']}"))
    (out / "briefing.md").write_text(result["reply"] or "", encoding="utf-8")
    print("\nBriefing:\n" + (result["reply"] or "(none)"))
    print(f"Cost: €{float((result.get('cost') or {}).get('total') or 0):.4f}")
    if not result["files"]:
        raise SystemExit("The agent did not return an Excel file.")
    name, data = result["files"][0]
    (out / report_filename(since)).write_bytes(data)
    checks = verify_workbook(data, rows)
    checks["checks"].append(verify_briefing(result["reply"], rows))
    checks["passed"], checks["total"] = sum(c["ok"] for c in checks["checks"]), len(checks["checks"])
    (out / "checks.json").write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWorkbook {name} saved in {out.relative_to(ROOT)}. Checks: {checks['passed']}/{checks['total']}")
    for c in checks["checks"]:
        print(f"  {'✅' if c['ok'] else '❌'} {c['name']}" + (f"  ({c['detail']})" if c["detail"] and not c["ok"] else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=datetime.now(timezone.utc).date().isoformat())
    asyncio.run(main_async(parser.parse_args().since))


if __name__ == "__main__":
    main()
