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
    "memory_read": ("🧠", "Reading its memory"),
    "memory_write": ("🧠", "Writing to its memory"),
}


def tool_label(name: str) -> tuple[str, str]:
    if name in TOOL_LABELS:
        return TOOL_LABELS[name]
    if "memory" in name:
        return ("🧠", "Using its memory")
    return ("🔧", f"Agent tool: {name}")


def agent_event(kind: str, status: str, name: str | None = None, text: str | None = None) -> dict | None:
    """One Cominty progress event -> one timeline item (or None to skip it)."""
    if kind == "tool_call":
        if status == "running":
            return None  # show each tool once, when it finishes
        icon, label = tool_label(name or "")
        return {"source": "agent", "icon": "⚠️" if status == "error" else icon, "text": label}
    if kind == "update" and text:
        return {"source": "agent", "icon": "💬", "text": text}
    if kind == "sandbox":
        return {"source": "agent", "icon": "📦", "text": "Preparing the agent's sandbox"}
    if kind == "start":
        return {"source": "agent", "icon": "⏳", "text": "The agent is starting"}
    return None


# --------------------------------------------------------- real runner
def clean_secret(value: str | None) -> str | None:
    """Remove what copy-paste often adds around a secret: spaces, line breaks, quotes."""
    if value is None:
        return None
    return value.strip().strip("\"'").strip()


class ComintyRunner:
    """Runs our Veridia Claims Handler through the Cominty SDK."""

    def __init__(self, agent_id: str | None = None, max_steps: int = 25,
                 memory_namespace: str | None = None):
        self.agent_id = clean_secret(agent_id or os.environ["COMINTY_AGENT_ID"])
        self.memory_namespace = memory_namespace
        self.api_token = clean_secret(os.environ.get("COMINTY_API_KEY"))
        self.user_id = clean_secret(os.environ.get("COMINTY_USER_ID"))
        self.max_steps = max_steps

    async def __call__(self, task: str, on_event: EventSink) -> dict:
        from cominty_sdk import AgentCapabilities, AsyncCominty, MemoryCapability, events

        # Memory is attached per conversation and frozen for it (Cominty capabilities).
        memory = (MemoryCapability(activation="always", namespace=self.memory_namespace)
                  if self.memory_namespace else MemoryCapability(activation="never"))

        cost = None
        async with AsyncCominty(api_token=self.api_token, user_id=self.user_id) as client:
            run = await client.chat.start(
                agent_id=self.agent_id, message=task, max_steps=self.max_steps,
                thread_capabilities=AgentCapabilities(memory=memory),
            )
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
