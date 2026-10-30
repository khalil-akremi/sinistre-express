"""Diagnostic: ask agents which tools and sub-agents they can see.

Usage:  uv run python scripts/check_agent_tools.py

Asks two agents the same short question, with no thread restrictions:
- Cominty's built-in Chat agent (can use workspace integrations at once)
- our Veridia Claims Handler (COMINTY_AGENT_ID in .env)
Costs well under one cent.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from cominty_sdk import AsyncCominty, events

ROOT = Path(__file__).resolve().parent.parent
QUESTION = (
    "Do not call any tool. Just list the exact names of every tool, integration "
    "and sub-agent available to you right now, one per line. Then say whether you "
    "can see a tool named get_policy or an integration named Veridia Claims System."
)


async def ask(client: AsyncCominty, label: str, agent_id: str) -> None:
    print(f"\n{'=' * 70}\n{label}  ({agent_id})\n{'=' * 70}")
    run = await client.chat.start(agent_id=agent_id, message=QUESTION, max_steps=1)
    cost = None
    async with run:
        async for event in run:
            if isinstance(event, events.Result):
                cost = event.data.cost
        reply = await run.result()
    print(reply.content)
    if cost is not None:
        print(f"\n(cost: €{cost.total})")


async def main() -> None:
    load_dotenv(ROOT / ".env")
    async with AsyncCominty() as client:
        await ask(client, "Built-in Chat agent", "__cominty_agents::agent.chat")
        await ask(client, "Veridia Claims Handler", os.environ["COMINTY_AGENT_ID"])


asyncio.run(main())
