import { useEffect, useState } from "react";
import { api, LANGS } from "./api.js";
import { ReportBody } from "./Report.jsx";
import { Bars } from "./Charts.jsx";

export default function Evidence() {
  const [ev, setEv] = useState(null);
  const [sel, setSel] = useState("all");
  useEffect(() => { api("/evidence").then(setEv); }, []);
  if (!ev) return <div className="page"><p className="muted">Loading…</p></div>;
  if (!ev.available) return <div className="page"><p className="err-line">No recorded runs found in data/paper.</p></div>;
  const rep = sel === "all" ? ev.all : ev.models[sel].report;
  const bias = sel === "all" ? null : ev.position_bias[sel];
  return (
    <div className="page">
      <h1 className="h1">Evidence from the study</h1>
      <p className="lead">The paper's Colab experiment, recorded as {ev.n_evals.toLocaleString()} real answers: Qwen2.5-3B, Qwen3-4B and Gemma-3-4B on 200 shared Belebele questions per language
        (Hindi, Bengali, Tamil), each under eight input conditions. This page re-analyses those files with the same code the Test lab uses — now with confidence intervals and exact tests the paper did not have.</p>
      <div className="tabs">
        <button className={sel === "all" ? "on" : ""} onClick={() => setSel("all")}>All three models</button>
        {Object.entries(ev.models).map(([k, m]) => <button key={k} className={sel === k ? "on" : ""} onClick={() => setSel(k)}>{m.label}</button>)}
      </div>
      <ReportBody rep={rep} />
      {bias && (
        <section className="card"><h3>Which letter does the model lean on?</h3>
          <p className="muted">Share of Roman-script answers by option letter. An unbiased guesser would be near 25% each; the answer key is not uniform either (C is correct {rep.gold_dist.C}% of the time).</p>
          <Bars rows={Object.entries(bias).map(([l, v]) => ({ key: l, label: `Option ${l}`, value: v, color: "var(--mid)" }))} />
        </section>
      )}
      <section className="card"><h3>Accuracy by model and language</h3>
        <div className="scroll"><table><thead><tr><th>Model</th><th>Language</th><th>Native</th><th>Roman</th><th>Respelled</th><th>Typos</th><th>Bridged</th></tr></thead>
          <tbody>{ev.grid.filter((g) => sel === "all" || g.model === sel).map((g) => (
            <tr key={g.model + g.lang}><td>{g.label}</td><td>{LANGS[g.lang]}</td><td>{g.native}%</td><td>{g.roman}%</td><td>{(["var1","var2","var3","var4"].reduce((s, k) => s + g[k], 0) / 4).toFixed(1)}%</td><td>{g.typo}%</td><td>{g.bridge}%</td></tr>
          ))}</tbody></table></div>
      </section>
    </div>
  );
}
