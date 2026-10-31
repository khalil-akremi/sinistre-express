"""Tests for the robustness experiment: rewritten emails keep their facts; the report counts right."""

import json
import re

from eval.paraphrases import PARAPHRASES
from eval.robustness import STYLES, paraphrase_cases, render, repeat_cases
from mcp_server.tools import ClaimsSystem
from tests.test_grade import CASES, replay

BY_ID = {c["case_id"]: c for c in CASES}
AMOUNT_WORDS = {700: "seven hundred", 650: "six hundred and fifty", 1200: "one thousand two hundred",
                1800: "one thousand eight hundred", 2400: "two thousand four hundred"}


def amounts_in(text: str) -> set[int]:
    found = set()
    for m in re.finditer(r"\d[\d.,]*", text):
        digits = re.sub(r"[.,]\d{2}$", "", m.group(0))  # drop cents: 2.400,00 -> 2.400
        value = int(re.sub(r"[.,]", "", digits))
        found.add(value)
    return found


def test_every_claim_has_four_styles():
    assert set(PARAPHRASES) == {"CLM-A", "CLM-B", "CLM-09", "CLM-12", "CLM-15", "CLM-16"}
    assert all(set(v) == set(STYLES) for v in PARAPHRASES.values())


def test_rewritten_emails_keep_the_repair_amount():
    for case_id, variants in PARAPHRASES.items():
        cost = BY_ID[case_id]["facts"]["repair_cost"]
        if not cost:
            continue
        for style, body in variants.items():
            assert cost in amounts_in(body) or AMOUNT_WORDS[cost] in body.lower(), (case_id, style)


def test_alcohol_and_missing_photos_signals_survive_every_rewrite():
    drink = ("drink", "alcohol", "beer", "wine")
    assert all(any(w in body.lower() for w in drink) for body in PARAPHRASES["CLM-16"].values())
    photos = ("photo", "pic", "picture")
    assert all(any(w in body.lower() for w in photos) for body in PARAPHRASES["CLM-12"].values())


def test_cases_keep_subject_date_attachments_and_answer_key():
    cases = paraphrase_cases(BY_ID)
    assert len(cases) == 24
    c = next(x for x in cases if x["case_id"] == "CLM-12_casual")
    assert c["email"]["subject"] == BY_ID["CLM-12"]["email"]["subject"]          # policy number is there
    assert c["email"]["date"] == BY_ID["CLM-12"]["email"]["date"]                # relative dates computable
    assert c["email"]["body"].endswith("Attached: repair_quote.pdf")
    assert c["expected"] == BY_ID["CLM-12"]["expected"]
    assert len(repeat_cases(BY_ID, 5)) == 20


def test_report_from_saved_runs(tmp_path):
    for case in paraphrase_cases(BY_ID) + repeat_cases(BY_ID, 3):
        record = replay(ClaimsSystem(tmp_path / f"{case['case_id']}.db"), case)
        (tmp_path / f"{case['case_id']}.json").write_text(json.dumps(record), encoding="utf-8")
    report = render(tmp_path, BY_ID, 3)
    assert "Right decision: **24/24**" in report
    assert "| CLM-B (settle) | settle ×3 | yes |" in report
    assert "Right decision on 12/12 repeated runs." in report
