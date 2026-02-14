"""Tests for _normalize_hints() and enriched cache hash functions (Fase 1)."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def svc():
    """Cria instância mínima de TranscriptionService com stubs."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}):
        from app.services.transcription_service import TranscriptionService
        return TranscriptionService.__new__(TranscriptionService)


# ── _normalize_hints ──────────────────────────────────────────────────────


class TestNormalizeHintsEmpty:
    def test_empty_returns_empty(self, svc):
        result = svc._normalize_hints()
        assert result["keyterms"] == []
        assert result["initial_prompt"] == ""
        assert result["hotwords"] == ""
        assert result["fingerprint"] == ""


class TestNormalizeHintsAreaOnly:
    def test_juridico_returns_area_terms(self, svc):
        result = svc._normalize_hints(area="juridico")
        assert len(result["keyterms"]) > 0
        assert "STF" in result["keyterms"]
        assert result["fingerprint"] != ""

    def test_unknown_area_returns_empty(self, svc):
        result = svc._normalize_hints(area="desconhecida")
        assert result["keyterms"] == []


class TestNormalizeHintsCustomOnly:
    def test_custom_keyterms_returned(self, svc):
        result = svc._normalize_hints(custom_keyterms=["LGPD", "Marco Civil"])
        assert result["keyterms"] == ["LGPD", "Marco Civil"]

    def test_empty_strings_filtered(self, svc):
        result = svc._normalize_hints(custom_keyterms=["", "  ", "LGPD", None])
        assert result["keyterms"] == ["LGPD"]


class TestNormalizeHintsMergeDedup:
    def test_dedup_preserves_order(self, svc):
        result = svc._normalize_hints(
            area="juridico",
            custom_keyterms=["STF", "LGPD"],  # STF duplicado
        )
        # STF aparece só uma vez, na posição da área (primeiro)
        assert result["keyterms"].count("STF") == 1
        assert "LGPD" in result["keyterms"]


class TestNormalizeHintsSpeakerNames:
    def test_speaker_names_included(self, svc):
        result = svc._normalize_hints(speaker_names=["Dr. Silva", "Dra. Costa"])
        assert "Dr. Silva" in result["keyterms"]
        assert "Dra. Costa" in result["keyterms"]


class TestNormalizeHintsProviderLimits:
    def test_assemblyai_limit_1000(self, svc):
        big_list = [f"term_{i}" for i in range(1500)]
        result = svc._normalize_hints(custom_keyterms=big_list, provider="assemblyai")
        assert len(result["keyterms"]) == 1000

    def test_whisper_limit_50(self, svc):
        big_list = [f"term_{i}" for i in range(100)]
        result = svc._normalize_hints(custom_keyterms=big_list, provider="whisper")
        assert len(result["keyterms"]) == 50

    def test_runpod_limit_200(self, svc):
        big_list = [f"term_{i}" for i in range(300)]
        result = svc._normalize_hints(custom_keyterms=big_list, provider="runpod")
        assert len(result["keyterms"]) == 200

    def test_elevenlabs_limit_100(self, svc):
        big_list = [f"term_{i}" for i in range(150)]
        result = svc._normalize_hints(custom_keyterms=big_list, provider="elevenlabs")
        assert len(result["keyterms"]) == 100


class TestNormalizeHintsFingerprint:
    def test_fingerprint_stable(self, svc):
        r1 = svc._normalize_hints(custom_keyterms=["A", "B"])
        r2 = svc._normalize_hints(custom_keyterms=["A", "B"])
        assert r1["fingerprint"] == r2["fingerprint"]

    def test_fingerprint_order_independent(self, svc):
        """Fingerprint usa sorted(), então ordem de input não importa."""
        r1 = svc._normalize_hints(custom_keyterms=["B", "A"])
        r2 = svc._normalize_hints(custom_keyterms=["A", "B"])
        assert r1["fingerprint"] == r2["fingerprint"]

    def test_fingerprint_differs_for_different_terms(self, svc):
        r1 = svc._normalize_hints(custom_keyterms=["A"])
        r2 = svc._normalize_hints(custom_keyterms=["B"])
        assert r1["fingerprint"] != r2["fingerprint"]


class TestNormalizeHintsOutputFormats:
    def test_initial_prompt_format(self, svc):
        result = svc._normalize_hints(custom_keyterms=["STF", "STJ"])
        assert result["initial_prompt"].startswith("Termos técnicos:")
        assert "STF" in result["initial_prompt"]

    def test_hotwords_comma_separated(self, svc):
        result = svc._normalize_hints(custom_keyterms=["STF", "STJ"])
        assert result["hotwords"] == "STF, STJ"

    def test_whisper_initial_prompt_truncated(self, svc):
        big_list = [f"termo_muito_longo_{i}" for i in range(100)]
        result = svc._normalize_hints(custom_keyterms=big_list, provider="whisper")
        assert len(result["initial_prompt"]) <= 500


