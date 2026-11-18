"""Saved model connections (data/user/models.json). API keys stay on this machine, in that file."""
from __future__ import annotations
import json
import uuid
from .config import DATA_DIR

P = DATA_DIR / "user" / "models.json"
PRESETS = [
    {"preset": "ollama", "label": "Ollama (on this computer)", "kind": "openai", "base_url": "http://localhost:11434/v1", "model": "qwen3:4b", "needs_key": False,
     "hint": "Install Ollama, then run: ollama pull qwen3:4b"},
    {"preset": "lmstudio", "label": "LM Studio (on this computer)", "kind": "openai", "base_url": "http://localhost:1234/v1", "model": "", "needs_key": False,
     "hint": "Start the local server in LM Studio and type the model name it shows."},
    {"preset": "groq", "label": "Groq API (GPT-OSS 20B)", "kind": "openai", "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-20b", "needs_key": True,
     "hint": "Add a Groq API key. This current model supports chat completions; confidence margins may be unavailable."},
    {"preset": "openai", "label": "OpenAI", "kind": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "needs_key": True, "hint": "Needs an API key."},
    {"preset": "hf-qwen3", "label": "Qwen3-4B (Hugging Face, local)", "kind": "hf", "hf_id": "Qwen/Qwen3-4B", "needs_key": False,
     "hint": "Same scoring as the paper. Needs PyTorch + a GPU or ~16 GB RAM; downloads ~8 GB once."},
    {"preset": "hf-gemma", "label": "Gemma-3-4B-it (Hugging Face, local)", "kind": "hf", "hf_id": "google/gemma-3-4b-it", "needs_key": False,
     "hint": "Gated model: accept the terms and wait for approval on Hugging Face. Then enter a read token below. If you do not have access, choose the public Qwen2.5-3B-Instruct model."},
    {"preset": "hf-qwen25", "label": "Qwen2.5-3B-Instruct (Hugging Face, local)", "kind": "hf", "hf_id": "Qwen/Qwen2.5-3B-Instruct", "needs_key": False, "hint": "Smallest of the paper's three."},
    {"preset": "hf-custom", "label": "Add my Hugging Face model (runs locally)", "kind": "hf", "hf_id": "", "device": "", "needs_key": False,
     "hint": "Enter a Hugging Face model ID or the path to a downloaded model folder. It downloads weights the first time if needed. Must support AutoModelForCausalLM and a chat template."},
    {"preset": "custom", "label": "Add my API-compatible model", "kind": "openai", "base_url": "", "model": "", "needs_key": False,
     "hint": "Any server that implements OpenAI chat completions, such as a hosted API or a local model server."},
]


def _all() -> list:
    return json.loads(P.read_text(encoding="utf-8")) if P.exists() else []


def list_models(mask: bool = True) -> list:
    out = _all()
    if mask:
        out = [{**{k: v for k, v in m.items() if k not in ("api_key", "hf_token")},
                "has_key": bool(m.get("api_key")), "has_hf_token": bool(m.get("hf_token"))} for m in out]
    return out


def get_model(mid: str) -> dict:
    for m in _all():
        if m["id"] == mid:
            return m
    raise KeyError(mid)


def save_model(m: dict) -> dict:
    ms = _all()
    m = {**m, "id": m.get("id") or uuid.uuid4().hex[:8]}
    old = next((x for x in ms if x["id"] == m["id"]), None)
    if old:
        if not m.get("api_key"):
            m["api_key"] = old.get("api_key", "")
        if not m.get("hf_token"):
            m["hf_token"] = old.get("hf_token", "")
    ms = [x for x in ms if x["id"] != m["id"]] + [m]
    P.parent.mkdir(parents=True, exist_ok=True)
    P.write_text(json.dumps(ms, indent=1), encoding="utf-8")
    return m


def delete_model(mid: str):
    P.write_text(json.dumps([m for m in _all() if m["id"] != mid], indent=1), encoding="utf-8")
