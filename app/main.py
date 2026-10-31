"""Entry point: one server for everything.

Run locally:   uv run python -m app.main     ->  http://localhost:8000

    /                       the claims-desk web page
    /api/...                the web app's API (talks to Cominty on the server side)
    /mcp or /mcp/<secret>   the MCP server the Cominty agent calls
    /admin/<secret>/...     read-only snapshot used by the evaluation
    /health                 health check

One process means one free Render service, and lets the web app read the
MCP server's audit log directly to show each tool call live.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from app.agent import ComintyRunner
from app.memory import ComintyMemory
from app.web import register_web_routes
from mcp.server.transport_security import TransportSecuritySettings
from mcp_server.db import db_path_from_env
from mcp_server.server import admin_token, build_server, mcp_path
from mcp_server.tools import ClaimsSystem


class MissingConfigRunner:
    """Used when the Cominty settings are absent: explains instead of crashing."""

    async def __call__(self, task, on_event, files=None):  # noqa: ARG002
        raise RuntimeError("COMINTY_AGENT_ID / COMINTY_API_KEY / COMINTY_USER_ID are not configured on the server.")


def create_server():
    load_dotenv()
    system = ClaimsSystem(db_path_from_env())
    server = build_server(system, admin_secret=admin_token())
    configured = bool(os.environ.get("COMINTY_AGENT_ID"))
    namespace = os.environ.get("MEMORY_NAMESPACE", "veridia-claims-desk").strip()
    use_memory = configured and os.environ.get("MEMORY_ENABLED", "true").lower() != "false"
    runner = (ComintyRunner(memory_namespace=namespace if use_memory else None)
              if configured else MissingConfigRunner())
    reviewer_id = os.environ.get("REVIEWER_AGENT_ID", "").strip()
    reviewer = ComintyRunner(agent_id=reviewer_id, max_steps=12) if configured and reviewer_id else None
    register_web_routes(server, system, runner, memory=ComintyMemory(namespace) if use_memory else None,
                        reviewer=reviewer)
    return server, system


def main() -> None:
    import anyio

    server, system = create_server()
    port = int(os.environ.get("PORT", "8000"))
    path = mcp_path()
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    shown = path if path == "/mcp" else "/mcp/<secret>"
    print(f"Sinistre Express on http://localhost:{port}  (MCP at {shown}, database {system.db_path})")
    anyio.run(lambda: server.run_streamable_http_async(
        host="0.0.0.0", port=port, streamable_http_path=path, transport_security=security))


if __name__ == "__main__":
    main()
