"""Model connectors. Every backend answers one multiple-choice prompt and returns an `Answer`.

Two real connectors, no simulated one:
  * HFLocal      loads a Hugging Face model and reads the next-token logits of A/B/C/D. This is exactly how the
                 paper's Colab notebook scored answers, so margins are comparable. Needs torch + transformers.
  * OpenAICompat any server that speaks POST /chat/completions: Ollama, LM Studio, vLLM, OpenAI, Groq, ...
                 Needs only an HTTP address. Uses token log-probabilities for the margin when the server returns them.
"""
from __future__ import annotations
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import httpx

from .prompts import LETTERS, format_prompt


@dataclass
class Answer:
    letter: Optional[str]                 # None = the model did not produce A-D
    margin: Optional[float] = None        # gap between the top two options (logit or log-prob units)
    probs: Optional[Dict[str, float]] = None
    raw: str = ""
    ms: int = 0


class BackendError(RuntimeError):
    pass


def _hf_load_error(hf_id: str, error: Exception) -> str:
    detail = str(error)
    low = detail.lower()
    if any(term in low for term in ("gated repo", "gatedrepo", "401 client error", "403 client error", "restricted to", "must have access")):
        return (f"Access to {hf_id} is restricted by Hugging Face: https://huggingface.co/{hf_id}. "
                "First accept the model terms and wait until access is approved. Then enter a Hugging Face read token in this model's settings and retry. "
                "Or choose the public Qwen2.5-3B-Instruct preset to continue without gated access. Vartani cannot bypass model approval.")
    if any(term in low for term in ("out of memory", "not enough memory", "cuda error: out of memory", "can't allocate memory")):
        return (f"Not enough memory to load {hf_id}. Close other model apps or choose a smaller model such as "
                "Qwen2.5-3B-Instruct. CPU mode may use more system RAM and run slowly.")
    if any(term in low for term in ("repository not found", "could not locate the file", "does not appear to have a file", "config.json")):
        return (f"Could not find a compatible model at {hf_id}. Check the exact Hugging Face model ID or local folder path "
                "and confirm that it contains a Transformers model configuration.")
    if "chat template" in low or "apply_chat_template" in low:
        return f"{hf_id} does not provide a compatible chat template, which Vartani needs for its test prompts."
    return f"Model {hf_id} failed while loading or answering: {detail[:900]}"


def _softmax(d: Dict[str, float]) -> Dict[str, float]:
    m = max(d.values())
    e = {k: math.exp(v - m) for k, v in d.items()}
    s = sum(e.values())
    return {k: round(v / s, 5) for k, v in e.items()}


def _margin(d: Dict[str, float]) -> Optional[float]:
    v = sorted(d.values(), reverse=True)
    return round(v[0] - v[1], 4) if len(v) >= 2 else None


_LETTER = re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])")


