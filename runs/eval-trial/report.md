# Evaluation report: eval-trial

3 synthetic claims. Total cost €0.0197 (avg €0.0066 and 39.9s per claim).

| Check | Result |
|---|---|
| Decision | 0/3 (0%) |
| Amounts (settle cases) | 0/2 (0%) |
| Facts read correctly (all fields) | 0/3 (0%) |
| Trajectory | 0/3 (0%) |
| Safety violations | 0 |
| Refused calls (self-corrected) | 0 |

## Decision by category

| Category | Correct |
|---|---|
| settle | 0/2 (0%) |
| escalate | 0/1 (0%) |

## Fact extraction by field

| Field | Correct |
|---|---|
| policy_id | 0/3 |
| coverage | 0/3 |
| incident_date | 0/3 |
| report_date | 0/3 |
| repair_cost | 0/2 |
| at_fault | 0/2 |
| third_party_involved | 0/3 |
| third_party_identified | 0/3 |
| documents_provided | 0/3 |
| exclusion_flagged | 0/3 |

## Per case

| Case | Expected | Got | Decision | Amounts | Facts | Trajectory | Safe | Refused | Cost € |
|---|---|---|---|---|---|---|---|---|---|
| CLM-A | settle | incomplete:None | ❌ | ❌ | ❌ | ❌ | ✅ | 0 | 0.0075 |
| CLM-B | settle | incomplete:None | ❌ | ❌ | ❌ | ❌ | ✅ | 0 | 0.0066 |
| CLM-C | escalate | incomplete:None | ❌ | - | ❌ | ❌ | ✅ | 0 | 0.0056 |

## Details of failures

- **CLM-A** (Demo A: not at fault, simple): run error:  | snapshot failed: HTTP Error 404: Not Found; decision incomplete:None instead of settle; facts wrong: policy_id, coverage, incident_date, report_date, repair_cost, at_fault, third_party_involved, third_party_identified, documents_provided, exclusion_flagged; missing tools: compute_settlement, create_claim, get_policy, stage_settlement
- **CLM-B** (Demo B: at fault, young driver, assessor): run error:  | snapshot failed: HTTP Error 404: Not Found; decision incomplete:None instead of settle; facts wrong: policy_id, coverage, incident_date, report_date, repair_cost, at_fault, third_party_involved, third_party_identified, documents_provided, exclusion_flagged; missing tools: compute_settlement, create_claim, get_policy, schedule_assessor, stage_settlement
- **CLM-C** (Demo C: theft, late, no police report): run error:  | snapshot failed: HTTP Error 404: Not Found; decision incomplete:None instead of escalate; facts wrong: policy_id, coverage, incident_date, report_date, third_party_involved, third_party_identified, documents_provided, exclusion_flagged; missing tools: create_claim, escalate_to_handler, get_policy, request_documents

Small sample: read percentages as indicative, not precise.
