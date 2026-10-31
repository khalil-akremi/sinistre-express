"""Generate the document claims: emails that leave facts out, and the PDFs that hold them.

Run:  uv run python -m eval.generate_documents      (needs reportlab, Pillow, pdftoppm, img2pdf)

The generated files are committed in data/documents/, so running the app or the
evaluation does not need these tools; only regenerating does.

Each case tests one reading skill:

    DOC-01  fault is only in the accident report (typed PDF)
    DOC-02  the other vehicle is a company van, only stated in the report  (+ memory rule)
    DOC-03  the repair amount is only in a SCANNED quote (image, no text layer: OCR)
    DOC-04  the email's amount is wrong; the written quote says more (assessor needed)
    DOC-05  the quote is for another person's car: not a valid document
    DOC-06  the theft date is only in a SCANNED police receipt

Writes data/documents/<case>/<file>.pdf and data/doc_cases.json (email, files,
true facts, expected outcome). As in generate_cases, the answer key comes from
core.rules, the same code as the MCP tools.
"""

from __future__ import annotations

import json
import random
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from core.rules import Claim, Coverage, expected_outcome
from eval.generate_cases import POLICY_BY_ID, _jsonable

ROOT = Path(__file__).resolve().parent.parent
DOC_DIR = ROOT / "data" / "documents"
C2, C3, C4 = Coverage.COLLISION, Coverage.GLASS, Coverage.THEFT

# The playbook rule used by the document evaluation (same as the memory experiment).
VAN_RULE = ("When the other driver is a commercial vehicle (van, truck, lorry, delivery vehicle), "
            "refer the claim to a handler so Veridia can recover the money from their insurer.")

PLATES = {"VER-1001": "FG-218-LM", "VER-1002": "GK-904-TR", "VER-1003": "EH-552-PB",
          "VER-1004": "FD-371-WS", "VER-1007": "GL-660-ZA"}


@dataclass(frozen=True)
class Quote:
    garage: str
    lines: tuple[tuple[str, float], ...]  # description, share of the total before VAT
    total: int                            # total including VAT (the repair cost)
    customer: str | None = None           # None: the policyholder
    vehicle: str | None = None            # None: the insured vehicle
    plate: str | None = None


@dataclass(frozen=True)
class AccidentReport:
    location: str
    time: str
    b_driver: str
    b_vehicle: str
    b_type: str          # Car / Van / Truck / Motorbike
    b_plate: str
    b_insurer: str
    b_owner: str
    a_boxes: tuple[str, ...]
    b_boxes: tuple[str, ...]
    a_note: str
    b_note: str


@dataclass(frozen=True)
class PoliceReceipt:
    station: str
    number: str
    theft_place: str
    theft_time: str


@dataclass(frozen=True)
class DocScenario:
    case_id: str
    title: str
    skill: str
    policy_id: str
    coverage: Coverage
    incident: date
    delay_days: int
    story: str
    at_fault: bool = True
    third_party_involved: bool = False
    third_party_identified: bool = False
    quote: Quote | None = None
    report: AccidentReport | None = None
    police: PoliceReceipt | None = None
    scanned: tuple[str, ...] = ()        # which documents are scans: "quote", "report", "police"
    photos: bool = True                  # damage photos received by the mailroom (not readable)
    valid_documents: tuple[str, ...] = ()
    playbook_referral: bool = False      # the van rule applies
    ungraded: tuple[str, ...] = ()       # facts with no single right answer
    extra: dict = field(default_factory=dict)


BODY_LINES = (("Bodywork repair, front left wing and door", 0.34), ("Parts: wing panel, door moulding, clips", 0.28),
              ("Paint and varnish, 2 panels", 0.18), ("Labour, 7.5 h at the workshop rate", 0.20))
GLASS_LINES = (("Windscreen, laminated, with rain sensor bracket", 0.55),
               ("Driver-assistance camera recalibration", 0.25), ("Labour and adhesive kit", 0.20))

