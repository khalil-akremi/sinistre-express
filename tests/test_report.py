"""Tests for the daily report: figures from code, workbook checks, the app routes."""

import io
import time
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from starlette.testclient import TestClient

from app.web import register_web_routes
from core.report import build_report_task, claim_rows, read_xlsx, summarise, to_csv, verify_workbook
from mcp_server.server import build_server
from mcp_server.tools import ClaimsSystem
from tests.test_app import FakeAgent, desk, start, wait_done  # noqa: F401  (desk is a fixture)


def make_xlsx(sheets: dict[str, list[list]]) -> bytes:
    """A minimal real .xlsx: values as inline strings or numbers; strings starting with '=' become formulas."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        sheet_xml = "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(sheets))
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   f"<sheets>{sheet_xml}</sheets></workbook>")
        rels = "".join(f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml" Type="x"/>'
                       for i in range(len(sheets)))
        z.writestr("xl/_rels/workbook.xml.rels",
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for i, rows in enumerate(sheets.values()):
            body = ""
            for r in rows:
                cells = ""
                for v in r:
                    if isinstance(v, (int, float)):
                        cells += f"<c><v>{v}</v></c>"
                    elif isinstance(v, str) and v.startswith("="):
                        cells += f"<c><f>{escape(v[1:])}</f><v>0</v></c>"
                    else:
                        cells += f'<c t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
                body += f"<row>{cells}</row>"
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml",
                       f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>')
    return buf.getvalue()


def claims_db(tmp_path):
    """A claims system with a staged payment, a referral and a document request."""
    from tests.test_grade import CASES, replay

    system = ClaimsSystem(tmp_path / "r.db")
    for case_id, ref in (("CLM-B", "DEMO-1"), ("CLM-15", "DEMO-2"), ("CLM-12", "DEMO-3")):
        replay(system, next(c for c in CASES if c["case_id"] == case_id) | {"case_id": ref})
    return system


def good_workbook(rows):
    table = [list(rows[0].keys())] + [list(r.values()) for r in rows]
    attention = [["claim_ref", "why"]] + [[r["claim_ref"], r["status"]] for r in rows if r["status"] != "Approved"]
    return make_xlsx({"Summary": [["Claims", "=COUNTA(Claims!A2:A100)"]], "Claims": table, "Needs attention": attention})


def test_rows_and_figures_come_from_the_claims_system(tmp_path):
    rows = claim_rows(claims_db(tmp_path).list_claims())
    by_ref = {r["claim_ref"]: r for r in rows}
    assert by_ref["DEMO-1"]["payout_eur"] == 1700 and by_ref["DEMO-1"]["policyholder"] == "Lucas Bernard"
    assert by_ref["DEMO-2"]["payout_eur"] == "" and "late_report" in by_ref["DEMO-2"]["reasons_or_missing"]
    assert "missing photos" in by_ref["DEMO-3"]["reasons_or_missing"]
    s = summarise(rows)
    assert s["claims"] == 3 and s["payments_waiting_approval_eur"] == 1700 and len(s["needs_attention"]) == 3
    assert to_csv(rows).splitlines()[0].startswith("claim_ref,channel,policy")
    task = build_report_task("2026-10-31", rows, "c.csv")
    assert '"Summary"' in task and "Excel formulas" in task and "1700" in task


def test_a_correct_workbook_passes_every_check(tmp_path):
    rows = claim_rows(claims_db(tmp_path).list_claims())
    result = verify_workbook(good_workbook(rows), rows)
    assert result["passed"] == result["total"] == 6, result


def test_a_wrong_payout_a_lost_claim_and_typed_numbers_are_caught(tmp_path):
    rows = claim_rows(claims_db(tmp_path).list_claims())
    table = [list(rows[0].keys())] + [list(r.values()) for r in rows if r["claim_ref"] != "DEMO-3"]
    table[1][table[0].index("payout_eur")] = 1500  # DEMO-1: the agent "rounded" the payout
    data = make_xlsx({"Summary": [["Claims", 3]], "Claims": table, "Needs attention": [["DEMO-1"]]})
    failed = {c["name"].split(" (")[0] for c in verify_workbook(data, rows)["checks"] if not c["ok"]}
    assert failed == {"Every claim is in the Claims sheet", "Every payout matches the claims system",
                      "The Summary figures are Excel formulas, not typed numbers",
                      "Every claim needing a person is in Needs attention"}


def test_not_an_excel_file(tmp_path):
    rows = claim_rows(claims_db(tmp_path).list_claims())
    assert verify_workbook(b"not a zip", rows)["passed"] == 0
    assert read_xlsx(good_workbook(rows))["Summary"]["formulas"] == 1


# ----------------------------------------------------------------- the app
class FakeReporter:
    def __init__(self):
        self.calls = []

    async def __call__(self, task, csv_name, csv_text, on_event):
        import csv as csvlib

        self.calls.append((task, csv_name, csv_text))
        on_event({"source": "agent", "icon": "🧰", "text": "Loading a skill (e.g. Spreadsheet)"})
        rows = list(csvlib.DictReader(io.StringIO(csv_text)))
        for r in rows:
            r["payout_eur"] = int(r["payout_eur"]) if r["payout_eur"] else ""
        return {"reply": "- 1 payment waiting for approval", "files": [("report.xlsx", good_workbook(rows))],
                "cost": {"total": "0.02"}}


def test_report_route_builds_checks_and_serves_the_workbook(tmp_path):
    system = ClaimsSystem(tmp_path / "t.db")
    server = build_server(system, admin_secret="s3cret")
    reporter = FakeReporter()
    register_web_routes(server, system, FakeAgent(system), daily_max=10, reporter=reporter)
    with TestClient(server.streamable_http_app()) as client:
        assert client.post("/api/report").status_code == 409  # nothing handled today yet
        wait_done(client, start(client, "CLM-B").json()["claim_ref"])
        report_id = client.post("/api/report").json()["report_id"]
        for _ in range(100):
            data = client.get(f"/api/report/{report_id}").json()
            if data["done"]:
                break
            time.sleep(0.05)
        assert data["claims"] == 1 and data["checks"]["passed"] == data["checks"]["total"], data
        assert "veridia-claims-" in reporter.calls[0][1] and "DEMO-" in reporter.calls[0][2]
        res = client.get(data["file_url"])
        day = datetime.now(timezone.utc).date().isoformat()
        assert res.status_code == 200 and res.content.startswith(b"PK")
        assert f"veridia-claims-report-{day}.xlsx" in res.headers["content-disposition"]


def test_report_is_off_without_a_reporter(desk):
    client, _ = desk
    assert client.post("/api/report").status_code == 404


def test_admin_claim_list_needs_the_secret(tmp_path):
    system = claims_db(tmp_path)
    with TestClient(build_server(system, admin_secret="s3cret").streamable_http_app()) as client:
        assert client.get("/admin/wrong/claims").status_code == 404
        assert len(client.get("/admin/s3cret/claims?since=2000-01-01").json()["claims"]) == 3
