const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const names = { hi: "Hindi", bn: "Bengali", ta: "Tamil" };
let items = [];
let savedModels = [];
let savedSuites = [];
let activeConfig = { native: true, variants: 4, variant_mode: "habit", typo: true, bridge: true, scan: false, seed: 42 };
let activeIds = [];
let refreshTimer;

async function api(path, options = {}) {
  const init = { ...options };
  if (options.body && typeof options.body !== "string") {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let message = response.statusText;
    try { message = (await response.json()).detail || message; } catch { /* response is not JSON */ }
    throw new Error(message);
  }
  return response.json();
}

function datasetReady(description) {
  $("dataset-state").textContent = description;
  $("run").disabled = !items.length || savedModels.filter((m) => document.querySelector(`[data-model="${m.id}"]`)?.checked).length < 2;
  $("save-suite").disabled = !items.length;
  window.dispatchEvent(new Event("guided-input-change"));
}

function showError(error) { $("message").textContent = error.message || String(error); $("message").className = "err-line"; }

async function loadSamples() {
  const samples = await api("/samples");
  for (const sample of samples) {
    const option = document.createElement("option");
    option.value = sample.id;
    option.textContent = `${sample.title} (${names[sample.lang] || sample.lang}, ${sample.n} questions)`;
    $("sample").append(option);
  }
}

async function loadModels() {
  const data = await api("/models");
  savedModels = data.saved;
  $("models").innerHTML = savedModels.length ? savedModels.map((m) => `<label class="model-option"><input type="checkbox" data-model="${esc(m.id)}" /> <b>${esc(m.label)}</b><small>${esc(m.kind === "hf" ? m.hf_id : m.model)}</small></label>`).join("") : '<p class="muted">No saved models yet. Add and test at least two models in the <a href="/#/lab">Test lab</a>.</p>';
  $("models").querySelectorAll("input").forEach((input) => input.addEventListener("change", () => datasetReady(`${items.length} questions ready. Select at least two models.`)));
  datasetReady(items.length ? `${items.length} questions loaded.` : "Choose a starter set or upload your test questions.");
}

async function refreshSuites() {
  savedSuites = await api("/suites");
  const select = $("suite-select");
  const previous = select.value;
  select.innerHTML = '<option value="">Choose a saved test set</option>' + savedSuites.map((s) => `<option value="${esc(s.id)}">${esc(s.name)} · ${s.n_items} questions · ${s.langs.map((l) => names[l] || l).join(", ")}</option>`).join("");
  if (savedSuites.some((s) => s.id === previous)) select.value = previous;
  const active = Boolean(select.value);
  $("load-suite").disabled = !active;
  $("delete-suite").disabled = !active;
}

$("suite-select").addEventListener("change", () => {
  const active = Boolean($("suite-select").value);
  $("load-suite").disabled = !active;
  $("delete-suite").disabled = !active;
});

$("save-suite").addEventListener("click", async () => {
  try {
    const suite = await api("/suites", { method: "POST", body: { name: $("suite-name").value, items, config: activeConfig } });
    await refreshSuites();
    $("suite-select").value = suite.id;
    $("load-suite").disabled = false; $("delete-suite").disabled = false;
    $("suite-state").textContent = `Saved “${suite.name}” with ${suite.n_items} questions. It is stored locally in Vartani’s data folder.`;
  } catch (e) { $("suite-state").textContent = e.message; }
});

$("load-suite").addEventListener("click", async () => {
  try {
    const suite = await api(`/suites/${encodeURIComponent($("suite-select").value)}`);
    items = suite.items; activeConfig = suite.config || activeConfig;
    $("suite-name").value = suite.name;
    datasetReady(`Loaded saved benchmark “${suite.name}” (${items.length} questions). Its spelling settings are restored.`);
    $("suite-state").textContent = `Loaded “${suite.name}”. You can compare this same suite against new or updated models.`;
  } catch (e) { $("suite-state").textContent = e.message; }
});

