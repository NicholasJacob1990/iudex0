"""
Testes de integração para o fluxo de correção estrutural (HIL).
Valida detecção e remoção de parágrafos/seções duplicados.
"""

import pytest
import sys
import os

# Adiciona o diretório raiz do projeto ao path para importar auto_fix_apostilas
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))


class TestStructuralFixesUnit:
    """Testes unitários para funções de correção estrutural."""

    def test_compute_paragraph_fingerprint_deterministic(self):
        """Fingerprint deve ser determinístico para o mesmo texto."""
        from auto_fix_apostilas import compute_paragraph_fingerprint
        
        text = "Este é um parágrafo de teste com mais de cinquenta caracteres para ser considerado."
        
        fp1 = compute_paragraph_fingerprint(text)
        fp2 = compute_paragraph_fingerprint(text)
        
        assert fp1 == fp2
        assert len(fp1) == 12  # MD5 truncado para 12 chars

    def test_compute_paragraph_fingerprint_normalized(self):
        """Fingerprint deve normalizar espaços e case."""
        from auto_fix_apostilas import compute_paragraph_fingerprint
        
        text1 = "Este é um parágrafo de teste com mais de cinquenta caracteres para ser considerado."
        text2 = "ESTE   É   UM   PARÁGRAFO   DE   TESTE   COM   MAIS   DE   CINQUENTA   CARACTERES   PARA   SER   CONSIDERADO."
        
        fp1 = compute_paragraph_fingerprint(text1)
        fp2 = compute_paragraph_fingerprint(text2)
        
        assert fp1 == fp2

    def test_analyze_structural_issues_detects_duplicate_paragraphs(self, tmp_path):
        """Deve detectar parágrafos duplicados no documento."""
        from auto_fix_apostilas import analyze_structural_issues
        
        # Cria conteúdo com parágrafo duplicado
        paragraph = "Este é um parágrafo longo o suficiente para ser considerado pelo algoritmo de fingerprinting. Ele precisa ter pelo menos cinquenta caracteres."
        content = f"""# Documento de Teste

{paragraph}

Outro parágrafo diferente aqui.

{paragraph}

Mais um parágrafo único.
"""
        
        test_file = tmp_path / "test_doc.md"
        test_file.write_text(content, encoding="utf-8")
        
        issues = analyze_structural_issues(str(test_file))
        
        assert "duplicate_paragraphs" in issues
        assert len(issues["duplicate_paragraphs"]) >= 1
        assert issues["total_issues"] >= 1

    def test_apply_structural_fixes_removes_duplicate(self, tmp_path):
        """Deve remover parágrafo duplicado quando aprovado."""
        from auto_fix_apostilas import analyze_structural_issues, apply_structural_fixes_to_file
        
        # Cria conteúdo com parágrafo duplicado
        paragraph = "Este é um parágrafo longo o suficiente para ser considerado pelo algoritmo de fingerprinting. Ele precisa ter pelo menos cinquenta caracteres."
        content = f"""# Documento de Teste

{paragraph}

Outro parágrafo diferente aqui.

{paragraph}

Mais um parágrafo único.
"""
        
        test_file = tmp_path / "test_doc.md"
        test_file.write_text(content, encoding="utf-8")
        
        # Primeiro analisa
        issues = analyze_structural_issues(str(test_file))
        assert len(issues["duplicate_paragraphs"]) >= 1
        
        # Prepara sugestões para aplicar
        suggestions = {
            "duplicate_paragraphs": issues["duplicate_paragraphs"],
            "duplicate_sections": [],
        }
        
        # Aplica correções
        result = apply_structural_fixes_to_file(str(test_file), suggestions)
        
        assert len(result["fixes_applied"]) >= 1
        assert "Removed duplicate paragraph" in result["fixes_applied"][0]
        assert result["new_size"] < result["original_size"]

    def test_apply_structural_fixes_no_false_positives(self, tmp_path):
        """Não deve remover parágrafos únicos."""
        from auto_fix_apostilas import apply_structural_fixes_to_file, compute_paragraph_fingerprint
        
        content = """# Documento de Teste

Este é o primeiro parágrafo único com texto suficiente para ser analisado pelo algoritmo.

Este é o segundo parágrafo único com texto completamente diferente do primeiro parágrafo.

Este é o terceiro parágrafo único com conteúdo totalmente distinto dos anteriores.
"""
        
        test_file = tmp_path / "test_doc.md"
        test_file.write_text(content, encoding="utf-8")
        
        # Tenta aplicar com fingerprint que não existe no documento
        suggestions = {
            "duplicate_paragraphs": [{"fingerprint": "inexistente1"}],
            "duplicate_sections": [],
        }
        
        result = apply_structural_fixes_to_file(str(test_file), suggestions)
        
        # Nenhuma correção deve ser aplicada
        assert len(result["fixes_applied"]) == 0
        assert result["new_size"] == result["original_size"]


