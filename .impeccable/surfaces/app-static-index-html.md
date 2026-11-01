---
version: 1
slug: "app-static-index-html"
primary_target: "app/static/index.html"
related_targets: ["app/static/style.css","app/static/app.js"]
---

# Claims desk (app/static/index.html)

Scope: the single page of the live demo: intake, live steps, claim file, memory, daily report, evaluation facts. Mode: Operate.
Audience: Cominty reviewers, a few minutes, laptop, daytime. Job: send one claim, watch it handled, judge the engineering, approve.
Constraints: every existing route, id-bound behaviour and state keeps working; vanilla HTML/CSS/JS; synthetic data labelled.
Unresolved: none.

## Direction contract

THESIS: The claims desk read like the constat amiable: two parties, two colours, one shared numbered spine. It refuses the category default of a grey activity feed with an accent colour and generic cards.
OWN-WORLD: White paper ground on a cool grey desk; constat blue (Cominty agent, party A) and constat yellow (Veridia claims system, party B) as committed lane tints and headers; ink-navy text; condensed uppercase field labels with small numbered field markers; Archivo (normal and condensed widths) with tabular figures; red only for refusals, green only for a person's approval.
STORY: The visitor sees who does what (agent in blue, system in yellow, reviewer, you), sends a claim, watches both lanes fill step by step around the numbered spine, reads the claim file and approves or not.
FIRST VIEWPORT: Ink-navy top bar (name, fictional label, section links, runs left). A legend strip naming the four actors in their colours. Three work areas: Incoming claim (left, 340px), Steps (centre, widest: blue lane left, numbered spine, yellow lane right), Claim file (right, 380px) with numbered fields and the Approve action at its foot.
FORM: Constat amiable (European joint accident report), candidate 1 of 7 on my ordered list (chosen by the user as the pick over the dealt candidate 6). seed:03a49bb67128a30b
Signature interaction: each step lands in its party's lane beside the next spine number; refusals land red in the system lane; reviewer steps span both lanes as Observations.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
