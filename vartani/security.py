"""Keep credential fields and echoed values out of output and metadata."""
from __future__ import annotations

import json
import re
from urllib.parse import quote, quote_plus

CREDENTIAL_FIELDS = ("api_key", "hf_token")
_SECRET_NAMES = {
    "apikey", "hftoken", "token", "accesstoken", "refreshtoken", "password",
    "secret", "authorization", "credential", "credentials", "credentialblobs",
}
_SECRET_SUFFIXES = ("_api_key", "_key", "_token", "_password", "_secret", "_credential", "_credentials")
_PUBLIC_FLAGS = {"has_key", "has_hf_token", "needs_key", "api_key_required"}


def _is_secret(key) -> bool:
    name = str(key).casefold().replace("-", "_")
    return name not in _PUBLIC_FLAGS and (name.replace("_", "") in _SECRET_NAMES or name.endswith(_SECRET_SUFFIXES))


def credential_values(value) -> set[str]:
    """Find legacy credential values before removing their field names."""
    if isinstance(value, dict):
        values = set()
        for key, item in value.items():
            if _is_secret(key) and isinstance(item, str) and item:
                values.add(item)
            else:
                values.update(credential_values(item))
        return values
    if isinstance(value, (list, tuple)):
        return {secret for item in value for secret in credential_values(item)}
    return set()


def _spellings(values):
    return sorted({variant for value in values for variant in (
        value, quote(value, safe=""), quote_plus(value, safe=""),
        json.dumps(value, ensure_ascii=False)[1:-1], json.dumps(value)[1:-1],
    ) if variant}, key=len, reverse=True)


def _redact_text(message: str, spellings) -> str:
    if not spellings:
        return message
    return re.sub("|".join(map(re.escape, spellings)), "[redacted]", message)


def redact_message(message: str, model: dict) -> str:
    return _redact_text(message, _spellings(credential_values(model)))


def redact_secrets(value, secrets=()):
    """Copy a value while dropping private fields and redacting known secret text."""
    spellings = _spellings(secrets)

    def clean(item):
        if isinstance(item, dict):
            return {key: clean(val)
                    for key, val in item.items() if not _is_secret(key)
                    and (key not in _PUBLIC_FLAGS or isinstance(val, bool))}
        if isinstance(item, list):
            return [clean(val) for val in item]
        if isinstance(item, tuple):
            return tuple(clean(val) for val in item)
        if isinstance(item, str):
            return _redact_text(item, spellings)
        return item

    return clean(value)