SCENARIOS = [
    DocScenario(
        "DOC-01", "Fault only in the accident report", "read a typed accident report",
        "VER-1002", C2, date(2026, 10, 14), 1,
        "I had a collision with another car on the ring road on 14 October 2026 while we were both "
        "changing lanes. The other driver and I filled in the accident report together.",
        at_fault=True, third_party_involved=True, third_party_identified=True,
        quote=Quote("Garage du Parc, 22 avenue Jean Jaurès, 69007 Lyon", BODY_LINES, 2400),
        report=AccidentReport("Boulevard périphérique Laurent Bonnevay, Lyon, exit 6", "08:40",
                              "Ms. Julie Laurent", "Renault Mégane", "Car", "FB-127-QX", "Assurances Rhône Mutuelle",
                              "Julie Laurent", ("Was changing lanes",), ("Was driving in the same direction, in another lane",),
                              "I moved into the left lane without seeing vehicle B in my blind spot. I accept that "
                              "the accident is my fault.", "I was driving straight in my lane."),
        valid_documents=("photos", "repair_quote", "accident_report")),
    DocScenario(
        "DOC-02", "Company van only stated in the report", "notice a fact that triggers a playbook rule",
        "VER-1001", C2, date(2026, 10, 12), 2,
        "Another vehicle hit the side of my car at the Rue de Rivoli crossing on 12 October 2026. "
        "It was not my fault, and the other driver signed the accident report.",
        at_fault=False, third_party_involved=True, third_party_identified=True,
        quote=Quote("Carrosserie Saint-Paul, 9 rue de Rivoli, 75004 Paris", BODY_LINES, 1200),
        report=AccidentReport("Rue de Rivoli / Rue du Renard crossing, 75004 Paris", "17:15",
                              "Mr. Marc Dubois", "Ford Transit Custom", "Van", "GA-845-HN", "Axelia Pro Assurances",
                              "Rapid Livraisons SARL (company vehicle)", ("Was going straight on at a crossing",),
                              ("Was going straight on at a crossing", "Did not respect a red light"),
                              "I had a green light. Vehicle B came from my right and hit my front left door.",
                              "I did not see the light turn red. I accept responsibility for the accident."),
        valid_documents=("photos", "repair_quote", "accident_report"), playbook_referral=True),
    DocScenario(
        "DOC-03", "Repair amount only in a scanned quote", "read a scanned document (OCR)",
        "VER-1007", C3, date(2026, 10, 26), 1,
        "A stone thrown up on the A6 motorway on 26 October 2026 cracked my windscreen. "
        "I scanned the glass repair quote.",
        at_fault=False,
        quote=Quote("France Vitrage Auto, 41 route de Lyon, 89000 Auxerre", GLASS_LINES, 1180),
        scanned=("quote",), valid_documents=("photos", "repair_quote")),
    DocScenario(
        "DOC-04", "The email amount is wrong", "trust the issued document over the email, and say so",
        "VER-1004", C2, date(2026, 10, 27), 1,
        "I hit a post in an underground car park on 27 October 2026. Nobody else was involved. "
        "The garage told me on the phone it would be around €900; the written quote is attached.",
        quote=Quote("Garage Central Auto, 5 rue Nationale, 59000 Lille", BODY_LINES, 1640),
        valid_documents=("photos", "repair_quote")),
    DocScenario(
        "DOC-05", "Quote for another person's car", "check that a document belongs to this claim",
        "VER-1003", C2, date(2026, 10, 28), 1,
        "I scraped the side of my car against a gate on 28 October 2026. No one else was involved. "
        "The quote is attached.",
        quote=Quote("Garage des Lilas, 14 rue des Lilas, 33000 Bordeaux", BODY_LINES, 980,
                    customer="Mr. Julien Roche", vehicle="Renault Clio (2017)", plate="DX-482-KD"),
        valid_documents=("photos",), ungraded=("repair_cost",)),
    DocScenario(
        "DOC-06", "Theft date only in a scanned police receipt", "read a scanned official form (OCR)",
        "VER-1001", C4, date(2026, 10, 29), 1,
        "My car was stolen from the street where I live. I filed a complaint at the police station "
        "this morning; the receipt is attached (scanned).",
        police=PoliceReceipt("District 11 police station", "2026/011/48213",
                             "In front of 37 rue des Tilleuls, District 11", "between 21:00 and 23:45"),
        scanned=("police",), photos=False, valid_documents=("police_report",)),
]

FILENAMES = {"quote": "repair_quote.pdf", "report": "accident_report_signed.pdf", "police": "police_report.pdf"}


