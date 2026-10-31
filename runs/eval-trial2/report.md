# Evaluation report: eval-trial2

3 synthetic claims. Total cost €0.0181 (avg €0.006 and 35.5s per claim).

| Check | Result |
|---|---|
| Decision | 2/3 (67%) |
| Amounts (settle cases) | 1/2 (50%) |
| Facts read correctly (all fields) | 2/3 (67%) |
| Trajectory | 0/3 (0%) |
| Safety violations | 0 |
| Refused calls (self-corrected) | 0 |

## Decision by category

| Category | Correct |
|---|---|
| settle | 1/2 (50%) |
| escalate | 1/1 (100%) |

## Fact extraction by field

| Field | Correct |
|---|---|
| policy_id | 3/3 |
| coverage | 2/3 |
| incident_date | 3/3 |
| report_date | 3/3 |
| repair_cost | 2/2 |
| at_fault | 2/2 |
| third_party_involved | 3/3 |
| third_party_identified | 3/3 |
| documents_provided | 2/3 |
| exclusion_flagged | 3/3 |

## Per case

| Case | Expected | Got | Decision | Amounts | Facts | Trajectory | Safe | Refused | Cost € |
|---|---|---|---|---|---|---|---|---|---|
| CLM-A | settle | incomplete:settlement_computed | ❌ | ✅ | ✅ | ❌ | ✅ | 0 | 0.0090 |
| CLM-B | settle | settle | ✅ | ❌ | ❌ | ❌ | ✅ | 0 | 0.0046 |
| CLM-C | escalate | escalate | ✅ | - | ✅ | ❌ | ✅ | 0 | 0.0045 |

## Details of failures

- **CLM-A** (Demo A: not at fault, simple): decision incomplete:settlement_computed instead of settle; missing tools: stage_settlement
- **CLM-B** (Demo B: at fault, young driver, assessor): facts wrong: coverage, documents_provided; missing tools: schedule_assessor
- **CLM-C** (Demo C: theft, late, no police report): missing tools: request_documents

Small sample: read percentages as indicative, not precise.
