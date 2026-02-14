"""
Testes de integração para o fluxo de correção estrutural (HIL).
Valida detecção e remoção de parágrafos/seções duplicados.
"""

import pytest
import sys
import os
import json

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

    def test_analyze_structural_issues_detects_table_misplacement(self, tmp_path):
        """Deve detectar tabela de síntese posicionada na abertura de H2 com subtópicos."""
        from auto_fix_apostilas import analyze_structural_issues

        content = """## 1. Tema Central

Introdução curta da seção.

#### 📋 Quadro-síntese — Tema Central
| Item | Regra |
| --- | --- |
| A | B |

### 1.1. Primeiro Subtópico

Texto do subtópico.
"""
        test_file = tmp_path / "test_table_misplacement.md"
        test_file.write_text(content, encoding="utf-8")

        issues = analyze_structural_issues(str(test_file))

        assert len(issues.get("table_misplacements", [])) >= 1
        first = issues["table_misplacements"][0]
        assert first["strategy"] == "h2_intro_to_section_end"
        assert "Tema Central" in (first.get("section_title") or "")

    def test_apply_structural_fixes_moves_misplaced_table(self, tmp_path):
        """Deve mover a tabela para o fechamento da seção quando aprovada."""
        from auto_fix_apostilas import analyze_structural_issues, apply_structural_fixes_to_file

        content = """## 1. Tema Central

Introdução curta da seção.

#### 📋 Quadro-síntese — Tema Central
| Item | Regra |
| --- | --- |
| A | B |

### 1.1. Primeiro Subtópico

Texto do subtópico.
"""
        test_file = tmp_path / "test_table_move.md"
        test_file.write_text(content, encoding="utf-8")

        issues = analyze_structural_issues(str(test_file))
        assert issues.get("table_misplacements"), "Esperava detectar tabela fora do lugar"

        suggestions = {
            "duplicate_paragraphs": [],
            "duplicate_sections": [],
            "heading_numbering_issues": [],
            "table_misplacements": issues["table_misplacements"],
        }
        result = apply_structural_fixes_to_file(str(test_file), suggestions)
        assert any("Moved misplaced table" in item for item in result["fixes_applied"])

        fixed = test_file.read_text(encoding="utf-8")
        table_pos = fixed.find("#### 📋 Quadro-síntese — Tema Central")
        subtopic_pos = fixed.find("### 1.1. Primeiro Subtópico")
        assert table_pos > subtopic_pos

    def test_analyze_structural_issues_detects_heading_semantic_issue(self, tmp_path):
        """Deve sugerir rename quando título de subtópico não condiz com o conteúdo."""
        from auto_fix_apostilas import analyze_structural_issues

        content = """## 1. Contexto Inicial

Texto introdutório da seção.

### 1.1. Introdução Geral

A responsabilidade subsidiária da administração pública na terceirização exige demonstração concreta de culpa in vigilando, com análise dos deveres de fiscalização e do ônus probatório no Tema 1118 do STF.
Também é necessário diferenciar inadimplemento trabalhista, encargos previdenciários e medidas preventivas previstas na Lei 14.133, com foco em governança contratual.
"""
        test_file = tmp_path / "test_heading_semantic.md"
        test_file.write_text(content, encoding="utf-8")

        issues = analyze_structural_issues(str(test_file))
        heading_issues = issues.get("heading_semantic_issues", [])
        assert len(heading_issues) >= 1
        first = heading_issues[0]
        assert first.get("type") in {"heading_semantic_mismatch", "parent_child_topic_drift", "near_duplicate_heading"}
        assert first.get("new_title")

    def test_apply_structural_fixes_renames_heading_title(self, tmp_path):
        """Deve renomear título com fix estrutural determinístico."""
        from auto_fix_apostilas import analyze_structural_issues, apply_structural_fixes_to_file

        content = """## 1. Contexto Inicial

Texto introdutório da seção.

### 1.1. Introdução Geral

A responsabilidade subsidiária da administração pública na terceirização exige demonstração concreta de culpa in vigilando, com análise dos deveres de fiscalização e do ônus probatório no Tema 1118 do STF.
Também é necessário diferenciar inadimplemento trabalhista, encargos previdenciários e medidas preventivas previstas na Lei 14.133, com foco em governança contratual.
"""
        test_file = tmp_path / "test_heading_rename.md"
        test_file.write_text(content, encoding="utf-8")

        analysis = analyze_structural_issues(str(test_file))
        heading_issues = analysis.get("heading_semantic_issues", [])
        assert heading_issues, "Esperava ao menos um heading semântico para renomear"

        suggestions = {
            "duplicate_paragraphs": [],
            "duplicate_sections": [],
            "heading_numbering_issues": [],
            "heading_title_updates": [heading_issues[0]],
            "table_misplacements": [],
        }
        result = apply_structural_fixes_to_file(str(test_file), suggestions)
        assert any("Renamed heading" in item for item in result["fixes_applied"])

        fixed = test_file.read_text(encoding="utf-8")
        new_title = str(heading_issues[0].get("new_title") or "").strip()
        assert new_title
        assert new_title in fixed


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

    @pytest.mark.asyncio
    async def test_analyze_structural_issues_ai_refines_heading_gray_zone(self, monkeypatch):
        """Em zona cinza, IA pode refinar o new_title sem quebrar o fluxo estrutural."""
        from app.services.quality_service import QualityService

        service = QualityService()

        class _AutoFixStub:
            @staticmethod
            def analyze_structural_issues(*_args, **_kwargs):
                return {
                    "duplicate_sections": [],
                    "duplicate_paragraphs": [],
                    "heading_numbering_issues": [],
                    "heading_semantic_issues": [
                        {
                            "id": "heading_semantic_12",
                            "type": "heading_semantic_mismatch",
                            "heading_line": 3,
                            "heading_level": 3,
                            "old_title": "Introdução Geral",
                            "new_title": "Introdução e Contexto",
                            "old_raw": "1.1. Introdução Geral",
                            "new_raw": "1.1. Introdução e Contexto",
                            "confidence": 0.83,  # gray zone
                            "reason": "Baixa aderência entre título e conteúdo.",
                            "action": "RENAME_RECOMMENDED",
                        }
                    ],
                    "table_misplacements": [],
                    "compression_ratio": None,
                    "compression_warning": None,
                    "missing_laws": [],
                    "missing_sumulas": [],
                    "missing_decretos": [],
                    "missing_julgados": [],
                    "total_content_issues": 0,
                    "total_issues": 1,
                }

        monkeypatch.setattr(service, "_get_auto_fix", lambda: _AutoFixStub())
        monkeypatch.setenv("IUDEX_HEADING_RENAME_AI_ENABLED", "true")
        monkeypatch.setenv("IUDEX_HEADING_RENAME_AI_MODEL", "gemini-2.0-flash")

        async def _fake_gemini(_prompt: str, model: str = "gemini-2.0-flash"):
            assert model.startswith("gemini")
            return json.dumps(
                {
                    "decision": "REWRITE",
                    "new_title": "Responsabilidade na Terceirização",
                    "confidence": 0.91,
                    "reason": "Título proposto cobre melhor o núcleo temático do bloco.",
                }
            )

        monkeypatch.setattr(service, "_call_gemini", _fake_gemini)

        content = """## 1. Tema Central

### 1.1. Introdução Geral

A responsabilidade subsidiária da administração pública na terceirização exige demonstração concreta de culpa e fiscalização contratual.
"""
        analysis = await service.analyze_structural_issues(
            content=content,
            document_name="test_ai_heading.md",
        )

        heading_fix = next((f for f in analysis.get("pending_fixes", []) if f.get("type") == "heading_semantic_mismatch"), None)
        assert heading_fix is not None
        assert heading_fix.get("new_title") == "Responsabilidade na Terceirização"
        assert heading_fix.get("action") == "RENAME"
        assert heading_fix.get("rename_source") == "hybrid_ai_rewrite"


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
            assert fix["id"].startswith(f"dup_para_{fix['fingerprint']}")
