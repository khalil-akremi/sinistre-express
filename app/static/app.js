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
  pending_approval: { cls: "settle", text: "Settlement prepared for human approval" },
  approved: { cls: "settle", text: "Payment approved by a claims handler" },
  awaiting_documents: { cls: "request_documents", text: "Waiting for documents from the customer" },
  escalated: { cls: "escalate", text: "Referred to a claims handler" },
};
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

const DOC_FILE = { photos: "damage_photos.zip", repair_quote: "repair_quote.pdf",
  accident_report: "accident_report_signed.pdf", police_report: "police_report.pdf" };

function showQuota(left, error) {
  els.quota.classList.toggle("error", Boolean(error));
  els.quota.textContent = error || `${left} agent runs left today on this public demo.`;
}

// ---------------------------------------------------------------- ledger
function resetLedger() {
  els.ledger.innerHTML = "";
  els.file.innerHTML = `<p class="empty">The agent is working on this claim…</p>`;
}

function addStep(step) {
  const li = document.createElement("li");
  const refused = step.source === "system" && step.ok === false;
  li.className = refused ? "refused" : `src-${step.source}`;
  const text = step.source === "system" && !refused ? `${step.icon} ${step.text}` : `${step.icon} ${step.text}`;
  li.innerHTML = `<span class="step-text">${escapeHtml(text)}</span>` +
    (step.detail ? `<span class="step-detail">${escapeHtml(step.detail)}</span>` : "");
  els.ledger.appendChild(li);
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
  const statusText = status ? status.text : (claim ? `Stopped at: ${claim.status}` : "No claim was opened");
  const staged = claim && ["pending_approval", "approved"].includes(claim.status);
  const figures = claim && claim.payout !== null && claim.payout !== undefined ? `
    <dl class="figures">
      <dt>Deductible paid by the customer</dt><dd>${euro(claim.deductible)}</dd>
      <dt>Assessor visit</dt><dd>${claim.assessor_required ? (claim.assessor_date || "required") : "not needed"}</dd>
      <dt>${staged ? "Payout" : "Payout computed for the handler (not staged)"}</dt><dd class="${staged ? "big" : ""}">${euro(claim.payout)}</dd>
    </dl>` : "";
  const cost = data.cost ? `€${Number(data.cost.total).toFixed(4)}` : "n/a";
  const approved = claim && claim.status === "approved";
  const canApprove = claim && claim.status === "pending_approval";
  const review = data.review;
  const concerns = review && review.verdict === "concerns";
  const reviewBox = review ? `
    <section class="review ${concerns ? "review-concerns" : "review-ok"}" aria-label="Second agent's review">
      <p class="review-head">${concerns ? "Reviewer raised concerns" : "Reviewer agrees"}
        <span>second agent, different model, read-only</span></p>
      ${review.summary ? `<p class="review-summary">${escapeHtml(review.summary)}</p>` : ""}
      ${(review.issues || []).length ? `<ul class="review-issues">${review.issues.map((i) => `
        <li><strong>${escapeHtml(i.field || "issue")}</strong>: recorded ${escapeHtml(String(i.recorded ?? "?"))},
          should be ${escapeHtml(String(i.should_be ?? "?"))}
          ${i.evidence ? `<span>${escapeHtml(i.evidence)}</span>` : ""}</li>`).join("")}</ul>` : ""}
    </section>` : "";

  els.file.innerHTML = `
    <div class="file-sheet">
      <p class="status-line status-${statusCls}">${escapeHtml(statusText)}</p>
      <p class="ref">Claim ${escapeHtml(data.claim_ref)}</p>
      ${figures}
      ${approved ? `<div class="stamp${landing ? " landing" : ""}" role="img" aria-label="Approved by a claims handler">Approved<small>by a claims handler</small></div>` : ""}
      <p class="run-meta">Agent run: ${data.seconds ?? "?"} s, cost ${cost}.</p>
      ${data.reply ? `<details class="letter" open><summary>Agent report and draft letter</summary>
        <div class="reply">${renderReply(data.reply)}</div></details>` : ""}
      ${data.error ? `<p class="error-box">${escapeHtml(data.error)}</p>` : ""}
      ${canApprove ? reviewBox : ""}
      ${canApprove ? `<button class="approve${concerns ? " override" : ""}" id="approve" type="button">${concerns ? "Approve anyway" : "Approve payment of"} ${euro(claim.payout)}</button>
        <p class="approve-note">Only a person can approve. The agent has no tool for it.</p>` : ""}
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
  addStep({ source: "system", icon: "🖊️", text: "approve_settlement (human)", detail: "approved by Demo claims handler", ok: true });
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
