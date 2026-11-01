---
name: Sinistre Express
description: A motor-claims desk read like a constat amiable; two parties, two colours, one numbered spine, and a person who signs.
colors:
  constat-blue: "#1D5BB0"
  constat-blue-deep: "#133F7E"
  constat-blue-tint: "#E4EDFA"
  constat-blue-line: "#B9CEEC"
  constat-yellow: "#E9BA12"
  constat-yellow-deep: "#6A5000"
  constat-yellow-tint: "#FDF4D0"
  constat-yellow-line: "#EED67F"
  ink-navy: "#14223B"
  ink-slate: "#46556D"
  ink-muted: "#56637A"
  desk-grey: "#E7EBF0"
  paper: "#FFFFFF"
  rule: "#CDD5DF"
  rule-soft: "#E3E8EE"
  reviewer-tint: "#EEF0F4"
  reviewer-line: "#C3CAD5"
  refusal-red: "#B42318"
  refusal-red-deep: "#7E1D14"
  refusal-red-tint: "#FDECEA"
  refusal-red-line: "#F2B8B2"
  approval-green: "#1C7347"
  approval-green-deep: "#155C38"
  approval-green-tint: "#E5F3EB"
  approval-green-line: "#A9D6BC"
  concerns-amber: "#8A4208"
  concerns-amber-deep: "#6E3506"
  concerns-amber-tint: "#FFF3E8"
  concerns-amber-line: "#F0C79F"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "21px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontVariation: "\"wdth\" 118"
  figure:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 750
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\""
    fontVariation: "\"wdth\" 92"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 750
    lineHeight: 1.5
    letterSpacing: "-0.005em"
    fontVariation: "\"wdth\" 112"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\""
  body-small:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 650
    lineHeight: 1.5
    letterSpacing: "0.06em"
    fontVariation: "\"wdth\" 78"
rounded:
  marker: "3px"
  sm: "4px"
  md: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  gutter: "28px"
components:
  button-primary:
    backgroundColor: "{colors.constat-blue}"
    textColor: "{colors.paper}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
  button-primary-hover:
    backgroundColor: "{colors.constat-blue-deep}"
  button-primary-disabled:
    backgroundColor: "{colors.rule-soft}"
    textColor: "{colors.ink-muted}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.constat-blue-deep}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.constat-blue-tint}"
  button-approve:
    backgroundColor: "{colors.approval-green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
  button-approve-hover:
    backgroundColor: "{colors.approval-green-deep}"
  button-approve-override:
    backgroundColor: "{colors.concerns-amber}"
    textColor: "{colors.paper}"
  button-approve-override-hover:
    backgroundColor: "{colors.concerns-amber-deep}"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.sm}"
    padding: "9px 11px"
  field-label:
    textColor: "{colors.ink-slate}"
    typography: "{typography.label}"
  field-number:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.marker}"
    height: "18px"
  lane-head-a:
    backgroundColor: "{colors.constat-blue}"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    padding: "6px 10px"
  lane-head-b:
    backgroundColor: "{colors.constat-yellow}"
    textColor: "{colors.ink-navy}"
    typography: "{typography.label}"
    padding: "6px 10px"
  step-cell:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-navy}"
    typography: "{typography.title}"
    rounded: "{rounded.sm}"
    padding: "8px 10px"
  step-cell-refused:
    backgroundColor: "{colors.refusal-red-tint}"
    textColor: "{colors.refusal-red}"
  step-cell-reviewer:
    backgroundColor: "{colors.reviewer-tint}"
  spine-number:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.marker}"
    height: "22px"
  panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.md}"
    padding: "18px 20px 20px"
  topbar:
    backgroundColor: "{colors.ink-navy}"
    textColor: "{colors.paper}"
    padding: "14px 28px"
  cite-chip:
    backgroundColor: "{colors.constat-blue-tint}"
    textColor: "{colors.constat-blue-deep}"
    rounded: "{rounded.marker}"
    padding: "1px 5px"
---

# Design System: Sinistre Express

## Overview

**Creative North Star: "The Constat Amiable"**

The whole desk is drawn from the European joint accident report: white paper on a cool grey desk, two parties identified by two committed colours, and one shared numbered spine that both parties write against. Party A, constat blue, is the Cominty agent. Party B, constat yellow, is the Veridia claims system. The Reviewer is a neutral grey observer whose notes span both lanes, and the person at the desk is the only actor allowed green, because green means a signature on money.