# ── _hash_list / _hash_spelling ──────────────────────────────────────────


class TestHashHelpers:
    def test_hash_list_empty(self, svc):
        assert svc._hash_list(None) == ""
        assert svc._hash_list([]) == ""

    def test_hash_list_stable(self, svc):
        h1 = svc._hash_list(["a", "b"])
        h2 = svc._hash_list(["a", "b"])
        assert h1 == h2
        assert len(h1) == 8

    def test_hash_list_order_independent(self, svc):
        """_hash_list sorts internally."""
        h1 = svc._hash_list(["b", "a"])
        h2 = svc._hash_list(["a", "b"])
        assert h1 == h2

    def test_hash_list_differs(self, svc):
        h1 = svc._hash_list(["a"])
        h2 = svc._hash_list(["b"])
        assert h1 != h2

    def test_hash_spelling_empty(self, svc):
        assert svc._hash_spelling(None) == ""
        assert svc._hash_spelling([]) == ""

    def test_hash_spelling_stable(self, svc):
        pairs = [{"from": "Sequel", "to": "SQL"}]
        h1 = svc._hash_spelling(pairs)
        h2 = svc._hash_spelling(pairs)
        assert h1 == h2
        assert len(h1) == 8

    def test_hash_spelling_differs(self, svc):
        h1 = svc._hash_spelling([{"from": "a", "to": "b"}])
        h2 = svc._hash_spelling([{"from": "x", "to": "y"}])
        assert h1 != h2


# ── Cache hash functions ──────────────────────────────────────────────────


class TestAAIConfigHash:
    def test_includes_hints(self, svc):
        h1 = svc._get_aai_config_hash(hints_fingerprint="abc12345")
        h2 = svc._get_aai_config_hash(hints_fingerprint="")
        assert h1 != h2

    def test_includes_speaker_id(self, svc):
        h1 = svc._get_aai_config_hash(speaker_id_type="name", speaker_id_values_hash="abc")
        h2 = svc._get_aai_config_hash(speaker_id_type=None, speaker_id_values_hash="")
        assert h1 != h2

    def test_includes_custom_spelling(self, svc):
        h1 = svc._get_aai_config_hash(custom_spelling_hash="abc12345")
        h2 = svc._get_aai_config_hash(custom_spelling_hash="")
        assert h1 != h2

    def test_includes_prompt_mode(self, svc):
        h1 = svc._get_aai_config_hash(prompt_mode="keyterms_only")
        h2 = svc._get_aai_config_hash(prompt_mode="prompt_only")
        assert h1 != h2

    def test_backwards_compat_defaults(self, svc):
        """Hash com defaults deve ser determinístico."""
        h1 = svc._get_aai_config_hash()
        h2 = svc._get_aai_config_hash()
        assert h1 == h2
        assert len(h1) == 8

    def test_differs_when_speaker_values_change(self, svc):
        h1 = svc._get_aai_config_hash(
            speaker_id_type="name",
            speaker_id_values_hash=svc._hash_list(["Dr. Silva", "Dra. Costa"]),
        )
        h2 = svc._get_aai_config_hash(
            speaker_id_type="name",
            speaker_id_values_hash=svc._hash_list(["Dr. Santos"]),
        )
        assert h1 != h2


class TestElevenLabsConfigHash:
    def test_includes_model(self, svc):
        h1 = svc._get_elevenlabs_config_hash(model_id="scribe_v1")
        h2 = svc._get_elevenlabs_config_hash(model_id="scribe_v2")
        assert h1 != h2

    def test_includes_hints(self, svc):
        h1 = svc._get_elevenlabs_config_hash(hints_fingerprint="abc")
        h2 = svc._get_elevenlabs_config_hash(hints_fingerprint="")
        assert h1 != h2

    def test_includes_speaker_id(self, svc):
        h1 = svc._get_elevenlabs_config_hash(
            speaker_id_type="role", speaker_id_values_hash="abc"
        )
        h2 = svc._get_elevenlabs_config_hash()
        assert h1 != h2


class TestWhisperServerConfigHash:
    def test_includes_hints(self, svc):
        h1 = svc._get_whisper_server_config_hash(hints_fingerprint="abc")
        h2 = svc._get_whisper_server_config_hash(hints_fingerprint="")
        assert h1 != h2

    def test_backwards_compat(self, svc):
        """Hash com defaults é determinístico."""
        h1 = svc._get_whisper_server_config_hash()
        h2 = svc._get_whisper_server_config_hash()
        assert h1 == h2
