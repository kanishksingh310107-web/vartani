"""Small helpers for keeping credentials out of public and persisted metadata."""
from __future__ import annotations


_SECRET_NAMES = {
    "api_key", "hf_token", "token", "access_token", "refresh_token",
    "password", "secret", "authorization", "credential", "credentials",
}
_SECRET_SUFFIXES = ("_api_key", "_key", "_token", "_password", "_secret", "_credential")


def redact_message(message: str, model: dict) -> str:
    """Remove credential values echoed in provider responses and exceptions."""
    for name in ("api_key", "hf_token"):
        value = model.get(name)
        if isinstance(value, str) and value:
            message = message.replace(value, "[redacted]")
    return message


def redact_secrets(value):
    """Return a recursively copied value with secret-bearing fields removed."""
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            name = str(key).casefold()
            if name.startswith("has_"):
                clean[key] = redact_secrets(item)
            elif name in _SECRET_NAMES or name.endswith(_SECRET_SUFFIXES):
                continue
            else:
                clean[key] = redact_secrets(item)
        return clean
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value
