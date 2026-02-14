"""
Testes para o módulo de pós-processamento de transcrição.

Cobre:
  - Dicionário jurídico (correções de termos legais)
  - Restauração de pontuação
  - Normalização de siglas
  - Pipeline completo
  - Detecção de segmentos suspeitos (heurística)
"""

import pytest
from app.services.transcription_postprocessing import (
    apply_legal_dictionary,
    restore_punctuation,
    normalize_acronyms,
    postprocess_transcription,
    postprocess_segment,
    _find_suspicious_segments,
)


class TestLegalDictionary:
    def test_agravo_split(self):
        text, count = apply_legal_dictionary("O a gravo foi interposto.")
        assert "agravo" in text
        assert count >= 1

    def test_embargo_split(self):
        text, count = apply_legal_dictionary("Os em bargos foram opostos.")
        assert "embargos" in text
        assert count >= 1

    def test_mandado_split(self):
        text, count = apply_legal_dictionary("O man dado de segurança.")
        assert "mandado" in text
        assert count >= 1

    def test_stf_spelled_out(self):
        text, count = apply_legal_dictionary("O est é efe decidiu.")
        assert "STF" in text
        assert count >= 1

    def test_habeas_corpus_variants(self):
        text, count = apply_legal_dictionary("O havias corpus foi impetrado.")
        assert "habeas corpus" in text
        assert count >= 1

    def test_no_changes_on_clean_text(self):
        original = "O recurso especial foi provido pelo STJ."
        text, count = apply_legal_dictionary(original)
        assert text == original
        assert count == 0

    def test_multiple_corrections(self):
        text, count = apply_legal_dictionary("O a gravo e o em bargo foram julgados.")
        assert "agravo" in text
        assert "embargo" in text
        assert count >= 2

    def test_competencia_split(self):
        text, count = apply_legal_dictionary("A com petência é do tribunal.")
        assert "competência" in text
        assert count >= 1


class TestPunctuationRestoration:
    def test_adds_period_before_artigo(self):
        text = restore_punctuation("foi decidido Artigo 5")
        assert ". Artigo" in text

    def test_comma_before_conjunction(self):
        text = restore_punctuation("o recurso porém não foi aceito")
        assert ", porém" in text

    def test_normalizes_multiple_spaces(self):
        text = restore_punctuation("o   recurso   foi   julgado")
        assert "  " not in text

    def test_preserves_already_punctuated(self):
        text = restore_punctuation("O recurso foi julgado. A sentença foi proferida.")
        assert text.count(".") >= 2


class TestAcronymNormalization:
    def test_uppercase_stf(self):
        result = normalize_acronyms("O stf decidiu o caso.")
        assert "STF" in result

    def test_uppercase_stj(self):
        result = normalize_acronyms("Recurso ao stj.")
        assert "STJ" in result

    def test_uppercase_cpc(self):
        result = normalize_acronyms("Conforme o cpc.")
        assert "CPC" in result

    def test_preserves_already_uppercase(self):
        result = normalize_acronyms("O STF e o STJ decidiram.")
        assert "STF" in result
        assert "STJ" in result

    def test_preserves_non_acronyms(self):
        result = normalize_acronyms("O juiz decidiu o caso.")
        assert result == "O juiz decidiu o caso."

    def test_handles_punctuation_around_acronym(self):
        result = normalize_acronyms("conforme oab, o cpc prevê.")
        assert "OAB" in result
        assert "CPC" in result


class TestPostprocessSegment:
    def test_applies_dictionary_to_segment(self):
        seg = {"start": 0, "end": 1, "text": "O a gravo foi interposto."}
        result = postprocess_segment(seg)
        assert "agravo" in result["text"]

    def test_preserves_other_fields(self):
        seg = {"start": 0.5, "end": 2.0, "text": "Texto normal.", "speaker": "SPEAKER_00"}
        result = postprocess_segment(seg)
        assert result["start"] == 0.5
        assert result["end"] == 2.0
        assert result["speaker"] == "SPEAKER_00"

    def test_empty_text_unchanged(self):
        seg = {"start": 0, "end": 0, "text": ""}
        result = postprocess_segment(seg)
        assert result["text"] == ""


class TestPostprocessTranscription:
    def test_full_pipeline(self):
        result = {
            "text": "O a gravo do stf foi julgado",
            "segments": [
                {"start": 0, "end": 2, "text": "O a gravo do stf"},
                {"start": 2, "end": 4, "text": "foi julgado"},
            ],
            "language": "pt",
        }
        processed = postprocess_transcription(result)

        assert "agravo" in processed["text"]
        assert "STF" in processed["text"]
        assert "agravo" in processed["segments"][0]["text"]
        assert "postprocessing" in processed

    def test_empty_text_returns_unchanged(self):
        result = {"text": "", "segments": []}
        processed = postprocess_transcription(result)
        assert processed["text"] == ""

    def test_preserves_extra_fields(self):
        result = {
            "text": "Texto normal sem correções.",
            "segments": [],
            "language": "pt",
            "speakers": ["SPEAKER_00"],
            "has_diarization": True,
        }
        processed = postprocess_transcription(result)
        assert processed["language"] == "pt"
        assert processed["speakers"] == ["SPEAKER_00"]
        assert processed["has_diarization"] is True


class TestSuspiciousSegments:
    def test_detects_short_segments(self):
        segments = [
            {"start": 0.0, "end": 5.0, "text": "Texto normal longo o suficiente."},
            {"start": 5.0, "end": 5.3, "text": "ah"},
            {"start": 5.3, "end": 10.0, "text": "Outro segmento normal."},
        ]
        suspicious = _find_suspicious_segments(segments, duration=10.0)
        assert 1 in suspicious

    def test_detects_repeated_text(self):
        segments = [
            {"start": 0.0, "end": 2.0, "text": "Obrigado."},
            {"start": 2.0, "end": 4.0, "text": "Obrigado."},
            {"start": 4.0, "end": 6.0, "text": "Obrigado."},
        ]
        suspicious = _find_suspicious_segments(segments, duration=6.0)
        assert len(suspicious) >= 2

    def test_detects_end_of_audio_segments(self):
        segments = [
            {"start": 0.0, "end": 50.0, "text": "Longo segmento normal."},
            {"start": 57.0, "end": 60.0, "text": "Algo no final."},
        ]
        suspicious = _find_suspicious_segments(segments, duration=60.0)
        assert 1 in suspicious

    def test_no_suspicious_on_clean_audio(self):
        segments = [
            {"start": 0.0, "end": 5.0, "text": "O ministro relator proferiu o voto."},
            {"start": 5.0, "end": 10.0, "text": "A turma acompanhou o relator."},
            {"start": 10.0, "end": 15.0, "text": "Recurso especial provido."},
        ]
        suspicious = _find_suspicious_segments(segments, duration=60.0)
        assert len(suspicious) == 0
