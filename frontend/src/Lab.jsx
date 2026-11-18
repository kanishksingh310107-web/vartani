import { useEffect, useMemo, useRef, useState } from "react";
import { api, LANGS } from "./api.js";

const EMPTY = { lang: "hi", passage: "", question: "", a: "", b: "", c: "", d: "", answer: "A" };

function TestSet({ items, setItems }) {
  const [tab, setTab] = useState("starter");
  const [samples, setSamples] = useState([]);
  const [q, setQ] = useState(EMPTY);
  const [lang, setLang] = useState("hi");
  const [msg, setMsg] = useState("");
  const file = useRef();
  useEffect(() => { api("/samples").then(setSamples); }, []);
  const load = (sid) => api(`/samples/${sid}`).then((d) => { setItems(d.items.map((i) => ({ ...i, id: i.id }))); setMsg(`Loaded ${d.items.length} items — ${d.title}`); });
  const addOne = async () => {
    const row = { lang: q.lang, passage: q.passage, question: q.question, option_a: q.a, option_b: q.b, option_c: q.c, option_d: q.d, answer: q.answer };
    try {
      const r = await api("/datasets/parse", { json: { text: JSON.stringify([row]), filename: "q.json", lang: q.lang } });
      if (!r.items.length) return setMsg(r.warnings[0] || "Fill in the question and all four options.");
      setItems(r.items); setMsg("Using your question.");
    } catch (e) { setMsg(e.message); }
  };
  const upload = async (f) => {
    if (!f) return;
    try {
      const r = await api("/datasets/parse", { json: { text: await f.text(), filename: f.name, lang } });
      setItems(r.items);
      setMsg(`Read ${r.items.length} items${r.skipped ? `, skipped ${r.skipped}` : ""}.${r.warnings.length ? " " + r.warnings[0] : ""}`);
    } catch (e) { setMsg(e.message); }
  };
  const set = (k) => (e) => setQ({ ...q, [k]: e.target.value });
  return (
    <section className="card">
      <h3><span className="num">1</span> Test set</h3>
      <div className="tabs">
        {[["starter", "Starter sets"], ["one", "Type one question"], ["file", "Upload CSV / JSONL"]].map(([k, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      {tab === "starter" && (
        <div className="row gap wrap">
          {samples.map((s) => <button key={s.id} className="btn" onClick={() => load(s.id)}>{s.title}</button>)}
          <p className="muted full">Six short passages per language, written for demonstration with native and natural Roman text. Good for trying the tool, too small to measure a model — upload your own set for that.</p>
        </div>
      )}
      {tab === "one" && (
        <div className="form">
          <div className="row gap">
            <label>Language<select value={q.lang} onChange={set("lang")}>{Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label>Correct answer<select value={q.answer} onChange={set("answer")}>{"ABCD".split("").map((x) => <option key={x}>{x}</option>)}</select></label>
          </div>
          <label>Passage (optional)<textarea rows={3} value={q.passage} onChange={set("passage")} placeholder="Suraj poorab se ugta hai aur paschim mein doobta hai…" /></label>
          <label>Question<input value={q.question} onChange={set("question")} placeholder="Suraj kahan se ugta hai?" /></label>
          <div className="grid2">{["a", "b", "c", "d"].map((k) => <label key={k}>Option {k.toUpperCase()}<input value={q[k]} onChange={set(k)} /></label>)}</div>
          <button className="btn" onClick={addOne}>Use this question</button>
        </div>
      )}
      {tab === "file" && (
        <div className="form">
          <label>Language of the file (if it has no <code>lang</code> column)<select value={lang} onChange={(e) => setLang(e.target.value)}>{Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <div className="drop" onClick={() => file.current.click()} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files[0]); }}>
            Drop a file here or click to choose<small>columns: passage, question, option_a…option_d, answer (A–D or 1–4), lang. Native or Roman script. Belebele rows work as they are.</small>
          </div>
          <input ref={file} type="file" hidden accept=".csv,.json,.jsonl" onChange={(e) => upload(e.target.files[0])} />
        </div>
      )}
      {msg && <p className="msg">{msg}</p>}
      {items.length > 0 && <p className="ok-line">✓ {items.length} item{items.length > 1 ? "s" : ""} ready ({[...new Set(items.map((i) => LANGS[i.lang]))].join(", ")}; {items.filter((i) => i.native).length} with native text, {items.filter((i) => !i.gold).length} without an answer key)</p>}
    </section>
  );
}

function ModelPicker({ modelId, setModelId }) {
  const [data, setData] = useState({ saved: [], presets: [] });
  const [form, setForm] = useState(null);
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);
  const [checkingId, setCheckingId] = useState(null);
  const refresh = () => api("/models").then(setData);
  useEffect(() => { refresh(); }, []);
  const pick = (p) => { setTest(null); setForm({ ...p, api_key: "" }); };
  const save = async () => {
    const m = await api("/models", { json: form });
    await refresh(); setForm(m); return m;
  };
  const doTest = async () => {
    setBusy(true); setTest(null);
    try {
      const m = await save();
      const result = await api("/models/test", { json: { id: m.id } });
      setTest(result);
      if (result.ok) setModelId(m.id);
      else if (modelId === m.id) setModelId(null);
    }
    catch (e) { setTest({ ok: false, error: e.message }); if (form?.id === modelId) setModelId(null); }
    setBusy(false);
  };
  const selectSaved = async (m) => {
    setCheckingId(m.id); setTest(null);
    try {
      const result = await api("/models/test", { json: { id: m.id } });
      setTest(result);
      if (result.ok) setModelId(m.id);
      else if (modelId === m.id) setModelId(null);
    } catch (e) { setTest({ ok: false, error: e.message }); if (modelId === m.id) setModelId(null); }
    finally { setCheckingId(null); }
  };
  const del = async (id) => { await api(`/models/${id}`, { method: "DELETE" }); if (modelId === id) setModelId(null); refresh(); };
  const f = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <section className="card">
      <h3><span className="num">2</span> Model to test</h3>
      {data.saved.length > 0 && (
        <div className="saved">
          {data.saved.map((m) => (
            <div key={m.id} className={`saved-row ${modelId === m.id ? "on" : ""}`}>
              <span className="radio" /><b>{m.label}</b><small>{m.kind === "hf" ? m.hf_id : m.model}</small>
              <button className="link" disabled={busy || checkingId === m.id} onClick={() => selectSaved(m)}>{checkingId === m.id ? "checking…" : modelId === m.id ? "test again" : "select & test"}</button>
              <button className="link" onClick={(e) => { e.stopPropagation(); pick(m); }}>edit</button>
              <button className="link" onClick={(e) => { e.stopPropagation(); del(m.id); }}>remove</button>
            </div>
          ))}
        </div>
      )}
      {!form && (
        <>
          <p className="muted">{data.saved.length ? "Add another model:" : "Connect a real model. Pick where it runs:"}</p>
          <div className="row gap wrap">{data.presets.map((p) => <button key={p.preset} className="btn" onClick={() => pick(p)}>{p.label}</button>)}</div>
        </>
      )}
      {form && (
        <div className="form">
          <label>Name<input value={form.label || ""} onChange={f("label")} /></label>
          {form.kind === "hf" ? (
            <>
              <label>Hugging Face model ID or local folder path<input value={form.hf_id || ""} onChange={f("hf_id")} placeholder="Qwen/Qwen3-4B or C:\\Models\\my-finetune" /></label>
              <label>Hugging Face read token (only for private or gated models)<input type="password" value={form.hf_token || ""} onChange={f("hf_token")} placeholder={form.has_hf_token ? "saved — leave blank to keep" : "hf_…"} autoComplete="new-password" /></label>
              <label>Run on<select value={form.device || ""} onChange={f("device")}><option value="">Auto detect</option><option value="cpu">CPU</option><option value="cuda">NVIDIA CUDA GPU</option></select></label>
              <small>For local Transformers models. Missing weights download on first use. For gated models, accept the terms and wait for approval, then enter a Hugging Face read token. GGUF files need a model server such as Ollama or LM Studio.</small>
            </>
          ) : (
            <>
              <label>Server address<input value={form.base_url || ""} onChange={f("base_url")} /></label>
              <label>Model name<input value={form.model || ""} onChange={f("model")} /></label>
              <label>API key {form.needs_key ? "" : "(only if the server needs one)"}<input type="password" value={form.api_key || ""} onChange={f("api_key")} placeholder={form.has_key ? "saved — leave blank to keep" : ""} /></label>
            </>
          )}
          {form.hint && <p className="muted">{form.hint}</p>}
          <div className="row gap">
            <button className="btn primary" disabled={busy} onClick={doTest}>{busy ? "Testing…" : "Save and test connection"}</button>
            <button className="btn" onClick={() => { setForm(null); setTest(null); }}>Close</button>
          </div>
          {test && (test.ok
            ? <p className="ok-line">✓ Connected. The model answered “{test.letter}” in {test.ms} ms{test.correct ? " (correct)" : ""}. {test.margin_available ? "Confidence margins are available." : "This server returns no log-probabilities, so confidence margins will be unavailable."}</p>
            : <p className="err-line">✗ {test.error}</p>)}
        </div>
      )}
      {!form && test && <p className={test.ok ? "ok-line" : "err-line"}>{test.ok ? `✓ ${test.letter} · connected in ${test.ms} ms` : `✗ ${test.error}`}</p>}
    </section>
  );
}

function Setup({ items, modelId, nav }) {
  const [cfg, setCfg] = useState({ native: true, variants: 4, variant_mode: "habit", typo: true, bridge: true, scan: false, seed: 42 });
  const [name, setName] = useState("My test");
  const [plan, setPlan] = useState(null);
  const [err, setErr] = useState("");
  const [compareIds, setCompareIds] = useState([]);
  const [compareBusy, setCompareBusy] = useState(false);
  const [gateEnabled, setGateEnabled] = useState(false);
  const [minAccuracy, setMinAccuracy] = useState(60);
  const [maxFlip, setMaxFlip] = useState(20);
  const [minItems, setMinItems] = useState(30);
  const key = useMemo(() => JSON.stringify([items.length, items[0]?.id, cfg]), [items, cfg]);
  useEffect(() => {
    if (!items.length) return setPlan(null);
    const t = setTimeout(() => api("/plan", { json: { items, config: cfg } }).then(setPlan).catch(() => setPlan(null)), 250);
    return () => clearTimeout(t);
  }, [key]);
  const upd = (k, v) => setCfg({ ...cfg, [k]: v });
  const gateValid = () => Number.isFinite(Number(minAccuracy)) && Number(minAccuracy) >= 0 && Number(minAccuracy) <= 100 &&
    Number.isFinite(Number(maxFlip)) && Number(maxFlip) >= 0 && Number(maxFlip) <= 100 && Number.isInteger(Number(minItems)) && Number(minItems) >= 1;
  const go = async () => {
    setErr("");
    if (gateEnabled && !gateValid()) return setErr("Use percentages between 0 and 100 and a minimum of at least one scored question.");
    try { const m = await api("/runs", { json: { name, items, model_id: modelId, config: runConfig } }); nav(`/run/${m.id}`); }
    catch (e) { setErr(e.message); }
  };
  const runConfig = { ...cfg, release_gate: gateEnabled ? { enabled: true, min_roman_accuracy: Number(minAccuracy), max_single_flip_rate: Number(maxFlip), min_items: Number(minItems) } : { enabled: false } };
  const startCompare = async () => {
    if (compareIds.length < 2) return setErr("Select at least two saved models to compare.");
    if (gateEnabled && !gateValid()) return setErr("Use percentages between 0 and 100 and a minimum of at least one scored question.");
    setCompareBusy(true); setErr("");
    const created = [];
    try {
      const models = (await api("/models")).saved;
      for (const id of compareIds) {
        const selected = models.find((m) => m.id === id);
        const run = await api("/runs", { json: { name: `${name} · ${selected?.label || "model"}`, items, model_id: id, config: runConfig } });
        created.push(run.id);
      }
      nav(`/compare/${created.join(",")}`);
    } catch (e) { setErr(created.length ? `${e.message} ${created.length} comparison run(s) did start; find them under Runs.` : e.message); }
    finally { setCompareBusy(false); }
  };
  const hasNative = items.some((i) => i.native);
  return (
    <section className="card">
      <h3><span className="num">3</span> What to test</h3>
      <div className="opts">
        <label className="check"><input type="checkbox" checked={cfg.native && hasNative} disabled={!hasNative} onChange={(e) => upd("native", e.target.checked)} /> Native script <small>(the ceiling; needs native text)</small></label>
        <label className="check"><input type="checkbox" checked={cfg.typo} onChange={(e) => upd("typo", e.target.checked)} /> Keyboard typos</label>
        <label className="check"><input type="checkbox" checked={cfg.bridge} onChange={(e) => upd("bridge", e.target.checked)} /> Bridge to native script <small>(the mitigation: convert before asking)</small></label>
        <label className="check"><input type="checkbox" checked={cfg.scan} onChange={(e) => upd("scan", e.target.checked)} /> Deep scan: test each spelling habit alone <small>(finds what breaks it; more calls)</small></label>
        <div className="row gap wrap">
          <label>Respellings per question: <b>{cfg.variants}</b><input type="range" min="1" max="8" value={cfg.variants} onChange={(e) => upd("variants", +e.target.value)} /></label>
          <label>Respelling style<select value={cfg.variant_mode} onChange={(e) => upd("variant_mode", e.target.value)}>
            <option value="habit">Writers with consistent habits (realistic)</option>
            <option value="paper">Random per word (as in the paper)</option></select></label>
        </div>
      </div>
      <div className="runbar">
        <label>Run name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <div className="plan">{plan ? <><b>{plan.calls.toLocaleString()}</b> model calls for {plan.items} item{plan.items > 1 ? "s" : ""}</> : <span className="muted">Choose a test set to see the cost</span>}</div>
        <button className="btn primary big" disabled={!items.length || !modelId} onClick={go}>Run test</button>
      </div>
      <div className="feature-box">
        <label className="check"><input type="checkbox" checked={gateEnabled} onChange={(e) => setGateEnabled(e.target.checked)} /> Set a release gate</label>
        <p className="muted">Decide what a model must pass before you ship it. Vartani checks the finished run against both limits.</p>
        {gateEnabled && <div className="grid2 gate-fields">
          <label>Minimum Roman accuracy (%)<input type="number" min="0" max="100" value={minAccuracy} onChange={(e) => setMinAccuracy(e.target.value)} /></label>
          <label>Maximum single-respelling flip rate (%)<input type="number" min="0" max="100" value={maxFlip} onChange={(e) => setMaxFlip(e.target.value)} /></label>
          <label>Minimum scored questions<input type="number" min="1" value={minItems} onChange={(e) => setMinItems(e.target.value)} /></label>
        </div>}
      </div>
      <div className="feature-box">
        <h4>Compare models on the same questions</h4>
        <p className="muted">Runs each saved model with the same dataset and spelling settings, then puts the results side by side.</p>
        <ComparePicker selected={compareIds} setSelected={setCompareIds} modelId={modelId} />
        <button className="btn" disabled={compareBusy || !items.length || compareIds.length < 2} onClick={startCompare}>{compareBusy ? "Starting comparison…" : `Compare ${compareIds.length || "selected"} models`}</button>
      </div>
      {!modelId && items.length > 0 && <p className="muted">Choose or connect a model above to start.</p>}
      {err && <p className="err-line">{err}</p>}
    </section>
  );
}

function ComparePicker({ selected, setSelected, modelId }) {
  const [models, setModels] = useState([]);
  useEffect(() => { api("/models").then((d) => setModels(d.saved)).catch(() => {}); }, [modelId]);
  const toggle = (id) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  if (!models.length) return <p className="muted">Save at least two models above to use comparison.</p>;
  return <div className="saved">{models.map((m) => <label className="check" key={m.id}><input type="checkbox" checked={selected.includes(m.id)} onChange={() => toggle(m.id)} /> {m.label} <small>{m.kind === "hf" ? m.hf_id : m.model}</small></label>)}</div>;
}

export default function Lab({ lab, setLab, nav }) {
  return (
    <div className="page">
      <h1 className="h1">Test lab</h1>
      <p className="lead">Three steps: pick questions, connect a real model, choose what to stress. Results appear as a report you can export.</p>
      <TestSet items={lab.items} setItems={(items) => setLab({ ...lab, items })} />
      <ModelPicker modelId={lab.modelId} setModelId={(modelId) => setLab({ ...lab, modelId })} />
      <Setup items={lab.items} modelId={lab.modelId} nav={nav} />
    </div>
  );
}
