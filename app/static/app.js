// Sinistre Express claims desk. Plain JavaScript, no build step.
// The browser never talks to Cominty: it only calls this server's /api routes.

const $ = (id) => document.getElementById(id);
const els = {
  select: $("case-select"), head: $("email-head"), body: $("email-body"),
  send: $("send"), quota: $("quota"), ledger: $("ledger"), clock: $("clock"), file: $("file-body"),
};
let cases = [];
let clockTimer = null;

const STATUS = {
  pending_approval: { cls: "settle", icon: "pen", text: "Payment prepared, waiting for your approval" },
  approved: { cls: "approved", icon: "check", text: "Payment approved by a claims handler" },
  awaiting_documents: { cls: "request_documents", icon: "doc", text: "Waiting for documents from the customer" },
  escalated: { cls: "escalate", icon: "handoff", text: "Referred to a claims handler" },
};
const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;

// Which drawn icon a step gets (the server's events carry emoji; the page draws its own set).
function iconFor(step) {
  const t = (step.text || "").toLowerCase();
  if (step.source === "system") {
    if (step.ok === false) return "block";
    if (t.startsWith("approve_settlement")) return "pen";
    if (t.startsWith("workbook checked")) return "check";
    return "check";
  }
  if (step.source === "reviewer") {
    if (t.includes("raised concerns")) return "alert";
    if (t.includes("agrees")) return "check";
    if (t.includes("reading")) return "file";
    return "eye";
  }
  if (step.icon === "⚠️") return "alert";
  if (t.includes("contract")) return "doc";
  if (t.includes("sub-agent")) return "handoff";
  if (t.includes("sandbox")) return "box";
  if (t.startsWith("attaching")) return "upload";
  if (t.includes("attached document") || t.includes("reading a file")) return "file";
  if (t.includes("memory")) return "note";
  if (t.includes("skill") || t.includes("running code")) return "tool";
  if (t.includes("starting")) return "clock";
  if (t.includes("question")) return "alert";
  if (step.icon === "💬") return "message";
  return "dot";
}
const euro = (n) => `€${Number(n).toLocaleString("en-GB")}`;

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Small, safe Markdown subset for the agent's reply (escape first, then format).
function renderReply(markdown) {
  let text = escapeHtml(markdown)
    .replace(/&lt;cite\b(.*?)\/&gt;/g, (_m, attrs) => {
      const pages = (attrs.match(/pages=&quot;([^&]*)&quot;/) || [])[1];
      return `<span class="cite">contract${pages ? " p." + pages : ""}</span>`;
    })
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }
    let m;
    if ((m = line.match(/^[-*] (.*)/))) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push(`<li>${m[1]}</li>`);
    } else if ((m = line.match(/^\d+\. (.*)/)) && !/^<strong>/.test(m[1])) {
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push(`<li>${m[1]}</li>`);
    } else if ((m = line.match(/^&gt; ?(.*)/))) {
      if (list !== "blockquote") { closeList(); out.push("<blockquote>"); list = "blockquote"; }
      out.push(m[1] ? `<p>${m[1]}</p>` : "");
    } else if (/^(#+ |<strong>[^<]+<\/strong>:?$|\d+\. <strong>)/.test(line)) {
      closeList(); out.push(`<h4>${line.replace(/^#+ /, "")}</h4>`);
    } else {
      closeList(); out.push(`<p>${line}</p>`);
    }
  }
  closeList();
  return out.join("");
}

// ---------------------------------------------------------------- intake
async function loadCases() {
  const res = await fetch("/api/cases");
  const data = await res.json();
  cases = data.cases;
  const demos = cases.filter((c) => c.demo);
  const withFiles = cases.filter((c) => c.files.length);
  const others = cases.filter((c) => !c.demo && !c.files.length);
  const option = (c) => `<option value="${c.case_id}">${escapeHtml(c.title)}</option>`;
  els.select.innerHTML =
    `<optgroup label="Demo claims">${demos.map(option).join("")}</optgroup>` +
    (withFiles.length ? `<optgroup label="Claims with real documents (PDF, scans)">${withFiles.map(option).join("")}</optgroup>` : "") +
    `<optgroup label="Test set">${others.map(option).join("")}</optgroup>`;
  showQuota(data.runs_left_today);
  fillCase(cases[0].case_id);
}

