"""Probe: how does a Cominty agent read attached documents? (~€0.02, two short conversations)

Run:  uv run python -m scripts.probe_documents

1. Uploads a typed accident report (PDF with text) and a scanned repair quote
   (image only, no text layer), asks the agent to extract fields as JSON,
   and compares them with the truth. Prints every tool the agent used.
2. Starts a NEW conversation that reuses the same file ids, to learn whether
   an uploaded file can be attached again (then the web app uploads each
   sample document once instead of on every run).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

from app.agent import clean_secret

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / "data/documents/DOC-02/accident_report_signed.pdf",   # typed PDF
         ROOT / "data/documents/DOC-03/repair_quote.pdf"]             # scan, OCR needed
TRUTH = {"accident_date": "2026-10-12", "other_vehicle_model": "Ford Transit Custom",
         "other_vehicle_type": "Van", "other_driver": "Marc Dubois", "at_fault_driver": "B",
         "quote_total_incl_vat_eur": 1180, "quote_customer": "Emma Rousseau",
         "quote_vehicle": "Tesla Model 3 (2023)"}
QUESTION = (
    "Do not use the Veridia claims system. Read the two attached documents and answer with JSON only, "
    "no other text, with exactly these keys: accident_date (YYYY-MM-DD, from the accident report), "
    "other_vehicle_model, other_vehicle_type, other_driver (name without title), at_fault_driver "
    "(\"A\" or \"B\", from the circumstances and observations), quote_total_incl_vat_eur (number), "
    "quote_customer, quote_vehicle. Then, after the JSON, on a new line starting with HOW:, say in one "
    "sentence how you read each file (text layer, OCR, image...)."
)


async def run(client, agent_id: str, message: str, file_ids: list[str]) -> dict:
    from cominty_sdk import AgentCapabilities, MemoryCapability, events

    started = time.monotonic()
    run = await client.chat.start(agent_id=agent_id, message=message, file_ids=file_ids, max_steps=12,
                                  thread_capabilities=AgentCapabilities(memory=MemoryCapability(activation="never")))
    steps, cost = [], None
    async with run:
        async for event in run:
            if isinstance(event, events.ToolCall) and event.status != "running":
                steps.append(f"tool {event.data.name} ({event.status})")
            elif isinstance(event, events.IntermediaryUpdate):
                steps.append(f"update: {event.data.message}")
            elif isinstance(event, (events.SettingUpSandbox,)):
                steps.append(f"sandbox ({event.status})")
            elif isinstance(event, events.Result):
                cost = event.data.cost
        reply = await run.result()
    return {"reply": reply.content, "steps": steps, "seconds": round(time.monotonic() - started, 1),
            "cost": float(cost.total) if cost is not None else None}


def compare(reply: str) -> None:
    match = re.search(r"\{.*\}", reply, re.S)
    try:
        got = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        got = {}
    for key, want in TRUTH.items():
        value = got.get(key)
        ok = str(value).strip().lower() == str(want).lower() or (key == "quote_total_incl_vat_eur" and _num(value) == want)
        print(f"  {'OK ' if ok else 'XX '} {key:26} got {value!r:32} truth {want!r}")


def _num(value) -> float | None:
    try:
        return float(str(value).replace("€", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


async def main() -> None:
    from cominty_sdk import AsyncCominty

    load_dotenv(ROOT / ".env")
    agent_id = clean_secret(os.environ["COMINTY_AGENT_ID"])
    async with AsyncCominty(api_token=clean_secret(os.environ.get("COMINTY_API_KEY")),
                            user_id=clean_secret(os.environ.get("COMINTY_USER_ID"))) as client:
        uploaded = [await client.chat.upload_file(path) for path in FILES]
        ids = [f.id for f in uploaded]
        print("Uploaded:", ", ".join(f"{p.parent.name}/{p.name} -> {i}" for p, i in zip(FILES, ids)))

        print("\n=== 1. Extraction from a typed PDF and a scanned PDF")
        first = await run(client, agent_id, QUESTION, ids)
        print("Steps:", *first["steps"], sep="\n  ")
        print(f"Time {first['seconds']} s, cost €{first['cost']}")
        print("Reply:\n" + first["reply"])
        print("Field by field:")
        compare(first["reply"])

        print("\n=== 2. Reusing the same file ids in a new conversation")
        try:
            second = await run(client, agent_id, "Do not use the Veridia claims system. What is the total "
                               "including VAT on the attached repair quote? Answer with the number only.", ids[1:])
            print(f"Reuse works. Reply: {second['reply'].strip()[:200]}  (cost €{second['cost']})")
        except Exception as exc:  # noqa: BLE001
            print(f"Reuse failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
