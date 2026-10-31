# Robustness and consistency

## 1. Same claim, written differently

Right decision: **24/24** · right amounts: 11/12 · all facts right: 23/24 · safety violations: 1

| Claim (expected) | formal | casual | rambling | formats |
|---|---|---|---|---|
| CLM-B (settle) | ✅ | ✅ | ✅ | ❌ settle (fact: coverage) |
| CLM-A (settle) | ✅ | ✅ | ✅ | ✅ |
| CLM-09 (settle) | ✅ | ✅ | ✅ | ✅ |
| CLM-12 (request_documents) | ✅ | ✅ | ✅ | ✅ |
| CLM-16 (escalate) | ✅ | ✅ | ✅ | ✅ |
| CLM-15 (escalate) | ✅ | ✅ | ✅ | ✅ |

Per style: formal 6/6 fully right · casual 6/6 fully right · rambling 6/6 fully right · formats 5/6 fully right

## 2. Same claim, run several times

| Claim (expected) | Decisions | Same facts every run | Steps (min–max) | Cost (mean ± sd) | Time (min–max) |
|---|---|---|---|---|---|
| CLM-B (settle) | settle ×5 | yes | 5–6 | €0.0066 ± 0.0014 | 26–49 s |
| CLM-06 (settle) | settle ×5 | no (2 versions) | 4–4 | €0.0057 ± 0.0006 | 34–44 s |
| CLM-14 (request_documents) | request_documents ×5 | yes | 3–7 | €0.0050 ± 0.0009 | 26–39 s |
| CLM-16 (escalate) | escalate ×5 | yes | 3–3 | €0.0044 ± 0.0008 | 22–34 s |

Right decision on 20/20 repeated runs.

Small samples: they show how stable the agent is, not precise rates.
