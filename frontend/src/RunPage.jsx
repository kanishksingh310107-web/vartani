import { useEffect, useState } from "react";
import { api } from "./api.js";
import { ReportBody } from "./Report.jsx";
import { scoreGate } from "./releaseGate.js";

function NextStep({ report, guidedBatch }) {
  const gain = report.bridge_gain;
  const script = report.script_gap;
  let advice;
  if (gain?.effect > 0) {
    advice = `Native-script conversion raised accuracy by ${gain.effect} points across ${gain.n} paired questions. It corrected ${gain.only_a} answers and worsened ${gain.only_b}. Try the converter and check the gain on fresh examples before changing how you send inputs.`;
  } else if (gain) {
    advice = `Keep the Roman input for now. Conversion changed accuracy by ${gain.effect} points on ${gain.n} paired questions. Try a different model on the same dataset and compare both workflows.`;
  } else {
    advice = "Run a guided comparison with answer keys to measure whether switching models or converting inputs improves accuracy.";
  }
  return <section className="card">
    <h3>What to do next</h3>
    <p>{advice}</p>
    {script?.effect > 0 && !(gain?.effect > 0) && <p>If users can supply native text directly, try that option. The original native text scored {script.effect} points higher on {script.n} paired questions.</p>}
    {guidedBatch && <p className="muted">These figures cover the original Roman inputs. The guided results also measure conversion on changed spellings.</p>}
    <div className="row gap wrap">
      <a className="btn primary" href="/features.html#guided">Compare models and input fixes</a>
      <a className="btn" href="/features.html#fix-input">Try the text converter</a>
    </div>
  </section>;
}

export default function RunPage({ id, nav, lab }) {
  const [meta, setMeta] = useState(null);
  const [rep, setRep] = useState(null);
  const [err, setErr] = useState("");
  const [stopRequested, setStopRequested] = useState(false);
  useEffect(() => {
    let alive = true, timer;
    const tick = async () => {
      try {
        const m = await api(`/runs/${id}`);
        if (!alive) return;
        setMeta(m);
        if (m.status === "queued" || m.status === "running") timer = setTimeout(tick, 1000);
        const r = await api(`/runs/${id}/report`);
        if (alive) setRep(r.report);
      } catch (e) { if (alive) setErr(e.message); }
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [id]);
  if (err) return <div className="page"><p className="err-line">{err}</p></div>;
  if (!meta) return <div className="page"><p className="muted">Loading…</p></div>;
  const running = meta.status === "running" || meta.status === "queued";
  const pct = meta.total_calls ? Math.round((100 * meta.done_calls) / meta.total_calls) : 0;
  const resume = () => api(`/runs/${id}/resume`, { json: { model_id: lab.modelId } }).then(() => location.reload()).catch((e) => setErr(e.message));
  const stop = async () => {
    setStopRequested(true);
    try { await api(`/runs/${id}/cancel`, { method: "POST", json: {} }); }
    catch (e) { setStopRequested(false); setErr(e.message); }
  };
  const gate = scoreGate(meta.config, rep, meta.status);
  return (
    <div className="page">
      <div className="row between wrap">
        <div><h1 className="h1">{meta.name}</h1><p className="muted">Model: {meta.model_label} · {meta.n_items} items · {meta.kind === "import" ? "imported results" : `${meta.total_calls} calls`}</p></div>
        <div className="row gap">
          {["csv", "jsonl", "html"].map((f) => <a key={f} className="btn" href={`/api/runs/${id}/export.${f}`}>Export {f.toUpperCase()}</a>)}
        </div>
      </div>
      {meta.status !== "done" && (
        <section className="card">
          <div className="row between"><b className={`status ${meta.status}`}>{meta.status}</b><span className="muted">{meta.done_items}/{meta.n_items} items · {meta.done_calls}/{meta.total_calls} calls</span></div>
          <div className="progress"><i style={{ width: `${pct}%` }} /></div>
          {running && <button className="btn" disabled={stopRequested} onClick={stop}>{stopRequested ? "Stopping after current call…" : "Stop test"}</button>}
          {running && !stopRequested && <p className="muted">Stopping keeps completed results. The model call already in progress will finish first.</p>}
          {meta.error && <p className="err-line">{meta.error}</p>}
          {!running && meta.config?.guided_batch && <a className="btn" href="/features.html#guided">Start a fresh comparison</a>}
          {!running && !meta.config?.guided_batch && <div className="row gap"><button className="btn primary" disabled={!lab.modelId} onClick={resume}>Resume with selected model</button><span className="muted">Finished items are kept; only the rest is run.</span></div>}
        </section>
      )}
      {gate && <section className={`card release-gate ${gate.status}`}>
        <div className="row between wrap"><div><span className="v-eyebrow">Release gate</span><h3>{gate.status === "pending" ? "Waiting for results" : gate.status === "pass" ? "Ready against your limits" : "Does not meet your limits"}</h3></div>
          {gate.status !== "pending" && <span className={`status ${gate.status === "pass" ? "done" : "failed"}`}>{gate.status.toUpperCase()}</span>}</div>
        <div className="gate-checks">{gate.checks.map((c) => <div key={c.label}><b className={c.pass ? "ok" : gate.status === "pending" ? "muted" : "bad"}>{c.pass ? "✓" : gate.status === "pending" ? "…" : "×"}</b> {c.label}: {c.actual == null ? "not available" : `${c.actual}${c.label === "Scored questions" ? "" : "%"}`} (target {c.op} {c.target}{c.label === "Scored questions" ? "" : "%"})</div>)}</div>
        <p className="muted">This is a configurable project check, not a universal definition of model quality.</p>
      </section>}
      {meta.status === "done" && rep?.n_items > 0 && <NextStep report={rep} guidedBatch={meta.config?.guided_batch} />}
      {rep && rep.n_items > 0 ? <ReportBody rep={rep} runId={id} /> : running && <p className="muted">The report appears as soon as the first item finishes.</p>}
    </div>
  );
}
