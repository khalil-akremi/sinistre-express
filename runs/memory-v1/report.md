# Memory experiment

Playbook rule taught by a handler: *When the other driver is a commercial vehicle (van, truck, lorry, delivery vehicle), refer the claim to a handler so Veridia can recover the money from their insurer.*

| | Without memory | With memory |
|---|---|---|
| Van/truck claims handled as expected | 2/2 settled (the agent cannot know the rule) | 2/2 referred to a handler |
| Control claims still settled (no false trigger) | 4/4 | 3/4 |
| Customer notes written | - | 6/6 |
| Average cost per claim | €0.0058 | €0.0073 |

| Condition | Case | Expected | Got | |
|---|---|---|---|---|
| without memory | CLM-A | settle | settle | ✅ |
| without memory | CLM-03 | settle | settle | ✅ |
| without memory | CLM-B | settle | settle | ✅ |
| without memory | CLM-01 | settle | settle | ✅ |
| without memory | CLM-02 | settle | settle | ✅ |
| without memory | CLM-05 | settle | settle | ✅ |
| with memory | CLM-A | escalate | escalate | ✅ |
| with memory | CLM-03 | escalate | escalate | ✅ |
| with memory | CLM-B | settle | settle | ✅ |
| with memory | CLM-01 | settle | settle | ✅ |
| with memory | CLM-02 | settle | settle | ✅ |
| with memory | CLM-05 | settle | escalate | ❌ |

Small sample: indicative, not a precise rate.