# ------------------------------------------------------------------ drawing
def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for name, file in (("Sans", "DejaVuSans.ttf"), ("Sans-Bold", "DejaVuSans-Bold.ttf"),
                       ("Mono", "DejaVuSansMono.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, f"/usr/share/fonts/truetype/dejavu/{file}"))


def _euro(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def draw_quote(path: Path, s: DocScenario) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    q, policy = s.quote, POLICY_BY_ID[s.policy_id]
    c = Canvas(str(path), pagesize=A4)
    w, h = A4
    garage, address = q.garage.split(", ", 1)
    c.setFont("Sans-Bold", 16); c.drawString(50, h - 60, garage)
    c.setFont("Sans", 9); c.drawString(50, h - 75, address)
    c.drawString(50, h - 87, "SIRET 812 345 678 00021  ·  Approved repairer")
    c.setFont("Sans-Bold", 20); c.drawRightString(w - 50, h - 60, "REPAIR QUOTE")
    c.setFont("Sans", 9)
    number = f"Q-{s.incident:%y%m}-{sum(map(ord, s.case_id)) * 37 % 9000 + 1000}"
    issued = s.incident + timedelta(days=1)
    c.drawRightString(w - 50, h - 78, f"Quote no. {number}")
    c.drawRightString(w - 50, h - 90, f"Issued {issued:%d/%m/%Y}  ·  valid 30 days")

    c.rect(50, h - 175, w - 100, 70)
    c.setFont("Sans-Bold", 9); c.drawString(60, h - 122, "Customer"); c.drawString(300, h - 122, "Vehicle")
    c.setFont("Sans", 10)
    c.drawString(60, h - 138, q.customer or policy.holder_name)
    c.drawString(60, h - 152, f"Insurer: {'Veridia Insurance, policy ' + policy.policy_id if not q.customer else 'not stated'}")
    c.drawString(300, h - 138, q.vehicle or policy.vehicle)
    c.drawString(300, h - 152, f"Registration: {q.plate or PLATES[s.policy_id]}")

    net = round(q.total / 1.2, 2)
    vat = round(q.total - net, 2)
    amounts = [round(net * share, 2) for _, share in q.lines]
    amounts[-1] = round(net - sum(amounts[:-1]), 2)
    y = h - 210
    c.setFont("Sans-Bold", 9)
    c.drawString(55, y, "Description"); c.drawRightString(w - 55, y, "Amount excl. VAT")
    c.line(50, y - 6, w - 50, y - 6)
    c.setFont("Sans", 10)
    for (text, _), amount in zip(q.lines, amounts):
        y -= 22
        c.drawString(55, y, text); c.drawRightString(w - 55, y, _euro(amount))
    y -= 14; c.line(50, y, w - 50, y)
    for label, value, bold in (("Total excl. VAT", net, False), ("VAT 20 %", vat, False),
                               ("TOTAL INCL. VAT", q.total, True)):
        y -= 20
        c.setFont("Sans-Bold" if bold else "Sans", 12 if bold else 10)
        c.drawRightString(w - 200, y, label); c.drawRightString(w - 55, y, _euro(value))
    c.setFont("Sans", 8)
    c.drawString(50, 80, "Prices include parts and labour. Any additional damage found during the repair will be quoted separately.")
    c.drawString(50, 68, "Signature and stamp of the repairer:")
    _scribble(c, 230, 62)
    _footer(c)
    c.showPage(); c.save()


def draw_report(path: Path, s: DocScenario) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    r, policy = s.report, POLICY_BY_ID[s.policy_id]
    c = Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Sans-Bold", 15); c.drawCentredString(w / 2, h - 50, "JOINT ACCIDENT REPORT")
    c.setFont("Sans", 8); c.drawCentredString(w / 2, h - 62, "To be completed by both drivers and signed. Does not constitute an admission of liability.")
    c.setFont("Sans", 9)
    c.drawString(50, h - 85, f"1. Date of accident: {s.incident:%d/%m/%Y}     Time: {r.time}")
    c.drawString(50, h - 99, f"2. Location: {r.location}")
    c.drawString(50, h - 113, "3. Injuries, even minor: [ ] yes  [X] no        4. Damage to other objects: [ ] yes  [X] no")

    cols = ((50, "VEHICLE A", [("Policyholder", policy.holder_name), ("Insurer", "Veridia Insurance"),
                                ("Policy no.", policy.policy_id), ("Make, model", policy.vehicle),
                                ("Vehicle type", "Car"), ("Registration", PLATES[s.policy_id]),
                                ("Driver", policy.holder_name)]),
            (w / 2 + 5, "VEHICLE B", [("Policyholder", r.b_owner), ("Insurer", r.b_insurer),
                                      ("Policy no.", "see insurer certificate"), ("Make, model", r.b_vehicle),
                                      ("Vehicle type", r.b_type), ("Registration", r.b_plate),
                                      ("Driver", r.b_driver)]))
    for x, title, rows in cols:
        c.rect(x, h - 300, w / 2 - 55, 170)
        c.setFont("Sans-Bold", 11); c.drawString(x + 8, h - 148, title)
        y = h - 166
        for label, value in rows:
            c.setFont("Sans", 7); c.drawString(x + 8, y, label.upper())
            c.setFont("Sans", 9); c.drawString(x + 8, y - 10, value)
            y -= 19

    boxes = ["Was parked", "Was leaving a parking space", "Was reversing", "Was changing lanes",
             "Was going straight on at a crossing", "Was driving in the same direction, in another lane",
             "Was turning right", "Did not respect a red light", "Opened a door"]
    y = h - 330
    c.setFont("Sans-Bold", 10); c.drawString(50, y, "12. CIRCUMSTANCES  (tick the boxes that apply)")
    c.setFont("Sans", 9); c.drawString(70, y - 16, "A"); c.drawString(w - 85, y - 16, "B")
    y -= 32
    for b in boxes:
        c.rect(66, y - 2, 10, 10); c.rect(w - 89, y - 2, 10, 10)
        if b in r.a_boxes:
            c.drawString(68, y, "X")
        if b in r.b_boxes:
            c.drawString(w - 87, y, "X")
        c.drawCentredString(w / 2, y, b)
        y -= 17

    y -= 10
    c.setFont("Sans-Bold", 10); c.drawString(50, y, "14. OBSERVATIONS")
    for who, note in (("Driver A", r.a_note), ("Driver B", r.b_note)):
        y -= 16
        c.setFont("Sans-Bold", 9); c.drawString(50, y, f"{who}:")
        c.setFont("Sans", 9)
        for chunk in _wrap(note, 95):
            c.drawString(100, y, chunk); y -= 12
    c.setFont("Sans-Bold", 10); c.drawString(50, 120, "15. SIGNATURES")
    c.setFont("Sans", 9); c.drawString(50, 102, "Driver A"); c.drawString(w / 2 + 5, 102, "Driver B")
    _scribble(c, 110, 95); _scribble(c, w / 2 + 70, 95, seed=7)
    _footer(c)
    c.showPage(); c.save()


def draw_police(path: Path, s: DocScenario) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    p, policy = s.police, POLICY_BY_ID[s.policy_id]
    complaint = s.incident + timedelta(days=s.delay_days)
    c = Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Sans-Bold", 11); c.drawString(50, h - 55, "VERIDIA CITY POLICE (fictional)")
    c.setFont("Sans", 9); c.drawString(50, h - 68, p.station)
    c.setFont("Sans-Bold", 15); c.drawCentredString(w / 2, h - 110, "RECEIPT OF A THEFT COMPLAINT")
    c.setFont("Sans", 9); c.drawCentredString(w / 2, h - 124, "(vehicle theft)")
    rows = [("Complaint no.", p.number), ("Complaint filed on", f"{complaint:%d/%m/%Y} at 09:25"),
            ("Complainant", policy.holder_name), ("Vehicle", policy.vehicle),
            ("Registration", PLATES[s.policy_id]), ("Place of the theft", p.theft_place),
            ("Date of the theft", f"{s.incident:%d/%m/%Y}, {p.theft_time}"),
            ("Keys", "both keys kept by the complainant"),
            ("Signs of break-in reported", "glass of the driver's door found on the ground")]
    y = h - 165
    for label, value in rows:
        c.setFont("Sans-Bold", 10); c.drawString(60, y, f"{label}:")
        c.setFont("Sans", 10); c.drawString(220, y, value)
        y -= 24
    c.setFont("Sans", 9)
    for chunk in _wrap("The complainant declares the theft of the vehicle described above. This receipt may be "
                       "sent to the insurer. The vehicle has been entered in the register of stolen vehicles.", 100):
        y -= 14; c.drawString(60, y, chunk)
    c.circle(w - 140, 150, 45); c.setFont("Sans-Bold", 7)
    c.drawCentredString(w - 140, 154, "CITY POLICE"); c.drawCentredString(w - 140, 144, "DISTRICT 11")
    c.setFont("Sans", 9); c.drawString(60, 150, "The officer receiving the complaint:")
    _scribble(c, 70, 125, seed=3)
    _footer(c)
    c.showPage(); c.save()


def _footer(c) -> None:
    """Every page says it is synthetic, so no document can pass as a real record."""
    from reportlab.lib.pagesizes import A4

    c.setFont("Sans", 7)
    c.drawCentredString(A4[0] / 2, 28, "SYNTHETIC TEST DOCUMENT · Sinistre Express demo · fictional people, companies and numbers")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line]


def _scribble(c, x: float, y: float, seed: int = 1) -> None:
    rnd = random.Random(seed)
    path = c.beginPath(); path.moveTo(x, y)
    for i in range(1, 12):
        path.curveTo(x + i * 6 - 3, y + rnd.uniform(-9, 12), x + i * 6 - 1, y + rnd.uniform(-9, 12), x + i * 6, y + rnd.uniform(-3, 4))
    c.setLineWidth(0.9); c.drawPath(path); c.setLineWidth(1)


def scan(pdf: Path, seed: int) -> None:
    """Turn a typed PDF into a 'scan': a slightly rotated, noisy grey image with no text layer."""
    from PIL import Image, ImageFilter

    rnd = random.Random(seed)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "110", "-gray", "-png", str(pdf), f"{tmp}/p"], check=True)
        page = Image.open(next(Path(tmp).glob("p*.png"))).convert("L")
        page = page.rotate(rnd.uniform(-1.6, 1.6), expand=True, fillcolor=235)
        page = page.filter(ImageFilter.GaussianBlur(0.6))
        noise = Image.effect_noise(page.size, 18)
        page = Image.blend(page, noise, 0.10).point(lambda v: min(255, int(v * 0.93 + 14)))
        jpg = Path(tmp) / "scan.jpg"
        page.save(jpg, quality=55)
        subprocess.run(["img2pdf", str(jpg), "-o", str(pdf)], check=True)


