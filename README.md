# Vartani — test your AI on Roman-script Indian languages

**The problem.** Hundreds of millions of people write Hindi, Bengali and Tamil in English letters ("Hinglish") and spell
the same word many ways. Our study (Colab notebook, `research/`) found that three open models drop from **60.8 % on native
script to 32.9 % on Roman script** (guessing = 25 %), and that **55–64 % of answers change** when only the spelling changes.
A team shipping a chatbot, quiz app or voice assistant has no easy way to find this out before users do.

**What Vartani does.** You bring questions and a real model; Vartani builds the inputs (native, Roman, several consistent
"writers", typos, a bridge back to native script), asks the model, and writes a report: verdict, accuracy with 95 % intervals,
tests against guessing, answer flips, which spelling habits break it, every item inspectable, export to CSV / JSONL / HTML.

**What makes it useful before shipping.** Save reusable benchmark suites and run them against updated models. Compare several
models on the same questions and set a release gate for minimum Roman accuracy, maximum spelling-driven answer flips, and a
minimum number of scored questions. That sample rule keeps the six-question demo from being mistaken for release evidence.
Vartani’s spelling fingerprint links consistent writer-style habits to harmful answer changes and recoveries. It is measured on
your dataset and is reported as an association, not proof that one spelling rule alone caused an answer change. Open
**Compare & ship** from the top navigation to use these features.

**Who it is for:** teams shipping Indic assistants · people choosing between models · researchers replicating the study.

## Run it

On 64-bit Windows, run **VartaniSetup-x64.exe** and open Vartani from the Start menu. It includes Python and the core app. See [Windows setup and build instructions](docs/windows-build.md) for profile migration and troubleshooting.

```
python main.py
```
First run creates `.venv` and installs six small packages (~1 min). Needs Python 3.10+. **No Node.js** (the UI is pre-built).
Then open the address it prints → **Test lab**: pick a test set, connect a model, run.

Models (nothing is simulated — there is no demo mode):
| Option | Needs |
|---|---|
| Ollama / LM Studio / vLLM / OpenAI / Groq / any `/chat/completions` server | just the address (+ key if hosted) |
| Hugging Face local (Qwen3-4B, Gemma-3-4B, Qwen2.5-3B) — same logit scoring as the paper | `pip install -r requirements-local-models.txt`, GPU or ~16 GB RAM |

**Speech-to-text robustness (optional):** open **Speech check**, select **Install speech support**, then choose a starter question and record or upload a short clip. First transcription downloads the chosen Whisper model. Later transcriptions reuse the cached model. Vartani compares the typed Roman baseline with the raw transcript and a native-to-Roman ITRANS version. Audio is deleted after transcription. Only the reviewed text is stored in the run.

**Windows users:** a bundled installer (no user-side Python installation) can be created with the steps in [`docs/windows-build.md`](docs/windows-build.md). It stores models, settings, logs, and runs in `%LOCALAPPDATA%\Vartani`, outside the installed app folder.

To add your own model, open the **Test lab** and choose **Add my Hugging Face model (runs locally)** for a compatible Transformers model ID or downloaded model folder. Select **Install local model support** if needed. Testing downloads missing model weights and reuses cached files. Choose **Add my API-compatible model** for a hosted or local server. GGUF files require a separate model server.

Gated Hugging Face models such as Gemma need access approved on the model page. From this project folder, authenticate once with `.\.venv\Scripts\hf.exe auth login`, then select and test the model again. A saved model is selectable for runs only after its connection test succeeds. **Run test** also needs a loaded question set: click a starter set or upload a CSV / JSONL file in step 1.

Your own data: CSV / JSONL with `passage, question, option_a..option_d, answer, lang` (native **or** Roman; Belebele rows work as is).
Notebook result files (`*.jsonl`) can be imported on the **Runs** page.

## How it works (mini-explainer)
- `perturb.py` builds conditions per question: `native`, `roman`, `var1..K`, `typo`, `bridge`, optional `rule:*` (deep scan).
  *Why habit-style variants:* a real person spells consistently ("aa"→"a" everywhere), unlike the paper's random per-word edits;
  the paper's generator is kept as "paper" mode for replication. Identical texts reuse one answer so "no change" is never counted as stability.
- `backends.py` — Hugging Face (next-token logits for A/B/C/D, exactly the notebook) or any OpenAI-compatible server (uses log-probs for the confidence margin when offered).
- `runner.py` — background job, results appended per item to `data/runs/<id>/rows.jsonl`, resumable, cancellable, parallel for HTTP models.
- `analysis.py` — Wilson intervals, exact binomial test vs 25 %, exact McNemar for paired comparisons (native vs Roman, bridge vs Roman), per-single-respelling flip rate (fair against the one-typo rate), consensus-vote and agreement analysis, verdict rubric.
- `evidence.py` — re-analyses the 1,800 recorded rows in `data/paper/` with the same code. Reproduces the paper's numbers exactly; adds what it lacked (intervals, tests, constant-guess baseline 33.5 %, majority vote gives no gain, confidence only informative in the top quartile).

**Verdict rubric** (shown, not hidden): *Not reliable* if Roman accuracy is not significantly above guessing; *Fragile* if ≥ 40 % of questions flip; *Shaky* if ≥ 25 % flip or the native gap ≥ 20 points; *Mostly robust* if < 15 % flip and gap < 8; otherwise *Some sensitivity*.

## Limits (read before quoting numbers)
- The bridge (Roman→native) is rule-based: ITRANS + final-vowel fix + ~200 Hindi function words. Bengali and Tamil conversion is rough. The report measures whether it helps *your* model; a stronger transliterator can replace `scripts.bridge`.
- Starter sets are 6 hand-written passages per language: for trying the tool, not for measuring a model.
- The built-in Roman for native-only data is the paper's ITRANS Romanization, which is not how people type; supply real Roman text when you have it.
- Margins are unavailable from servers that return no log-probabilities (e.g. Groq).
- On Windows, saved API keys and Hugging Face tokens are encrypted for your Windows account. Vartani upgrades older saved keys on startup. If you move the profile to another computer or account, re-enter the keys there. Saving credentials is available on Windows; connections that do not need a key still work from source on other platforms.

For a reproducible comparison of two local models, see [real-model comparison](docs/real-model-comparison.md).

## Tests
`pip install pytest` then `python -m pytest` — checks that the paper's numbers reproduce, the statistics, perturbations, and a full run against a stub OpenAI-compatible server.
Rebuild the UI after editing `frontend/`: `cd frontend && npm install && npm run build`.

`research/` holds your original notebook, paper and guide, byte-for-byte unchanged.