def parse_letter(text: str) -> Optional[str]:
    """Pull the answer letter out of a short reply: 'B', 'B)', '(B)', 'Answer: B', 'Option B'."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = _LETTER.search(text.upper() if len(text) <= 4 else text)
    return m.group(1) if m else None


class OpenAICompat:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        self.model, self.key, self.timeout = model, api_key, timeout
        self._logprobs_ok = True
        self.parallel = True

    def _post(self, body: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        last = ""
        for attempt in range(4):
            try:
                r = httpx.post(f"{self.base}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            except httpx.ConnectError:
                raise BackendError(f"Cannot reach {self.base}. Is the server running and the address right?")
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                raise BackendError(f"The model server rejected authentication (HTTP {r.status_code}). Check the API key and confirm this account can use model {self.model!r}.")
            last = f"HTTP {r.status_code}: {r.text[:300]}"
            error_text = r.text.lower()
            model_unavailable = (
                "model_not_found" in error_text
                or "model_decommissioned" in error_text
                or "model has been decommissioned" in error_text
                or "model is decommissioned" in error_text
                or "model does not exist" in error_text
                or "model not found" in error_text
                or bool(re.search(r"model.{0,100}(?:not found|does not exist|decommissioned)", error_text))
                or bool(re.search(r"(?:not found|does not exist).{0,100}model", error_text))
            )
            if ("api.groq.com" in self.base and r.status_code in (400, 404)
                    and model_unavailable):
                raise BackendError(f"Groq says model {self.model!r} is unavailable. Check its exact ID in Groq's active model list: https://console.groq.com/docs/models. Provider detail: {r.text[:220]}")
            if r.status_code == 404 and model_unavailable:
                raise BackendError(f"The server is reachable, but model {self.model!r} was not found there. Check the exact model name and make sure it is installed/enabled on that provider.")
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            break
        raise BackendError(last)

    def answer(self, t: dict) -> Answer:
        started = time.time()
        body = {"model": self.model, "messages": [{"role": "user", "content": format_prompt(t)}],
                "temperature": 0, "max_tokens": 8}
        if self._logprobs_ok:
            body.update(logprobs=True, top_logprobs=20)
        try:
            data = self._post(body)
        except BackendError as e:
            # Several requests may be in flight at once. Another worker can
            # discover that Groq rejects logprobs before this worker handles
            # its own 400. Retry based on this request's error, not the shared
            # capability flag, or that race can fail an otherwise valid run.
            if "logprob" in str(e).lower() and ("not supported" in str(e).lower() or "unsupported" in str(e).lower()):
                self._logprobs_ok = False           # this server cannot return log-probs: stop asking
                body.pop("logprobs", None); body.pop("top_logprobs", None)
                data = self._post(body)
            else:
                raise
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        letter = parse_letter(text)
        if letter is None:                           # chatty / reasoning model: give it room, then take the last letter
            body.pop("logprobs", None); body.pop("top_logprobs", None); body["max_tokens"] = 600
            text = ((self._post(body).get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            found = _LETTER.findall(re.sub(r"<think>.*?</think>", "", text, flags=re.S))
            letter = found[-1] if found else None
            return Answer(letter, None, None, text[:200], int((time.time() - started) * 1000))
        margin = probs = None
        lp = ((choice.get("logprobs") or {}).get("content") or [])
        if lp:
            cand: Dict[str, float] = {}
            for tok in lp[0].get("top_logprobs") or []:
                l = (tok.get("token") or "").strip().upper()
                if l in LETTERS and l not in cand:
                    cand[l] = float(tok["logprob"])
            if len(cand) >= 2:
                margin, probs = _margin(cand), _softmax(cand)
        return Answer(letter, margin, probs, text[:200], int((time.time() - started) * 1000))


class HFLocal:
    """Next-token logit scoring, with a one-model cache to limit local memory use."""
    _cache: dict = {}
    _lock = threading.RLock()

    def __init__(self, hf_id: str, device: str = "", token: str = ""):
        self.hf_id, self.device_pref, self.token = hf_id, device, token
        self.parallel = False

    def _load(self):
        with HFLocal._lock:
            if self.hf_id in HFLocal._cache:
                return HFLocal._cache[self.hf_id]
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
            except ImportError as e:
                raise BackendError("Local models need PyTorch and Transformers. Open the model settings in Test lab and select Install local model support.") from e
            dev = self.device_pref or ("cuda" if torch.cuda.is_available() else "cpu")
            dtype = (torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16) if dev == "cuda" else torch.float32
            stale = [key for key in HFLocal._cache if key != self.hf_id]
            for key in stale:
                HFLocal._cache.pop(key, None)
            if stale:
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            try:
                auth = {"token": self.token} if self.token else {}
                tok = AutoTokenizer.from_pretrained(self.hf_id, **auth)
                try:
                    try:
                        model = AutoModelForCausalLM.from_pretrained(self.hf_id, dtype=dtype, **auth)
                    except TypeError:                  # older transformers call it torch_dtype
                        model = AutoModelForCausalLM.from_pretrained(self.hf_id, torch_dtype=dtype, **auth)
                except Exception:
                    if "gemma" not in self.hf_id.lower():
                        raise
                    from transformers import Gemma3ForConditionalGeneration
                    model = Gemma3ForConditionalGeneration.from_pretrained(self.hf_id, dtype=dtype, **auth)
                model = model.to(dev).eval()
            except Exception as e:
                raise BackendError(_hf_load_error(self.hf_id, e)) from e
            ids = {}
            for l in LETTERS:
                enc = tok.encode(l, add_special_tokens=False)
                if len(enc) != 1:
                    raise BackendError(f"{self.hf_id} splits the answer letter {l!r} into several tokens.")
                ids[l] = enc[-1]
            HFLocal._cache[self.hf_id] = (torch, tok, model, ids, dev)
            return HFLocal._cache[self.hf_id]

    def answer(self, t: dict) -> Answer:
        with self._lock:
            try:
                torch, tok, model, ids, dev = self._load()
                started = time.time()
                msgs = [{"role": "user", "content": format_prompt(t)}]
                try:
                    chat = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
                except TypeError:
                    chat = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                inputs = tok(chat, return_tensors="pt", add_special_tokens=False).to(dev)
                with torch.inference_mode():
                    try:
                        out = model(**inputs, logits_to_keep=1)
                    except TypeError:
                        out = model(**inputs)
                    last = out.logits[0, -1, :].float()
                logits = {l: float(last[i]) for l, i in ids.items()}
                if not all(math.isfinite(v) for v in logits.values()):
                    raise BackendError("Model produced non-finite logits (try a different dtype/device).")
                letter = max(logits, key=logits.get)
                return Answer(letter, _margin(logits), _softmax(logits), "", int((time.time() - started) * 1000))
            except BackendError:
                raise
            except Exception as e:
                raise BackendError(_hf_load_error(self.hf_id, e)) from e


def make_backend(cfg: dict):
    if cfg["kind"] == "openai":
        return OpenAICompat(cfg["base_url"], cfg["model"], cfg.get("api_key", ""))
    if cfg["kind"] == "hf":
        return HFLocal(cfg["hf_id"], cfg.get("device", ""), cfg.get("hf_token", ""))
    raise BackendError(f"unknown model kind {cfg['kind']!r}")


def torch_status() -> dict:
    try:
        import torch
        return {"installed": True, "cuda": bool(torch.cuda.is_available())}
    except Exception:
        return {"installed": False, "cuda": False}


PROBE = {"passage": "The sky is blue on a clear day.", "question": "What colour is the sky on a clear day?",
         "options": ["Red", "Blue", "Green", "Black"]}
