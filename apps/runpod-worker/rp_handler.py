"""
RunPod Serverless Handler v3 — Unified Whisper transcription + diarization.

Features:
  - BatchedInferencePipeline (2-4x speedup)
  - Multi-model support (large-v3, large-v3-turbo)
  - Legal hotwords for improved recognition
  - Anti-hallucination (repetition_penalty, ngram blocking)
  - All official worker params supported
  - Generator handler (streaming segments via /stream/{job_id})
  - int8_float16 compute type (35% less VRAM)
  - Optional FFmpeg audio preprocessing
  - SRT/VTT output formats
  - Metadata passthrough
  - Integrated pyannote diarization (no separate endpoint)
  - Optional WhisperX word-level alignment

Expected input:
  { "input": {
      "audio": "<url>",
      "model": "large-v3-turbo",
      "language": "pt",
      "beam_size": 5,
      "word_timestamps": true,
      "diarize": true,
      "num_speakers": null,
      "hotwords": "STJ, STF, agravo, mandado",
      "output_formats": ["json"],
      "preprocess_audio": false,
      "align_words": false,
      "metadata": {}
  }}
"""

import gc
import hashlib
import logging
import os
import subprocess
import tempfile
import time
from typing import Any, Dict, Generator, List, Optional

import requests
import runpod

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8_float16")
DEFAULT_BATCH_SIZE = int(os.environ.get("WHISPER_BATCH_SIZE", "16"))

# Legal vocabulary hotwords (improves recognition of domain-specific terms)
DEFAULT_HOTWORDS = (
    "Tribunal, Ministro, Recurso Especial, STF, STJ, TST, TRF, TRT, TJSP, TJRJ, "
    "agravo, mandado, liminar, exequente, recorrente, recorrido, embargante, embargado, "
    "impetrado, impetrante, litisconsórcio, jurisdição, competência, tutela, "
    "habeas corpus, mandado de segurança, ação civil pública, recurso ordinário, "
    "acórdão, sentença, despacho, petição inicial, contestação, réplica, "
    "CPC, CPP, CLT, CDC, Constituição Federal, artigo, parágrafo, inciso, alínea, "
    "doutor, doutora, excelência, meritíssimo"
)

# Hallucination phrases commonly produced by Whisper on silence/noise
HALLUCINATION_PHRASES = {
    "obrigado por assistir",
    "inscreva-se no canal",
    "legendas pela comunidade",
    "continue assistindo",
    "obrigado pela audiência",
    "transcrição automática",
    "legendado por",
    "tradução e legendagem",
    "música",
    "aplausos",
}

# ---------------------------------------------------------------------------
# Model cache (lazy-loaded, supports hot-swap between models)
# ---------------------------------------------------------------------------
_model_cache: Dict[str, Any] = {}  # model_name -> (WhisperModel, BatchedInferencePipeline)


def _get_model(model_name: str):
    """Get or load a Whisper model + batched pipeline. Supports model hot-swap."""
    global _model_cache

    if model_name in _model_cache:
        return _model_cache[model_name]

    from faster_whisper import WhisperModel

    # Free previous model if loading a different one (save VRAM)
    if _model_cache:
        logger.info("Freeing previous model(s) to load %s...", model_name)
        _model_cache.clear()
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    logger.info("Loading Whisper model %s on %s (%s)...", model_name, DEVICE, COMPUTE_TYPE)
    model = WhisperModel(model_name, device=DEVICE, compute_type=COMPUTE_TYPE)

    # BatchedInferencePipeline for 2-4x speedup
    try:
        from faster_whisper import BatchedInferencePipeline
        batched = BatchedInferencePipeline(model=model)
        logger.info("BatchedInferencePipeline initialized for %s.", model_name)
    except ImportError:
        logger.warning("BatchedInferencePipeline not available; falling back to sequential.")
        batched = None

    _model_cache[model_name] = (model, batched)
    return model, batched


# ---------------------------------------------------------------------------
# Diarization (pyannote) — loaded on demand
# ---------------------------------------------------------------------------
_diarization_pipeline = None


def _get_diarization_pipeline():
    """Load pyannote diarization pipeline (lazy, ~2.5GB VRAM)."""
    global _diarization_pipeline
    if _diarization_pipeline is not None:
        return _diarization_pipeline

    try:
        from pyannote.audio import Pipeline as PyannotePipeline
        import torch

        hf_token = os.environ.get("HF_TOKEN", "")
        logger.info("Loading pyannote/speaker-diarization-community-1...")
        _diarization_pipeline = PyannotePipeline.from_pretrained(
            "pyannote/speaker-diarization-community-1",
            use_auth_token=hf_token if hf_token else None,
        )
        if torch.cuda.is_available():
            _diarization_pipeline.to(torch.device("cuda"))
        logger.info("Diarization pipeline loaded.")
        return _diarization_pipeline
    except Exception as e:
        logger.error("Failed to load diarization pipeline: %s", e)
        return None


