"""The agent's long-term memory, as the web app sees it.

One Cominty memory namespace (a conversation can attach only one) holds:

    playbook.md            company practice taught by human handlers, shared by all claims
    customers/<policy>.md  short notes the agent writes about each customer

The agent reads and writes these files itself during a claim (the namespace is
attached with a memory capability). The web app also reads them, to show
"what the agent remembers", and writes the playbook when a handler teaches a rule.

`ComintyMemory` talks to Cominty through the SDK; `InMemoryStore` is a fake for tests.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

PLAYBOOK = "playbook.md"
PLAYBOOK_PURPOSE = "Company practice taught by Veridia claims handlers. Read before every claim."
CUSTOMER_PURPOSE = "Notes about one Veridia customer, written by the claims agent."
SEED_PLAYBOOK = (
    "# Veridia handler playbook\n"
    "Rules taught by human claims handlers. They apply to every claim, on top of the contract.\n"
)
MAX_RULES = 12
MAX_RULE_CHARS = 300


def customer_path(policy_id: str) -> str:
    return f"customers/{policy_id}.md"


def add_rule(playbook: str, rule: str) -> str:
    """Append a dated rule; keep only the latest MAX_RULES rules."""
    lines = playbook.rstrip().splitlines() or SEED_PLAYBOOK.rstrip().splitlines()
    header = [line for line in lines if not line.startswith("- ")]
    rules = [line for line in lines if line.startswith("- ")]
    rules.append(f"- ({datetime.now(timezone.utc):%Y-%m-%d}) {rule.strip()}")
    return "\n".join(header + rules[-MAX_RULES:]) + "\n"


def rules_of(playbook: str | None) -> list[str]:
    return [line[2:] for line in (playbook or "").splitlines() if line.startswith("- ")]


# ------------------------------------------------------------ fake store
class InMemoryStore:
    """Same interface as ComintyMemory, kept in a dict. Used by the tests."""

    def __init__(self, namespace: str = "test"):
        self.namespace = namespace
        self.files: dict[str, str] = {PLAYBOOK: SEED_PLAYBOOK}

    async def read(self, path: str) -> str | None:
        return self.files.get(path)

    async def teach(self, rule: str) -> str:
        self.files[PLAYBOOK] = add_rule(self.files.get(PLAYBOOK, SEED_PLAYBOOK), rule)
        return self.files[PLAYBOOK]

    async def reset(self) -> None:
        self.files = {PLAYBOOK: SEED_PLAYBOOK}


# ------------------------------------------------------------ real store
class ComintyMemory:
    """Cominty memory files in one namespace, through the SDK."""

    def __init__(self, namespace: str):
        self.namespace = namespace

    def _client(self):
        from cominty_sdk import AsyncCominty

        from app.agent import clean_secret

        return AsyncCominty(api_token=clean_secret(os.environ.get("COMINTY_API_KEY")),
                            user_id=clean_secret(os.environ.get("COMINTY_USER_ID")))

    async def read(self, path: str) -> str | None:
        from cominty_sdk import NotFoundError

        async with self._client() as client:
            try:
                return (await client.memory.get(path, namespace=self.namespace)).content
            except NotFoundError:
                return None

    async def _write(self, client, path: str, content: str, purpose: str) -> None:
        """Create or update one file. `version` guards against a concurrent change."""
        from cominty_sdk import ConflictError, NotFoundError

        for _ in range(2):
            try:
                current = await client.memory.get(path, namespace=self.namespace)
            except NotFoundError:
                await client.memory.create(path=path, namespace=self.namespace,
                                           purpose=purpose, content=content)
                return
            try:
                await client.memory.update(path, namespace=self.namespace,
                                           version=current.version, content=content)
                return
            except ConflictError:
                continue  # someone changed it meanwhile: read again and retry once
        raise RuntimeError(f"Could not update {path}: it keeps changing.")

    async def teach(self, rule: str) -> str:
        from cominty_sdk import NotFoundError

        async with self._client() as client:
            try:
                playbook = (await client.memory.get(PLAYBOOK, namespace=self.namespace)).content
            except NotFoundError:
                playbook = SEED_PLAYBOOK
            updated = add_rule(playbook, rule)
            await self._write(client, PLAYBOOK, updated, PLAYBOOK_PURPOSE)
            return updated

    async def reset(self) -> None:
        """Back to a clean demo: seed playbook, no customer notes."""
        async with self._client() as client:
            await self._write(client, PLAYBOOK, SEED_PLAYBOOK, PLAYBOOK_PURPOSE)
            for summary in await client.memory.list(namespace=self.namespace):
                if summary.path.startswith("customers/"):
                    await client.memory.delete(summary.path, namespace=self.namespace)
