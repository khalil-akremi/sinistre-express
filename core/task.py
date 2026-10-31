"""The task message the agent receives for one claim.

Shared by the web app, the evaluation and scripts/run_claim.py, so the agent
is always asked the same way. Only the customer email is given: the true
facts and the expected outcome stay hidden.
"""

INTEGRATION_ID = "veridia_claims"  # the sub-agent name Cominty gives our integration


def build_task(email: dict, claim_ref: str) -> str:
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
    )
