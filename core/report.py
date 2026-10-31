"""The daily claims report: our code computes, a built-in Cominty agent writes, our code checks.

1. `claim_rows` and `summarise` turn the claims database into a table and the day's
   figures (counts, totals, what needs a person). Every number comes from here.
2. A built-in Cominty agent (Chat, with the Spreadsheet skill, no access to the
   claims system) receives the table as a CSV and builds an Excel workbook plus a
   short briefing for the claims manager.
3. `verify_workbook` opens the .xlsx (standard library only) and checks it against
   the table: sheets present, every claim there, every payout right, formulas used.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from xml.etree import ElementTree

STATUS_LABELS = {
    "pending_approval": "Payment prepared, waiting for approval",
    "approved": "Approved",
    "awaiting_documents": "Waiting for documents",
    "escalated": "Referred to a claims handler",
    "settlement_computed": "Amounts computed, not finished",
    "open": "Opened, not finished",
}
COLUMNS = ["claim_ref", "channel", "policy", "policyholder", "coverage", "received", "status",
           "deductible_eur", "payout_eur", "assessor_visit", "reasons_or_missing", "reviewer", "approved_by"]
SHEETS = ("Summary", "Claims", "Needs attention")


def claim_rows(claims: list[dict], reviews: dict[str, dict] | None = None) -> list[dict]:
    reviews = reviews or {}
    rows = []
    for c in claims:
        reasons = json.loads(c.get("escalation_reasons") or "[]") + \
            [f"missing {d}" for d in json.loads(c.get("requested_documents") or "[]")]
        staged = c["status"] in ("pending_approval", "approved")
        review = reviews.get(c["claim_ref"])
        rows.append({
            "claim_ref": c["claim_ref"],
            "channel": "website" if c["claim_ref"].startswith("DEMO-") else "evaluation",
            "policy": c["policy_id"],
            "policyholder": c.get("holder_name", ""),
            "coverage": c["coverage"],
            "received": c["report_date"],
            "status": STATUS_LABELS.get(c["status"], c["status"]),
            "deductible_eur": c["deductible"] if staged else "",
            "payout_eur": c["payout"] if staged else "",
            "assessor_visit": c.get("assessor_date") or "",
            "reasons_or_missing": "; ".join(reasons),
            "reviewer": {"approve": "agrees", "concerns": "raised concerns"}.get((review or {}).get("verdict"), ""),
            "approved_by": c.get("approved_by") or "",
        })
    return rows


def summarise(rows: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    waiting = [r for r in rows if r["status"] == STATUS_LABELS["pending_approval"]]
    approved = [r for r in rows if r["status"] == STATUS_LABELS["approved"]]
    attention = [r["claim_ref"] for r in rows if needs_attention(r)]
    return {
        "claims": len(rows),
        "by_status": by_status,
        "payments_waiting_approval_eur": sum(r["payout_eur"] for r in waiting),
        "payments_approved_eur": sum(r["payout_eur"] for r in approved),
        "needs_attention": attention,
    }


def needs_attention(row: dict) -> bool:
    return row["status"] not in (STATUS_LABELS["approved"],) or row["reviewer"] == "raised concerns"


def to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def report_filename(day: str) -> str:
    return f"veridia-claims-report-{day}.xlsx"


REPORT_TASK = """Build the daily claims report for Veridia Insurance's claims manager, for {day}.

The attached file {csv_name} lists every claim handled today, one row per claim ({n} claims). \
Use only this data: do not invent, drop or change any claim or amount.

Create an Excel workbook named {xlsx_name} with exactly these three sheets:
1. "Summary": the day's key figures, calculated with Excel formulas on the Claims sheet (for example \
COUNTA, COUNTIF, SUMIF): number of claims, claims per status, total payout waiting for approval, total \
payout approved. A clear title and the date.
2. "Claims": the full table from the CSV, same columns and values, with a header row, filters and readable \
column widths. Keep claim_ref in column A and payout_eur as numbers.
3. "Needs attention": the claims a person must look at (every status other than "Approved", and any \
claim where the reviewer raised concerns), with the reason.

