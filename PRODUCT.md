# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary: reviewers at Cominty (Paris) judging an AI Engineer internship challenge. They open the live link, often for a few minutes, and must understand within seconds what the agents do, then watch one claim go through and judge the engineering. Secondary, in the fiction: claims handlers at Veridia Insurance, who use the desk to supervise an agent and approve payments.

## Product Purpose
Sinistre Express is a motor-claims desk where Cominty agents do the preparation and a person keeps the decision. A Handler agent reads a customer email and attached PDFs (typed or scanned), checks the Veridia contract, and acts in a claims system over MCP: opens the claim, gets exact amounts from tested rules, requests missing documents, refers risky cases. A Reviewer agent on another model provider checks every staged payment fact by fact. A built-in Cominty agent writes the daily report. Success for the visitor: seeing a claim handled end to end, live, and trusting why the numbers are right.

## Positioning
The AI reads and judges; deterministic code applies the rules, computes every euro, refuses unsafe actions, and checks the AI's work. Every step is visible and every claim is measured by an evaluation suite. No tool can approve money: a person clicks Approve.

## Operating Context
- One claim at a time; a daily run limit protects credits. A run takes 30–90 seconds (Handler, then Reviewer when a payment is staged).
- Inputs: sample customer emails (editable), mailroom attachments (names only), and real PDFs the agent opens (quotes, signed accident reports, scanned police receipts).
- Live timeline mixes three sources: the agent on Cominty, the Veridia claims system (MCP tool calls, including refusals), and the Reviewer.
- Claim file: status, deductible, assessor visit, payout, agent report and draft customer letter, reviewer verdict, human approval with a stamp.
- Memory panel: handler playbook rules (teachable), customer note per policy, clear memory.
- Daily report: Excel built by a built-in agent, checked against the database (7 checks), plus an AI-written briefing labelled as partly verified.

## Capabilities and Constraints
- Single static page (HTML/CSS/vanilla JS) served by a Python Starlette app on Render's free tier, same process as the MCP server. No build step, no framework.
- All existing API routes, element behaviour and states must keep working (SSE stream, approve with override, memory routes, report routes).
- Free hosting sleeps: first load can take ~1 minute; the server forgets claims on restart.

## Brand Commitments
- Name: Sinistre Express ("sinistre" is French for an insurance claim). Fictional insurer: Veridia Insurance.
- Every visible piece of data is synthetic and must stay labelled as fictional.
- Voice: plain, precise English; numbers with their contract article; no hype.

## Evidence on Hand
- Real evaluation results in README.md (23/23 main claims after fixes, 6/6 documents with OCR, Reviewer 8/8 caught and 0/8 false alarms, memory 2/2 with 0 false triggers, robustness 24/24 and 20/20). These may be shown; nothing beyond them may be claimed.
- Synthetic documents in data/documents/ (marked "synthetic test document").
- No customers, testimonials, logos or partners exist: none may be invented.

## Product Principles
- The person decides money; the interface makes that boundary unmistakable.
- Show the work: every agent step, tool call and refusal is visible, in order.
- Numbers come with their source (contract article, system calculation, check result).
- Honest labels: what is verified by code, what is AI-written, what is fictional.

## Accessibility & Inclusion
WCAG AA contrast, full keyboard use, visible focus, reduced-motion respected, readable at 390 px wide.