function fillCase(caseId) {
  const c = cases.find((x) => x.case_id === caseId);
  loadMemory(c.policy_id);
  els.head.innerHTML = `<strong>${escapeHtml(c.from)}</strong>, ${escapeHtml(c.date)}<br>${escapeHtml(c.subject)}`;
  els.body.value = c.body;
  fitEmail();
  const fileNames = c.files.map((f) => f.name);
  document.querySelectorAll(".docs input").forEach((box) => {
    box.checked = c.documents.includes(box.value);
    // a document uploaded as a real file is not also offered as a mailroom item
    box.closest("label").hidden = fileNames.includes(DOC_FILE[box.value]);
  });
  $("docs-legend").textContent = c.files.length ? "Also received by the mailroom (not readable)" : "Documents received";
  $("files-box").hidden = !c.files.length;
  $("files").innerHTML = c.files.map((f) => `
    <label class="file-row"><input type="checkbox" value="${escapeHtml(f.name)}" checked>
      <span>${escapeHtml(f.name)}${f.scanned ? ' <em class="scan-tag">scan</em>' : ""}</span>
      <a href="${f.url}" target="_blank" rel="noopener">open</a></label>`).join("");
  $("skill").hidden = !c.skill;
  $("skill").textContent = c.skill ? `Tests whether the agent can ${c.skill}.` : "";
}

// The email box grows to its text (up to a cap), so no line is cut in half.
function fitEmail() {
  els.body.style.height = "auto";
  // On a desktop the Send button must stay in the first viewport: cap lower, scroll the rest.
  // The cap is a whole number of lines, so a scrolled box never shows half a line.
  // Scrolled text also shows inside the bottom padding, so an overflowing box drops it.
  els.body.style.paddingBottom = "";
  const style = getComputedStyle(els.body);
  const line = parseFloat(style.lineHeight);
  const top = parseFloat(style.paddingTop);
  const lines = window.matchMedia("(min-width: 861px)").matches ? 11 : 26;
  const cap = Math.round(line * lines + top + 2);
  const overflows = els.body.scrollHeight + 2 > cap + parseFloat(style.paddingBottom);
  els.body.style.paddingBottom = overflows ? "0px" : "";
  els.body.style.height = `${overflows ? cap : els.body.scrollHeight + 2}px`;
}
els.body.addEventListener("input", fitEmail);

// The Send bar casts a shadow only while it is pinned over the form (its sentinel is off screen).
if ("IntersectionObserver" in window) {
  const bar = document.querySelector(".send-bar");
  new IntersectionObserver(([entry]) => bar.classList.toggle("stuck", !entry.isIntersecting))
    .observe(document.querySelector(".send-sentinel"));
}

const DOC_FILE = { photos: "damage_photos.zip", repair_quote: "repair_quote.pdf",
  accident_report: "accident_report_signed.pdf", police_report: "police_report.pdf" };

function showQuota(left, error) {
  els.quota.classList.toggle("error", Boolean(error));
  els.quota.textContent = error || `${left} runs left today`;
}

// ---------------------------------------------------------------- ledger
function resetLedger() {
  els.ledger.innerHTML = "";
  els.ledger.classList.remove("is-empty");
  lastStep = null;
  reviewWork = null;
  els.file.innerHTML = `<p class="empty">The agent is working on this claim…</p>`;
}

// Each step lands in its party's lane: A (agent) left, B (claims system) right,
// the Reviewer and the person across both, refusals in red in lane B.
let lastStep = null;     // {key, li, count}: the same step twice in a row becomes one row "×2"
let reviewWork = null;   // the one row that gathers the Reviewer's own steps

const REVIEW_WORK = [["contract", "contract"], ["code", "code run"], ["sandbox", "sandbox"],
  ["document", "document read"], ["memory", "memory"], ["skill", "skill"]];

function addReviewerWork(step) {
  const t = (step.text || "").toLowerCase();
  const label = (REVIEW_WORK.find(([k]) => t.includes(k)) || [null, null])[1];
  if (!label || t.includes("starting")) return;   // "starting" adds nothing a reader needs
  if (!reviewWork) {
    const li = document.createElement("li");
    li.className = "lane-full lane-r";
    li.innerHTML = `<div class="cell"><span class="step-text">${icon("eye")}<span>The Reviewer is checking the sources</span>` +
      `<span class="step-tag">Observations</span></span><span class="step-detail"></span></div>`;
    els.ledger.appendChild(li);
    reviewWork = { li, counts: {} };
    lastStep = null;
  }
  reviewWork.counts[label] = (reviewWork.counts[label] || 0) + 1;
  reviewWork.li.querySelector(".step-detail").textContent = Object.entries(reviewWork.counts)
    .map(([k, n]) => `${k}${n > 1 ? ` ×${n}` : ""}`).join(" · ");
}