Then reply with a briefing of at most 6 short lines for the claims manager: what happened today and what \
needs a decision first. Our system computed these figures from the same CSV, for reference: {summary}"""


def build_report_task(day: str, rows: list[dict], csv_name: str) -> str:
    return REPORT_TASK.format(day=day, csv_name=csv_name, n=len(rows), xlsx_name=report_filename(day),
                              summary=json.dumps(summarise(rows), ensure_ascii=False))


# ------------------------------------------------------------ checking the workbook
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def read_xlsx(data: bytes) -> dict[str, dict]:
    """Minimal .xlsx reader: {sheet name: {"rows": [[values]], "formulas": n}}."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in root.findall("m:si", _NS)]
    rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels.findall("rel:Relationship", _NS)}
    workbook = ElementTree.fromstring(z.read("xl/workbook.xml"))
    sheets = {}
    for sheet in workbook.find("m:sheets", _NS):
        target = targets[sheet.get(f"{{{_NS['r']}}}id")].lstrip("/")
        path = target if target.startswith("xl/") else f"xl/{target}"
        root = ElementTree.fromstring(z.read(path))
        rows, formulas = [], 0
        for row in root.iter(f"{{{_NS['m']}}}row"):
            values = []
            for cell in row.findall("m:c", _NS):
                if cell.find("m:f", _NS) is not None:
                    formulas += 1
                v, kind = cell.find("m:v", _NS), cell.get("t")
                if kind == "s" and v is not None:
                    values.append(shared[int(v.text)])
                elif kind == "inlineStr":
                    values.append("".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t")))
                else:
                    values.append(v.text if v is not None else None)
            rows.append(values)
        sheets[sheet.get("name")] = {"rows": rows, "formulas": formulas}
    return sheets


def _number(value) -> float | None:
    try:
        return float(str(value).replace("€", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def verify_workbook(data: bytes, rows: list[dict]) -> dict:
    """Check the agent's workbook against our table. Returns {"checks": [...], "passed", "total"}."""
    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        sheets = read_xlsx(data)
    except Exception as exc:  # noqa: BLE001
        check("The file is a readable Excel workbook", False, f"{type(exc).__name__}: {exc}")
        return {"checks": checks, "passed": 0, "total": 1}
    check("The file is a readable Excel workbook", True)
    names = {n.lower(): n for n in sheets}
    missing = [s for s in SHEETS if s.lower() not in names]
    check("The three sheets are there (Summary, Claims, Needs attention)", not missing,
          f"missing: {', '.join(missing)}" if missing else "")

    table = sheets.get(names.get("claims", ""), {"rows": []})["rows"]
    refs = {x["claim_ref"] for x in rows}
    found = {}
    for r in table:
        ref = next((v for v in r if isinstance(v, str) and v.strip() in refs), None)
        if ref:
            found[ref.strip()] = r
    lost = [x["claim_ref"] for x in rows if x["claim_ref"] not in found]
    check(f"Every claim is in the Claims sheet ({len(rows)})", not lost, f"missing: {', '.join(lost)}" if lost else "")

    wrong = []
    for x in rows:
        if x["payout_eur"] == "" or x["claim_ref"] not in found:
            continue
        if not any(_number(v) == float(x["payout_eur"]) for v in found[x["claim_ref"]]):
            wrong.append(x["claim_ref"])
    paid = sum(1 for x in rows if x["payout_eur"] != "")
    check(f"Every payout matches the claims system ({paid} payments)", not wrong,
          f"wrong or missing for: {', '.join(wrong)}" if wrong else "")

    summary = sheets.get(names.get("summary", ""), {"formulas": 0})
    check("The Summary figures are Excel formulas, not typed numbers", summary["formulas"] > 0,
          f"{summary['formulas']} formulas")
    attention = {x["claim_ref"] for x in rows if needs_attention(x)}
    listed = {v for r in sheets.get(names.get("needs attention", ""), {"rows": []})["rows"] for v in r if v in attention}
    check(f"Every claim needing a person is in Needs attention ({len(attention)})", listed == attention,
          f"missing: {', '.join(sorted(attention - listed))}" if listed != attention else "")
    return {"checks": checks, "passed": sum(c["ok"] for c in checks), "total": len(checks)}


def verify_briefing(text: str | None, rows: list[dict]) -> dict:
    """The briefing is free text: check what can be checked. Every euro amount and every claim
    reference it mentions must exist in the claims system (amounts: payouts, deductibles, totals)."""
    text = text or ""
    s = summarise(rows)
    known_amounts = {float(v) for r in rows for v in (r["payout_eur"], r["deductible_eur"]) if v != ""} | \
        {float(s["payments_waiting_approval_eur"]), float(s["payments_approved_eur"]), 0.0}
    amounts = [m.group(1) for m in re.finditer(r"(?:€|EUR\s?)\s?(\d[\d,. ]*\d|\d)", text)] + \
        [m.group(1) for m in re.finditer(r"(\d[\d,. ]*\d|\d)\s?(?:€|EUR)", text)]
    unknown_amounts = sorted({a for a in amounts if _number(a.replace(" ", "")) not in known_amounts})
    refs = set(re.findall(r"\b(?:DEMO|DOCS|MEM|CLM|R)-[A-Za-z0-9-]+\b", text))
    unknown_refs = sorted(refs - {r["claim_ref"] for r in rows})
    ok = not unknown_amounts and not unknown_refs
    detail = "; ".join(filter(None, [f"amounts not in the system: {', '.join(unknown_amounts)}" if unknown_amounts else "",
                                     f"unknown claims: {', '.join(unknown_refs)}" if unknown_refs else ""]))
    return {"name": "Briefing: every amount and claim it mentions exists in the claims system",
            "ok": ok, "detail": detail}
