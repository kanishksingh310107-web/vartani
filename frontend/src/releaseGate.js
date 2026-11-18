export function scoreGate(config, report, runStatus) {
  const gate = config?.release_gate;
  if (!gate?.enabled) return null;
  const accuracy = report?.accuracy?.roman?.acc;
  const scored = report?.accuracy?.roman?.n;
  const flips = report?.stability?.single_flip_rate;
  const complete = runStatus == null || runStatus === "done";
  const checks = [
    { label: "Roman accuracy", actual: accuracy, target: gate.min_roman_accuracy, op: ">=", pass: complete && accuracy != null && accuracy >= gate.min_roman_accuracy },
    { label: "Single-respelling flips", actual: flips, target: gate.max_single_flip_rate, op: "<=", pass: complete && flips != null && flips <= gate.max_single_flip_rate },
    { label: "Scored questions", actual: scored, target: gate.min_items ?? 30, op: ">=", pass: complete && scored != null && scored >= (gate.min_items ?? 30) },
  ];
  return { status: !complete ? "pending" : checks.every((c) => c.pass) ? "pass" : "fail", checks };
}