def _run_diarization(audio_path: str, num_speakers: Optional[int] = None) -> Optional[List[Dict]]:
    """Run speaker diarization and return list of {start, end, speaker}."""
    pipeline = _get_diarization_pipeline()
    if pipeline is None:
        return None

    try:
        import torch
        kwargs = {}
        if num_speakers is not None and num_speakers > 0:
            kwargs["num_speakers"] = num_speakers

        diarization = pipeline(audio_path, **kwargs)

        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": speaker,
            })
        return segments
    except Exception as e:
        logger.error("Diarization failed: %s", e)
        return None


def _assign_speakers(transcription_segments: List[Dict], diarization_segments: List[Dict]) -> List[Dict]:
    """Assign speaker labels to transcription segments by midpoint overlap."""
    if not diarization_segments:
        return transcription_segments

    for seg in transcription_segments:
        midpoint = (seg["start"] + seg["end"]) / 2
        best_speaker = "UNKNOWN"
        best_overlap = 0

        for d_seg in diarization_segments:
            # Check overlap
            overlap_start = max(seg["start"], d_seg["start"])
            overlap_end = min(seg["end"], d_seg["end"])
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = d_seg["speaker"]

        seg["speaker"] = best_speaker

    return transcription_segments


# ---------------------------------------------------------------------------
# WhisperX word alignment (optional)
# ---------------------------------------------------------------------------
def _align_words(audio_path: str, segments: List[Dict], language: str) -> Optional[List[Dict]]:
    """Use WhisperX for precise word-level timestamps via wav2vec2."""
    try:
        import whisperx
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        align_model, align_metadata = whisperx.load_align_model(
            language_code=language, device=device
        )

        # whisperx expects segments in its own format
        wx_segments = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments]
        import numpy as np
        audio = whisperx.load_audio(audio_path)

        result = whisperx.align(
            wx_segments, align_model, align_metadata, audio, device,
            return_char_alignments=False,
        )

        aligned_words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                aligned_words.append({
                    "start": round(w.get("start", 0), 3),
                    "end": round(w.get("end", 0), 3),
                    "word": w.get("word", ""),
                    "score": round(w.get("score", 0), 4),
                })

        # Free alignment model
        del align_model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return aligned_words
    except Exception as e:
        logger.warning("WhisperX alignment failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Audio download + optional preprocessing
# ---------------------------------------------------------------------------
def _download_audio(url: str) -> str:
    """Download audio to a temp file; return path."""
    logger.info("Downloading audio from %s", url[:200])
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


def _preprocess_audio(input_path: str) -> str:
    """Apply FFmpeg preprocessing: noise reduction, normalization, resample to 16kHz mono."""
    output_path = input_path + ".processed.wav"
    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-af", "highpass=f=80,afftdn=nr=20,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=16000",
            "-ac", "1", "-ar", "16000",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info("Audio preprocessed: %s -> %s", input_path, output_path)
            return output_path
        else:
            logger.warning("FFmpeg preprocessing failed (rc=%d), using original audio", result.returncode)
            return input_path
    except Exception as e:
        logger.warning("FFmpeg preprocessing error: %s, using original audio", e)
        return input_path


# ---------------------------------------------------------------------------
# SRT/VTT formatting
# ---------------------------------------------------------------------------
def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds to VTT timestamp: HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _segments_to_srt(segments: List[Dict]) -> str:
    """Convert segments list to SRT format string."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_srt(seg["start"])
        end = _format_timestamp_srt(seg["end"])
        text = seg["text"]
        if seg.get("speaker"):
            text = f"[{seg['speaker']}] {text}"
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _segments_to_vtt(segments: List[Dict]) -> str:
    """Convert segments list to WebVTT format string."""
    lines = ["WEBVTT\n"]
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_vtt(seg["start"])
        end = _format_timestamp_vtt(seg["end"])
        text = seg["text"]
        if seg.get("speaker"):
            text = f"<v {seg['speaker']}>{text}"
        lines.append(f"\n{i}\n{start} --> {end}\n{text}\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Hallucination filter
# ---------------------------------------------------------------------------
def _is_hallucination(text: str) -> bool:
    """Check if a segment text matches known Whisper hallucination patterns."""
    normalized = text.strip().lower().rstrip(".")
    if normalized in HALLUCINATION_PHRASES:
        return True
    # Repetitive short segments (e.g., "..." repeated)
    if len(normalized) < 3 and normalized not in ("é", "e", "a", "o", "eu"):
        return True
    return False


# ---------------------------------------------------------------------------
# Generator Handler (streaming via /stream/{job_id})
# ---------------------------------------------------------------------------
def handler(event: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
    """RunPod generator handler — yields segments progressively, then final result."""
    job_input: Dict[str, Any] = event.get("input", {})

    # --- Parse audio URL (multiple aliases for compatibility) ---
    audio_url = (
        job_input.get("audio")
        or job_input.get("audio_url")
        or job_input.get("input_file")
        or job_input.get("file_url")
    )
    if not audio_url:
        yield {"error": "Missing 'audio' URL in input"}
        return

    # --- Parse parameters ---
    model_name = job_input.get("model", DEFAULT_MODEL)
    # Normalize model names
    if model_name == "turbo":
        model_name = "large-v3-turbo"
    elif model_name in ("large", "large-v3"):
        model_name = "large-v3"

    language = job_input.get("language", "pt")
    beam_size = int(job_input.get("beam_size", 5))
    word_timestamps = bool(job_input.get("word_timestamps", True))
    batch_size = int(job_input.get("batch_size", DEFAULT_BATCH_SIZE))
    hotwords = job_input.get("hotwords", DEFAULT_HOTWORDS)
    preprocess = bool(job_input.get("preprocess_audio", False))
    diarize = bool(job_input.get("diarize", False))
    num_speakers = job_input.get("num_speakers")
    align_words_flag = bool(job_input.get("align_words", False))
    output_formats = job_input.get("output_formats", ["json"])
    metadata = job_input.get("metadata", {})

    # Official worker params
    initial_prompt = job_input.get("initial_prompt")
    temperature = job_input.get("temperature", 0)
    best_of = int(job_input.get("best_of", 1))
    patience = float(job_input.get("patience", 1.0))
    length_penalty = float(job_input.get("length_penalty", 1.0))
    suppress_tokens = job_input.get("suppress_tokens", [-1])
    condition_on_previous_text = bool(job_input.get("condition_on_previous_text", True))
    compression_ratio_threshold = float(job_input.get("compression_ratio_threshold", 2.4))
    logprob_threshold = float(job_input.get("logprob_threshold", -1.0))
    no_speech_threshold = float(job_input.get("no_speech_threshold", 0.6))

    # Anti-hallucination params
    repetition_penalty = float(job_input.get("repetition_penalty", 1.1))
    no_repeat_ngram_size = int(job_input.get("no_repeat_ngram_size", 3))

    audio_path: Optional[str] = None
    processed_path: Optional[str] = None

    try:
        # --- Download ---
        yield {"stage": "downloading", "progress": 0, "message": "Baixando áudio..."}
        audio_path = _download_audio(audio_url)

        # --- Optional preprocessing ---
        if preprocess:
            yield {"stage": "preprocessing", "progress": 5, "message": "Pré-processando áudio..."}
            processed_path = _preprocess_audio(audio_path)
            transcribe_path = processed_path
        else:
            transcribe_path = audio_path

        # --- Load model ---
        yield {"stage": "loading_model", "progress": 10, "message": f"Carregando modelo {model_name}..."}
        model, batched = _get_model(model_name)

        # --- Transcription params ---
        transcribe_kwargs = dict(
            language=language,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
            ),
            initial_prompt=initial_prompt,
            temperature=temperature,
            best_of=best_of,
            patience=patience,
            length_penalty=length_penalty,
            suppress_tokens=suppress_tokens,
            condition_on_previous_text=condition_on_previous_text,
            compression_ratio_threshold=compression_ratio_threshold,
            log_prob_threshold=logprob_threshold,
            no_speech_threshold=no_speech_threshold,
            repetition_penalty=repetition_penalty,
            no_repeat_ngram_size=no_repeat_ngram_size,
        )

        # Hotwords only supported by BatchedInferencePipeline
        if batched and hotwords:
            transcribe_kwargs["hotwords"] = hotwords

        # --- Transcribe ---
        yield {"stage": "transcribing", "progress": 15, "message": "Transcrevendo..."}
        t0 = time.time()

        if batched:
            transcribe_kwargs["batch_size"] = batch_size
            segments_gen, info = batched.transcribe(transcribe_path, **transcribe_kwargs)
        else:
            # Remove batched-only params
            transcribe_kwargs.pop("hotwords", None)
            transcribe_kwargs.pop("batch_size", None)
            segments_gen, info = model.transcribe(transcribe_path, **transcribe_kwargs)

        segments_list = []
        words_list = []
        full_text = []
        total_duration = info.duration if hasattr(info, "duration") else 0
        hallucinated_count = 0

        for seg in segments_gen:
            text = seg.text.strip()

            # Skip hallucinated segments
            if _is_hallucination(text):
                hallucinated_count += 1
                continue

            seg_data = {
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": text,
            }
            segments_list.append(seg_data)
            full_text.append(text)

            if word_timestamps and seg.words:
                for w in seg.words:
                    words_list.append({
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "word": w.word,
                        "probability": round(w.probability, 4),
                    })

            # Yield segment progressively (streaming)
            if total_duration > 0:
                pct = min(85, 15 + int((seg.end / total_duration) * 70))
            else:
                pct = min(85, 15 + len(segments_list))

            yield {
                "stage": "transcribing",
                "progress": pct,
                "segment": seg_data,
                "segment_index": len(segments_list) - 1,
            }

        transcription_time = time.time() - t0
        logger.info(
            "Transcription done: %d segments, %.1fs, %d hallucinations filtered",
            len(segments_list), transcription_time, hallucinated_count,
        )

        # --- Diarization (if requested) ---
        diarization_data = None
        speakers = []
        if diarize:
            yield {"stage": "diarizing", "progress": 87, "message": "Identificando falantes..."}
            t_diar = time.time()
            diar_segments = _run_diarization(transcribe_path, num_speakers=num_speakers)

            if diar_segments:
                segments_list = _assign_speakers(segments_list, diar_segments)
                speakers = sorted(set(s.get("speaker", "") for s in segments_list if s.get("speaker")))
                diarization_data = {
                    "segments": diar_segments,
                    "num_speakers": len(speakers),
                    "speakers": speakers,
                    "time": round(time.time() - t_diar, 2),
                }
                logger.info("Diarization done: %d speakers, %.1fs", len(speakers), time.time() - t_diar)

                # Also assign speakers to words if we have diarization
                if words_list and diar_segments:
                    for w in words_list:
                        mid = (w["start"] + w["end"]) / 2
                        for d in diar_segments:
                            if d["start"] <= mid <= d["end"]:
                                w["speaker"] = d["speaker"]
                                break

        # --- Word alignment (optional WhisperX) ---
        aligned_words = None
        if align_words_flag and segments_list:
            yield {"stage": "aligning", "progress": 92, "message": "Alinhando palavras..."}
            aligned_words = _align_words(transcribe_path, segments_list, language)
            if aligned_words:
                logger.info("WhisperX alignment: %d words aligned", len(aligned_words))

        # --- Build final result ---
        final_text = " ".join(full_text)
        text_sha256 = hashlib.sha256(final_text.encode("utf-8")).hexdigest()

        result: Dict[str, Any] = {
            "done": True,
            "text": final_text,
            "text_length": len(final_text),
            "text_sha256": text_sha256,
            "segments": segments_list,
            "segments_count": len(segments_list),
            "words": aligned_words if aligned_words else words_list,
            "language": info.language if hasattr(info, "language") else language,
            "language_probability": round(info.language_probability, 4) if hasattr(info, "language_probability") else None,
            "duration": round(total_duration, 2),
            "transcription_time": round(transcription_time, 2),
            "model": model_name,
            "device": DEVICE,
            "compute_type": COMPUTE_TYPE,
            "batch_size": batch_size if batched else 1,
            "hallucinations_filtered": hallucinated_count,
        }

        # Diarization data
        if diarization_data:
            result["diarization"] = diarization_data
            result["has_diarization"] = True
            result["speakers"] = speakers
            result["num_speakers"] = len(speakers)
        else:
            result["has_diarization"] = diarize  # requested but may have failed
            result["speakers"] = []
            result["num_speakers"] = 0

        # Output formats
        if "srt" in output_formats:
            result["srt"] = _segments_to_srt(segments_list)
        if "vtt" in output_formats:
            result["vtt"] = _segments_to_vtt(segments_list)

        # Metadata passthrough
        if metadata:
            result["metadata"] = metadata

        yield {"stage": "completed", "progress": 100, "message": "Transcrição concluída."}
        yield result

    except Exception as exc:
        logger.exception("Handler failed")
        yield {"error": str(exc), "done": True}

    finally:
        # Cleanup temp files
        for path in [audio_path, processed_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Entry point — generator handler with aggregate stream
# ---------------------------------------------------------------------------
runpod.serverless.start({
    "handler": handler,
    "return_aggregate_stream": True,
})
