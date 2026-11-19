import test from "node:test";
import assert from "node:assert/strict";
import { scoreGate } from "../src/releaseGate.js";

const config = { release_gate: { enabled: true, min_roman_accuracy: 80, max_single_flip_rate: 10, min_items: 25 } };
const report = (scored) => ({ n_items: 100,
  accuracy: { roman: scored === 0 ? null : { acc: 100, n: scored } },
  stability: { single_flip_rate: 0 }
});

test("a comparison rejects high accuracy when too few questions have answer keys", () => {
  const results = [24, 25, 0].map((count) => scoreGate(config, report(count), "done"));
  assert.deepEqual(results.map(({ status }) => status), ["fail", "pass", "fail"]);
  const min = results[0].checks.find((c) => c.label === "Scored questions");
  assert.deepEqual([min.actual, min.target, min.pass], [24, 25, false]);
  assert.equal(results[0].checks.find((c) => c.label === "Roman accuracy").pass, true);
});

test("an unfinished comparison cannot pass on interim results", () => {
  assert.equal(scoreGate(config, report(50), "running").status, "pending");
});
