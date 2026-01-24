"""
Testes para FidelityMatcher - validação de matching fuzzy para referências legais.
"""
import pytest
from app.services.fidelity_matcher import FidelityMatcher, validate_issues_batch


class TestFidelityMatcher:
    """Testes para a classe FidelityMatcher."""
    
    def test_extract_digits(self):
        """Testa extração de dígitos."""
        assert FidelityMatcher.extract_digits("tema 1070") == "1070"
        assert FidelityMatcher.extract_digits("Art. 345") == "345"
        assert FidelityMatcher.extract_digits("Lei 13.465/2017") == "134652017"
        assert FidelityMatcher.extract_digits("ADPF 1.063") == "1063"
        assert FidelityMatcher.extract_digits("") == ""
    
    def test_build_fuzzy_pattern(self):
        """Testa criação de padrão fuzzy."""
        pattern = FidelityMatcher.build_fuzzy_pattern("1070")
        # Deve aceitar separadores entre dígitos
        assert "1" in pattern
        assert "0" in pattern
        assert "7" in pattern
    
    def test_detect_reference_type(self):
        """Testa detecção automática de tipo de referência."""
        assert FidelityMatcher.detect_reference_type("tema 1070") == "tema"
        assert FidelityMatcher.detect_reference_type("Tema 1.070 do STF") == "tema"
        assert FidelityMatcher.detect_reference_type("Art. 345") == "artigo"
        assert FidelityMatcher.detect_reference_type("artigo 182") == "artigo"
        assert FidelityMatcher.detect_reference_type("ADPF 1063") == "adpf"
        assert FidelityMatcher.detect_reference_type("Lei 13.465") == "lei"
        assert FidelityMatcher.detect_reference_type("Súmula 331") == "sumula"
        assert FidelityMatcher.detect_reference_type("Decreto 9.310") == "decreto"
    
    def test_exists_in_text_tema_basic(self):
        """Testa matching básico de tema."""
        text = "O tema 1070 do STF estabelece..."
        
        # Matching exato
        exists, matched = FidelityMatcher.exists_in_text("tema 1070", text)
        assert exists is True
        assert "1070" in matched.lower()
    
    def test_exists_in_text_tema_with_dot(self):
        """Testa matching de tema com ponto decimal (falso positivo comum)."""
        # Texto formatado usa ponto como separador de milhar
        formatted_text = "O **Tema 1.070 do STF** decidiu que..."
        
        # RAW usa sem ponto
        exists, matched = FidelityMatcher.exists_in_text("tema 1070", formatted_text)
        assert exists is True, "Deveria encontrar '1070' mesmo formatado como '1.070'"
        assert "1" in matched and "0" in matched and "7" in matched
    
    def test_exists_in_text_adpf(self):
        """Testa matching de ADPF."""
        text = "A ADPF 1063 julgou..."
        
        exists, matched = FidelityMatcher.exists_in_text("ADPF 1063", text)
        assert exists is True
    
    def test_exists_in_text_artigo(self):
        """Testa matching de artigo com variações."""
        text = "Conforme o Art. 345 do Plano Diretor..."
        
        # "artigo 345" deve encontrar "Art. 345"
        exists, matched = FidelityMatcher.exists_in_text("artigo 345", text)
        assert exists is True
    
    def test_exists_in_text_lei(self):
        """Testa matching de lei com número composto."""
        text = "A Lei nº 13.465/2017 regulamenta..."
        
        exists, matched = FidelityMatcher.exists_in_text("Lei 13465", text)
        assert exists is True
    
    def test_exists_in_text_not_found(self):
        """Testa quando referência não existe."""
        text = "Este texto não menciona nenhum tema."
        
        exists, matched = FidelityMatcher.exists_in_text("tema 999", text)
        assert exists is False
        assert matched is None
    
    def test_validate_issue_false_positive(self):
        """Testa detecção de falso positivo."""
        raw_text = "O tema 1070 do STF..."
        formatted_text = "O **Tema 1.070 do STF** estabelece..."
        
        issue = {
            "type": "missing_julgado",
            "reference": "tema 1070",
            "description": "Julgado possivelmente ausente: tema 1070"
        }
        
        validated = FidelityMatcher.validate_issue(issue, raw_text, formatted_text)
        
        assert validated["is_false_positive"] is True
        assert "Encontrado no formatado" in validated["validation_evidence"]
    
    def test_validate_issue_real_omission(self):
        """Testa detecção de omissão real."""
        raw_text = "O tema 1070 do STF... e o Art. 21, XI da CF/88..."
        formatted_text = "O **Tema 1.070 do STF** estabelece..."  # Art. 21 omitido
        
        issue = {
            "type": "missing_law",
            "reference": "Art. 21",
            "description": "Lei possivelmente ausente: Art. 21, XI"
        }
        
        validated = FidelityMatcher.validate_issue(issue, raw_text, formatted_text)
        
        # Art. 21 está no RAW mas não no formatado = omissão real
        assert validated["is_false_positive"] is False
    
    def test_filter_false_positives(self):
        """Testa filtragem em lote."""
        raw_text = "tema 1070... ADPF 1063... Art. 21, XI..."
        formatted_text = "Tema 1.070... ADPF 1.063..."  # Art. 21 omitido
        
        issues = [
            {"type": "missing_julgado", "reference": "tema 1070"},
            {"type": "missing_julgado", "reference": "ADPF 1063"},
            {"type": "missing_law", "reference": "Art. 21"},
        ]
        
        real, false_pos = FidelityMatcher.filter_false_positives(
            issues, raw_text, formatted_text
        )
        
        # tema 1070 e ADPF 1063 são falsos positivos (existem no formatado)
        # Art. 21 é omissão real
        assert len(false_pos) == 2
        assert len(real) == 1
        assert real[0]["reference"] == "Art. 21"


