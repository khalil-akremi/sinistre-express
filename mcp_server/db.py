"""The claims database: a single SQLite file with three tables.

- policies    the 8 Policy Schedules, loaded from data/customers.json
- claims      every claim the agent opens, with its facts and status
- action_log  every tool call (time, tool, inputs, result): the audit trail
              and the raw material of the evaluation

SQLite keeps the demo free and self-contained. The SQL is plain and portable,
so moving to PostgreSQL later only means changing the connection.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "claims.db"
CUSTOMERS_FILE = PROJECT_ROOT / "data" / "customers.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    policy_id     TEXT PRIMARY KEY,
    holder_name   TEXT NOT NULL,
    vehicle       TEXT NOT NULL,
    market_value  INTEGER NOT NULL,
    licence_date  TEXT NOT NULL,          -- ISO date
    coverages     TEXT NOT NULL           -- JSON list, e.g. ["C1","C2"]
);

CREATE TABLE IF NOT EXISTS claims (
    claim_ref               TEXT PRIMARY KEY,
    policy_id               TEXT NOT NULL REFERENCES policies(policy_id),
    coverage                TEXT NOT NULL,
    incident_date           TEXT NOT NULL,
    report_date             TEXT NOT NULL,
    description             TEXT NOT NULL,
    repair_cost             INTEGER NOT NULL,
    at_fault                INTEGER NOT NULL,
    third_party_involved    INTEGER NOT NULL,
    third_party_identified  INTEGER NOT NULL,
    documents_provided      TEXT NOT NULL,   -- JSON list
    exclusion_signal        TEXT,
    status                  TEXT NOT NULL,
    blocking_issues         TEXT NOT NULL,   -- JSON list
    deductible              INTEGER,
    payout                  INTEGER,
    assessor_required       INTEGER,
    assessor_date           TEXT,
    requested_documents     TEXT,            -- JSON list
    escalation_reasons      TEXT,            -- JSON list
    handler_note            TEXT,
    approved_by             TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    claim_ref   TEXT,
    tool        TEXT NOT NULL,
    arguments   TEXT NOT NULL,   -- JSON
    ok          INTEGER NOT NULL,
    result      TEXT NOT NULL    -- JSON result, or the error message
);
"""


def db_path_from_env() -> Path:
    return Path(os.environ.get("SINISTRE_DB", DEFAULT_DB_PATH))


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def reset_database(db_path: Path | str, customers_file: Path = CUSTOMERS_FILE) -> None:
    """Start from a clean demo state: empty claims and log, 8 customers loaded."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    customers = json.loads(Path(customers_file).read_text(encoding="utf-8"))
    with connect(db_path) as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS action_log; DROP TABLE IF EXISTS claims; "
            "DROP TABLE IF EXISTS policies;"
        )
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO policies VALUES (?, ?, ?, ?, ?, ?)",
            [
                (c["policy_id"], c["holder_name"], c["vehicle"], c["market_value"],
                 c["licence_date"], json.dumps(c["coverages"]))
                for c in customers
            ],
        )
    conn.close()


def ensure_database(db_path: Path | str) -> None:
    """Create and seed the database only if it does not exist yet."""
    if not Path(db_path).exists():
        reset_database(db_path)


if __name__ == "__main__":
    # uv run python -m mcp_server.db  ->  back to a clean demo state
    path = db_path_from_env()
    reset_database(path)
    print(f"Database reset: {path} (8 customers, no claims, empty log)")
