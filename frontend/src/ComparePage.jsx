import { useEffect, useState } from "react";
import { api, LANGS } from "./api.js";
import { scoreGate } from "./releaseGate.js";

function ModelGate({ meta, report }) {
  const gate = scoreGate(meta?.config, report, meta?.status);
  if (!gate) return <span className="muted">No release gate set</span>;
  if (gate.status === "pending") return <span className="status queued">Gate waiting for report</span>;
  const sample = gate.checks.find((c) => c.label === "Scored questions");
  if (!sample.pass) return <span className="status failed">Gate failed · {sample.actual ?? 0}/{sample.target} scored</span>;
  return <span className={`status ${gate.status === "pass" ? "done" : "failed"}`}>{gate.status === "pass" ? "Gate passed" : "Gate failed"}</span>;
}

export default function ComparePage({ ids, nav }) {
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true, timer;
    const load = async () => {
      try {
        const result = await Promise.all(ids.split(",").filter(Boolean).map(async (id) => {
          const [meta, result] = await Promise.all([api(`/runs/${id}`), api(`/runs/${id}/report`)]);
          return { id, meta, report: result.report };
        }));
        if (!alive) return;
        setRuns(result);
        if (result.some((r) => ["queued", "running"].includes(r.meta.status))) timer = setTimeout(load, 1200);
      } catch (e) { if (alive) setError(e.message); }
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [ids]);
  const ready = runs.length && runs.every((r) => r.meta.status === "done");
  return <div className="page">
    <div className="row between wrap"><div><h1 className="h1">Model comparison</h1><p className="lead">Same questions and spelling conditions. Compare accuracy, stability and release-gate results before choosing a model.</p></div><button className="btn" onClick={() => nav("runs")}>All runs</button></div>
    {error && <p className="err-line">{error}</p>}
    {!runs.length && !error && <p className="muted">Loading comparison…</p>}
    {!!runs.length && <section className="card">
      <h3>{ready ? "Results" : "Runs in progress"}</h3>
      <div className="scroll"><table>
        <thead><tr><th>Model</th><th>Status</th><th>Roman accuracy</th><th>Single spelling flip</th><th>Bridge gain</th><th>Release gate</th><th></th></tr></thead>
        <tbody>{runs.map(({ id, meta, report }) => <tr key={id}>
          <td><b>{meta.model_label}</b><small className="table-sub">{meta.n_items} items</small></td>
          <td><span className={`status ${meta.status}`}>{meta.status}</span></td>
          <td>{report?.accuracy?.roman?.acc != null ? `${report.accuracy.roman.acc}% (${report.accuracy.roman.n} scored)` : "—"}</td>
          <td>{report?.stability?.single_flip_rate != null ? `${report.stability.single_flip_rate}%` : "—"}</td>
          <td>{report?.bridge_gain?.effect != null ? `${report.bridge_gain.effect > 0 ? "+" : ""}${report.bridge_gain.effect} pts` : "—"}</td>
          <td><ModelGate meta={meta} report={report} /></td>
          <td><button className="link" onClick={() => nav(`run/${id}`)}>Open report</button></td>
        </tr>)}</tbody>
      </table></div>
      {!ready && <p className="muted">This page updates while each model runs. Rows use the same dataset and conditions.</p>}
    </section>}
    {ready && <section className="card"><h3>How to read this</h3><p className="muted">Higher accuracy is useful only when answers also stay stable across spelling styles. Bridge gain is the paired accuracy difference from converting Roman text back to native script. A missing score means the run did not include enough data for that measure.</p></section>}
  </div>;
}
