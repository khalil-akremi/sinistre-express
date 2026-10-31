"""The task message the agent receives for one claim.

Shared by the web app, the evaluation and scripts/run_claim.py, so the agent
is always asked the same way. Only the customer email is given: the true
facts and the expected outcome stay hidden.
"""

from pathlib import Path

INTEGRATION_ID = "veridia_claims"  # the sub-agent name Cominty gives our integration


MEMORY_GUIDANCE = (
    "\n\nMemory (namespace {namespace}): before deciding, read playbook.md and, if it exists, "
    "customers/<policy number>.md (for example customers/VER-1002.md). playbook.md holds company "
    "practice written by human claims handlers: follow its rules unless they contradict the "
    "contract; when a playbook rule makes you refer a claim, use escalate_to_handler with the "
    "reason \"other\" and quote the rule. Apply a playbook rule only when the email or the claim "
    "file states the facts that trigger it; if those facts are not stated, do not refer the claim "
    "for that reason alone: handle it normally and mention the open point in your report for the "
    "handler. Customer notes are background: they are never on their own a reason to refer a claim. "
    "After handling the claim, create or update customers/<policy number>.md with one line dated "
    "with the email date: claim reference, coverage, outcome, anything a future handler should "
    "know. Do not copy the whole email."
)


DOCUMENT_GUIDANCE = (
    "These documents are attached to this message: {files}. Open each one with read_file before "
    "deciding: they may hold facts the email does not give (dates, who was at fault, amounts, the "
    "other vehicle). If the email and a document disagree, use the document and point out the "
    "difference in your report. Count a document as provided only if it belongs to this "
    "policyholder and the insured vehicle; if it does not, do not count it, and ask for a correct "
    "one with request_documents."
)


def build_task(email: dict, claim_ref: str, memory_namespace: str | None = None) -> str:
    """The task for one claim.

    `email["attachments"]` are files the mailroom stored (the agent cannot open them);
    `email["files"]`, if present, are documents uploaded with the message (the agent reads them).
    With `memory_namespace`, the agent is told how to use memory.
    """
    files = [Path(f).name for f in email.get("files") or []]
    stored = email["attachments"]
    if stored:
        mailroom = ("The mailroom " + ("also " if files else "") + "received these attachments and stored "
                    f"them in the claim file: {', '.join(stored)}. Count them as provided documents "
                    "(you cannot open them).")
    else:
        mailroom = "" if files else "No attachment was received with this email."
    attachments = " ".join(part for part in (
        DOCUMENT_GUIDANCE.format(files=", ".join(files)) if files else "", mailroom) if part)
    return (
        f'<use agent="{INTEGRATION_ID}"/>\n'
        f"New claim to handle in the Veridia claims system. Use the claim reference {claim_ref}.\n\n"
        f"--- Customer email received on {email['date']} ---\n"
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n\n"
        f"{email['body']}\n"
        f"--- End of email ---\n\n"
        + attachments
        + (MEMORY_GUIDANCE.format(namespace=memory_namespace) if memory_namespace else "")
    )