class TestQualityServiceIntegration:
    """Testes de integração para o QualityService."""

    @pytest.mark.asyncio
    async def test_analyze_and_apply_flow(self):
        """Testa o fluxo completo: análise → aprovação → aplicação."""
        from app.services.quality_service import QualityService
        
        service = QualityService()
        
        # Conteúdo com parágrafo duplicado
        paragraph = "Este é um parágrafo longo o suficiente para ser considerado pelo algoritmo de fingerprinting. Ele precisa ter pelo menos cinquenta caracteres para o cálculo do hash MD5."
        content = f"""# Documento de Teste

{paragraph}

Outro parágrafo diferente aqui com texto único.

{paragraph}

Mais um parágrafo único no final.
"""
        
        # 1. Analisa
        analysis = await service.analyze_structural_issues(
            content=content,
            document_name="test_doc.md"
        )
        
        assert analysis["total_issues"] >= 1
        assert len(analysis["pending_fixes"]) >= 1
        
        # Encontra o fix de parágrafo duplicado
        para_fix = next(
            (f for f in analysis["pending_fixes"] if f["type"] == "duplicate_paragraph"),
            None
        )
        assert para_fix is not None
        assert para_fix["fingerprint"] is not None
        
        # 2. Aplica apenas o fix aprovado
        result = await service.apply_approved_fixes(
            content=content,
            approved_fix_ids=[para_fix["id"]],
            approved_fixes=[para_fix]
        )
        
        assert result["success"] is True
        assert len(result["fixes_applied"]) >= 1
        assert "Removed duplicate paragraph" in result["fixes_applied"][0]
        
        # Verifica que o conteúdo foi reduzido
        assert len(result["fixed_content"]) < len(content)
        
        # Verifica que o parágrafo duplicado foi removido (aparece só 1x)
        count = result["fixed_content"].count(paragraph)
        assert count == 1

    @pytest.mark.asyncio
    async def test_apply_with_empty_approved_fixes(self):
        """Deve retornar conteúdo inalterado quando não há fixes aprovados."""
        from app.services.quality_service import QualityService
        
        service = QualityService()
        
        content = "# Documento\n\nConteúdo simples."
        
        result = await service.apply_approved_fixes(
            content=content,
            approved_fix_ids=[],
            approved_fixes=[]
        )
        
        assert result["success"] is True
        assert result["fixed_content"] == content
        assert len(result["fixes_applied"]) == 0

    @pytest.mark.asyncio
    async def test_apply_with_nonexistent_fingerprint(self):
        """Deve retornar conteúdo inalterado quando fingerprint não existe."""
        from app.services.quality_service import QualityService
        
        service = QualityService()
        
        content = """# Documento de Teste

Este é um parágrafo único com texto suficiente para ser analisado pelo algoritmo.

Outro parágrafo também único e diferente do primeiro.
"""
        
        # Tenta aplicar com fingerprint inexistente
        result = await service.apply_approved_fixes(
            content=content,
            approved_fix_ids=["dup_para_inexistente123"],
            approved_fixes=[{
                "id": "dup_para_inexistente123",
                "type": "duplicate_paragraph",
                "fingerprint": "inexistente123",
                "description": "Teste",
                "action": "REMOVE",
                "severity": "low"
            }]
        )
        
        assert result["success"] is True
        # Nenhuma correção aplicada
        assert len(result["fixes_applied"]) == 0


class TestIDConsistency:
    """Testes para garantir consistência de IDs entre análise e aplicação."""

    @pytest.mark.asyncio
    async def test_section_ids_are_consistent(self):
        """IDs de seções duplicadas devem ser consistentes."""
        from app.services.quality_service import QualityService
        
        service = QualityService()
        
        # Conteúdo com seção duplicada
        content = """# Documento

## 1. Introdução

Texto da introdução.

## 2. Desenvolvimento

Texto do desenvolvimento.

## 3. Introdução

Texto duplicado da introdução.

## 4. Conclusão

Texto da conclusão.
"""
        
        analysis = await service.analyze_structural_issues(
            content=content,
            document_name="test_sections.md"
        )
        
        # Verifica que os IDs são consistentes (dup_section_0, dup_section_1, etc.)
        section_fixes = [f for f in analysis["pending_fixes"] if f["type"] == "duplicate_section"]
        
        for i, fix in enumerate(section_fixes):
            expected_id = f"dup_section_{i}"
            assert fix["id"] == expected_id, f"ID esperado: {expected_id}, obtido: {fix['id']}"

    @pytest.mark.asyncio
    async def test_paragraph_ids_use_fingerprint(self):
        """IDs de parágrafos duplicados devem usar fingerprint."""
        from app.services.quality_service import QualityService
        
        service = QualityService()
        
        paragraph = "Este é um parágrafo longo o suficiente para ser considerado pelo algoritmo de fingerprinting."
        content = f"""# Documento

{paragraph}

Outro texto.

{paragraph}
"""
        
        analysis = await service.analyze_structural_issues(
            content=content,
            document_name="test_paragraphs.md"
        )
        
        para_fixes = [f for f in analysis["pending_fixes"] if f["type"] == "duplicate_paragraph"]
        
        for fix in para_fixes:
            # ID deve conter o fingerprint
            assert fix["id"].startswith("dup_para_")
            assert fix["fingerprint"] is not None
            assert fix["id"] == f"dup_para_{fix['fingerprint']}"
