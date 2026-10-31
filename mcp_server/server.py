"""Publishes the claims system as an MCP server ("the menu").

Run locally:   uv run python -m mcp_server.server
It listens on  http://localhost:8000/mcp
In production (Hugging Face), the secret environment variable MCP_SECRET_TOKEN
moves the MCP endpoint to /mcp/<token>, so only someone who knows the full URL
(our Cominty integration) can call the tools.

Each @server.tool() function below is one item on the menu the Cominty agent
sees. The docstring and the field descriptions are what the agent reads to
decide when and how to call a tool, so they are written carefully.
The logic itself lives in tools.py.
"""

from __future__ import annotations

import os
from typing import Annotated, Literal

from pydantic import Field

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_server.db import db_path_from_env
from mcp_server.tools import ClaimsSystem, ToolRefused

CoverageCode = Literal["C1", "C2", "C3", "C4"]
DocumentType = Literal["photos", "repair_quote", "accident_report", "police_report"]
EscalationReason = Literal["late_report", "possible_exclusion", "coverage_not_in_schedule", "other"]
ClaimRef = Annotated[str, Field(description="The claim reference given in your task, e.g. 'CLM-B'.")]

INSTRUCTIONS = """Veridia Insurance claims system.
Typical order: get_policy -> create_claim -> then, depending on the blocking_issues
returned by create_claim:
- no blocking issue: compute_settlement -> schedule_assessor (only if assessor_required)
  -> stage_settlement;
- missing documents: request_documents;
- late report, possible exclusion or coverage not in the schedule: escalate_to_handler.
The system computes all amounts. Payments are only prepared; a human approves them."""


def _run(method, **kwargs) -> dict:
    """Call a claims-system method; turn a refusal into an error the agent can read."""
    try:
        return method(**kwargs)
    except ToolRefused as exc:
        raise ToolError(str(exc)) from exc


def admin_token() -> str:
    """Token protecting the read-only admin endpoint: the MCP secret, or 'local'."""
    return os.environ.get("MCP_SECRET_TOKEN", "").strip() or "local"