$("delete-suite").addEventListener("click", async () => {
  const id = $("suite-select").value;
  const suite = savedSuites.find((s) => s.id === id);
  if (!id || !window.confirm(`Delete the saved benchmark “${suite?.name || ""}”? Existing runs will stay.`)) return;
  try { await api(`/suites/${encodeURIComponent(id)}`, { method: "DELETE" }); await refreshSuites(); $("suite-state").textContent = "Saved benchmark deleted. Existing runs are unchanged."; }
  catch (e) { $("suite-state").textContent = e.message; }
});

$("sample").addEventListener("change", async (event) => {
  if (!event.target.value) return;
  try {
    const d = await api(`/samples/${encodeURIComponent(event.target.value)}`);
    items = d.items; activeConfig = { native: true, variants: 4, variant_mode: "habit", typo: true, bridge: true, scan: false, seed: 42 };
    datasetReady(`Loaded ${items.length} example questions for ${names[d.lang] || d.lang}. For a meaningful decision, use a larger set from your own use case.`);
  } catch (e) { showError(e); }
});

$("file").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const parsed = await api("/datasets/parse", { method: "POST", body: { text: await file.text(), filename: file.name, lang: $("default-lang").value } });
    items = parsed.items; activeConfig = { native: true, variants: 4, variant_mode: "habit", typo: true, bridge: true, scan: false, seed: 42 };
    datasetReady(`Loaded ${items.length} questions${parsed.skipped ? `; skipped ${parsed.skipped} invalid rows` : ""}.${parsed.warnings?.length ? ` ${parsed.warnings[0]}` : ""}`);
  } catch (e) { showError(e); }
});

$("run").addEventListener("click", async () => {
  const selected = [...document.querySelectorAll("[data-model]:checked")].map((x) => x.dataset.model);
  if (selected.length < 2 || !items.length) return;
  const minAccuracy = Number($("min-accuracy").value), maxFlip = Number($("max-flips").value);
  const minItems = Number($("min-items").value);
  if (![minAccuracy, maxFlip].every((v) => Number.isFinite(v) && v >= 0 && v <= 100) || !Number.isInteger(minItems) || minItems < 1) return showError(new Error("Enter percentage limits between 0 and 100 and a minimum question count of at least 1."));
  $("run").disabled = true; $("message").className = "msg"; $("message").textContent = "Starting matching test runs…";
  try {
    const modelById = new Map(savedModels.map((m) => [m.id, m]));
    const cfg = { ...activeConfig,
      release_gate: { enabled: true, min_roman_accuracy: minAccuracy, max_single_flip_rate: maxFlip, min_items: minItems } };
    const created = await Promise.all(selected.map((id) => api("/runs", { method: "POST", body: {
      name: `Release check · ${modelById.get(id)?.label || "model"}`, items, model_id: id, config: cfg,
    } })));
    activeIds = created.map((run) => run.id);
    const url = new URL(location.href); url.searchParams.set("runs", activeIds.join(",")); history.replaceState({}, "", url);
    $("results").hidden = false;
    $("message").textContent = `${created.length} model runs started. This page will update as results arrive.`;
    refreshResults();
  } catch (e) { showError(e); $("run").disabled = false; }
});

function renderFingerprint(report) {
  const profiles = report?.spelling_fingerprint?.profiles || [];
  if (!profiles.length) return '<p class="muted">No writer-style profile data is available for this run.</p>';
  return `<details class="fingerprint-details"><summary>View spelling fingerprint (${profiles.length} language/style profiles)</summary><p class="muted">This connects each consistent writer-style spelling combination with answer changes on this test set. It is an observed association, not proof that one spelling rule caused the change.</p><div class="scroll"><table><thead><tr><th>Language</th><th>Style combination</th><th>Items</th><th>Changed</th><th>Right → wrong</th><th>Wrong → right</th></tr></thead><tbody>${profiles.slice(0, 12).map((p) => `<tr><td>${esc(names[p.lang] || p.lang)}</td><td>${esc(p.label)}</td><td>${p.n}</td><td>${p.flip_rate}%</td><td class="${p.harmful ? "bad" : "ok"}">${p.harmful}</td><td class="${p.helpful ? "ok" : "muted"}">${p.helpful}</td></tr>`).join("")}</tbody></table></div></details>`;
}

