"""
RunPod Serverless client — pipeline híbrido de transcrição + diarização.

Arquitetura:
  1. Endpoint de transcrição (worker oficial faster-whisper) → texto + segments
  2. Endpoint de diarização (custom pyannote worker, opcional) → speaker labels
  3. Merge dos resultados

Endpoints RunPod:
  POST /v2/{endpoint_id}/run       → submete job
  GET  /v2/{endpoint_id}/status/{id} → polling de status
  POST /v2/{endpoint_id}/cancel/{id} → cancela job

Worker oficial espera:
  { "input": { "audio": "<url>", "model": "turbo", "language": "pt", ... } }

Alguns handlers customizados em RunPod usam chaves diferentes para o áudio
(ex.: `audio_url`, `input_file`, `file_url`). Para compatibilidade, enviamos
aliases com a mesma URL.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

RUNPOD_BASE = "https://api.runpod.ai/v2"


@dataclass
class RunPodResult:
    run_id: str
    status: str  # "IN_QUEUE", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED"
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


@dataclass
class RunPodClient:
    """Async HTTP client para RunPod Serverless API.

    Suporta dois endpoints:
    - endpoint_id: transcrição (worker oficial faster-whisper)
    - diarize_endpoint_id: diarização (custom pyannote worker, opcional)
    """

    api_key: str = field(default_factory=lambda: os.getenv("RUNPOD_API_KEY", ""))
    endpoint_id: str = field(default_factory=lambda: os.getenv("RUNPOD_ENDPOINT_ID", ""))
    diarize_endpoint_id: str = field(
        default_factory=lambda: os.getenv("RUNPOD_DIARIZE_ENDPOINT_ID", "")
    )
    poll_interval: float = 5.0
    timeout: float = 3600.0  # 1h max
    completed_output_grace_seconds: float = field(
        default_factory=lambda: float(os.getenv("RUNPOD_COMPLETED_OUTPUT_GRACE_SECONDS", "20"))
    )

    def __post_init__(self):
        if not self.api_key or not self.endpoint_id:
            logger.warning("RunPod API key or endpoint ID not configured")

    def _url(self, endpoint_id: str) -> str:
        return f"{RUNPOD_BASE}/{endpoint_id}"

    @property
    def _base_url(self) -> str:
        return self._url(self.endpoint_id)

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.endpoint_id)

    @property
    def diarize_configured(self) -> bool:
        return bool(self.api_key and self.diarize_endpoint_id)

    # ── Transcrição (worker oficial faster-whisper) ──────────────────────

    def _with_audio_aliases(self, input_data: Dict[str, Any], audio_url: str) -> Dict[str, Any]:
        """Adiciona aliases de áudio para compatibilidade com handlers customizados."""
        normalized = (audio_url or "").strip()
        if not normalized:
            raise ValueError("audio_url vazio ao montar payload do RunPod")

        aliases = (
            "audio",
            "audio_url",
            "url",
            "input_audio",
            "input_file",
            "audio_file",
            "file_url",
        )
        for key in aliases:
            input_data[key] = normalized
        return input_data

    async def submit_job(
        self,
        audio_url: str,
        language: str = "pt",
        diarization: bool = True,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
        initial_prompt: Optional[str] = None,
        word_timestamps: bool = True,
    ) -> RunPodResult:
        """Submete job de transcrição ao RunPod (worker oficial faster-whisper).

        Args:
            audio_url: URL pública do arquivo de áudio
            language: Código do idioma (ex: "pt")
            diarization: Se True e diarize endpoint configurado, roda diarização depois
            min_speakers: Dica de número mínimo de falantes (usado na diarização)
            max_speakers: Dica de número máximo de falantes (usado na diarização)
            initial_prompt: Prompt inicial para guiar Whisper
            word_timestamps: Ativar timestamps por palavra
        """
        input_data: Dict[str, Any] = {
            "audio": audio_url.strip(),
            "model": "turbo",
            "language": language,
            "word_timestamps": word_timestamps,
            "enable_vad": True,
        }

        if initial_prompt:
            input_data["initial_prompt"] = initial_prompt

        payload: Dict[str, Any] = {"input": input_data}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/run",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info("RunPod transcription job submitted: %s (status=%s)", data.get("id"), data.get("status"))
        return RunPodResult(
            run_id=data["id"],
            status=data.get("status", "IN_QUEUE"),
        )

    # ── Diarização (custom pyannote worker) ──────────────────────────────

    async def submit_diarize_job(
        self,
        audio_url: str,
        hf_token: Optional[str] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> RunPodResult:
        """Submete job de diarização ao endpoint pyannote separado."""
        if not self.diarize_configured:
            raise RuntimeError("RUNPOD_DIARIZE_ENDPOINT_ID not configured")

        token = hf_token or os.getenv("HUGGINGFACE_ACCESS_TOKEN", "")
        input_data: Dict[str, Any] = {
            "diarize": True,
            "huggingface_access_token": token,
        }
        input_data = self._with_audio_aliases(input_data, audio_url)
        if min_speakers is not None:
            input_data["min_speakers"] = min_speakers
        if max_speakers is not None:
            input_data["max_speakers"] = max_speakers

        payload: Dict[str, Any] = {"input": input_data}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._url(self.diarize_endpoint_id)}/run",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info("RunPod diarize job submitted: %s", data.get("id"))
        return RunPodResult(
            run_id=data["id"],
            status=data.get("status", "IN_QUEUE"),
        )

    # ── Status / Cancel / Poll ───────────────────────────────────────────

    async def get_status(self, run_id: str, endpoint_id: Optional[str] = None) -> RunPodResult:
        """Consulta status de um job."""
        url = self._url(endpoint_id) if endpoint_id else self._base_url
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{url}/status/{run_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return RunPodResult(
            run_id=data.get("id", run_id),
            status=data.get("status", "UNKNOWN"),
            output=data.get("output"),
            error=data.get("error"),
            execution_time_ms=data.get("executionTime"),
        )

    async def cancel_job(self, run_id: str, endpoint_id: Optional[str] = None) -> bool:
        """Cancela um job. Retorna True se aceito."""
        url = self._url(endpoint_id) if endpoint_id else self._base_url
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{url}/cancel/{run_id}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                logger.info("RunPod job cancelled: %s", run_id)
                return True
        except httpx.HTTPStatusError as e:
            logger.warning("RunPod cancel failed for %s: %s", run_id, e)
            return False

    async def poll_until_complete(
        self,
        run_id: str,
        endpoint_id: Optional[str] = None,
        on_progress: Optional[Callable[[str, int, str], Coroutine]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> RunPodResult:
        """Faz polling até o job completar ou falhar."""
        elapsed = 0.0
        last_status = "IN_QUEUE"
        completed_without_output_since: Optional[float] = None

        while elapsed < self.timeout:
            if cancel_check and cancel_check():
                await self.cancel_job(run_id, endpoint_id)
                return RunPodResult(run_id=run_id, status="CANCELLED")

            result = await self.get_status(run_id, endpoint_id)

            if result.status != last_status:
                last_status = result.status
                logger.info("RunPod %s: %s (%.1fs)", run_id, result.status, elapsed)

            if result.status == "COMPLETED":
                # Alguns workers/reporters podem marcar COMPLETED alguns segundos antes
                # de o `output` ficar visível no status final.
                if result.output is None and not result.error:
                    if completed_without_output_since is None:
                        completed_without_output_since = elapsed
                        logger.warning(
                            "RunPod %s completed sem output; aguardando até %.1fs por consistência...",
                            run_id,
                            self.completed_output_grace_seconds,
                        )
                    grace_elapsed = elapsed - completed_without_output_since
                    if grace_elapsed < self.completed_output_grace_seconds:
                        if on_progress:
                            await on_progress("transcription", 95, "RunPod finalizando resultado...")
                        step = min(2.0, self.poll_interval)
                        await asyncio.sleep(step)
                        elapsed += step
                        continue
                    logger.error(
                        "RunPod %s completed sem output após %.1fs de espera.",
                        run_id,
                        self.completed_output_grace_seconds,
                    )
                    return RunPodResult(
                        run_id=run_id,
                        status="FAILED",
                        error="RunPod completou sem output",
                    )
                if on_progress:
                    await on_progress("transcription", 100, "Transcrição concluída (RunPod)")
                return result

            if result.status == "FAILED":
                logger.error("RunPod job %s failed: %s", run_id, result.error)
                return result

            if result.status == "CANCELLED":
                return result

            if on_progress:
                if result.status == "IN_QUEUE":
                    await on_progress("transcription", 5, "Aguardando worker RunPod...")
                elif result.status == "IN_PROGRESS":
                    pct = min(90, 10 + int(elapsed / 10))
                    await on_progress("transcription", pct, "Transcrevendo no RunPod...")

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        logger.error("RunPod job %s timed out after %.0fs", run_id, self.timeout)
        await self.cancel_job(run_id, endpoint_id)
        return RunPodResult(
            run_id=run_id,
            status="FAILED",
            error=f"Timeout após {self.timeout:.0f}s",
        )

    # ── Pipeline completo (transcrição + diarização opcional) ────────────

    async def transcribe_and_diarize(
        self,
        audio_url: str,
        language: str = "pt",
        diarization: bool = True,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
        initial_prompt: Optional[str] = None,
        on_progress: Optional[Callable[[str, int, str], Coroutine]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> RunPodResult:
        """Pipeline completo: transcrição + diarização opcional (segundo estágio).

        1. Submete transcrição ao worker oficial
        2. Se diarização pedida e endpoint configurado, submete diarização em paralelo
        3. Merge dos resultados
        """
        # 1. Transcrição
        transcribe_result = await self.submit_job(
            audio_url=audio_url,
            language=language,
            diarization=diarization,
            initial_prompt=initial_prompt,
        )

        # Poll transcrição
        final = await self.poll_until_complete(
            run_id=transcribe_result.run_id,
            on_progress=on_progress,
            cancel_check=cancel_check,
        )

        if final.status != "COMPLETED":
            return final

        # 2. Diarização (se pedida e endpoint configurado)
        if diarization and self.diarize_configured:
            if on_progress:
                await on_progress("diarization", 0, "Iniciando diarização...")

            try:
                dia_result = await self.submit_diarize_job(
                    audio_url=audio_url,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )
                dia_final = await self.poll_until_complete(
                    run_id=dia_result.run_id,
                    endpoint_id=self.diarize_endpoint_id,
                    cancel_check=cancel_check,
                )
                if dia_final.status == "COMPLETED" and dia_final.output:
                    # Merge diarização no output da transcrição
                    final.output["diarization"] = dia_final.output.get("diarization")
                    if on_progress:
                        await on_progress("diarization", 100, "Diarização concluída")
                else:
                    logger.warning("Diarization failed, returning transcription only: %s", dia_final.error)
            except Exception as e:
                logger.warning("Diarization error, returning transcription only: %s", e)
        elif diarization and not self.diarize_configured:
            logger.info("Diarization requested but RUNPOD_DIARIZE_ENDPOINT_ID not set — skipping")

        return final


# ── Extração de resultados ───────────────────────────────────────────────


def _merge_diarization(segments: list, diarization: dict) -> list:
    """Merge diarization speaker labels into whisper segments.

    The diarization worker returns:
      {"segments": [{"start": 0.0, "end": 1.5, "speaker": 0}, ...], "num_speakers": N}

    We assign a speaker to each whisper segment based on temporal overlap.
    """
    dia_segs = diarization.get("segments", [])
    if not dia_segs:
        return segments

    merged = []
    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        seg_mid = (seg_start + seg_end) / 2

        # Find diarization segment that covers the midpoint
        best_speaker = None
        for ds in dia_segs:
            if ds["start"] <= seg_mid <= ds["end"]:
                best_speaker = ds["speaker"]
                break

        new_seg = {**seg}
        if best_speaker is not None:
            new_seg["speaker"] = f"SPEAKER_{best_speaker:02d}"
        merged.append(new_seg)

    return merged


def _parse_json_if_possible(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if not (text.startswith("{") or text.startswith("[")):
        return value
    try:
        return json.loads(text)
    except Exception:
        return value


def _unwrap_output_payload(output: Any) -> Any:
    """
    Normaliza payloads heterogêneos de workers RunPod.

    Alguns workers retornam:
    - dict direto com `transcription`/`segments`
    - dict aninhado em `output`/`result`/`data`
    - lista com um único dict
    - string JSON
    """
    current: Any = output
    for _ in range(6):
        current = _parse_json_if_possible(current)

        if isinstance(current, list):
            if not current:
                return current
            picked = None
            for item in current:
                if isinstance(item, dict) and any(
                    key in item
                    for key in ("transcription", "text", "transcript", "segments", "chunks", "output", "result", "data")
                ):
                    picked = item
                    break
                if isinstance(item, str) and item.strip():
                    picked = item
                    break
            if picked is None:
                return current
            current = picked
            continue

        if isinstance(current, dict):
            has_direct_payload = any(
                key in current for key in ("transcription", "text", "transcript", "segments", "chunks", "utterances")
            )
            if has_direct_payload:
                return current
            for wrapper in ("output", "result", "data", "response"):
                nested = current.get(wrapper)
                if isinstance(nested, (dict, list, str)) and nested not in ("", None):
                    current = nested
                    break
            else:
                return current
            continue

        return current

    return current


def _coerce_text_from_segments(segments: Any) -> str:
    if not isinstance(segments, list):
        return ""
    parts = []
    for seg in segments:
        if isinstance(seg, dict):
            text = seg.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        elif isinstance(seg, str) and seg.strip():
            parts.append(seg.strip())
    return " ".join(parts).strip()


def _coerce_segments(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        nested = value.get("segments")
        if isinstance(nested, list):
            return nested
    return []


def _coerce_words_from_segments(segments: Any) -> list:
    if not isinstance(segments, list):
        return []
    words: list = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        seg_words = seg.get("words")
        if isinstance(seg_words, list):
            for w in seg_words:
                if isinstance(w, dict):
                    words.append(w)
    return words


def _looks_like_truncated_tail(text: str) -> bool:
    tail = (text or "").strip()
    if not tail:
        return False
    if tail[-1] in {".", "!", "?", ";", ":", ")", "]", "\"", "”", "'"}:
        return False
    # Normalmente transcrições truncadas acabam "no meio" de um token/frase.
    return bool(tail[-1].isalnum())


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "transcription", "transcript", "full_text"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
    if isinstance(value, list):
        texts = []
        for item in value:
            if isinstance(item, str) and item.strip():
                texts.append(item.strip())
            elif isinstance(item, dict):
                item_text = item.get("text") or item.get("transcript")
                if isinstance(item_text, str) and item_text.strip():
                    texts.append(item_text.strip())
        if texts:
            return " ".join(texts).strip()
    return ""


def extract_transcription(result: RunPodResult) -> Optional[Dict[str, Any]]:
    """
    Extrai texto e segments do output do worker faster-whisper.

    O worker oficial retorna:
    {
      "segments": [{"id": 0, "start": 0.0, "end": 1.5, "text": "...", ...}],
      "detected_language": "pt",
      "transcription": "texto completo...",
      "device": "cuda",
      "model": "turbo"
    }

    Se diarização foi executada, o campo "diarization" é adicionado pelo pipeline.
    """
    if not result.output:
        return None

    output = _unwrap_output_payload(result.output)
    text = ""
    segments: list = []
    words: list = []
    language = "pt"
    diarization = None

    if isinstance(output, dict):
        raw_text = (
            output.get("transcription")
            or output.get("text")
            or output.get("transcript")
            or output.get("full_text")
            or output.get("output_text")
        )
        text = _coerce_text(raw_text)
        segments = _coerce_segments(
            output.get("segments")
            or output.get("chunks")
            or output.get("utterances")
            or output.get("transcription_segments")
            or output.get("segments_with_words")
        )
        output_words = output.get("words") or output.get("word_timestamps")
        if isinstance(output_words, list):
            words = [w for w in output_words if isinstance(w, dict)]
        language = str(output.get("detected_language") or output.get("language") or "pt")
        diarization = output.get("diarization")
    elif isinstance(output, str):
        text = output.strip()
    elif isinstance(output, list):
        segments = _coerce_segments(output)
        text = _coerce_text(output)

    segments_text = _coerce_text_from_segments(segments) if segments else ""
    if not text and segments_text:
        text = segments_text
    elif text and segments_text:
        # Alguns workers retornam `transcription` truncado e `segments` completo.
        # Priorizamos o texto reconstruído quando for materialmente mais rico.
        longer_by_ratio = len(segments_text) > int(len(text) * 1.03)
        truncated_tail = _looks_like_truncated_tail(text) and len(segments_text) >= (len(text) + 24)
        if longer_by_ratio or truncated_tail:
            logger.warning(
                "RunPod payload mismatch: using segments text (%d chars) over transcription field (%d chars).",
                len(segments_text),
                len(text),
            )
            text = segments_text

    if not text:
        if isinstance(output, dict):
            logger.warning(
                "RunPod completed with empty transcription payload. keys=%s",
                sorted(output.keys()),
            )
        else:
            logger.warning(
                "RunPod completed with empty transcription payload. type=%s",
                type(output).__name__,
            )
        return None

    # Integrity check: if worker returned text_length / text_sha256, validate them.
    if isinstance(output, dict):
        expected_len = output.get("text_length")
        expected_sha = output.get("text_sha256")
        if expected_len is not None and len(text) != int(expected_len):
            logger.warning(
                "RunPod integrity: text_length mismatch (expected=%s, got=%d). "
                "Possible transport truncation.",
                expected_len,
                len(text),
            )
        if expected_sha and isinstance(expected_sha, str):
            import hashlib
            actual_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if actual_sha != expected_sha:
                logger.warning(
                    "RunPod integrity: text_sha256 mismatch (expected=%s, got=%s). "
                    "Text may have been truncated or corrupted in transport.",
                    expected_sha[:16] + "...",
                    actual_sha[:16] + "...",
                )

    # Merge diarization speaker info into whisper segments
    if diarization:
        segments = _merge_diarization(segments, diarization)

    if not words and segments:
        words = _coerce_words_from_segments(segments)

    # Extrair falantes únicos dos segments
    speakers = sorted({
        seg.get("speaker", "")
        for seg in segments
        if seg.get("speaker")
    })

    return {
        "text": text,
        "segments": segments,
        "words": words,
        "language": language,
        "speakers": speakers,
        "has_diarization": len(speakers) > 0,
        "num_speakers": diarization.get("num_speakers", 0) if diarization else 0,
        "execution_time_ms": result.execution_time_ms,
        "provider": "runpod",
    }


# Singleton lazy
_client: Optional[RunPodClient] = None


def get_runpod_client() -> RunPodClient:
    """Retorna singleton do RunPod client."""
    global _client
    if _client is None:
        _client = RunPodClient()
    return _client
