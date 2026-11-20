"""Optional local speech recognition for the speech robustness workflow.

Audio is written to a temporary file and deleted after transcription. Only the
returned transcript is kept if the user chooses to run the benchmark.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path


class SpeechError(RuntimeError):
    pass


_ALLOWED = {"tiny", "base", "small"}
_models: dict = {}
_cpu_fallback: set[str] = set()
_lock = threading.Lock()


def _recognize(whisper_model, path: Path, lang: str, size: str, device: str):
    with _lock:
        key = (size, device)
        if key not in _models:
            _models[key] = whisper_model(size, device=device, compute_type="float16" if device == "cuda" else "int8")
        model = _models[key]
    segments, info = model.transcribe(str(path), language=lang, beam_size=3, vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip(), info


def transcribe(path: Path, lang: str, model_size: str = "base") -> dict:
    if model_size not in _ALLOWED:
        raise SpeechError("Choose the tiny, base, or small speech model.")
    if lang not in {"hi", "bn", "ta"}:
        raise SpeechError("Choose Hindi, Bengali, or Tamil.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise SpeechError("Open Speech check and select Install speech support before transcribing.") from e

    try:
        import ctranslate2
        has_cuda = model_size not in _cpu_fallback and ctranslate2.get_cuda_device_count() > 0
    except Exception:
        has_cuda = False
    try:
        if has_cuda:
            try:
                text, info = _recognize(WhisperModel, path, lang, model_size, "cuda")
            except (RuntimeError, OSError):
                with _lock:
                    _models.pop((model_size, "cuda"), None)
                    _cpu_fallback.add(model_size)
                text, info = _recognize(WhisperModel, path, lang, model_size, "cpu")
        else:
            text, info = _recognize(WhisperModel, path, lang, model_size, "cpu")
    except Exception as e:
        raise SpeechError(f"Could not transcribe this audio: {e}") from e
    if not text:
        raise SpeechError("No speech was recognized. Try a clearer, longer recording.")
    return {"text": text, "language": info.language, "duration": round(float(info.duration or 0), 2),
            "model": f"Whisper {model_size}"}


def transcribe_for_app(path: Path, lang: str, model_size: str = "base") -> dict:
    """Run Whisper separately from PyTorch and the embedded app on Windows."""
    from .config import PACKAGED, ROOT
    if os.name != "nt" or not PACKAGED:
        return transcribe(path, lang, model_size)
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    try:
        proc = subprocess.run(
            [str(executable), "-E", "-s", "-B", "-m", "vartani.speech_worker", str(path), lang, model_size],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", timeout=600, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise SpeechError("Whisper did not finish in time. Check your connection for a first download, or try a smaller model.") from None
    except OSError:
        raise SpeechError("Vartani could not start speech recognition. Restart Vartani and retry.") from None
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        if proc.returncode == 0 and isinstance(data.get("result"), dict):
            return data["result"]
        if proc.returncode == 1 and isinstance(data.get("error"), str):
            raise SpeechError(data["error"])
    except (ValueError, IndexError, AttributeError):
        pass
    raise SpeechError("Speech recognition stopped unexpectedly. Restart Vartani and retry.")
