import { useEffect, useState } from "react";
import Home from "./Home.jsx";
import Lab from "./Lab.jsx";
import RunPage from "./RunPage.jsx";
import Evidence from "./Evidence.jsx";
import Runs from "./Runs.jsx";
import ComparePage from "./ComparePage.jsx";

const parse = () => (location.hash.replace(/^#/, "") || "/").split("/").filter(Boolean);

export default function App() {
  const [route, setRoute] = useState(parse());
  const [lab, setLab] = useState({ items: [], modelId: null });
  useEffect(() => {
    const on = () => { setRoute(parse()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const nav = (p) => { location.hash = p; };
  const [a, b] = route;
  const link = (to, label, key) => <a href={`#/${to}`} className={a === key || (!a && key === "") ? "on" : ""}>{label}</a>;
  return (
    <>
      <div className="glow" />
      <div className="app">
        <nav className="nav">
          <a className="brand" href="#/"><span className="logo">व</span>Vartani</a>
          <div className="links">{link("", "Overview", "")}{link("lab", "Test lab", "lab")}<a data-feature-link="true" href="/features.html">Compare &amp; ship</a>{link("runs", "Runs", "runs")}{link("evidence", "Evidence", "evidence")}</div>
        </nav>
        {!a && <Home />}
        {a === "lab" && <Lab lab={lab} setLab={setLab} nav={nav} />}
        {a === "run" && <RunPage key={b} id={b} nav={nav} lab={lab} />}
        {a === "compare" && <ComparePage key={b} ids={b} nav={nav} />}
        {a === "runs" && <Runs nav={nav} />}
        {a === "evidence" && <Evidence />}
        <footer>Vartani (वर्तनी, “spelling”) · results are measurements of a model on your questions, not proof an answer is correct.</footer>
      </div>
    </>
  );
}