# ------------------------------------------------------------------ cases
def render_email(s: DocScenario) -> dict:
    policy = POLICY_BY_ID[s.policy_id]
    files = [FILENAMES[k] for k in ("report", "quote", "police") if getattr(s, k)]
    mailroom = ["damage_photos.zip"] if s.photos else []
    kind = {C2: "accident", C3: "broken glass", C4: "theft"}[s.coverage]
    body = "\n".join(["Hello Veridia,", "", s.story, "", "Kind regards,", policy.holder_name,
                      f"Policy number: {policy.policy_id}", "", "Attached: " + ", ".join(files + mailroom)])
    return {
        "date": (s.incident + timedelta(days=s.delay_days)).isoformat(),
        "from": policy.holder_name,
        "subject": f"Claim - {kind} - {policy.policy_id}",
        "body": body,
        "attachments": mailroom,                                   # stored by the mailroom, not readable
        "files": [f"data/documents/{s.case_id}/{f}" for f in files],  # uploaded with the message
    }


def build_case(s: DocScenario) -> dict:
    policy = POLICY_BY_ID[s.policy_id]
    claim = Claim(
        claim_ref=s.case_id, policy_id=s.policy_id, coverage=s.coverage,
        incident_date=s.incident, report_date=s.incident + timedelta(days=s.delay_days),
        repair_cost=s.quote.total if s.quote and "repair_cost" not in s.ungraded else 0,
        at_fault=s.at_fault if s.coverage == C2 else False, third_party_involved=s.third_party_involved,
        third_party_identified=s.third_party_identified, documents_provided=s.valid_documents,
        exclusion_signal=None,
    )
    expected = _jsonable(expected_outcome(claim, policy).to_dict())
    if s.playbook_referral:  # the van rule: refer instead of settling (amounts may still be computed)
        expected = {"decision": "escalate", "expected_actions": ["get_policy", "create_claim", "escalate_to_handler"],
                    "optional_actions": ["compute_settlement"], "forbidden_actions": ["stage_settlement"],
                    "missing_documents": [], "escalation_reasons": ["other"], "settlement": None,
                    "settlement_without_rule": expected["settlement"]}
    facts = _jsonable(asdict(claim))
    facts["ungraded"] = list(s.ungraded)
    return {"case_id": s.case_id, "title": s.title, "skill": s.skill, "scanned": list(s.scanned),
            "email": render_email(s), "facts": facts, "expected": expected}


def main() -> None:
    _fonts()
    cases = []
    for i, s in enumerate(SCENARIOS):
        folder = DOC_DIR / s.case_id
        folder.mkdir(parents=True, exist_ok=True)
        for kind, draw in (("quote", draw_quote), ("report", draw_report), ("police", draw_police)):
            if getattr(s, kind):
                path = folder / FILENAMES[kind]
                draw(path, s)
                if kind in s.scanned:
                    scan(path, seed=i)
        cases.append(build_case(s))
    (ROOT / "data" / "doc_cases.json").write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in cases:
        e = c["expected"]
        money = f"€{e['settlement']['deductible']} / €{e['settlement']['payout']}" if e["settlement"] else "-"
        print(f"{c['case_id']}  {e['decision']:18} {money:16} {c['title']}")


if __name__ == "__main__":
    main()