class TestValidateIssuesBatch:
    """Testes para a função utilitária validate_issues_batch."""
    
    def test_batch_validation(self):
        """Testa validação em lote."""
        raw = "tema 815... tema 1070..."
        formatted = "Tema 815... Tema 1.070..."
        
        issues = [
            {"type": "missing_julgado", "reference": "tema 815"},
            {"type": "missing_julgado", "reference": "tema 1070"},
        ]
        
        result = validate_issues_batch(issues, raw, formatted)
        
        assert result["total_original"] == 2
        assert result["total_false_positives"] == 2
        assert result["total_real"] == 0


class TestRealWorldCases:
    """Testes com casos reais do job f8d62a74."""
    
    def test_tema_1070_case(self):
        """Caso real: tema 1070 vs Tema 1.070."""
        raw = (
            "Competência para dar o nome, falei para vocês, é o tema 1070 do STF. "
            "É comum aos poderes executivos e legislativo..."
        )
        formatted = (
            "reforço a questão da competência para nomear logradouros, tratada no "
            "**Tema 1.070 do STF**. O Supremo decidiu que é comum aos poderes "
            "Executivo e Legislativo..."
        )
        
        exists, matched = FidelityMatcher.exists_in_text("tema 1070", formatted)
        assert exists is True, f"Falso positivo! tema 1070 existe como: {matched}"
    
    def test_adpf_1063_case(self):
        """Caso real: ADPF 1063 - era marcado como alucinação mas existe no RAW."""
        raw = (
            "Artigo 380 vai trazer o regramento da zona especial de interesse social. "
            "E aí, em relação ao zoneamento, a gente tem uma questão importante, "
            "recente, enfrentada pelo STF. ADPF 1063. Leiam. É importante."
        )
        formatted = (
            "Recentemente, o STF enfrentou uma questão polêmica na **ADPF 1063** e no "
            "**Tema 919** de Repercussão Geral..."
        )
        
        # Verifica que ADPF 1063 existe em ambos
        exists_raw, _ = FidelityMatcher.exists_in_text("ADPF 1063", raw)
        exists_fmt, _ = FidelityMatcher.exists_in_text("ADPF 1063", formatted)
        
        assert exists_raw is True, "ADPF 1063 deveria estar no RAW"
        assert exists_fmt is True, "ADPF 1063 deveria estar no formatado"
    
    def test_art_345_case(self):
        """Caso real: artigo 345 - era marcado como alucinação mas existe no RAW."""
        raw = (
            "E aí a gente tem no artigo 345 o conceito de aproveitamento de terreno, "
            "o conceito de ATE, área total edificável."
        )
        formatted = (
            "Art. 345 do Plano Diretor"
        )
        
        exists, matched = FidelityMatcher.exists_in_text("artigo 345", formatted)
        assert exists is True, f"artigo 345 deveria ser encontrado como: {matched}"
    
    def test_enel_case(self):
        """Caso real: Enel - mencionada no RAW, marcada como alucinação."""
        raw = (
            "A Light, o Supremo, entendeu que quem tem que definir isso é a União. "
            "A gente viu o caso da Enel, né? Da Enel em São Paulo."
        )
        formatted = (
            "tema que gera embates clássicos com concessionárias como a Light e a Enel"
        )
        
        # Verifica que Enel existe em ambos
        exists_raw, _ = FidelityMatcher.exists_in_text("Enel", raw)
        exists_fmt, _ = FidelityMatcher.exists_in_text("Enel", formatted)
        
        assert exists_raw is True
        assert exists_fmt is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
