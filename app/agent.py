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
from pathlib import Path
from typing import Protocol

EventSink = Callable[[dict], None]


class AgentRunner(Protocol):
    def __call__(self, task: str, on_event: EventSink, files: list[Path] | None = None) -> Awaitable[dict]:
        """Run the agent on `task` with `files` attached, call `on_event` for each
        progress event, and return {"reply": str, "cost": dict | None, "status": str}."""


# ---------------------------------------------------------- event mapping
TOOL_LABELS = {
    "company_doc_find_by_name": ("📄", "Finding the Veridia contract"),
    "company_doc_content_search": ("📄", "Searching the contract (RAG)"),
    "company_doc_read_full_text": ("📄", "Reading the contract"),
    "subagent": ("🤝", "Handing work to the Veridia claims sub-agent"),
    "execute": ("🧪", "Running code in the sandbox"),
    "read_file": ("📎", "Reading an attached document"),
    "load_skill": ("🧰", "Loading a skill (e.g. Spreadsheet)"),
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
        # Each tool is shown once, when it finishes, except the hand-off to the claims sub-agent:
        # it finishes after all the tool calls it makes, so it is shown when it starts.
        handoff = name == "subagent"
        if (status == "running") != handoff and status != "error":
            return None
        icon, label = tool_label(name or "")
        return {"source": "agent", "icon": "⚠️" if status == "error" else icon, "text": label}
    if kind == "update" and text:
        return {"source": "agent", "icon": "💬", "text": text}
    if kind == "sandbox":
        if status != "running":
            return None  # once, when it starts
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

    async def __call__(self, task: str, on_event: EventSink, files: list[Path] | None = None) -> dict:
        from cominty_sdk import AgentCapabilities, AsyncCominty, MemoryCapability, events

        # Memory is attached per conversation and frozen for it (Cominty capabilities).
        memory = (MemoryCapability(activation="always", namespace=self.memory_namespace)
                  if self.memory_namespace else MemoryCapability(activation="never"))

        cost = None
        async with AsyncCominty(api_token=self.api_token, user_id=self.user_id) as client:
            # An uploaded file can be attached to one conversation only ("Bad file_ids"
            # when reused), so the documents are uploaded for every run.
            file_ids = []
            for path in files or []:
                on_event({"source": "agent", "icon": "📤", "text": f"Attaching {path.name} to the conversation"})
                file_ids.append((await client.chat.upload_file(Path(path))).id)
            run = await client.chat.start(
                agent_id=self.agent_id, message=task, max_steps=self.max_steps,
                thread_capabilities=AgentCapabilities(memory=memory), file_ids=file_ids or None,
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


# ------------------------------------------------------ the daily report runner
BUILTIN_CHAT_AGENT = "__cominty_agents::agent.chat"


class ComintyReportRunner:
    """A built-in Cominty agent (Chat) with skills on, and nothing else: no claims
    system, no memory, no web. It gets the CSV, returns a workbook and a briefing."""

    def __init__(self, agent_id: str = BUILTIN_CHAT_AGENT, max_steps: int = 25):
        self.agent_id = agent_id
        self.api_token = clean_secret(os.environ.get("COMINTY_API_KEY"))
        self.user_id = clean_secret(os.environ.get("COMINTY_USER_ID"))
        self.max_steps = max_steps

    async def __call__(self, task: str, csv_name: str, csv_text: str, on_event: EventSink) -> dict:
        from cominty_sdk import (AgentCapabilities, AsyncCominty, McpCapability, MemoryCapability,
                                 SkillsCapability, WebCapability, events)

        caps = AgentCapabilities(skills=SkillsCapability(activation="always"), mcp=McpCapability(activation="never"),
                                 memory=MemoryCapability(activation="never"), web=WebCapability(activation="never"))
        cost, files = None, []
        async with AsyncCominty(api_token=self.api_token, user_id=self.user_id) as client:
            on_event({"source": "agent", "icon": "📤", "text": f"Attaching {csv_name} (today's claims)"})
            uploaded = await client.chat.upload_file(csv_text.encode("utf-8"), filename=csv_name)
            run = await client.chat.start(agent_id=self.agent_id, message=task, file_ids=[uploaded.id],
                                          max_steps=self.max_steps, thread_capabilities=caps)
            async with run:
                async for event in run:
                    item = None
                    if isinstance(event, events.SettingUpSandbox):
                        item = agent_event("sandbox", event.status)
                    elif isinstance(event, events.ToolCall):
                        item = agent_event("tool_call", event.status, name=event.data.name)
                    elif isinstance(event, events.IntermediaryUpdate):
                        item = agent_event("update", event.status, text=event.data.message)
                    elif isinstance(event, events.Result):
                        cost = event.data.cost
                        files += list(getattr(event.data, "files", None) or [])
                    if item:
                        on_event(item)
                reply = await run.result()
            unique = {f.id: f for f in files + list(getattr(reply, "files", None) or [])}
            produced = []
            for f in unique.values():
                if getattr(f, "origin", "agent") == "agent" and str(getattr(f, "name", "")).lower().endswith(".xlsx"):
                    produced.append((f.name, await client.chat.download_file(f.id)))
        return {"reply": reply.content, "files": produced,
                "cost": cost.model_dump(mode="json") if cost is not None else None}
