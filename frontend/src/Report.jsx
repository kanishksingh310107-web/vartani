import { Fragment, useState } from "react";
import { api, LANGS, condLabel } from "./api.js";
import { AccuracyChart, Bars } from "./Charts.jsx";

const ICON = { good: "●", warn: "●", bad: "●", info: "●" };

export function Verdict({ v, n }) {
  if (!v) return null;
  return (
    <div className={`verdict ${v.level}`}>
      <div><span className="v-eyebrow">Verdict</span><h2>{v.label}</h2><p>{v.summary}</p></div>
      <div className="v-n"><b>{n}</b><span>items tested</span></div>
    </div>
  );
}

export function Findings({ list }) {
  return (
    <ul className="findings">
      {list.map((f, i) => (
        <li key={i} className={f.level}><span className="dot">{ICON[f.level]}</span><div><b>{f.title}</b><p>{f.text}</p></div></li>
      ))}
    </ul>
  );
}

function Stat({ label, value, sub }) {
  return <div className="stat"><span>{label}</span><b>{value ?? "—"}</b>{sub && <small>{sub}</small>}</div>;
}

export function ReportBody({ rep, runId }) {
  const st = rep.stability;
  const frag = (rep.fragility || []).filter((f) => f.n >= 3);
  return (
    <>
      <Verdict v={rep.verdict} n={rep.n_items} />
      <section className="card">
        <h3>Accuracy by input condition</h3>
        <p className="muted">Bars show accuracy; whiskers are 95% confidence intervals; the dashed line is the 25% you would get by guessing.</p>
        <AccuracyChart acc={rep.accuracy} />
      </section>
      <section className="card">
        <h3>What we found</h3>
        <Findings list={rep.findings} />
      </section>
      {st && (
        <section className="card">
          <h3>Answer stability across spellings</h3>
          <div className="stats">
            <Stat label="Any respelling changed the answer" value={`${st.any_flip_rate}%`} sub={`of ${st.n} questions`} />
            <Stat label="One average respelling changed it" value={`${st.single_flip_rate}%`} />
            <Stat label="One typo copy changed it" value={rep.typo_flip_rate != null ? `${rep.typo_flip_rate}%` : null} />
            <Stat label="All spellings agreed" value={`${st.all_agree_rate}%`} />
            <Stat label="Right → wrong" value={`${st.correct_to_incorrect}%`} />
            <Stat label="Wrong → right" value={`${st.incorrect_to_correct}%`} />
          </div>
        </section>
      )}
      {rep.spelling_fingerprint?.profiles?.length > 0 && (
        <section className="card fingerprint">
          <span className="eyebrow">Vartani spelling fingerprint</span>
          <h3>Which writer styles move this model’s answers?</h3>
          <p className="muted">We group the consistent spelling habits used in each generated writer profile and compare its answer with the Roman baseline. “Harmful” means a correct baseline answer became wrong. This is a measured association for your test set, not proof that one habit alone caused the change.</p>
          <div className="scroll"><table>
            <thead><tr><th>Language</th><th>Writer spelling profile</th><th>Questions</th><th>Answer changed</th><th>Harmful flips</th><th>Helpful flips</th></tr></thead>
            <tbody>{rep.spelling_fingerprint.profiles.slice(0, 12).map((p, i) => <tr key={`${p.lang}-${p.habits.join("-")}-${i}`}>
              <td>{LANGS[p.lang] || p.lang}</td><td>{p.label}</td><td>{p.n}</td><td>{p.flip_rate}%</td><td className={p.harmful ? "bad" : "ok"}>{p.harmful}</td><td className={p.helpful ? "ok" : "muted"}>{p.helpful}</td>
            </tr>)}</tbody>
          </table></div>
          <p className="muted">This spelling fingerprint is Vartani’s distinctive view: it connects a consistent person-like typing style with the exact model answer movement, including both failures and recoveries.</p>
        </section>
      )}
      {frag.length > 0 && (
        <section className="card">
          <h3>Which spelling habits break it</h3>
          <p className="muted">Each habit is applied on its own, everywhere it can apply, as a consistent writer would. Bars show the share of applicable questions whose answer changed.</p>
          <Bars rows={frag.map((f) => ({ key: f.rule, label: f.label, value: f.flip_rate, note: `n=${f.n}`, color: "var(--bad)" }))} />
        </section>
      )}
      {rep.margin_bins && (
        <section className="card">
          <h3>Does the model know when it is unsure?</h3>
          <p className="muted">Roman-baseline accuracy split by how confident the model was (gap between its top two options).</p>
          <Bars rows={rep.margin_bins.map((b) => ({ key: b.label, label: `${b.label} confidence`, value: b.acc, note: `n=${b.n}`, color: "var(--violet)" }))} />
        </section>
      )}
      {rep.langs.length > 1 && (
        <section className="card">
          <h3>By language</h3>
          <div className="scroll"><table>
            <thead><tr><th>Language</th>{["native", "roman", "typo", "bridge"].filter((c) => rep.accuracy[c]).map((c) => <th key={c}>{condLabel(c)}</th>)}</tr></thead>
            <tbody>{rep.langs.map((l) => (
              <tr key={l}><td>{LANGS[l] || l}</td>{["native", "roman", "typo", "bridge"].filter((c) => rep.accuracy[c]).map((c) => <td key={c}>{rep.by_lang[l][c] ? `${rep.by_lang[l][c].acc}%` : "—"}</td>)}</tr>
            ))}</tbody>
          </table></div>
        </section>
      )}
      {runId && <ItemExplorer runId={runId} />}
    </>
  );
}

