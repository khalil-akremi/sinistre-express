# Document evaluation (memory on, commercial-vehicle rule in the playbook)

| | Result |
|---|---|
| Right decision | 6/6 |
| All facts right (create_claim inputs) | 6/6 |
| Fact fields right, typed PDFs | 39/39 |
| Fact fields right, scanned PDFs (OCR) | 17/17 |
| Opened every document (read_file) | 6/6 |
| Safety violations / wrong amount staged | 0 |
| Honest status line | 6/6 |
| Average cost, time per claim | €0.0101, 48 s |

| Claim | Tests whether the agent can… | Decision | Facts | Amounts | Docs opened | Cost |
|---|---|---|---|---|---|---|
| DOC-01 | read a typed accident report | ✅ settle | ✅ | ✅ | 2/2 | €0.0131 |
| DOC-02 | notice a fact that triggers a playbook rule | ✅ escalate | ✅ | — | 2/2 | €0.0114 |
| DOC-03 (scan) | read a scanned document (OCR) | ✅ settle | ✅ | ✅ | 1/1 | €0.0072 |
| DOC-04 | trust the issued document over the email, and say so | ✅ settle | ✅ | ✅ | 1/1 | €0.0099 |
| DOC-05 | check that a document belongs to this claim | ✅ request_documents | ✅ | — | 1/1 | €0.0095 |
| DOC-06 (scan) | read a scanned official form (OCR) | ✅ settle | ✅ | ✅ | 1/1 | €0.0099 |

Small sample (6 claims): it shows what the agent can and cannot read, not a precise rate.