function addStep(step) {
  const t = (step.text || "").toLowerCase();
  const reviewerStart = t.startsWith("a second agent"), reviewerVerdict = t.includes("reviewer agrees") || t.includes("raised concerns");
  if (step.source === "reviewer" && !reviewerStart && !reviewerVerdict) { addReviewerWork(step); return; }
  const key = `${step.source}|${step.text}|${step.ok}`;
  if (lastStep && lastStep.key === key && !step.detail) {
    lastStep.count += 1;
    let badge = lastStep.li.querySelector(".step-count");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "step-count";
      lastStep.li.querySelector(".step-text > span").after(badge);
    }
    badge.textContent = `×${lastStep.count}`;
    return;
  }
  const li = document.createElement("li");
  const refused = step.source === "system" && step.ok === false;
  const human = step.source === "system" && (step.text || "").startsWith("approve_settlement");
  const lane = human ? "lane-full lane-you" : step.source === "reviewer" ? "lane-full lane-r"
    : step.source === "system" ? (refused ? "lane-b lane-refused" : "lane-b") : "lane-a";
  const tag = human ? "You" : step.source === "reviewer" ? "Observations" : refused ? "Refused" : "";
  li.className = lane;
  li.innerHTML = `<div class="cell"><span class="step-text">${icon(iconFor(step))}<span>${escapeHtml(step.text)}</span>` +
    (tag ? `<span class="step-tag">${tag}</span>` : "") + `</span>` +
    (step.detail ? `<span class="step-detail">${escapeHtml(step.detail)}</span>` : "") + `</div>`;
  els.ledger.appendChild(li);
  lastStep = { key, li, count: 1 };
  li.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function startClock() {
  const t0 = Date.now();
  stopClock();
  clockTimer = setInterval(() => { els.clock.textContent = `${Math.round((Date.now() - t0) / 1000)} s`; }, 500);
}
function stopClock() { if (clockTimer) clearInterval(clockTimer); clockTimer = null; }

