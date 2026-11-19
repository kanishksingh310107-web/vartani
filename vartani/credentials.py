"""Windows account protection for model credentials and atomic profile writes."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile

from .security import CREDENTIAL_FIELDS, credential_values, redact_secrets

BLOBS = "credential_blobs"
_PREFIX = "dpapi-v1:"
_NO_UI = 0x1


class CredentialError(RuntimeError):
    """A message that is safe to return to the app."""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


def _dpapi(data: bytes, *, encrypt: bool) -> bytes:
    if os.name != "nt":
        raise CredentialError("Saving and opening protected model credentials requires Windows.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    blob_ptr = ctypes.POINTER(_Blob)
    fn.argtypes = (blob_ptr, ctypes.c_wchar_p if encrypt else ctypes.c_void_p,
                   blob_ptr, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_ptr)
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data)
    src, dst = _Blob(len(data), ctypes.addressof(buf)), _Blob()
    try:
        if not fn(ctypes.byref(src), None, None, None, None, _NO_UI, ctypes.byref(dst)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        if encrypt:
            ctypes.memset(buf, 0, len(buf))
        if dst.pbData:
            if not encrypt:
                ctypes.memset(dst.pbData, 0, dst.cbData)
            kernel.LocalFree(dst.pbData)


def seal(value: str) -> str:
    try:
        return _PREFIX + base64.b64encode(_dpapi(value.encode("utf-8"), encrypt=True)).decode("ascii")
    except (OSError, ValueError):
        raise CredentialError("Windows could not protect the credential. Check your Windows sign-in and try again.") from None


def unseal(value: str) -> str:
    try:
        if not isinstance(value, str) or not value.startswith(_PREFIX):
            raise ValueError("Unknown protected credential format")
        data = base64.b64decode(value[len(_PREFIX):], validate=True)
        return _dpapi(data, encrypt=False).decode("utf-8")
    except (OSError, ValueError):
        raise CredentialError("Windows could not open a saved credential. Edit the model and re-enter its key or token on this Windows account.") from None


def write_json(path: Path, data, *, replace: bool = True) -> bool:
    """Publish a complete file; unlink the temporary file on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as f:
            pending = Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        if replace:
            pending.replace(path)
        else:
            try:
                if os.name == "nt":
                    pending.rename(path)  # Windows rename fails if the destination exists.
                else:
                    os.link(pending, path)
            except FileExistsError:
                return False
        return True
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def read_profiles(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        raise CredentialError("Vartani could not read saved model settings. Check the settings file and its access permissions.") from None
    if not isinstance(data, list) or any(not isinstance(m, dict) or not isinstance(m.get("id"), str)
                                         or not isinstance(m.get(BLOBS, {}), dict) for m in data):
        raise CredentialError("Vartani could not read the format of saved model settings.")
    return data


def protect_profiles(records: list[dict]) -> list[dict]:
    """Prepare all records before any file is written. A failure leaves the source intact."""
    protected = []
    for m in records:
        blobs = {field: m[BLOBS][field] for field in CREDENTIAL_FIELDS if m.get(BLOBS, {}).get(field)}
        if any(field in m for field in CREDENTIAL_FIELDS) or blobs != m.get(BLOBS, {}):
            for field in CREDENTIAL_FIELDS:
                value = m.get(field)
                if value:
                    if not isinstance(value, str):
                        raise CredentialError("A saved model credential has an invalid format.")
                    blobs[field] = seal(value)
            clean = redact_secrets(m, credential_values(m))
            protected.append({**clean, **({BLOBS: blobs} if blobs else {})})
        else:
            protected.append(m)
    return protected


def import_profiles(source: Path, target: Path) -> bool:
    """Encrypt legacy credentials before publishing a new profile copy."""
    return write_json(target, protect_profiles(read_profiles(source)), replace=False)