Density is that of a working form, not a marketing page: three panels side by side at desktop width, condensed uppercase field labels with small boxed field numbers, tabular figures everywhere, and plain ink-navy text. Colour is structural, never decorative. A lane tint tells you who acted; red tells you something was refused; green tells you a person signed. The form's own devices (numbered fields, boxed markers, a dashed signature box, a header split half blue and half yellow) are the ornament; nothing is added on top of them.

The world rejects the category default of a grey activity feed with one accent colour and generic cards. Every step on screen belongs to a party and lands in that party's lane.

**Key Characteristics:**
- Two-party colour coding (blue A, yellow B) carried by lane tints, lane headers and party marks.
- A shared numbered spine between the lanes; numbers sit in small bordered boxes, like constat fields.
- Archivo variable at several widths: wide for the wordmark and panel titles, condensed for field labels, tabular figures throughout.
- White paper panels on a cool grey desk, 1px rules, one soft ambient shadow.
- Semantic colours with exclusive meanings: red for refusals and failures, green for a person's approval, amber for approving over the Reviewer's concerns.
- Self-drawn 16px stroke icons (1.5px stroke, round caps), never glyphs or emoji.

## Colors

A form palette: two party colours on paper and ink, with three semantic colours that each own exactly one meaning.

### Primary
- **Constat Blue** (constat-blue): party A, the Cominty agent. Lane A header, party mark A, the primary "Send to the agent" action, links, focus ring, caret, checkbox accent, step icons in lane A. Its deep shade is the hover and the text colour on blue tints; its tint fills lane A; its line colour borders lane A cells and secondary buttons.

### Secondary
- **Constat Yellow** (constat-yellow): party B, the Veridia claims system. Lane B header (with ink-navy text, never white), party mark B, the right half of the top-bar stripe, text selection (via its line shade). Its deep olive shade colours icons and status text on yellow tints, where yellow itself would fail contrast; its tint fills lane B and the customer note.

### Tertiary
- **Refusal Red** (refusal-red): a refused tool call in lane B, a failed report check, an error status, and the hover of the destructive "Clear memory" link. The deep shade is for running text on the red tint.
- **Approval Green** (approval-green): only a person's approval. The Approve button, the signed box, the "You" party mark, passed report checks.
- **Concerns Amber** (concerns-amber): the Reviewer raised concerns. Tints the review box and recolours the Approve button to "Approve anyway"; nothing else.

### Neutral
- **Ink Navy** (ink-navy): body text, headings, the top bar ground, spine and field numbers.
- **Ink Slate** (ink-slate): secondary text, field labels, the borders of numbered markers.
- **Ink Muted** (ink-muted): hints, metadata, placeholders, disabled text; still at least 4.5:1 on paper.
- **Desk Grey** (desk-grey): the page ground the paper panels sit on; also quoted blocks inside the agent's letter.
- **Paper** (paper): every panel, input and lane cell.
- **Rule / Rule Soft** (rule, rule-soft): panel and input borders, and the hairlines between rows, parties and list items.
- **Reviewer Tint / Line** (reviewer-tint, reviewer-line): the Reviewer's observations, both in the steps and in the claim file.

### Named Rules
**The Two Parties Rule.** Blue is always party A and yellow is always party B. Neither colour is ever used as a generic accent, a highlight, or for a third actor.

**The Exclusive Meaning Rule.** Red means refused or failed, green means a person approved, amber means approved over concerns. If an element does not carry that meaning, it does not get that colour.

**The Ink On Yellow Rule.** Text on constat yellow is ink-navy; on the yellow tint, icons and status text use the deep olive shade. White never sits on yellow.

## Typography

**Display Font:** Archivo (self-hosted variable woff, weight 100–900, width 62–125%), with system-ui fallback
**Body Font:** Archivo, same file
**Label/Mono Font:** none; labels are Archivo condensed

**Character:** One grotesque used across its width axis does all the work: stretched wide and heavy for the wordmark and panel titles, set condensed and tracked in capitals for the form's field labels, and plain at normal width for reading. Tabular figures are on for the whole page so euros, dates and step numbers align.

