"""
RunPod Serverless client — pipeline híbrido de transcrição + diarização.

Arquitetura:
  1. Endpoint primário (worker oficial faster-whisper) → texto + segments
  2. Endpoint fallback (custom worker v3 unificado) → transcrição + diarização integrada
  3. Endpoint de diarização legado (pyannote worker separado, deprecado)

O worker custom v3 suporta:
  - Transcrição + diarização em um único job (sem endpoint separado)
  - Generator handler (streaming via /stream/{job_id})
  - Webhook callbacks (elimina polling)
  - BatchedInferencePipeline, hotwords, anti-hallucination
  - SRT/VTT output formats

Endpoints RunPod:
  POST /v2/{endpoint_id}/run         → submete job
  POST /v2/{endpoint_id}/runsync     → job síncrono (curtos)
  GET  /v2/{endpoint_id}/status/{id} → polling de status
  GET  /v2/{endpoint_id}/stream/{id} → streaming de segmentos (generator handler)
  POST /v2/{endpoint_id}/cancel/{id} → cancela job

Worker oficial espera:
  { "input": { "audio": "<url>", "model": "turbo", "language": "pt", ... } }

Worker custom v3 espera:
  { "input": { "audio": "<url>", "model": "large-v3-turbo", "language": "pt",
               "diarize": true, "hotwords": "STJ, STF", ... },
    "webhook": "https://api.example.com/api/v1/transcription/webhook" }
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional, Set

import httpx

logger = logging.getLogger(__name__)

RUNPOD_BASE = "https://api.runpod.ai/v2"

# ── Hallucination filter (Bag of Hallucinations) ─────────────────────────
# Common phrases Whisper hallucinates on silence, music, or noise
HALLUCINATION_PHRASES: Set[str] = {
    "obrigado por assistir",
    "inscreva-se no canal",
    "legendas pela comunidade",
    "continue assistindo",
    "obrigado pela audiência",
    "transcrição automática",
    "legendado por",
    "tradução e legendagem",
    "thanks for watching",
    "subscribe to the channel",
    "like and subscribe",
    "please subscribe",
    "subtitles by the community",
    "amara.org community",
}


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

    Suporta três endpoints:
    - endpoint_id: transcrição primária (worker oficial faster-whisper)
    - fallback_endpoint_id: transcrição fallback (custom worker, usado se o primário falhar)
    - diarize_endpoint_id: diarização (custom pyannote worker, opcional)
    """

    api_key: str = field(default_factory=lambda: os.getenv("RUNPOD_API_KEY", ""))
    endpoint_id: str = field(default_factory=lambda: os.getenv("RUNPOD_ENDPOINT_ID", ""))
    fallback_endpoint_id: str = field(
        default_factory=lambda: os.getenv("RUNPOD_FALLBACK_ENDPOINT_ID", "")
    )
    diarize_endpoint_id: str = field(
        default_factory=lambda: os.getenv("RUNPOD_DIARIZE_ENDPOINT_ID", "")
    )
    poll_interval: float = 5.0
    timeout: float = 3600.0  # 1h max
    webhook_url: str = field(
        default_factory=lambda: os.getenv("RUNPOD_WEBHOOK_URL", "")
    )
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
    def fallback_configured(self) -> bool:
        return bool(self.api_key and self.fallback_endpoint_id)

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

    async def submit_unified_job(
        self,
        audio_url: str,
        endpoint_id: str,
        language: str = "pt",
        diarize: bool = True,
        num_speakers: Optional[int] = None,
        hotwords: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        preprocess_audio: bool = False,
        output_formats: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
        stream_segments: bool = False,
        stream_segment_interval: Optional[int] = None,
    ) -> RunPodResult:
        """Submit job to custom v3 worker (unified transcription + diarization).

        The v3 worker handles both transcription and diarization in a single job,
        supports streaming via generator handler, and can call back via webhook.
        """
        input_data: Dict[str, Any] = {
            "language": language,
            "word_timestamps": True,
            "diarize": diarize,
            "beam_size": 5,
        }
        input_data = self._with_audio_aliases(input_data, audio_url)

        if num_speakers is not None:
            input_data["num_speakers"] = num_speakers
        if hotwords:
            input_data["hotwords"] = hotwords
        if initial_prompt:
            input_data["initial_prompt"] = initial_prompt
        if preprocess_audio:
            input_data["preprocess_audio"] = True
        if output_formats:
            input_data["output_formats"] = output_formats
        if metadata:
            input_data["metadata"] = metadata
        if stream_segments:
            input_data["stream_segments"] = True
            if stream_segment_interval is not None and stream_segment_interval > 0:
                input_data["stream_segment_interval"] = int(stream_segment_interval)

        payload: Dict[str, Any] = {"input": input_data}

        # Add webhook if configured (eliminates need for polling)
        if self.webhook_url:
            payload["webhook"] = self.webhook_url

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._url(endpoint_id)}/run",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info(
            "RunPod unified job submitted: %s (endpoint=%s, diarize=%s, webhook=%s)",
            data.get("id"), endpoint_id, diarize, bool(self.webhook_url),
        )
        return RunPodResult(
            run_id=data["id"],
            status=data.get("status", "IN_QUEUE"),
        )

    async def stream_results(
        self,
        run_id: str,
        endpoint_id: str,
        on_segment: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
        on_progress: Optional[Callable[[str, int, str], Coroutine]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> RunPodResult:
        """Consume streaming results from a generator handler via /stream/{job_id}.

        The v3 worker yields segments progressively. This method:
        1. Polls /stream/{job_id} for new chunks
        2. Calls on_segment for each transcription segment received
        3. Returns the final aggregated result

        Falls back to regular polling if streaming is not available.
        """
        url = f"{self._url(endpoint_id)}/stream/{run_id}"
        elapsed = 0.0
        all_segments: list = []
        final_result: Optional[Dict[str, Any]] = None

        while elapsed < self.timeout:
            if cancel_check and cancel_check():
                await self.cancel_job(run_id, endpoint_id)
                return RunPodResult(run_id=run_id, status="CANCELLED")

            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url, headers=self._headers)

                    if resp.status_code == 404:
                        # Stream not available — fall back to polling
                        logger.info("Stream not available for %s, falling back to polling", run_id)
                        return await self.poll_until_complete(
                            run_id=run_id,
                            endpoint_id=endpoint_id,
                            on_progress=on_progress,
                            cancel_check=cancel_check,
                        )

                    resp.raise_for_status()
                    data = resp.json()

                # RunPod stream returns {"stream": [...chunks], "status": "..."}
                stream_chunks = data.get("stream", [])
                stream_status = data.get("status", "IN_PROGRESS")

                for chunk in stream_chunks:
                    chunk_output = chunk.get("output", chunk)

                    # Progress updates
                    if "stage" in chunk_output and on_progress:
                        await on_progress(
                            chunk_output.get("stage", "transcribing"),
                            chunk_output.get("progress", 0),
                            chunk_output.get("message", ""),
                        )

                    # Segment streaming
                    if "segment" in chunk_output:
                        all_segments.append(chunk_output["segment"])
                        if on_segment:
                            await on_segment(chunk_output["segment"])

                    # Final result (has "done": True)
                    if chunk_output.get("done"):
                        final_result = chunk_output

                    # Error
                    if "error" in chunk_output:
                        return RunPodResult(
                            run_id=run_id,
                            status="FAILED",
                            error=chunk_output["error"],
                        )

                if stream_status == "COMPLETED":
                    if final_result:
                        return RunPodResult(
                            run_id=run_id,
                            status="COMPLETED",
                            output=final_result,
                        )

                    # Alguns workers encerram com COMPLETED e stream vazio.
                    # Tenta resgatar output pelo status endpoint; se vier vazio, falha rápido
                    # para permitir fallback ao endpoint oficial.
                    try:
                        status_result = await self.get_status(run_id, endpoint_id)
                        if status_result.output is not None:
                            return RunPodResult(
                                run_id=run_id,
                                status="COMPLETED",
                                output=status_result.output,
                                execution_time_ms=status_result.execution_time_ms,
                            )
                    except Exception as status_exc:
                        logger.warning("Failed to fetch status output for completed stream %s: %s", run_id, status_exc)

                    logger.error(
                        "RunPod stream completed sem output/stream para %s (endpoint=%s).",
                        run_id,
                        endpoint_id,
                    )
                    return RunPodResult(
                        run_id=run_id,
                        status="FAILED",
                        error="Custom worker completou sem output (stream vazio).",
                    )

                if stream_status in ("FAILED", "CANCELLED"):
                    return RunPodResult(
                        run_id=run_id,
                        status=stream_status,
                        error=data.get("error", f"Job {stream_status}"),
                    )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.info("Stream endpoint not found for %s, using polling", run_id)
                    return await self.poll_until_complete(
                        run_id=run_id,
                        endpoint_id=endpoint_id,
                        on_progress=on_progress,
                        cancel_check=cancel_check,
                    )
                logger.warning("Stream request error for %s: %s", run_id, e)
            except Exception as e:
                logger.warning("Stream consumption error for %s: %s", run_id, e)

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        # Timeout
        await self.cancel_job(run_id, endpoint_id)
        return RunPodResult(
            run_id=run_id,
            status="FAILED",
            error=f"Stream timeout após {self.timeout:.0f}s",
        )

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
        hotwords: Optional[str] = None,
        preprocess_audio: bool = False,
        output_formats: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
        on_progress: Optional[Callable[[str, int, str], Coroutine]] = None,
        on_segment: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> RunPodResult:
        """Pipeline completo: transcrição + diarização opcional.

        Strategy:
        1. Submit to primary endpoint (official worker — transcription only)
        2. If primary fails and fallback configured, submit to custom v3 worker
           (unified: transcription + diarization in one job, with streaming)
        3. If primary succeeded and diarization requested:
           a. Prefer custom v3 worker (if fallback configured) for unified diarization
           b. Fall back to legacy separate pyannote endpoint (if configured)
        """
        # 1. Transcription — primary endpoint
        transcribe_result = await self.submit_job(
            audio_url=audio_url,
            language=language,
            diarization=diarization,
            initial_prompt=initial_prompt,
        )

        # Poll transcription
        final = await self.poll_until_complete(
            run_id=transcribe_result.run_id,
            on_progress=on_progress,
            cancel_check=cancel_check,
        )

        # 2. Fallback — if primary failed, try custom v3 worker (unified)
        if final.status != "COMPLETED" and self.fallback_configured:
            logger.warning(
                "RunPod primary endpoint failed (%s: %s). Trying custom v3 fallback %s...",
                final.status,
                final.error,
                self.fallback_endpoint_id,
            )
            if on_progress:
                await on_progress("transcription", 5, "Primário falhou, tentando worker custom v3...")

            try:
                # Submit to unified v3 worker (handles diarization internally)
                fb_result = await self.submit_unified_job(
                    audio_url=audio_url,
                    endpoint_id=self.fallback_endpoint_id,
                    language=language,
                    diarize=diarization,
                    num_speakers=max_speakers or min_speakers,
                    hotwords=hotwords,
                    initial_prompt=initial_prompt,
                    preprocess_audio=preprocess_audio,
                    output_formats=output_formats,
                    metadata=metadata,
                    stream_segments=bool(on_segment),
                )

                # Try streaming first, fall back to polling
                final = await self.stream_results(
                    run_id=fb_result.run_id,
                    endpoint_id=self.fallback_endpoint_id,
                    on_segment=on_segment,
                    on_progress=on_progress,
                    cancel_check=cancel_check,
                )

                # If v3 worker handled diarization, we're done
                if final.status == "COMPLETED":
                    return final

            except Exception as fb_exc:
                logger.error("RunPod fallback also failed: %s", fb_exc)

        if final.status != "COMPLETED":
            return final

        # 3. Diarization — if primary succeeded but didn't include diarization
        output_has_diarization = (
            isinstance(final.output, dict)
            and (final.output.get("has_diarization") or final.output.get("diarization"))
        )

        if diarization and not output_has_diarization:
            # 3a. Prefer unified v3 worker for diarization (submit new job with diarize=True)
            if self.fallback_configured:
                logger.info("Primary lacks diarization — submitting unified job to custom v3 worker")
                if on_progress:
                    await on_progress("diarization", 0, "Iniciando diarização no worker v3...")

                try:
                    dia_result = await self.submit_unified_job(
                        audio_url=audio_url,
                        endpoint_id=self.fallback_endpoint_id,
                        language=language,
                        diarize=True,
                        num_speakers=max_speakers or min_speakers,
                        hotwords=hotwords,
                        initial_prompt=initial_prompt,
                        stream_segments=False,
                    )
                    dia_final = await self.stream_results(
                        run_id=dia_result.run_id,
                        endpoint_id=self.fallback_endpoint_id,
                        on_progress=on_progress,
                        cancel_check=cancel_check,
                    )
                    if dia_final.status == "COMPLETED" and isinstance(dia_final.output, dict):
                        diarization_data = dia_final.output.get("diarization")
                        if diarization_data and isinstance(final.output, dict):
                            final.output["diarization"] = diarization_data
                            final.output["has_diarization"] = True
                            final.output["speakers"] = dia_final.output.get("speakers", [])
                            final.output["num_speakers"] = dia_final.output.get("num_speakers", 0)
                            if on_progress:
                                await on_progress("diarization", 100, "Diarização concluída (v3)")
                        else:
                            logger.warning("V3 diarization completed but no diarization data in output")
                    else:
                        logger.warning("V3 diarization failed: %s", dia_final.error)
                except Exception as e:
                    logger.warning("V3 diarization error: %s — trying legacy endpoint", e)

            # 3b. Legacy separate pyannote endpoint (deprecado, mantido como fallback)
            output_has_diarization = (
                isinstance(final.output, dict)
                and (final.output.get("has_diarization") or final.output.get("diarization"))
            )
            if not output_has_diarization and self.diarize_configured:
                if on_progress:
                    await on_progress("diarization", 0, "Diarização via endpoint legado...")

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
                        if isinstance(final.output, dict):
                            final.output["diarization"] = dia_final.output.get("diarization")
                        if on_progress:
                            await on_progress("diarization", 100, "Diarização concluída (legado)")
                    else:
                        logger.warning("Legacy diarization failed: %s", dia_final.error)
                except Exception as e:
                    logger.warning("Legacy diarization error: %s", e)

        elif diarization and not output_has_diarization and not self.fallback_configured and not self.diarize_configured:
            logger.info("Diarization requested but no diarization-capable endpoint configured — skipping")

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
            # Handle both int (legacy pyannote) and str (v3 worker) speaker labels
            if isinstance(best_speaker, int):
                new_seg["speaker"] = f"SPEAKER_{best_speaker:02d}"
            else:
                new_seg["speaker"] = str(best_speaker)
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
    def _looks_like_transcription_payload(value: Any) -> bool:
        return isinstance(value, dict) and any(
            key in value for key in ("transcription", "text", "transcript", "segments", "chunks", "utterances", "full_text")
        )

    def _unwrap_chunk_output(item: Any) -> Any:
        if isinstance(item, dict):
            nested = item.get("output", item)
            return _parse_json_if_possible(nested)
        return _parse_json_if_possible(item)

    current: Any = output
    for _ in range(6):
        current = _parse_json_if_possible(current)

        if isinstance(current, list):
            if not current:
                return current

            # Stream agregado do RunPod costuma vir como lista de chunks
            # [{"output": {...progress...}}, ..., {"output": {...done/text...}}].
            # Preferimos o último chunk que pareça payload de transcrição.
            picked = None
            for item in reversed(current):
                candidate = _unwrap_chunk_output(item)
                if _looks_like_transcription_payload(candidate):
                    picked = candidate
                    break

            # Fallback: último chunk marcado como done (mesmo sem texto explícito).
            if picked is None:
                for item in reversed(current):
                    candidate = _unwrap_chunk_output(item)
                    if isinstance(candidate, dict) and candidate.get("done") is True:
                        picked = candidate
                        break

            # Fallback legado: primeiro item minimamente útil.
            if picked is None:
                for item in current:
                    candidate = _unwrap_chunk_output(item)
                    if isinstance(candidate, dict) and any(
                        key in candidate
                        for key in ("transcription", "text", "transcript", "segments", "chunks", "output", "result", "data")
                    ):
                        picked = candidate
                        break
                    if isinstance(candidate, str) and candidate.strip():
                        picked = candidate
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


def _filter_hallucinated_segments(segments: list) -> tuple:
    """Remove segments that match known Whisper hallucination phrases.

    Returns (filtered_segments, hallucination_count).
    """
    filtered = []
    count = 0
    for seg in segments:
        text = seg.get("text", "").strip().lower().rstrip(".")
        if text in HALLUCINATION_PHRASES:
            count += 1
            continue
        # Very short repetitive segments
        if len(text) < 3 and text not in ("é", "e", "a", "o", "eu"):
            count += 1
            continue
        filtered.append(seg)
    return filtered, count


def extract_transcription(result: RunPodResult) -> Optional[Dict[str, Any]]:
    """
    Extrai texto e segments do output do worker faster-whisper.

    Suporta múltiplos formatos de output:
    - Worker oficial: {"transcription": "...", "segments": [...], "detected_language": "pt"}
    - Worker custom v3: {"text": "...", "segments": [...], "diarization": {...}, "has_diarization": true}
    - Outros workers RunPod com formatos variados

    Aplica filtro de alucinação (BoH) e validação de integridade.
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

    # Apply hallucination filter (BoH)
    hallucination_count = 0
    if segments:
        segments, hallucination_count = _filter_hallucinated_segments(segments)
        if hallucination_count > 0:
            logger.info("Filtered %d hallucinated segments from RunPod output", hallucination_count)
            # Rebuild text from filtered segments if we removed any
            text = _coerce_text_from_segments(segments) or text

    if not words and segments:
        words = _coerce_words_from_segments(segments)

    # Extract unique speakers from segments
    speakers = sorted({
        seg.get("speaker", "")
        for seg in segments
        if seg.get("speaker")
    })

    # V3 worker may provide speakers/num_speakers directly
    if isinstance(output, dict):
        v3_speakers = output.get("speakers")
        v3_num_speakers = output.get("num_speakers")
        if isinstance(v3_speakers, list) and v3_speakers and not speakers:
            speakers = v3_speakers
        if v3_num_speakers and isinstance(v3_num_speakers, int):
            num_speakers = v3_num_speakers
        else:
            num_speakers = diarization.get("num_speakers", 0) if isinstance(diarization, dict) else len(speakers)
    else:
        num_speakers = diarization.get("num_speakers", 0) if isinstance(diarization, dict) else 0

    result_dict: Dict[str, Any] = {
        "text": text,
        "segments": segments,
        "words": words,
        "language": language,
        "speakers": speakers,
        "has_diarization": len(speakers) > 0,
        "num_speakers": num_speakers,
        "execution_time_ms": result.execution_time_ms,
        "provider": "runpod",
    }

    # Pass through v3 metadata
    if isinstance(output, dict):
        if output.get("srt"):
            result_dict["srt"] = output["srt"]
        if output.get("vtt"):
            result_dict["vtt"] = output["vtt"]
        if output.get("metadata"):
            result_dict["metadata"] = output["metadata"]
        if output.get("model"):
            result_dict["model"] = output["model"]
        if output.get("hallucinations_filtered"):
            result_dict["hallucinations_filtered"] = (
                output["hallucinations_filtered"] + hallucination_count
            )
        elif hallucination_count > 0:
            result_dict["hallucinations_filtered"] = hallucination_count
        if output.get("transcription_time"):
            result_dict["transcription_time"] = output["transcription_time"]
        if output.get("duration"):
            result_dict["duration"] = output["duration"]
        if "words_truncated" in output:
            result_dict["words_truncated"] = bool(output.get("words_truncated"))

    return result_dict


# Singleton lazy
_client: Optional[RunPodClient] = None


def get_runpod_client() -> RunPodClient:
    """Retorna singleton do RunPod client."""
    global _client
    if _client is None:
        _client = RunPodClient()
    return _client
