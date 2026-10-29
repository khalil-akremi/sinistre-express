---
title: Sinistre Express
emoji: 🚗
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Sinistre Express

An agentic motor-claims workflow built on Cominty Managed Agents.

A Cominty agent reads a customer's claim, checks it against a (fictional)
insurance contract, and acts in a claims system exposed through MCP: it opens
the claim, gets exact amounts from tested business rules, requests missing
documents, escalates risky cases, and prepares payments that only a human can
approve.

All data is synthetic. Veridia Insurance is a fictional company.

## Project layout

| Folder | Content |
|---|---|
| `core/` | Business rules of the contract (`rules.py`), the single source of truth for amounts |
| `data/` | The contract, customers and test cases with their expected outcomes |
| `eval/` | Test-case generator (and later the evaluation pipeline) |
| `mcp_server/` | The claims system: SQLite database, 7 MCP tools, action log |
| `tests/` | Automated tests (rules, tools, MCP protocol) |
| `scripts/` | Utilities, e.g. `check_server.py` |

## Run locally

```bash
uv sync
uv run pytest                          # all tests
uv run python -m mcp_server.server     # MCP server on http://localhost:8000/mcp
uv run python scripts/check_server.py  # connect like the agent and list the tools
```
