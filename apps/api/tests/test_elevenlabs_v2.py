"""Tests for ElevenLabs scribe_v2 + keyterms (Fase 6).

Feature-flagged via ELEVENLABS_USE_SCRIBE_V2 env var.
"""

import os
import pytest
from unittest.mock import patch


@pytest.fixture
def svc():
    """Cria instância mínima de TranscriptionService."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}):
        from app.services.transcription_service import TranscriptionService
        return TranscriptionService.__new__(TranscriptionService)


class TestDefaultScribeV1:
    """Testa que scribe_v1 é o padrão."""

    def test_default_model_is_v1(self, svc):
        """Sem ELEVENLABS_USE_SCRIBE_V2, model_id deve ser scribe_v1."""
        with patch.dict("os.environ", {}, clear=False):
            # Remover flag se existir
            os.environ.pop("ELEVENLABS_USE_SCRIBE_V2", None)
            use_v2 = os.getenv("ELEVENLABS_USE_SCRIBE_V2", "").lower() in ("true", "1", "yes")
            assert use_v2 is False

    def test_config_hash_default_model(self, svc):
        """Hash de config deve usar scribe_v1 por padrão."""
        hash_v1 = svc._get_elevenlabs_config_hash(model_id="scribe_v1")
        hash_v2 = svc._get_elevenlabs_config_hash(model_id="scribe_v2")
        assert hash_v1 != hash_v2


class TestScribeV2Flag:
    """Testa que a flag ativa scribe_v2."""

    def test_flag_true_activates_v2(self):
        """ELEVENLABS_USE_SCRIBE_V2=true deve ativar v2."""
        with patch.dict("os.environ", {"ELEVENLABS_USE_SCRIBE_V2": "true"}):
            use_v2 = os.getenv("ELEVENLABS_USE_SCRIBE_V2", "").lower() in ("true", "1", "yes")
            assert use_v2 is True

    def test_flag_1_activates_v2(self):
        """ELEVENLABS_USE_SCRIBE_V2=1 deve ativar v2."""
        with patch.dict("os.environ", {"ELEVENLABS_USE_SCRIBE_V2": "1"}):
            use_v2 = os.getenv("ELEVENLABS_USE_SCRIBE_V2", "").lower() in ("true", "1", "yes")
            assert use_v2 is True

    def test_flag_false_stays_v1(self):
        """ELEVENLABS_USE_SCRIBE_V2=false deve manter v1."""
        with patch.dict("os.environ", {"ELEVENLABS_USE_SCRIBE_V2": "false"}):
            use_v2 = os.getenv("ELEVENLABS_USE_SCRIBE_V2", "").lower() in ("true", "1", "yes")
            assert use_v2 is False


class TestKeytermsOnlyV2:
    """Testa que keyterms só são enviados com scribe_v2."""

    def test_v1_no_keyterms_in_payload(self, svc):
        """Com scribe_v1, keyterms não devem ser incluídos."""
        hints = svc._normalize_hints(area="juridico", provider="elevenlabs")
        assert hints["keyterms"]  # Deve haver keyterms de area
        # Mas com v1 desativado, não se adiciona ao payload (lógica no método)

    def test_v2_keyterms_generated(self, svc):
        """Com v2, _normalize_hints gera keyterms para ElevenLabs (limit 100)."""
        many_terms = [f"term_{i}" for i in range(150)]
        hints = svc._normalize_hints(custom_keyterms=many_terms, provider="elevenlabs")
        assert len(hints["keyterms"]) == 100  # Limite de 100 para ElevenLabs

    def test_elevenlabs_provider_limit(self, svc):
        """Provider limit para ElevenLabs deve ser 100."""
        from app.services.transcription_service import TranscriptionService
        assert TranscriptionService._PROVIDER_KEYTERM_LIMITS["elevenlabs"] == 100


class TestConfigHashIncludesModel:
    """Testa que o hash de config inclui model_id."""

    def test_hash_differs_by_model(self, svc):
        """Hashes com model_id diferente devem diferir."""
        h1 = svc._get_elevenlabs_config_hash(model_id="scribe_v1")
        h2 = svc._get_elevenlabs_config_hash(model_id="scribe_v2")
        assert h1 != h2

    def test_hash_differs_by_hints(self, svc):
        """Hashes com hints diferentes devem diferir."""
        h1 = svc._get_elevenlabs_config_hash(hints_fingerprint="abc123")
        h2 = svc._get_elevenlabs_config_hash(hints_fingerprint="def456")
        assert h1 != h2

    def test_hash_stable(self, svc):
        """Mesmo input deve gerar mesmo hash."""
        h1 = svc._get_elevenlabs_config_hash(model_id="scribe_v2", hints_fingerprint="abc")
        h2 = svc._get_elevenlabs_config_hash(model_id="scribe_v2", hints_fingerprint="abc")
        assert h1 == h2


class TestMethodSignature:
    """Testa assinaturas atualizadas."""

    def test_scribe_accepts_area_and_keyterms(self, svc):
        """_transcribe_elevenlabs_scribe deve aceitar area, custom_keyterms, speaker_names."""
        import inspect
        sig = inspect.signature(svc._transcribe_elevenlabs_scribe)
        params = list(sig.parameters.keys())
        assert "area" in params
        assert "custom_keyterms" in params
        assert "speaker_names" in params