// ------------------------------------------------------------ claim file
function renderFile(data, { landing = false } = {}) {
  if (data.error && !data.claim) {
    els.file.innerHTML = `<p class="error-box">${escapeHtml(data.error)}</p>`;
    return;
  }
  const claim = data.claim;
  const status = claim ? STATUS[claim.status] : null;
  const statusCls = status ? status.cls : "other";
  const statusIcon = status ? status.icon : "alert";
  const statusText = status ? status.text : (claim ? `Stopped at: ${claim.status}` : "No claim was opened");
  const staged = claim && ["pending_approval", "approved"].includes(claim.status);
  const figures = claim && claim.payout !== null && claim.payout !== undefined ? `
    <dl class="figures">
      <dt>Deductible paid by the customer</dt><dd>${euro(claim.deductible)}</dd>
      <dt>Assessor visit</dt><dd>${claim.assessor_required ? (claim.assessor_date || "required") : "not needed"}</dd>
      <dt>${staged ? "Payout" : "Payout computed for the handler, not staged"}</dt><dd class="${staged ? "big" : ""}">${euro(claim.payout)}</dd>
    </dl>` : "";
  const reviewCost = data.review && data.review.cost ? Number(data.review.cost.total) : null;
  const cost = (data.cost ? `€${Number(data.cost.total).toFixed(4)}` : "n/a") +
    (reviewCost !== null ? ` + Reviewer €${reviewCost.toFixed(4)}` : "");
  const approved = claim && claim.status === "approved";
  const canApprove = claim && claim.status === "pending_approval";
  const review = data.review;
  const concerns = review && review.verdict === "concerns";
  const reviewBox = review ? `
    <section class="review ${concerns ? "review-concerns" : "review-ok"}" aria-label="Second agent's review">
      <p class="review-head">${icon(concerns ? "alert" : "check")} ${concerns ? "Reviewer raised concerns" : "Reviewer agrees"}</p>
      <span class="review-by">Second agent, another model provider, read-only</span>
      ${review.summary ? `<p class="review-summary">${escapeHtml(review.summary)}</p>` : ""}
      ${(review.issues || []).length ? `<ul class="review-issues">${review.issues.map((i) => `
        <li><strong>${escapeHtml(i.field || "issue")}</strong>: recorded ${escapeHtml(String(i.recorded ?? "?"))},
          should be ${escapeHtml(String(i.should_be ?? "?"))}
          ${i.evidence ? `<span>${escapeHtml(i.evidence)}</span>` : ""}</li>`).join("")}</ul>` : ""}
    </section>` : "";

  const signature = canApprove ? `
      <div class="signature">
        <p class="field">Signature of the claims handler</p>
        <button class="btn approve${concerns ? " override" : ""}" id="approve" type="button">${icon("pen")} ${concerns ? "Approve anyway" : "Approve payment of"} ${euro(claim.payout)}</button>
        <p class="signature-note">Only a person can sign. The agent has no tool for it${concerns ? "; approving over the Reviewer's concerns is recorded in the audit log" : ""}.</p>
      </div>` : approved ? `
      <div class="signature signed${landing ? " landing" : ""}">
        <p class="field">Signature of the claims handler</p>
        <p class="signed-line">${icon("check")} Approved by a claims handler</p>
        <p class="signed-by">${escapeHtml(claim.approved_by || "Demo claims handler")}</p>
      </div>` : "";

  els.file.innerHTML = `
    <div class="file-sheet">
      <p class="status status-${statusCls}">${icon(statusIcon)}<span>${escapeHtml(statusText)}</span></p>
      <p class="ref">Claim ${escapeHtml(data.claim_ref)}</p>
      ${figures}
      ${canApprove ? reviewBox : ""}
      ${signature}
      <p class="run-meta">Agent run ${data.seconds ?? "?"} s · cost ${cost}</p>
      ${data.error ? `<p class="error-box">${escapeHtml(data.error)}</p>` : ""}
      ${data.reply ? `<details class="letter" open><summary>${icon("chevron")}Agent report and draft letter</summary>
        <div class="reply">${renderReply(data.reply)}</div></details>` : ""}
    </div>`;
  if (canApprove) $("approve").addEventListener("click", () => approve(data.claim_ref, concerns));
}

async function approve(ref, override = false) {
  const button = $("approve");
  button.disabled = true;
  const res = await fetch(`/api/claims/${encodeURIComponent(ref)}/approve`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ override }),
  });
  const data = await res.json();
  if (!res.ok) { button.disabled = false; showQuota(null, data.error); return; }
  addStep({ source: "system", text: "approve_settlement (signed by a person)", detail: override ? "approved over the Reviewer's concerns" : "approved by Demo claims handler", ok: true });
  renderFile(data, { landing: true });
}

// ------------------------------------------------------------------ send
async function send() {
  const documents = [...document.querySelectorAll(".docs label:not([hidden]) input:checked")].map((b) => b.value);
  const files = [...document.querySelectorAll("#files input:checked")].map((b) => b.value);
  els.send.disabled = true;
  const res = await fetch("/api/claims", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: els.select.value, body: els.body.value, documents, files }),
  });
  const data = await res.json();
  if (!res.ok) { els.send.disabled = false; showQuota(null, data.error); return; }

  resetLedger();
  startClock();
  const stream = new EventSource(`/api/claims/${encodeURIComponent(data.claim_ref)}/stream`);
  stream.addEventListener("step", (e) => addStep(JSON.parse(e.data)));
  stream.addEventListener("done", (e) => {
    stream.close();
    stopClock();
    els.send.disabled = false;
    renderFile(JSON.parse(e.data));
    loadMemory(currentPolicy());
    fetch("/api/cases").then((r) => r.json()).then((d) => showQuota(d.runs_left_today));
  });
  stream.onerror = () => {
    stream.close(); stopClock(); els.send.disabled = false;
    fetch(`/api/claims/${encodeURIComponent(data.claim_ref)}`).then((r) => r.json()).then((d) => renderFile(d));
  };
}

// ---------------------------------------------------------------- memory
const currentPolicy = () => (cases.find((x) => x.case_id === els.select.value) || {}).policy_id;

function showMemoryMessage(text, isError) {
  const msg = $("memory-msg");
  msg.textContent = text || "";
  msg.style.color = isError ? "var(--red)" : "";
}

