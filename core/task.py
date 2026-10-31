"""The task message the agent receives for one claim.

Shared by the web app, the evaluation and scripts/run_claim.py, so the agent
is always asked the same way. Only the customer email is given: the true
facts and the expected outcome stay hidden.
"""

INTEGRATION_ID = "veridia_claims"  # the sub-agent name Cominty gives our integration


MEMORY_GUIDANCE = (
    "\n\nMemory (namespace {namespace}): before deciding, read playbook.md and, if it exists, "
    "customers/<policy number>.md (for example customers/VER-1002.md). playbook.md holds company "
    "practice written by human claims handlers: follow its rules unless they contradict the "
    "contract; when a playbook rule makes you refer a claim, use escalate_to_handler with the "
    "reason \"other\" and quote the rule. After handling the claim, create or update "
    "customers/<policy number>.md with one dated line: claim reference, coverage, outcome, "
    "anything a future handler should know. Do not copy the whole email."
)


def build_task(email: dict, claim_ref: str, memory_namespace: str | None = None) -> str:
    """The task for one claim. With `memory_namespace`, the agent is told how to use memory."""
    return (
        f'<use agent="{INTEGRATION_ID}"/>\n'
        f"New claim to handle in the Veridia claims system. Use the claim reference {claim_ref}.\n\n"
        f"--- Customer email received on {email['date']} ---\n"
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n\n"
        f"{email['body']}\n"
        f"--- End of email ---\n\n"
        + (
            "The mailroom received these attachments and stored them in the claim file: "
            f"{', '.join(email['attachments'])}. Count them as provided documents "
            "(you cannot open them)."
            if email["attachments"]
            else "No attachment was received with this email."
        )
        + (MEMORY_GUIDANCE.format(namespace=memory_namespace) if memory_namespace else "")
    )
