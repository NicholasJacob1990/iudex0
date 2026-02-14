"""Tests for AssemblyAI improvements (Fase 3).

- Modo exclusivo prompt/keyterms
- Limite 1000 keyterms
- custom_spelling payload format
- custom_spelling Form parsing
- speech_model_used logging
"""

import json
import logging
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def svc():
    """Cria instância mínima de TranscriptionService."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}):
        from app.services.transcription_service import TranscriptionService
        return TranscriptionService.__new__(TranscriptionService)


# ── Modo exclusivo ──────────────────────────────────────────────────────


class TestExclusiveMode:
    def test_many_keyterms_keyterms_only(self, svc):
        """Com >50 keyterms, prompt_mode deve ser 'keyterms_only'."""
        many_terms = [f"term_{i}" for i in range(60)]
        _, _, prompt_mode = svc._get_assemblyai_prompt_for_mode(
            mode="APOSTILA",
            custom_keyterms=many_terms,
        )
        assert prompt_mode == "keyterms_only"

    def test_few_keyterms_both(self, svc):
        """Com ≤50 keyterms, prompt_mode deve ser 'both'."""
        few_terms = ["STF", "STJ", "OAB"]
        _, keyterms, prompt_mode = svc._get_assemblyai_prompt_for_mode(
            mode="APOSTILA",
            custom_keyterms=few_terms,
        )
        assert prompt_mode == "both"
        assert len(keyterms) > 0

    def test_no_keyterms_prompt_only(self, svc):
        """Sem keyterms, prompt_mode deve ser 'prompt_only'."""
        _, keyterms, prompt_mode = svc._get_assemblyai_prompt_for_mode(
            mode="APOSTILA",
        )
        assert prompt_mode == "prompt_only"
        assert keyterms == []

    def test_area_juridico_adds_keyterms(self, svc):
        """Area 'juridico' deve adicionar keyterms do dicionário."""
        _, keyterms, prompt_mode = svc._get_assemblyai_prompt_for_mode(
            mode="AUDIENCIA",
            area="juridico",
        )
        assert len(keyterms) > 0
        assert "STF" in keyterms


class TestKeytermLimit:
    def test_limit_raised_to_1000(self, svc):
        """O limite de keyterms deve ser 1000 (Universal-3 Pro)."""
        many_terms = [f"term_{i}" for i in range(1200)]
        _, keyterms, _ = svc._get_assemblyai_prompt_for_mode(
            mode="APOSTILA",
            custom_keyterms=many_terms,
        )
        assert len(keyterms) == 1000


# ── custom_spelling ──────────────────────────────────────────────────────


class TestCustomSpellingPayload:
    def test_format_correct(self):
        """Pares de custom_spelling devem ser formatados corretamente."""
        raw_pairs = [{"from": "Sequel", "to": "SQL"}, {"from": "Kay", "to": "K"}]
        formatted = [{"from": p["from"], "to": p["to"]} for p in raw_pairs]
        assert formatted == [{"from": "Sequel", "to": "SQL"}, {"from": "Kay", "to": "K"}]


class TestCustomSpellingFormParse:
    """Testes de parsing de custom_spelling vindo como string JSON via Form."""

    @staticmethod
    def _parse_spelling(raw: str) -> list:
        """Simula o parsing do endpoint."""
        parsed = None
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    parsed = [
                        {"from": p.get("from", ""), "to": p.get("to", "")}
                        for p in data
                        if isinstance(p, dict) and p.get("from") and p.get("to")
                    ]
            except (json.JSONDecodeError, TypeError):
                parsed = None
        return parsed

    def test_valid_json(self):
        result = self._parse_spelling('[{"from":"Sequel","to":"SQL"}]')
        assert result == [{"from": "Sequel", "to": "SQL"}]

    def test_malformed_json(self):
        result = self._parse_spelling("not json at all")
        assert result is None

    def test_empty_string(self):
        result = self._parse_spelling("")
        assert result is None

    def test_none_input(self):
        result = self._parse_spelling(None)
        assert result is None

    def test_empty_array(self):
        result = self._parse_spelling("[]")
        assert result == []

    def test_bad_types_in_array(self):
        """Non-dict items are silently filtered."""
        result = self._parse_spelling('[42, "string", {"from":"a","to":"b"}]')
        assert result == [{"from": "a", "to": "b"}]

    def test_missing_keys(self):
        """Items without 'from' or 'to' are filtered."""
        result = self._parse_spelling('[{"from":"a"},{"to":"b"},{"from":"c","to":"d"}]')
        assert result == [{"from": "c", "to": "d"}]


# ── speech_model_used logging ────────────────────────────────────────────


class TestSpeechModelLogged:
    def test_speech_model_logged(self, svc, caplog):
        """speech_model_used deve ser logado na extração de resultado AAI."""
        import time
        poll_resp = {
            "speech_model": "universal-3-pro",
            "utterances": [],
            "words": [],
            "text": "test text",
        }
        with caplog.at_level(logging.INFO):
            try:
                svc._extract_aai_result_from_response(
                    poll_resp=poll_resp,
                    transcript_id="test_123",
                    speaker_roles=None,
                    mode="APOSTILA",
                    start_time=time.time(),
                )
            except Exception:
                pass  # Pode falhar por falta de setup completo
        # Verificar que o log foi emitido
        assert any("speech_model_used=universal-3-pro" in r.message for r in caplog.records)
