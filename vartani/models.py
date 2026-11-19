"""Saved model settings and Windows-protected model credentials."""
from __future__ import annotations
import threading
import uuid
from .config import DATA_DIR
from . import credentials
from .credentials import BLOBS, CredentialError
from .security import CREDENTIAL_FIELDS, credential_values, redact_secrets

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


_lock = threading.RLock()
_MODEL_FIELDS = {"id", "preset", "label", "kind", "base_url", "model", "hf_id", "device", "needs_key", "hint"}


def _write(records):
    try:
        credentials.write_json(P, records)
    except OSError:
        raise CredentialError("Vartani could not save model settings. Check disk space and folder permissions, then retry.") from None


def _all() -> list[dict]:
    original = credentials.read_profiles(P)
    try:
        protected = credentials.protect_profiles(original)
        if protected != original:
            _write(protected)
    except CredentialError:
        raise CredentialError("Vartani could not protect the older saved credentials. The original settings were preserved. Check Windows sign-in, disk space and folder permissions, then retry.") from None
    return protected


def _public(m: dict) -> dict:
    blobs = m.get(BLOBS, {})
    return {**redact_secrets(m), "has_key": bool(blobs.get("api_key")),
            "has_hf_token": bool(blobs.get("hf_token"))}


def list_models() -> list[dict]:
    with _lock:
        return [_public(m) for m in _all()]


def get_model(mid: str) -> dict:
    with _lock:
        for m in _all():
            if m["id"] == mid:
                cfg = redact_secrets(m)
                field = "hf_token" if cfg.get("kind") == "hf" else "api_key"
                if sealed := m.get(BLOBS, {}).get(field):
                    cfg[field] = credentials.unseal(sealed)
                return cfg
    raise KeyError(mid)


def require_model_key(cfg: dict):
    if cfg.get("kind") == "openai" and (cfg.get("needs_key") is True or cfg.get("preset") in {"openai", "groq"}) and not cfg.get("api_key"):
        raise CredentialError("This model needs an API key. Edit the model to enter one.")


def save_model(body: dict) -> dict:
    with _lock:
        ms = _all()
        mid = body.get("id") or uuid.uuid4().hex[:8]
        if not isinstance(mid, str):
            raise ValueError("Invalid model ID.")
        old = next((m for m in ms if m["id"] == mid), {})
        blobs = dict(old.get(BLOBS, {}))
        for field in CREDENTIAL_FIELDS:
            value = body.get(field)
            if value is not None and not isinstance(value, str):
                raise ValueError("Enter the credential as text.")
            if body.get(f"clear_{field}") is True:
                if value and value.strip():
                    raise ValueError("Choose either to remove or replace the saved credential.")
                blobs.pop(field, None)
            elif value and value.strip():
                blobs[field] = credentials.seal(value.strip())
        fields = {k: body.get(k, old.get(k)) for k in _MODEL_FIELDS - {"id"} if k in body or k in old}
        secrets = credential_values(body) | {v.strip() for v in credential_values(body)}
        m = {**redact_secrets(fields, secrets), "id": mid, **({BLOBS: blobs} if blobs else {})}
        _write([x for x in ms if x["id"] != mid] + [m])
        return _public(m)


def delete_model(mid: str):
    with _lock:
        # Deleting a broken saved connection does not require decrypting it.
        ms = credentials.read_profiles(P)
        remaining = [m for m in ms if m["id"] != mid]
        if len(remaining) != len(ms):
            _write(credentials.protect_profiles(remaining))