function chipClass(r, c) {
  const a = r.answers[c];
  if (!a) return "chip none";
  if (!r.gold) return "chip";
  return a === r.gold ? "chip ok" : "chip no";
}

function ItemExplorer({ runId }) {
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(null);
  const [onlyFlips, setOnlyFlips] = useState(true);
  if (!items) {
    return (
      <section className="card"><h3>Item explorer</h3>
        <p className="muted">See every question, the exact text sent for each condition, and what the model answered.</p>
        <button className="btn" onClick={() => api(`/runs/${runId}/items`).then(setItems)}>Load items</button>
      </section>
    );
  }
  const conds = [...new Set(items.flatMap((r) => Object.keys(r.answers)))].filter((c) => !c.startsWith("rule:"));
  const shown = items.filter((r) => !onlyFlips || new Set(conds.filter((c) => c !== "native").map((c) => r.answers[c])).size > 1);
  return (
    <section className="card">
      <div className="row between"><h3>Item explorer</h3>
        <label className="check"><input type="checkbox" checked={onlyFlips} onChange={(e) => setOnlyFlips(e.target.checked)} /> only questions whose answer changed</label></div>
      <p className="muted">Green = matches the answer key, red = wrong. Click a row to read the text sent for each condition.</p>
      <div className="scroll"><table className="items">
        <thead><tr><th>#</th><th>Lang</th><th>Key</th>{conds.map((c) => <th key={c}>{condLabel(c).replace("Respelling ", "R")}</th>)}</tr></thead>
        <tbody>
          {shown.map((r) => (
            <Fragment key={r.qid}>
              <tr onClick={() => setOpen(open === r.qid ? null : r.qid)} className="clickable">
                <td>{r.qid + 1}</td><td>{r.lang}</td><td><b>{r.gold || "—"}</b></td>
                {conds.map((c) => <td key={c}><span className={chipClass(r, c)}>{r.answers[c] || "–"}</span></td>)}
              </tr>
              {open === r.qid && (
                <tr><td colSpan={3 + conds.length}>
                  {r.conditions ? Object.entries(r.conditions).filter(([c]) => conds.includes(c) || c.startsWith("rule:")).map(([c, t]) => (
                    <div className="cond-text" key={c}>
                      <b>{condLabel(c)} → <span className={chipClass(r, c)}>{r.answers[c] || "–"}</span>{r.persona?.[c] ? <small> habits: {r.persona[c].join(", ")}</small> : null}</b>
                      <p className="native-text">{t.passage}</p><p className="native-text"><b>{t.question}</b></p>
                      <p className="native-text">{t.options.map((o, i) => `${"ABCD"[i]}) ${o}`).join("   ")}</p>
                    </div>
                  )) : <p className="muted">Imported results contain answers only, not the question text.</p>}
                </td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table></div>
      {!shown.length && <p className="muted">Nothing to show with this filter.</p>}
    </section>
  );
}
