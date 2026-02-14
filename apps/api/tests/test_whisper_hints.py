"""Tests for Whisper local hints wiring (Fase 5).

Verifica que extra_terms são passados explicitamente (sem estado global)
para _get_whisper_initial_prompt_for_asr() e propagados nas APIs públicas.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# mlx_vomo está na raiz do monorepo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture
def vomo_instance():
    """Cria instância mínima de VomoMLX."""
    with patch.dict("os.environ", {
        "VOMO_LLM_MODEL": "test-model",
        "VOMO_WHISPER_MODEL": "tiny",
    }):
        try:
            from mlx_vomo import VomoMLX
            vomo = VomoMLX.__new__(VomoMLX)
            vomo.model_name = "tiny"
            vomo.llm_model = "test-model"
            vomo.thinking_level = "medium"
            vomo._current_mode = "APOSTILA"
            vomo._current_language = "pt"
            vomo.INITIAL_PROMPTS = {
                "APOSTILA": "Transcrição de aula acadêmica.",
                "FIDELIDADE": "Transcrição fiel do áudio.",
                "AUDIENCIA": "Transcrição de audiência judicial.",
            }
            vomo.INITIAL_PROMPTS_I18N = {}
            return vomo
        except Exception:
            pytest.skip("mlx_vomo não disponível para testes")


@pytest.fixture
def svc():
    """Cria instância mínima de TranscriptionService."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}):
        from app.services.transcription_service import TranscriptionService
        return TranscriptionService.__new__(TranscriptionService)


class TestWhisperPromptExtraTerms:
    """Testa que extra_terms são concatenados ao prompt base."""

    def test_extra_terms_appended_with_mode_prompt(self, vomo_instance):
        """Com high_accuracy + extra_terms, ambos devem aparecer no prompt."""
        result = vomo_instance._get_whisper_initial_prompt_for_asr(
            high_accuracy=True,
            extra_terms="Termos técnicos: STF, STJ, OAB",
        )
        assert result is not None
        # Deve conter tanto o prompt de modo quanto os termos
        assert "Transcrição" in result  # prompt base de APOSTILA
        assert "STF" in result

    def test_extra_terms_alone_without_mode_prompt(self, vomo_instance):
        """Sem high_accuracy e sem VOMO_WHISPER_USE_MODE_PROMPT, extra_terms sozinho."""
        result = vomo_instance._get_whisper_initial_prompt_for_asr(
            high_accuracy=False,
            extra_terms="Termos técnicos: habeas corpus",
        )
        assert result is not None
        assert "habeas corpus" in result

    def test_no_extra_terms_default_behavior(self, vomo_instance):
        """Sem extra_terms, comportamento padrão mantido."""
        result_no_ha = vomo_instance._get_whisper_initial_prompt_for_asr(
            high_accuracy=False,
        )
        # Sem high_accuracy e sem extra_terms → None
        assert result_no_ha is None

        result_ha = vomo_instance._get_whisper_initial_prompt_for_asr(
            high_accuracy=True,
        )
        # Com high_accuracy → prompt de modo
        assert result_ha is not None
        assert "Transcrição" in result_ha

    def test_explicit_env_prompt_plus_extra_terms(self, vomo_instance):
        """VOMO_WHISPER_INITIAL_PROMPT env + extra_terms são combinados."""
        with patch.dict("os.environ", {"VOMO_WHISPER_INITIAL_PROMPT": "My explicit prompt"}):
            result = vomo_instance._get_whisper_initial_prompt_for_asr(
                high_accuracy=False,
                extra_terms="Termos técnicos: STF",
            )
            assert "My explicit prompt" in result
            assert "STF" in result

    def test_explicit_env_prompt_without_extra_terms(self, vomo_instance):
        """VOMO_WHISPER_INITIAL_PROMPT sem extra_terms retorna só o env."""
        with patch.dict("os.environ", {"VOMO_WHISPER_INITIAL_PROMPT": "My prompt"}):
            result = vomo_instance._get_whisper_initial_prompt_for_asr(
                high_accuracy=False,
            )
            assert result == "My prompt"


class TestNoGlobalState:
    """Verifica que não há estado mutável global — tudo via params explícitos."""

    def test_two_calls_different_terms_independent(self, vomo_instance):
        """Duas chamadas com extra_terms diferentes produzem resultados diferentes."""
        result_a = vomo_instance._get_whisper_initial_prompt_for_asr(
            high_accuracy=True,
            extra_terms="Termos técnicos: STF, STJ",
        )
        result_b = vomo_instance._get_whisper_initial_prompt_for_asr(
            high_accuracy=True,
            extra_terms="Termos técnicos: habeas corpus",
        )
        assert result_a != result_b
        assert "STF" in result_a
        assert "habeas corpus" in result_b

    def test_no_request_hints_attribute(self, vomo_instance):
        """Não deve existir atributo _request_hints_prompt no vomo."""
        assert not hasattr(vomo_instance, "_request_hints_prompt")


class TestMethodSignatures:
    """Testa que as APIs públicas aceitam extra_terms."""

    def test_transcribe_with_segments_accepts_extra_terms(self, vomo_instance):
        """transcribe_with_segments deve aceitar extra_terms como keyword arg."""
        import inspect
        sig = inspect.signature(vomo_instance.transcribe_with_segments)
        assert "extra_terms" in sig.parameters

    def test_transcribe_beam_with_segments_accepts_extra_terms(self, vomo_instance):
        """transcribe_beam_with_segments deve aceitar extra_terms."""
        import inspect
        sig = inspect.signature(vomo_instance.transcribe_beam_with_segments)
        assert "extra_terms" in sig.parameters

    def test_transcribe_accepts_extra_terms(self, vomo_instance):
        """transcribe deve aceitar extra_terms."""
        import inspect
        sig = inspect.signature(vomo_instance.transcribe)
        assert "extra_terms" in sig.parameters

    def test_transcribe_file_full_accepts_extra_terms(self, vomo_instance):
        """transcribe_file_full deve aceitar extra_terms."""
        import inspect
        sig = inspect.signature(vomo_instance.transcribe_file_full)
        assert "extra_terms" in sig.parameters


class TestServiceWhisperHints:
    """Testa integração no transcription_service."""

    def test_whisper_normalize_hints_provider_limit(self, svc):
        """Whisper deve limitar keyterms a 50."""
        many_terms = [f"term_{i}" for i in range(100)]
        hints = svc._normalize_hints(
            custom_keyterms=many_terms,
            provider="whisper",
        )
        assert len(hints["keyterms"]) == 50

    def test_hearing_accepts_area_and_keyterms(self, svc):
        """process_hearing_with_progress deve aceitar area e custom_keyterms."""
        import inspect
        sig = inspect.signature(svc.process_hearing_with_progress)
        assert "area" in sig.parameters
        assert "custom_keyterms" in sig.parameters

    def test_whisper_diarization_method_accepts_hints(self, svc):
        """_transcribe_whisper_with_optional_external_diarization deve aceitar area/keyterms."""
        import inspect
        sig = inspect.signature(svc._transcribe_whisper_with_optional_external_diarization)
        assert "area" in sig.parameters
        assert "custom_keyterms" in sig.parameters
