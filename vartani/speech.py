"""Optional local speech recognition for the speech robustness workflow.

Audio is written to a temporary file and deleted after transcription. Only the
returned transcript is kept if the user chooses to run the benchmark.
"""
from __future__ import annotations

import threading
from pathlib import Path


class SpeechError(RuntimeError):
    pass


_ALLOWED = {"tiny", "base", "small"}
_models: dict = {}
_lock = threading.Lock()


def transcribe(path: Path, lang: str, model_size: str = "base") -> dict:
    if model_size not in _ALLOWED:
        raise SpeechError("Choose the tiny, base, or small speech model.")
    if lang not in {"hi", "bn", "ta"}:
        raise SpeechError("Choose Hindi, Bengali, or Tamil.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise SpeechError("Open Speech check and select Install speech support before transcribing.") from e

    with _lock:
        model = _models.get(model_size)
        if model is None:
            try:
                import ctranslate2
                has_cuda = ctranslate2.get_cuda_device_count() > 0
            except Exception:
                has_cuda = False
            try:
                model = WhisperModel(model_size, device="cuda" if has_cuda else "cpu",
                                     compute_type="float16" if has_cuda else "int8")
            except Exception as e:
                raise SpeechError(f"Could not load Whisper {model_size}: {e}") from e
            _models[model_size] = model
    try:
        segments, info = model.transcribe(str(path), language=lang, beam_size=3, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as e:
        raise SpeechError(f"Could not transcribe this audio: {e}") from e
    if not text:
        raise SpeechError("No speech was recognized. Try a clearer, longer recording.")
    return {"text": text, "language": info.language, "duration": round(float(info.duration or 0), 2),
            "model": f"Whisper {model_size}"}
