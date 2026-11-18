import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

export default function Runs({ nav }) {
  const [runs, setRuns] = useState([]);
  const [msg, setMsg] = useState("");
  const f = useRef();
  const load = () => api("/runs").then(setRuns);
  useEffect(() => { load(); }, []);
  const importFiles = async (files) => {
    const fd = new FormData();
    [...files].forEach((x) => fd.append("files", x));
    try { const m = await api("/import", { method: "POST", body: fd }); nav(`/run/${m.id}`); } catch (e) { setMsg(e.message); }
  };
  return (
    <div className="page">
      <h1 className="h1">Your runs</h1>
      <div className="row gap"><button className="btn" onClick={() => f.current.click()}>Import Colab results (.jsonl)</button>
        <input ref={f} type="file" hidden multiple accept=".jsonl" onChange={(e) => importFiles(e.target.files)} /></div>
      {msg && <p className="err-line">{msg}</p>}
      {!runs.length && <section className="card"><p className="muted">No runs yet. Start one in the <a href="#/lab">Test lab</a>, or import result files from the notebook.</p></section>}
      {runs.map((r) => (
        <section className="card run-row" key={r.id}>
          <div onClick={() => nav(`/run/${r.id}`)} className="grow"><b>{r.name}</b><span className="muted"> · {r.model_label} · {r.n_items} items · {new Date(r.created * 1000).toLocaleString()}</span></div>
          <span className={`status ${r.status}`}>{r.status}</span>
          <button className="link" onClick={() => api(`/runs/${r.id}`, { method: "DELETE" }).then(load)}>delete</button>
        </section>
      ))}
    </div>
  );
}