function renderRules(rules) {
  $("rules").innerHTML = rules.length
    ? rules.map((r) => `<li>${escapeHtml(r)}</li>`).join("")
    : `<li class="empty">No rules yet. Teach one below, then send a claim it applies to.</li>`;
}

async function loadMemory(policy) {
  const res = await fetch(`/api/memory${policy ? `?policy=${encodeURIComponent(policy)}` : ""}`);
  const data = await res.json();
  if (!data.enabled) return;
  $("memory").hidden = false;
  if (!res.ok) { showMemoryMessage(data.error, true); return; }
  renderRules(data.rules);
  $("note-scope").textContent = policy ? `for ${policy}` : "";
  const note = $("customer-note");
  const text = (data.customer_note || "").replace(/^#.*\n?/gm, "").trim();
  note.classList.toggle("empty", !text);
  note.textContent = text || "No note yet. The agent writes one after handling this customer's claim.";
}

async function teach() {
  const rule = $("rule").value.trim();
  if (!rule) { showMemoryMessage("Write a rule first.", true); return; }
  $("teach").disabled = true;
  const res = await fetch("/api/memory/playbook", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rule }),
  });
  const data = await res.json();
  $("teach").disabled = false;
  if (!res.ok) { showMemoryMessage(data.error, true); return; }
  $("rule").value = "";
  renderRules(data.rules);
  showMemoryMessage("Added. The agent will read it on the next claim.");
}

async function resetMemory() {
  const res = await fetch("/api/memory/reset", { method: "POST" });
  const data = await res.json();
  if (!res.ok) { showMemoryMessage(data.error, true); return; }
  renderRules([]);
  loadMemory(currentPolicy());
  showMemoryMessage("Memory cleared.");
}

$("teach").addEventListener("click", teach);
$("reset-memory").addEventListener("click", resetMemory);
els.select.addEventListener("change", () => fillCase(els.select.value));
els.send.addEventListener("click", send);
loadCases().catch(() => showQuota(null, "Cannot reach the claims desk. Refresh in a minute: the free server may be waking up."));


// ---------------------------------------------------------------- daily report
async function makeReport() {
  const button = $("make-report");
  button.disabled = true;
  $("report-msg").textContent = "";
  $("report-steps").innerHTML = "";
  $("report-result").innerHTML = "";
  const res = await fetch("/api/report", { method: "POST" });
  const data = await res.json();
  if (!res.ok) { button.disabled = false; $("report-msg").textContent = data.error; return; }
  $("report-msg").textContent = "The built-in agent is building the report (about a minute)…";
  const poll = async () => {
    const r = await fetch(`/api/report/${data.report_id}`);
    const rep = await r.json();
    if (!r.ok) { button.disabled = false; $("report-msg").textContent = rep.error; return; }
    $("report-steps").innerHTML = rep.events.map((e) =>
      `<li>${icon(iconFor(e))}<span>${escapeHtml(e.text)}</span></li>`).join("");
    if (!rep.done) { setTimeout(poll, 2000); return; }
    button.disabled = false;
    $("report-msg").textContent = `${rep.claims} claims, ${rep.seconds} s` +
      (rep.cost ? `, cost €${Number(rep.cost.total).toFixed(4)}` : "") + ".";
    const checks = rep.checks ? `<ul class="checks">${rep.checks.checks.map((c) =>
      `<li class="${c.ok ? "ok" : "ko"}">${icon(c.ok ? "check" : "cross")}<span>${escapeHtml(c.name)}${c.detail && !c.ok ? `<span class="detail">${escapeHtml(c.detail)}</span>` : ""}</span></li>`).join("")}</ul>` : "";
    $("report-result").innerHTML =
      (rep.error ? `<p class="error-box">${escapeHtml(rep.error)}</p>` : "") +
      (rep.file_url ? `<a class="download" href="${rep.file_url}">${icon("download")} Download ${escapeHtml(rep.file_name || "the report")}</a>` : "") +
      (rep.checks ? `<h3>Checked against the claims system: ${rep.checks.passed}/${rep.checks.total}</h3>${checks}` : "") +
      (rep.briefing ? `<h3>Briefing for the claims manager</h3><p class="hint">Written by the AI. Amounts and claim references are checked against the claims system; the sentences are not.</p><div class="reply">${renderReply(rep.briefing)}</div>` : "");
  };
  poll();
}
$("make-report").addEventListener("click", makeReport);
