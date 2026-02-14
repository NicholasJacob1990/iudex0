"""Tests for RunPod hints wiring (Fase 4).

Verifica que _transcribe_runpod() passa initial_prompt via _normalize_hints()
para submit_job() do RunPod.
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def svc():
    """Cria instância mínima de TranscriptionService."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}):
        from app.services.transcription_service import TranscriptionService
        return TranscriptionService.__new__(TranscriptionService)


class TestRunPodHintsWiring:
    """Testa que hints de área/keyterms são passados ao RunPod via initial_prompt."""

    def test_transcribe_runpod_accepts_hint_params(self, svc):
        """_transcribe_runpod() deve aceitar area, custom_keyterms, speaker_names."""
        import inspect
        sig = inspect.signature(svc._transcribe_runpod)
        params = list(sig.parameters.keys())
        assert "area" in params
        assert "custom_keyterms" in params
        assert "speaker_names" in params

    def test_normalize_hints_called_with_runpod_provider(self, svc):
        """_normalize_hints() deve ser chamado com provider='runpod'."""
        hints = svc._normalize_hints(
            area="juridico",
            custom_keyterms=["habeas corpus"],
            speaker_names=["Juiz"],
            provider="runpod",
        )
        assert hints["keyterms"]
        assert hints["initial_prompt"]
        assert hints["fingerprint"]
        # RunPod limit = 200
        assert len(hints["keyterms"]) <= 200

    def test_runpod_provider_limit_200(self, svc):
        """RunPod deve limitar keyterms a 200."""
        many_terms = [f"term_{i}" for i in range(300)]
        hints = svc._normalize_hints(
            custom_keyterms=many_terms,
            provider="runpod",
        )
        assert len(hints["keyterms"]) == 200

    def test_submit_job_receives_initial_prompt(self, svc):
        """submit_job() do RunPod deve receber initial_prompt quando hints disponíveis."""
        # Testar que _normalize_hints gera initial_prompt não-vazio para area juridico
        hints = svc._normalize_hints(area="juridico", provider="runpod")
        assert hints["initial_prompt"]
        assert "Termos" in hints["initial_prompt"]

    def test_no_hints_when_empty(self, svc):
        """Sem area/keyterms/speaker_names, initial_prompt deve ser vazio."""
        hints = svc._normalize_hints(provider="runpod")
        assert hints["initial_prompt"] == ""
        assert hints["keyterms"] == []
        assert hints["fingerprint"] == ""

    def test_hotwords_generated_for_runpod(self, svc):
        """_normalize_hints deve gerar hotwords comma-separated para RunPod."""
        hints = svc._normalize_hints(
            custom_keyterms=["STF", "STJ", "OAB"],
            provider="runpod",
        )
        assert hints["hotwords"]
        assert "STF" in hints["hotwords"]
        assert "," in hints["hotwords"]


class TestRunPodCallSiteIntegration:
    """Testa integração do call site com area/keyterms."""

    @pytest.mark.asyncio
    async def test_transcribe_runpod_passes_initial_prompt(self, svc):
        """_transcribe_runpod() deve passar initial_prompt para submit_job()."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.run_id = "test_run_123"
        mock_result.status = "COMPLETED"
        mock_result.output = {"text": "transcribed text"}
        mock_client.is_configured = True
        mock_client.submit_job = AsyncMock(return_value=mock_result)
        mock_client.poll_until_complete = AsyncMock(return_value=mock_result)

        with patch("app.services.transcription_service.TranscriptionService._resolve_runpod_base_url", return_value=("http://localhost:8000", "test")), \
             patch("app.services.transcription_service.TranscriptionService._validate_runpod_base_url"), \
             patch("app.services.transcription_service.TranscriptionService._extract_transcription_job_id_from_audio_path", return_value="job123"), \
             patch("app.services.runpod_transcription.get_runpod_client", return_value=mock_client), \
             patch("app.api.endpoints.transcription.generate_runpod_audio_url", return_value="http://localhost:8000/audio/job123"), \
             patch("app.services.transcription_service.TranscriptionService._preflight_runpod_audio_url"), \
             patch("app.services.runpod_transcription.extract_transcription", return_value={"text": "transcribed", "words": [], "segments": []}):

            result = await svc._transcribe_runpod(
                file_path="/tmp/test.wav",
                audio_path="/tmp/test.wav",
                language="pt",
                diarization=False,
                area="juridico",
                custom_keyterms=["habeas corpus"],
                speaker_names=["Juiz"],
            )

            # Verificar que submit_job foi chamado com initial_prompt
            mock_client.submit_job.assert_called_once()
            call_kwargs = mock_client.submit_job.call_args
            assert call_kwargs.kwargs.get("initial_prompt") is not None
            assert "Termos" in call_kwargs.kwargs["initial_prompt"]

    @pytest.mark.asyncio
    async def test_transcribe_runpod_no_hints_no_prompt(self, svc):
        """Sem area/keyterms, initial_prompt deve ser None."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.run_id = "test_run_456"
        mock_result.status = "COMPLETED"
        mock_result.output = {"text": "transcribed text"}
        mock_client.is_configured = True
        mock_client.submit_job = AsyncMock(return_value=mock_result)
        mock_client.poll_until_complete = AsyncMock(return_value=mock_result)

        with patch("app.services.transcription_service.TranscriptionService._resolve_runpod_base_url", return_value=("http://localhost:8000", "test")), \
             patch("app.services.transcription_service.TranscriptionService._validate_runpod_base_url"), \
             patch("app.services.transcription_service.TranscriptionService._extract_transcription_job_id_from_audio_path", return_value="job456"), \
             patch("app.services.runpod_transcription.get_runpod_client", return_value=mock_client), \
             patch("app.api.endpoints.transcription.generate_runpod_audio_url", return_value="http://localhost:8000/audio/job456"), \
             patch("app.services.transcription_service.TranscriptionService._preflight_runpod_audio_url"), \
             patch("app.services.runpod_transcription.extract_transcription", return_value={"text": "transcribed", "words": [], "segments": []}):

            result = await svc._transcribe_runpod(
                file_path="/tmp/test.wav",
                audio_path="/tmp/test.wav",
                language="pt",
                diarization=False,
                # Sem area/keyterms/speaker_names
            )

            mock_client.submit_job.assert_called_once()
            call_kwargs = mock_client.submit_job.call_args
            # initial_prompt deve ser None (sem hints)
            assert call_kwargs.kwargs.get("initial_prompt") is None
