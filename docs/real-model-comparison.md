# Reproduce a two-model Vartani comparison

The exploratory result uses 18 bundled starter questions: six Hindi, six Bengali, and six Tamil. It checks the evaluation workflow with real models and does not establish their accuracy for any of those languages. The generated variants in that run were not approved by language reviewers. Official benchmark results must wait for the reviewed dataset.

## Input contract for the reviewed benchmark

Supply a UTF-8 JSON object with a `version` and an `items` array using `--dataset`. Each item needs a unique string `id`, `lang` (hi, bn, or ta), `gold` (A, B, C, or D), source and license, `review_status: "approved"`, and `conditions`. Export only variants approved by the reviewers after checking answer alignment and preserving option order. The runner checks schema, duplicate IDs, and recorded approval; it cannot certify human review or licensing on its own.

Each condition uses fields `passage`, `question`, and `options` (four strings). Include `native`, `roman`, and at least one reviewed `var1`/ `var2` / etc. condition per item. The comparison uses these exact texts; it never regenerates the reviewed variants. Optional `typo` and `bridge` conditions can also be supplied when approved. Include questions from all three languages and publish counts and sampling limits with the results.

## Run

Install Vartani's normal Python dependencies and local-model requirements into a separate environment. Download the two model snapshots at exact revisions so their local model folders end in their 40-character revision SHA. Example for the demonstration run:

```powershell
python scripts/compare_local.py --starter-smoke `
  --model HuggingFaceTB/SmolLM2-135M-Instruct 12fd25f77366fa6b3b4b768ec3050bf629380bac <135M-cache-snapshot> `
  --model HuggingFaceTB/SmolLM2-360M-Instruct a10cc1512eabd3dde888204e902eca88bddb4951 <360M-cache-snapshot> `
  --output .\comparison-output
```

The inference runs on CPU with deterministic next-token scoring over A–D. Both models see the same prepared inputs and use the same spelling conditions. Replace `--starter-smoke` with `--dataset <reviewed-manifest.json>` for the official run.

The comparison manifest contains the dataset checksum, prepared input checksum, per-language coverage, exact model revisions, runtime versions, errors, and example answer flips. Each model gets a standalone HTML report plus JSON, JSONL, and CSV. A failed or partial run exits nonzero and is marked incomplete in the manifest. Reported gaps are native minus Roman accuracy, in percentage points.
