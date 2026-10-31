"""Running the Cominty agent for the web app, and turning its events into timeline items.

The web app never talks to Cominty from the browser: this module runs on the
server, holds the API key (from environment variables) and streams progress.

`AgentRunner` is the contract the web layer depends on. The real runner calls
Cominty through the SDK; the tests plug in a fake one that calls the claims
system directly, so the web app is tested without spending credits.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Protocol

EventSink = Callable[[dict], None]


class AgentRunner(Protocol):
    def __call__(self, task: str, on_event: EventSink) -> Awaitable[dict]:
        """Run the agent on `task`, call `on_event` for each progress event,
        and return {"reply": str, "cost": dict | None, "status": str}."""


# ---------------------------------------------------------- event mapping
TOOL_LABELS = {
    "company_doc_find_by_name": ("📄", "Finding the Veridia contract"),
    "company_doc_content_search": ("📄", "Searching the contract (RAG)"),
    "company_doc_read_full_text": ("📄", "Reading the contract"),
    "subagent": ("🤝", "Handing work to the Veridia claims sub-agent"),
    "execute": ("🧪", "Running code in the sandbox"),
    "read_file": ("📎", "Reading a file"),
    "load_skill": ("🧰", "Loading a skill"),
    "ask_questions": ("❓", "Preparing a question for you"),
}


def agent_event(kind: str, status: str, name: str | None = None, text: str | None = None) -> dict | None:
    """One Cominty progress event -> one timeline item (or None to skip it)."""
    if kind == "tool_call":
        if status == "running":
            return None  # show each tool once, when it finishes
        icon, label = TOOL_LABELS.get(name or "", ("🔧", f"Agent tool: {name}"))
        return {"source": "agent", "icon": "⚠️" if status == "error" else icon, "text": label}
    if kind == "update" and text:
        return {"source": "agent", "icon": "💬", "text": text}
    if kind == "sandbox":
        return {"source": "agent", "icon": "📦", "text": "Preparing the agent's sandbox"}
    if kind == "start":
        return {"source": "agent", "icon": "⏳", "text": "The agent is starting"}
    return None


# --------------------------------------------------------- real runner
class ComintyRunner:
    """Runs our Veridia Claims Handler through the Cominty SDK."""

    def __init__(self, agent_id: str | None = None, max_steps: int = 25):
        self.agent_id = agent_id or os.environ["COMINTY_AGENT_ID"]
        self.max_steps = max_steps

    async def __call__(self, task: str, on_event: EventSink) -> dict:
        from cominty_sdk import AsyncCominty, events  # imported here: tests never need it

        cost = None
        async with AsyncCominty() as client:
            run = await client.chat.start(agent_id=self.agent_id, message=task, max_steps=self.max_steps)
            started_sent = False
            async with run:
                async for event in run:
                    item = None
                    if isinstance(event, events.WaitingForStart) and not started_sent:
                        item, started_sent = agent_event("start", event.status), True
                    elif isinstance(event, events.SettingUpSandbox):
                        item = agent_event("sandbox", event.status)
                    elif isinstance(event, events.ToolCall):
                        item = agent_event("tool_call", event.status, name=event.data.name)
                    elif isinstance(event, events.IntermediaryUpdate):
                        item = agent_event("update", event.status, text=event.data.message)
                    elif isinstance(event, events.Result):
                        cost = event.data.cost
                    if item:
                        on_event(item)
                reply = await run.result()
        return {
            "reply": reply.content,
            "status": str(reply.status),
            "cost": cost.model_dump(mode="json") if cost is not None else None,
        }
