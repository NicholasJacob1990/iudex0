"""
Testes para o RunPod Serverless client (faster-whisper + diarizacao).

Mock de todas as chamadas HTTP — não requer conta RunPod.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.runpod_transcription import (
    RunPodClient,
    RunPodResult,
    extract_transcription,
)


@pytest.fixture
def client():
    return RunPodClient(
        api_key="rpa_test_key",
        endpoint_id="test_endpoint_123",
        fallback_endpoint_id="",
        diarize_endpoint_id="",
        poll_interval=0.01,  # Fast polling para testes
        timeout=1.0,
    )


@pytest.fixture
def client_with_fallback():
    return RunPodClient(
        api_key="rpa_test_key",
        endpoint_id="primary_endpoint",
        fallback_endpoint_id="fallback_endpoint",
        poll_interval=0.01,
        timeout=1.0,
    )


class TestRunPodClient:
    def test_is_configured(self, client):
        assert client.is_configured is True

    def test_not_configured_without_key(self):
        c = RunPodClient(api_key="", endpoint_id="abc")
        assert c.is_configured is False

    def test_not_configured_without_endpoint(self):
        c = RunPodClient(api_key="rpa_test", endpoint_id="")
        assert c.is_configured is False

    def test_fallback_configured(self, client_with_fallback):
        assert client_with_fallback.fallback_configured is True

    def test_fallback_not_configured(self, client):
        assert client.fallback_configured is False

    @pytest.mark.asyncio
    async def test_submit_job(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "run-abc123", "status": "IN_QUEUE"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            result = await client.submit_job(
                audio_url="https://example.com/audio.mp3",
                language="pt",
                diarization=True,
            )

            assert result.run_id == "run-abc123"
            assert result.status == "IN_QUEUE"
            mock_instance.post.assert_called_once()

            call_kwargs = mock_instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert "audio" in payload["input"]
            assert payload["input"]["audio"] == "https://example.com/audio.mp3"
            assert payload["input"]["language"] == "pt"
            assert payload["input"]["model"] == "turbo"

    @pytest.mark.asyncio
    async def test_get_status_completed(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "run-abc123",
            "status": "COMPLETED",
            "output": {
                "transcription": "Texto transcrito",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "Texto transcrito", "speaker": "SPEAKER_00"}
                ],
                "detected_language": "pt",
            },
            "executionTime": 5000,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            result = await client.get_status("run-abc123")

            assert result.status == "COMPLETED"
            assert result.output is not None
            assert result.output["transcription"] == "Texto transcrito"
            assert result.execution_time_ms == 5000

    @pytest.mark.asyncio
    async def test_cancel_job(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            success = await client.cancel_job("run-abc123")
            assert success is True

    @pytest.mark.asyncio
    async def test_poll_until_complete(self, client):
        """Simula polling: IN_QUEUE → IN_PROGRESS → COMPLETED."""
        statuses = [
            {"id": "run-1", "status": "IN_QUEUE"},
            {"id": "run-1", "status": "IN_PROGRESS"},
            {"id": "run-1", "status": "COMPLETED", "output": {"transcription": "OK"}, "executionTime": 3000},
        ]
        call_count = 0

        async def mock_get_status(run_id, endpoint_id=None):
            nonlocal call_count
            data = statuses[min(call_count, len(statuses) - 1)]
            call_count += 1
            return RunPodResult(
                run_id=data["id"],
                status=data["status"],
                output=data.get("output"),
                execution_time_ms=data.get("executionTime"),
            )

        client.get_status = mock_get_status

        progress_calls = []

        async def on_progress(stage, pct, msg):
            progress_calls.append((stage, pct, msg))

        result = await client.poll_until_complete("run-1", on_progress=on_progress)

        assert result.status == "COMPLETED"
        assert result.output["transcription"] == "OK"
        assert len(progress_calls) >= 1  # Pelo menos o "concluída"

    @pytest.mark.asyncio
    async def test_poll_with_cancel(self, client):
        """Cancel check interrompe o polling."""

        async def mock_get_status(run_id, endpoint_id=None):
            return RunPodResult(run_id=run_id, status="IN_QUEUE")

        client.get_status = mock_get_status
        client.cancel_job = AsyncMock(return_value=True)

        result = await client.poll_until_complete(
            "run-1",
            cancel_check=lambda: True,  # Sempre cancelar
        )

        assert result.status == "CANCELLED"
        client.cancel_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_timeout(self, client):
        """Timeout retorna FAILED."""
        client.timeout = 0.05  # 50ms

        async def mock_get_status(run_id, endpoint_id=None):
            return RunPodResult(run_id=run_id, status="IN_QUEUE")

        client.get_status = mock_get_status
        client.cancel_job = AsyncMock(return_value=True)

        result = await client.poll_until_complete("run-1")

        assert result.status == "FAILED"
        assert "Timeout" in (result.error or "")


class TestFallbackEndpoint:
    """Testes para fallback entre endpoint primário e custom v3."""

    @pytest.mark.asyncio
    async def test_fallback_triggered_on_primary_failure(self, client_with_fallback):
        """Se primário falha, tenta o fallback endpoint (v3 unificado)."""
        client = client_with_fallback

        async def mock_submit_job(**kwargs):
            return RunPodResult(run_id="run-primary", status="IN_QUEUE")

        async def mock_submit_unified_job(**kwargs):
            return RunPodResult(run_id="run-fallback", status="IN_QUEUE")

        async def mock_poll(run_id, endpoint_id=None, on_progress=None, cancel_check=None):
            if endpoint_id == "fallback_endpoint":
                return RunPodResult(
                    run_id=run_id,
                    status="COMPLETED",
                    output={"text": "Fallback OK", "segments": [], "text_length": 11, "text_sha256": "abc"},
                )
            # Primary fails
            return RunPodResult(run_id=run_id, status="FAILED", error="GPU unavailable")

        async def mock_stream(run_id, endpoint_id=None, on_segment=None, on_progress=None, cancel_check=None):
            # Stream falls back to polling internally
            return await mock_poll(run_id, endpoint_id=endpoint_id, on_progress=on_progress, cancel_check=cancel_check)

        client.submit_job = mock_submit_job
        client.submit_unified_job = mock_submit_unified_job
        client.poll_until_complete = mock_poll
        client.stream_results = mock_stream

        result = await client.transcribe_and_diarize(
            audio_url="https://example.com/audio.mp3",
        )

        assert result.status == "COMPLETED"
        assert result.output["text"] == "Fallback OK"

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_succeeds(self, client_with_fallback):
        """Se primário tem sucesso, fallback não é tentado."""
        client = client_with_fallback

        async def mock_submit_job(**kwargs):
            return RunPodResult(run_id="run-primary", status="IN_QUEUE")

        async def mock_poll(run_id, endpoint_id=None, on_progress=None, cancel_check=None):
            return RunPodResult(
                run_id=run_id,
                status="COMPLETED",
                output={"text": "Primary OK", "segments": [], "has_diarization": False},
            )

        client.submit_job = mock_submit_job
        client.poll_until_complete = mock_poll

        result = await client.transcribe_and_diarize(
            audio_url="https://example.com/audio.mp3",
            diarization=False,
        )

        assert result.status == "COMPLETED"
        assert result.output["text"] == "Primary OK"

    @pytest.mark.asyncio
    async def test_no_fallback_without_config(self, client):
        """Sem fallback configurado, retorna falha do primário."""

        async def mock_submit_job(**kwargs):
            return RunPodResult(run_id="run-primary", status="IN_QUEUE")

        async def mock_poll(run_id, endpoint_id=None, on_progress=None, cancel_check=None):
            return RunPodResult(run_id=run_id, status="FAILED", error="GPU unavailable")

        client.submit_job = mock_submit_job
        client.poll_until_complete = mock_poll

        result = await client.transcribe_and_diarize(
            audio_url="https://example.com/audio.mp3",
        )

        assert result.status == "FAILED"
        assert "GPU unavailable" in (result.error or "")

    @pytest.mark.asyncio
    async def test_unified_diarization_via_fallback(self, client_with_fallback):
        """Primary succeeds without diarization, v3 fallback adds it."""
        client = client_with_fallback

        async def mock_submit_job(**kwargs):
            return RunPodResult(run_id="run-primary", status="IN_QUEUE")

        poll_calls = {"n": 0}

        async def mock_poll(run_id, endpoint_id=None, on_progress=None, cancel_check=None):
            poll_calls["n"] += 1
            # Primary succeeds without diarization
            return RunPodResult(
                run_id=run_id,
                status="COMPLETED",
                output={"text": "Transcription OK", "segments": [{"start": 0, "end": 1, "text": "Transcription OK"}]},
            )

        async def mock_submit_unified(**kwargs):
            return RunPodResult(run_id="run-diar-v3", status="IN_QUEUE")

        async def mock_stream(run_id, endpoint_id=None, on_segment=None, on_progress=None, cancel_check=None):
            return RunPodResult(
                run_id=run_id,
                status="COMPLETED",
                output={
                    "text": "Transcription OK",
                    "segments": [{"start": 0, "end": 1, "text": "Transcription OK", "speaker": "SPEAKER_00"}],
                    "has_diarization": True,
                    "diarization": {"segments": [{"start": 0, "end": 1, "speaker": "SPEAKER_00"}], "num_speakers": 1},
                    "speakers": ["SPEAKER_00"],
                    "num_speakers": 1,
                },
            )

        client.submit_job = mock_submit_job
        client.poll_until_complete = mock_poll
        client.submit_unified_job = mock_submit_unified
        client.stream_results = mock_stream

        result = await client.transcribe_and_diarize(
            audio_url="https://example.com/audio.mp3",
            diarization=True,
        )

        assert result.status == "COMPLETED"
        assert result.output.get("has_diarization") is True
        assert result.output.get("num_speakers") == 1


class TestExtractTranscription:
    def test_extract_full_output_with_diarization(self):
        """Output completo com diarização separada."""
        result = RunPodResult(
            run_id="run-1",
            status="COMPLETED",
            output={
                "transcription": "Bom dia. Pode sentar.",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "Bom dia."},
                    {"start": 1.5, "end": 3.0, "text": "Pode sentar."},
                ],
                "detected_language": "pt",
                "diarization": {
                    "segments": [
                        {"start": 0.0, "end": 1.5, "speaker": 0},
                        {"start": 1.5, "end": 3.0, "speaker": 1},
                    ],
                    "num_speakers": 2,
                },
            },
            execution_time_ms=4500,
        )

        extracted = extract_transcription(result)
        assert extracted is not None
        assert extracted["text"] == "Bom dia. Pode sentar."
        assert len(extracted["segments"]) == 2
        assert extracted["language"] == "pt"
        assert extracted["provider"] == "runpod"
        assert extracted["execution_time_ms"] == 4500
        assert extracted["has_diarization"] is True
        assert extracted["speakers"] == ["SPEAKER_00", "SPEAKER_01"]
        assert extracted["num_speakers"] == 2

    def test_extract_output_without_diarization(self):
        """Output sem diarização."""
        result = RunPodResult(
            run_id="run-1",
            status="COMPLETED",
            output={
                "transcription": "Texto completo aqui",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "Texto"},
                    {"start": 1.5, "end": 3.0, "text": "completo aqui"},
                ],
                "detected_language": "pt",
            },
            execution_time_ms=3000,
        )

        extracted = extract_transcription(result)
        assert extracted is not None
        assert extracted["has_diarization"] is False
        assert extracted["speakers"] == []

    def test_extract_no_output_returns_none(self):
        result = RunPodResult(run_id="run-1", status="FAILED", output=None)
        assert extract_transcription(result) is None

    def test_extract_empty_output_returns_none(self):
        """Empty dict is falsy → treated same as no output."""
        result = RunPodResult(run_id="run-1", status="COMPLETED", output={})
        assert extract_transcription(result) is None

    def test_extract_minimal_output(self):
        """Output with just transcription key."""
        result = RunPodResult(
            run_id="run-1",
            status="COMPLETED",
            output={"transcription": "hello"},
        )
        extracted = extract_transcription(result)
        assert extracted is not None
        assert extracted["text"] == "hello"
        assert extracted["segments"] == []
        assert extracted["has_diarization"] is False

    def test_integrity_check_with_custom_worker_output(self):
        """Custom worker retorna text_length e text_sha256 para validação."""
        import hashlib
        text = "Texto do custom worker"
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

        result = RunPodResult(
            run_id="run-1",
            status="COMPLETED",
            output={
                "text": text,
                "text_length": len(text),
                "text_sha256": sha,
                "segments": [],
                "segments_count": 0,
            },
        )
        extracted = extract_transcription(result)
        assert extracted is not None
        assert extracted["text"] == text

    def test_hallucination_filter_removes_known_phrases(self):
        """Segments com frases alucinadas devem ser removidos."""
        result = RunPodResult(
            run_id="run-1",
            status="COMPLETED",
            output={
                "transcription": "Bom dia. Obrigado por assistir.",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "Bom dia."},
                    {"start": 1.5, "end": 3.0, "text": "Obrigado por assistir."},
                ],
                "detected_language": "pt",
            },
        )
        extracted = extract_transcription(result)
        assert extracted is not None
        # "Obrigado por assistir" should be filtered
        assert len(extracted["segments"]) == 1
        assert extracted["segments"][0]["text"] == "Bom dia."
        assert extracted.get("hallucinations_filtered", 0) >= 1

    def test_hallucination_filter_preserves_normal_text(self):
        """Texto normal não é filtrado."""
        result = RunPodResult(
            run_id="run-1",
            status="COMPLETED",
            output={
                "transcription": "O recurso especial foi provido.",
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "O recurso especial foi provido."},
                ],
                "detected_language": "pt",
            },
        )
        extracted = extract_transcription(result)
        assert extracted is not None
        assert len(extracted["segments"]) == 1

    def test_extract_v3_unified_output(self):
        """Worker v3 retorna output unificado com diarização, metadata, SRT."""
        result = RunPodResult(
            run_id="run-1",
            status="COMPLETED",
            output={
                "done": True,
                "text": "Bom dia. Pode sentar.",
                "text_length": 21,
                "text_sha256": "abc123",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "Bom dia.", "speaker": "SPEAKER_00"},
                    {"start": 1.5, "end": 3.0, "text": "Pode sentar.", "speaker": "SPEAKER_01"},
                ],
                "segments_count": 2,
                "words": [],
                "language": "pt",
                "duration": 3.0,
                "transcription_time": 1.5,
                "model": "large-v3-turbo",
                "has_diarization": True,
                "speakers": ["SPEAKER_00", "SPEAKER_01"],
                "num_speakers": 2,
                "diarization": {
                    "segments": [
                        {"start": 0.0, "end": 1.5, "speaker": "SPEAKER_00"},
                        {"start": 1.5, "end": 3.0, "speaker": "SPEAKER_01"},
                    ],
                    "num_speakers": 2,
                },
                "srt": "1\n00:00:00,000 --> 00:00:01,500\nBom dia.\n",
                "metadata": {"conversation_id": "conv-123"},
                "hallucinations_filtered": 2,
            },
            execution_time_ms=5000,
        )

        extracted = extract_transcription(result)
        assert extracted is not None
        assert extracted["text"] == "Bom dia. Pode sentar."
        assert extracted["has_diarization"] is True
        assert extracted["num_speakers"] == 2
        assert extracted["speakers"] == ["SPEAKER_00", "SPEAKER_01"]
        assert extracted["model"] == "large-v3-turbo"
        assert extracted["srt"] is not None
        assert extracted["metadata"]["conversation_id"] == "conv-123"
        assert extracted["transcription_time"] == 1.5
        assert extracted["duration"] == 3.0
        assert extracted["hallucinations_filtered"] >= 2

    def test_extract_from_aggregated_stream_output_list(self):
        """Status output pode vir como lista agregada de chunks do stream."""
        result = RunPodResult(
            run_id="run-agg",
            status="COMPLETED",
            output=[
                {"output": {"stage": "downloading", "progress": 0, "message": "Baixando"}},
                {"output": {"stage": "transcribing", "progress": 50, "message": "Transcrevendo"}},
                {
                    "output": {
                        "done": True,
                        "text": "Texto final do worker",
                        "segments": [{"start": 0.0, "end": 1.0, "text": "Texto final do worker"}],
                        "language": "pt",
                    }
                },
            ],
        )

        extracted = extract_transcription(result)
        assert extracted is not None
        assert extracted["text"] == "Texto final do worker"
        assert len(extracted["segments"]) == 1
