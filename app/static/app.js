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
  const others = cases.filter((c) => !c.demo);
  const option = (c) => `<option value="${c.case_id}">${escapeHtml(c.title)}</option>`;
  els.select.innerHTML =
    `<optgroup label="Demo claims">${demos.map(option).join("")}</optgroup>` +
    `<optgroup label="Test set">${others.map(option).join("")}</optgroup>`;
  showQuota(data.runs_left_today);
  fillCase(cases[0].case_id);
}

function fillCase(caseId) {
  const c = cases.find((x) => x.case_id === caseId);
  els.head.innerHTML = `<strong>${escapeHtml(c.from)}</strong>, ${escapeHtml(c.date)}<br>${escapeHtml(c.subject)}`;
  els.body.value = c.body;
  document.querySelectorAll(".docs input").forEach((box) => { box.checked = c.documents.includes(box.value); });
}

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
  const figures = claim && claim.payout !== null && claim.payout !== undefined ? `
    <dl class="figures">
      <dt>Deductible paid by the customer</dt><dd>${euro(claim.deductible)}</dd>
      <dt>Assessor visit</dt><dd>${claim.assessor_required ? (claim.assessor_date || "required") : "not needed"}</dd>
      <dt>Payout</dt><dd class="big">${euro(claim.payout)}</dd>
    </dl>` : "";
  const cost = data.cost ? `€${Number(data.cost.total).toFixed(4)}` : "n/a";
  const approved = claim && claim.status === "approved";
  const canApprove = claim && claim.status === "pending_approval";

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
      ${canApprove ? `<button class="approve" id="approve" type="button">Approve payment of ${euro(claim.payout)}</button>
        <p class="approve-note">Only a person can approve. The agent has no tool for it.</p>` : ""}
    </div>`;
  if (canApprove) $("approve").addEventListener("click", () => approve(data.claim_ref));
}

async function approve(ref) {
  const button = $("approve");
  button.disabled = true;
  const res = await fetch(`/api/claims/${encodeURIComponent(ref)}/approve`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) { button.disabled = false; showQuota(null, data.error); return; }
  addStep({ source: "system", icon: "🖊️", text: "approve_settlement (human)", detail: "approved by Demo claims handler", ok: true });
  renderFile(data, { landing: true });
}

// ------------------------------------------------------------------ send
async function send() {
  const documents = [...document.querySelectorAll(".docs input:checked")].map((b) => b.value);
  els.send.disabled = true;
  const res = await fetch("/api/claims", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: els.select.value, body: els.body.value, documents }),
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
    fetch("/api/cases").then((r) => r.json()).then((d) => showQuota(d.runs_left_today));
  });
  stream.onerror = () => {
    stream.close(); stopClock(); els.send.disabled = false;
    fetch(`/api/claims/${encodeURIComponent(data.claim_ref)}`).then((r) => r.json()).then((d) => renderFile(d));
  };
}

els.select.addEventListener("change", () => fillCase(els.select.value));
els.send.addEventListener("click", send);
loadCases().catch(() => showQuota(null, "Cannot reach the claims desk. Refresh in a minute: the free server may be waking up."));