### Hierarchy
- **Display** (800, 21px, 1.1, width 118%): the "Sinistre Express" wordmark in the top bar only.
- **Figure** (750, 26px, 1.1, width 92%): the staged payout in the claim file; the one big number.
- **Headline** (750, 17px, width 112%): panel titles (Incoming claim, Steps, Claim file, lower sections). The claim status line shares the size at 700.
- **Title** (600–700, 14px, 1.35): step text inside lane cells, sub-headings, reviewer and report headings.
- **Body** (400, 15px, 1.5): default text and inputs; letters and textareas at 14px/1.55. Section intros cap at 80ch.
- **Body Small** (400, 13px): hints, metadata, step details, colophon.
- **Label** (650–700, 12px, 0.06–0.07em, uppercase, width 78%): constat field labels, lane headers, table headers, letter summary. Step tags and scan tags drop to 11px.

### Named Rules
**The Width Axis Rule.** Hierarchy comes from Archivo's width and weight, not from new families: wide for names and titles, condensed for labels, normal for reading.

**The Tabular Rule.** Figures are tabular everywhere. Amounts are right-aligned and weighted 650 or heavier.

## Layout

At desktop width (above 1240px) the desk is a three-column grid: Incoming claim (340px), Steps (fluid, widest), Claim file (390px), with 20px gaps and 28px page gutters. Above it sit the ink-navy top bar and a four-cell party legend (A, B, Reviewer, You) in one paper strip. Below, full-width panels for memory, the daily report and the evaluation table, with a quiet colophon.

Inside Steps, the two lanes are a three-track grid: lane A, a 40px spine track, lane B. Lane tints are painted as background bands so they run the full height even when only one side has cells; a 1px rule draws the spine itself.

Between 860px and 1240px the claim file drops below as a full-width row and the party legend becomes 2×2. Below 860px everything is one column with 16px gutters: the top-bar section links wrap into a horizontally scrollable row, and the lanes collapse onto a left spine (34px track) with each cell tinted by its party instead of by its position. The evaluation table becomes stacked rows. Below 420px the document checkboxes go to one column.

Spacing rhythm is 4 / 8 / 12 / 16 / 20 / 28px: 6–8px inside groups (label to input, cell to cell), 16–18px between field groups, 20px between panels, 28px at the page edge.

The single primary action ("Send to the agent") rides in a sticky bar at the foot of the intake panel and gains an upward shadow only while it is stuck.

## Elevation & Depth

Mostly flat: paper panels sit one step above the grey desk with a single soft, offset ambient shadow, and everything inside a panel is separated by 1px rules and tints rather than further elevation.

### Shadow Vocabulary
- **Panel** (`box-shadow: 0 1px 2px rgba(20, 34, 59, .06), 0 4px 12px -6px rgba(20, 34, 59, .10)`): every desk and lower panel.
- **Stuck send bar** (`box-shadow: 0 -8px 16px -10px rgba(20, 34, 59, .28)`): only while the send bar is pinned over scrolling content.
- **Signature landing** (`0 0 0 6px rgba(28, 115, 71, .18)` fading to none over 0.5s): the one-off stamp when a person approves.
- **Input focus** (`box-shadow: 0 0 0 3px` constat-blue-tint, with the border turning constat blue).

### Named Rules
**The One Layer Rule.** Paper sits on the desk; nothing sits on paper. Inside a panel, depth is a rule, a tint or a dashed border, never another shadow. The only exception is the send bar while it is stuck over scrolling content.

## Shapes

Gently squared form geometry: panels round at 6px, controls, cells and tints at 4px, and the small numbered markers (field numbers, spine numbers, rule numbers, cite chips, scan tags) at 3px with a 1px ink-slate border, like the boxes printed on a paper form. Lane headers round only their top corners and sit flush on their lane.

Borders are 1px throughout. Dashed borders carry meaning: the empty signature box waiting for a person, the ghost placeholder steps in an empty ledger, and an empty customer note. A filled state turns the dash solid.

The top bar ends in a 4px full-width stripe split exactly half constat blue and half constat yellow: the constat's two-party header, and the system's one signature device.

## Components

