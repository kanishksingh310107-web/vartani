export async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.method = init.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.json);
  }
  const r = await fetch("/api" + path, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch { /* ignore */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

export const LANGS = { hi: "Hindi", bn: "Bengali", ta: "Tamil" };
export const condLabel = (c) =>
  ({ native: "Native script", roman: "Roman baseline", typo: "Keyboard typos", bridge: "Bridged to native", asr: "Speech transcript", asr_roman: "ASR → Romanized", variants: "Respellings (avg.)" }[c] ||
    (c.startsWith("var") ? `Respelling ${c.slice(3)}` : c.startsWith("rule:") ? `Habit ${c.slice(5)}` : c));
