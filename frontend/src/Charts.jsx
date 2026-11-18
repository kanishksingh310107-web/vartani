import { condLabel } from "./api.js";

const COLOR = { native: "#7BE0AD", roman: "#9B8CFF", variants: "#FFC857", typo: "#FF7A59", bridge: "#4CC9F0" };

/** Horizontal bars with 95% interval whiskers and a dashed line at chance. */
export function AccuracyChart({ acc, chance = 25, order }) {
  const keys = (order || ["native", "roman", "asr", "asr_roman", "variants", "typo", "bridge"]).filter((k) => acc[k]);
  const rowH = 44, W = 640, L = 150, R = 20, H = keys.length * rowH + 34;
  const x = (v) => L + ((W - L - R) * v) / 100;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Accuracy by input condition">
      {[0, 25, 50, 75, 100].map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={6} y2={H - 28} className={t === chance ? "chance" : "grid"} />
          <text x={x(t)} y={H - 10} textAnchor="middle" className="tick">{t}%</text>
        </g>
      ))}
      {keys.map((k, i) => {
        const a = acc[k], y = 12 + i * rowH;
        return (
          <g key={k}>
            <text x={L - 12} y={y + 17} textAnchor="end" className="rowlbl">{condLabel(k)}</text>
            <rect x={L} y={y} width={x(a.acc) - L} height={24} rx={6} fill={COLOR[k] || "#9B8CFF"} opacity=".85" />
            <line x1={x(a.lo)} x2={x(a.hi)} y1={y + 12} y2={y + 12} stroke="#fff" strokeWidth="2" />
            <line x1={x(a.lo)} x2={x(a.lo)} y1={y + 6} y2={y + 18} stroke="#fff" strokeWidth="2" />
            <line x1={x(a.hi)} x2={x(a.hi)} y1={y + 6} y2={y + 18} stroke="#fff" strokeWidth="2" />
            <text x={Math.max(x(a.hi), x(a.acc)) + 8} y={y + 17} className="val">{a.acc}%</text>
          </g>
        );
      })}
      <text x={x(chance) + 4} y={10} className="tick chance-lbl">guessing</text>
    </svg>
  );
}

export function Bars({ rows, max = 100, unit = "%" }) {
  return (
    <div className="bars">
      {rows.map((r) => (
        <div className="bar-row" key={r.key}>
          <span className="bar-lbl" title={r.label}>{r.label}</span>
          <span className="bar-track"><i style={{ width: `${Math.min(100, (r.value / max) * 100)}%`, background: r.color || "var(--violet)" }} /></span>
          <span className="bar-val">{r.value}{unit}{r.note ? <small> {r.note}</small> : null}</span>
        </div>
      ))}
    </div>
  );
}
