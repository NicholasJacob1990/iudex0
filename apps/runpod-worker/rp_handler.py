"""
RunPod Serverless Handler — Whisper transcription with integrity fields.

Expected input:
  { "input": { "audio": "<url>", "model": "large-v3", "language": "pt",
                "beam_size": 5, "word_timestamps": true } }

Output includes integrity fields (text_length, text_sha256, segments_count)
so the client can detect truncation during transport.
"""

import hashlib
import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional

import requests
import runpod

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Model (lazy-loaded once per cold start)
# ---------------------------------------------------------------------------
DEFAULT_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        logger.info("Loading Whisper model %s on %s (%s)...", DEFAULT_MODEL, DEVICE, COMPUTE_TYPE)
        _whisper_model = WhisperModel(DEFAULT_MODEL, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info("Model loaded successfully.")
    return _whisper_model


# ---------------------------------------------------------------------------
# Audio download
# ---------------------------------------------------------------------------
def _download_audio(url: str) -> str:
    """Download audio to a temp file; return path."""
    logger.info("Downloading audio from %s", url)
    resp = requests.get(url, timeout=600, stream=True)
    resp.raise_for_status()

    suffix = ".wav"
    if "." in url.split("/")[-1].split("?")[0]:
        suffix = "." + url.split("/")[-1].split("?")[0].rsplit(".", 1)[-1]

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    for chunk in resp.iter_content(chunk_size=1024 * 1024):
        tmp.write(chunk)
    tmp.close()
    logger.info("Audio saved to %s (%d bytes)", tmp.name, os.path.getsize(tmp.name))
    return tmp.name


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """RunPod serverless handler — transcribe audio and return result with integrity fields."""
    job_input: Dict[str, Any] = event.get("input", {})

    audio_url = (
        job_input.get("audio")
        or job_input.get("audio_url")
        or job_input.get("input_file")
        or job_input.get("file_url")
    )
    if not audio_url:
        return {"error": "Missing 'audio' URL in input"}

    language = job_input.get("language", "pt")
    beam_size = int(job_input.get("beam_size", 5))
    word_timestamps = bool(job_input.get("word_timestamps", True))
    model_name = job_input.get("model", DEFAULT_MODEL)

    audio_path: Optional[str] = None
    try:
        audio_path = _download_audio(audio_url)
        model = _get_model()

        t0 = time.time()
        segments_gen, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
            vad_filter=True,
        )

        segments_list = []
        words_list = []
        full_text = []
        total_duration = info.duration if hasattr(info, "duration") else 0

        for seg in segments_gen:
            seg_data = {
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            }
            segments_list.append(seg_data)
            full_text.append(seg.text.strip())

            if word_timestamps and seg.words:
                for w in seg.words:
                    words_list.append({
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "word": w.word,
                        "probability": round(w.probability, 4),
                    })

            # Report progress to RunPod dashboard
            if total_duration > 0:
                pct = min(95, int((seg.end / total_duration) * 100))
                runpod.serverless.progress_update(event, f"{pct}%")

        elapsed = time.time() - t0
        final_text = " ".join(full_text)
        text_sha256 = hashlib.sha256(final_text.encode("utf-8")).hexdigest()

        return {
            "text": final_text,
            "text_length": len(final_text),
            "text_sha256": text_sha256,
            "segments": segments_list,
            "segments_count": len(segments_list),
            "words": words_list,
            "language": info.language if hasattr(info, "language") else language,
            "duration": round(total_duration, 2),
            "transcription_time": round(elapsed, 2),
            "model": model_name,
            "device": DEVICE,
        }

    except Exception as exc:
        logger.exception("Transcription failed")
        return {"error": str(exc)}

    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
runpod.serverless.start({"handler": handler})