function gateResult(meta, report) {
  if (meta.status !== "done") return { label: meta.status === "failed" ? "Run failed" : "Waiting", pass: false, pending: !["failed", "cancelled", "interrupted"].includes(meta.status) };
  const gate = meta.config?.release_gate;
  const acc = report?.accuracy?.roman?.acc;
  const scored = report?.accuracy?.roman?.n;
  const flip = report?.stability?.single_flip_rate;
  const pass = acc != null && flip != null && scored >= (gate.min_items ?? 30) && acc >= gate.min_roman_accuracy && flip <= gate.max_single_flip_rate;
  return { label: pass ? "PASS" : "FAIL", pass, pending: false };
}

async function refreshResults() {
  if (!activeIds.length) return;
  try {
    const entries = await Promise.all(activeIds.map(async (id) => {
      const [meta, result] = await Promise.all([api(`/runs/${id}`), api(`/runs/${id}/report`)]);
      return { id, meta, report: result.report };
    }));
    $("results").hidden = false;
    $("results-body").innerHTML = `<div class="scroll"><table><thead><tr><th>Model</th><th>Status</th><th>Roman accuracy</th><th>Single spelling flips</th><th>Bridge gain</th><th>Release gate</th><th>Report</th></tr></thead><tbody>${entries.map(({ id, meta, report }) => {
      const gate = gateResult(meta, report);
      return `<tr><td><b>${esc(meta.model_label)}</b><small class="table-sub">${meta.n_items} items</small></td><td><span class="status ${esc(meta.status)}">${esc(meta.status)}</span></td><td>${report?.accuracy?.roman?.acc == null ? "—" : `${report.accuracy.roman.acc}%`}</td><td>${report?.stability?.single_flip_rate == null ? "—" : `${report.stability.single_flip_rate}%`}</td><td>${report?.bridge_gain?.effect == null ? "—" : `${report.bridge_gain.effect > 0 ? "+" : ""}${report.bridge_gain.effect} pts`}</td><td class="${gate.pending ? "" : gate.pass ? "gate-pass" : "gate-fail"}"><b>${gate.label}</b><small class="table-sub">Accuracy ≥ ${meta.config?.release_gate?.min_roman_accuracy}%<br/>Flip rate ≤ ${meta.config?.release_gate?.max_single_flip_rate}%<br/>Scored questions ≥ ${meta.config?.release_gate?.min_items ?? 30}</small></td><td><a class="btn feature-action" href="/#/run/${encodeURIComponent(id)}">Detailed report</a></td></tr>`;
    }).join("")}</tbody></table></div>${entries.map(({ id, meta, report }) => `<div><h4>${esc(meta.model_label)} · spelling fingerprint</h4>${renderFingerprint(report)}</div>`).join("")}`;
    if (entries.some(({ meta }) => ["queued", "running"].includes(meta.status))) refreshTimer = setTimeout(refreshResults, 1400);
    else $("message").textContent = "All comparison runs have finished.";
  } catch (e) { showError(e); }
}

const remembered = new URLSearchParams(location.search).get("runs");
if (remembered) {
  activeIds = remembered.split(",").filter((x) => /^[a-f0-9]{6,16}$/i.test(x));
  if (activeIds.length) { $("results").hidden = false; refreshResults(); }
}
Promise.all([loadSamples(), loadModels(), refreshSuites()]).catch(showError);
window.addEventListener("beforeunload", () => clearTimeout(refreshTimer));