### Buttons
Firm and plain; one primary per panel.
- **Shape:** gently squared (4px).
- **Primary:** constat blue on white text, full width in the intake send bar, 12px 16px, weight 650. Hover deepens to constat-blue-deep. Disabled goes to rule-soft with muted text.
- **Secondary:** paper with constat-blue-deep text and a constat-blue-line border; hover fills the blue tint and the border turns constat blue.
- **Quiet:** underlined ink-slate text with no box, for the destructive "Clear memory"; hover turns refusal red.
- **Approve:** approval green, full width inside the signature box, pen icon plus the exact amount ("Approve payment of €1,700"). When the Reviewer raised concerns it becomes concerns amber and reads "Approve anyway".
- **Focus:** 2px constat-blue outline at 2px offset (constat yellow on the ink-navy top bar).

### Inputs / Fields
- **Label:** a constat field: condensed uppercase label preceded by a boxed field number (1 Sample claim, 2 Customer email, 3 Documents received, 4 Documents the agent opens).
- **Style:** paper, 1px rule border, 4px radius, 9px 11px padding; hover darkens the border slightly.
- **Focus:** border turns constat blue with a 3px blue-tint ring; the caret is constat blue.
- **Checkboxes:** native, 16px, accent constat blue.

### Navigation
The ink-navy top bar: wordmark and fictional tagline on the left, section anchor links (14px, 550) on the right with a translucent white hover fill, then the runs-left counter. At narrow widths the links wrap onto their own scrollable row. The blue/yellow stripe closes the bar.

### Party Legend
A single paper strip of four cells divided by soft rules, each with a 28px rounded mark: a solid blue "A", a solid yellow "B" (ink text), a grey eye icon for the Reviewer and a green pen icon for You, followed by one sentence on what that actor may do.

### Two-Lane Ledger (signature component)
Each step lands as a paper cell in its party's lane beside the next spine number, sliding 8px in from its own side over 0.26s with an exponential ease-out (`cubic-bezier(.16, 1, .3, 1)`) from an already-visible state. Lane A cells carry a blue-line border and blue icon; lane B cells a yellow-line border and olive icon. A refused system action lands in lane B on the red tint with red text, a red block icon and a "Refused" step tag. Reviewer observations and the person's approval span both lanes, on the reviewer tint or green tint, and take no spine number. Before any run, dashed ghost cells explain what each lane will receive.

### Claim File
A status line on a tint that matches its meaning (blue tint for prepared or referred, yellow tint for documents requested, green tint for approved, red tint for failure), then a ruled definition list of figures with right-aligned tabular amounts and the payout set at Figure size. The Reviewer's verdict follows in a reviewer-tint box (amber when concerns are raised), then the dashed signature box labelled "Signature of the claims handler" holding the Approve button; once signed it turns solid green-tint with a check and the signer's name. The agent's report and draft letter sit in a collapsible ruled box whose contract citations render as small blue-tint cite chips.

### Lists and Tables
Playbook rules are numbered with the same 3px boxed markers as the form fields. Report checks use green check and red cross icons. The evaluation table uses condensed uppercase headers, 1px soft row rules and right-aligned bold results; it stacks into rows on mobile.

## Do's and Don'ts

### Do:
- **Do** assign every new actor-bound element to a party: constat blue for the agent (A), constat yellow for the claims system (B), reviewer grey for the Reviewer, green only for the person.
- **Do** label form inputs as constat fields: condensed uppercase Archivo (12px, 650, 0.06em, width 78%) with a 3px boxed field number.
- **Do** keep text on constat yellow ink-navy, and use the deep olive shade for icons and text on the yellow tint.
- **Do** keep figures tabular and amounts right-aligned, with the contract article beside the number when one applies.
- **Do** draw icons from the inline SVG set: 16px, 1.5px stroke, round caps and joins, currentColor.
- **Do** theme browser surfaces from the palette: yellow-line selection, constat-blue caret and focus ring, thin rule-coloured scrollbars, 3px underline offset.
- **Do** keep motion to the step landing and the signature stamp, and drop both under reduced motion.

### Don't:
- **Don't** use constat blue or yellow as a generic accent, highlight or decoration on anything that is not party A or party B.
- **Don't** use red for anything but a refusal, a failure or a destructive hover, or green for anything but a person's approval and passed checks.
- **Don't** stack shadows inside a panel (the stuck send bar excepted); separate with 1px rules, tints and dashed borders instead.
- **Don't** render emoji or Unicode glyphs as icons, even when a payload carries them.
- **Don't** put a label above a panel title; the title stands alone, and condensed caps belong to fields, lane headers and table headers.
- **Don't** introduce another typeface; reach for Archivo's width axis instead.
