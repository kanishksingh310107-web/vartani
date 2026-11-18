import { useEffect, useState } from "react";
import { api } from "./api.js";

export default function Home() {
  const [ev, setEv] = useState(null);
  useEffect(() => { api("/evidence").then(setEv).catch(() => {}); }, []);
  const a = ev?.all?.accuracy;
  const flips = ev ? Object.values(ev.models).map((m) => m.report.stability.any_flip_rate) : [];
  return (
    <div className="page">
      <header className="hero">
        <span className="eyebrow">For teams building AI for India</span>
        <h1>Will your AI still get it right when people type the way they text?</h1>
        <p>Hundreds of millions of people write Hindi, Bengali and Tamil in English letters — and spell the same word a dozen ways.
          Vartani tests whether a model still answers correctly, and consistently, when the script or the spelling changes.</p>
        <div className="row gap">
          <a className="btn primary" href="#/lab">Test a model</a>
          <a className="btn" href="#/evidence">See the evidence</a>
        </div>
      </header>

      {a && (
        <section className="proof">
          <div className="proof-main">
            <div className="big-pair">
              <div><b className="ok">{a.native.acc}%</b><span>native script</span></div>
              <i>→</i>
              <div><b className="bad">{a.roman.acc}%</b><span>Roman script</span></div>
            </div>
            <p>Same questions, same three open models, same Hindi / Bengali / Tamil passages. Guessing scores 25%.</p>
          </div>
          <div className="proof-side">
            <div><b>{Math.min(...flips)}–{Math.max(...flips)}%</b><span>of questions changed answer when only the spelling changed</span></div>
            <div><b>{ev.n_evals.toLocaleString()}</b><span>real model answers behind these numbers (recorded in the paper's Colab study)</span></div>
          </div>
        </section>
      )}

      <section className="three">
        <article className="card"><h3>If you ship a chatbot or quiz app</h3>
          <p>Upload a few dozen real questions. Get a pass/fail style report: accuracy by script, how often answers flip, and which spelling habits break your bot — before your users find out.</p></article>
        <article className="card"><h3>If you are choosing a model</h3>
          <p>Run the same test on two or three candidates (local or hosted) and compare. A model that looks fine on native-script benchmarks can be a coin flip on Roman input.</p></article>
        <article className="card"><h3>If you do research</h3>
          <p>Reproduce the study on a new model or language in one run. Results use the notebook's JSONL format, with confidence intervals and exact tests added.</p></article>
      </section>

      <section className="card">
        <h3>How a test works</h3>
        <ol className="steps">
          <li><b>Bring questions.</b> A CSV/JSONL of passages with four options, or one question typed in the box. Native or Roman script.</li>
          <li><b>We build the inputs.</b> Native, Roman, several "writers" who spell consistently their own way, keyboard typos, and a version converted back to native script.</li>
          <li><b>Your model answers each one.</b> A real model — local Hugging Face, Ollama, LM Studio, or any OpenAI-compatible API. Nothing is simulated.</li>
          <li><b>You get a report.</b> Verdict, accuracy with confidence intervals, answer flips, fragile spelling habits, every item to inspect, exportable.</li>
        </ol>
      </section>
      <section className="note"><b>Honest by design.</b> Reports show the uncertainty, test every result against guessing, and say when a
        mitigation did not help. The built-in script converter is rule-based and approximate, so the report measures whether it helps <i>your</i> model rather than assuming it does.</section>
    </div>
  );
}