def build_server(system: ClaimsSystem, admin_secret: str = "local") -> MCPServer:
    server = MCPServer(name="veridia-claims", instructions=INSTRUCTIONS)

    @server.tool()
    def get_policy(
        policy_id: Annotated[str, Field(description="Policy number from the customer's email, e.g. 'VER-1002'.")],
        claim_ref: ClaimRef,
    ) -> dict:
        """Look up a customer's Policy Schedule: the coverages they bought, their
        vehicle, its market value and their driving licence date."""
        return _run(system.get_policy, policy_id=policy_id, claim_ref=claim_ref)

    @server.tool()
    def create_claim(
        claim_ref: ClaimRef,
        policy_id: Annotated[str, Field(description="Policy number, e.g. 'VER-1002'.")],
        coverage: Annotated[CoverageCode, Field(description=(
            "C1 third-party liability, C2 collision damage to the insured car, "
            "C3 glass breakage, C4 theft of the whole car."))],
        incident_date: Annotated[str, Field(description="Date of the incident, YYYY-MM-DD.")],
        report_date: Annotated[str, Field(description="Date the customer reported it (the email date), YYYY-MM-DD.")],
        description: Annotated[str, Field(description="One or two neutral sentences summarising what happened.")],
        repair_cost: Annotated[int, Field(ge=0, description=(
            "Repair cost in euros from the repair quote. Use 0 for theft or if no quote was given."))],
        at_fault: Annotated[bool, Field(description="True if the insured driver caused the incident.")],
        third_party_involved: Annotated[bool, Field(description="True if another person or vehicle was involved.")],
        third_party_identified: Annotated[bool, Field(description="True if that other driver or person is identified by name.")],
        documents_provided: Annotated[list[DocumentType], Field(description=(
            "Documents actually attached to the email. Never include a document that is not attached."))],
        exclusion_signal: Annotated[str | None, Field(description=(
            "If the story suggests a possible exclusion (alcohol or drugs, no valid licence, racing "
            "or track day, intentional damage, wear only), one word naming it, e.g. 'alcohol'. "
            "Otherwise leave empty."))] = None,
    ) -> dict:
        """Open a claim with the facts you read in the customer's email. Returns the
        automatic checks (deadline, coverage, required and missing documents) and the
        list of blocking_issues that decide the next step."""
        return _run(system.create_claim, claim_ref=claim_ref, policy_id=policy_id, coverage=coverage,
            incident_date=incident_date, report_date=report_date, description=description,
            repair_cost=repair_cost, at_fault=at_fault, third_party_involved=third_party_involved,
            third_party_identified=third_party_identified, documents_provided=list(documents_provided),
            exclusion_signal=exclusion_signal,
        )

    @server.tool()
    def compute_settlement(claim_ref: ClaimRef) -> dict:
        """Compute the deductible, the payout and whether an assessor is required,
        with the contract article behind each step. Only for claims with no blocking
        issue. Never compute amounts yourself; always use this tool."""
        return _run(system.compute_settlement, claim_ref=claim_ref)

    @server.tool()
    def request_documents(
        claim_ref: ClaimRef,
        documents: Annotated[list[DocumentType], Field(description="The missing documents to request.")],
        message_to_customer: Annotated[str, Field(description="A short, polite request to the customer.")],
    ) -> dict:
        """Ask the customer for missing documents. The claim waits until they arrive."""
        return _run(system.request_documents, claim_ref=claim_ref, documents=list(documents), message_to_customer=message_to_customer
        )

    @server.tool()
    def escalate_to_handler(
        claim_ref: ClaimRef,
        reasons: Annotated[list[EscalationReason], Field(description="Why a human must decide.")],
        summary: Annotated[str, Field(description="Two or three sentences for the human claims handler.")],
    ) -> dict:
        """Refer a claim to a human claims handler, who decides. Use it for late
        reports, possible exclusions and coverages not in the Policy Schedule.
        Never refuse a claim yourself."""
        return _run(system.escalate_to_handler, claim_ref=claim_ref, reasons=list(reasons), summary=summary)

    @server.tool()
    def schedule_assessor(claim_ref: ClaimRef) -> dict:
        """Book an independent assessor visit. Only when compute_settlement returned
        assessor_required = true."""
        return _run(system.schedule_assessor, claim_ref=claim_ref)

    @server.tool()
    def stage_settlement(claim_ref: ClaimRef) -> dict:
        """Prepare the payment of a clean claim for human approval. It does NOT pay:
        a human claims handler approves it afterwards."""
        return _run(system.stage_settlement, claim_ref=claim_ref)

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(request):  # public: proves the service is up (the web app serves "/")
        from starlette.responses import JSONResponse

        return JSONResponse({"service": "Veridia claims system (Sinistre Express)", "status": "ok"})

    @server.custom_route("/admin/{token}/claims/{claim_ref}", methods=["GET"], include_in_schema=False)
    async def claim_snapshot(request):
        """Read-only view of one claim and its action log, for the evaluation.
        Protected by the same secret as the MCP endpoint. Never published to the agent."""
        import secrets

        from starlette.responses import JSONResponse

        if not secrets.compare_digest(request.path_params["token"], admin_secret):
            return JSONResponse({"error": "not found"}, status_code=404)
        claim_ref = request.path_params["claim_ref"]
        try:
            claim = system.get_claim(claim_ref)
        except ToolRefused:
            claim = None
        return JSONResponse({"claim": claim, "action_log": system.action_log(claim_ref)})

    @server.custom_route("/admin/{token}/claims", methods=["GET"], include_in_schema=False)
    async def claim_list(request):
        """Read-only list of claims created since ?since=YYYY-MM-DD (for the daily report script)."""
        import secrets

        from starlette.responses import JSONResponse

        if not secrets.compare_digest(request.path_params["token"], admin_secret):
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"claims": system.list_claims(request.query_params.get("since"))})

    return server


def mcp_path() -> str:
    """/mcp locally, /mcp/<secret> when MCP_SECRET_TOKEN is set."""
    token = os.environ.get("MCP_SECRET_TOKEN", "").strip()
    return f"/mcp/{token}" if token else "/mcp"


def main() -> None:
    import anyio

    system = ClaimsSystem(db_path_from_env())
    server = build_server(system, admin_secret=admin_token())
    port = int(os.environ.get("PORT", "8000"))
    path = mcp_path()
    # Behind a public host (Hugging Face) the Host header is the public domain,
    # so we do not restrict it; the secret path is our access control.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    shown = path if path == "/mcp" else "/mcp/<secret>"
    print(f"Veridia claims MCP server on http://localhost:{port}{shown}  (database: {system.db_path})")
    anyio.run(
        lambda: server.run_streamable_http_async(
            host="0.0.0.0", port=port, streamable_http_path=path, transport_security=security
        )
    )


if __name__ == "__main__":
    main()
