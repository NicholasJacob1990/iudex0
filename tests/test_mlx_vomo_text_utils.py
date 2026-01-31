"""
Tests for deterministic text utilities in mlx_vomo.py.
Run with: pytest tests/test_mlx_vomo_text_utils.py -v
"""
import importlib
import os
import sys
import types

import pytest


def _install_stub(name, attrs=None):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    if attrs:
        for key, value in attrs.items():
            if not hasattr(module, key):
                setattr(module, key, value)
    return module


def _install_external_stubs():
    google = _install_stub("google")
    genai = _install_stub("google.genai")
    types_mod = _install_stub("google.genai.types")
    if not hasattr(google, "genai"):
        google.genai = genai
    if not hasattr(genai, "types"):
        genai.types = types_mod
    if not hasattr(types_mod, "CreateCachedContentConfig"):
        class DummyCachedConfig:
            pass
        types_mod.CreateCachedContentConfig = DummyCachedConfig
    if not hasattr(genai, "Client"):
        class DummyGenaiClient:
            pass
        genai.Client = DummyGenaiClient

    openai = _install_stub("openai")
    class DummyOpenAI:
        pass
    if not hasattr(openai, "OpenAI"):
        openai.OpenAI = DummyOpenAI
    if not hasattr(openai, "AsyncOpenAI"):
        openai.AsyncOpenAI = DummyOpenAI

    tenacity = _install_stub("tenacity")
    if not hasattr(tenacity, "retry"):
        def _retry(*args, **kwargs):
            def decorator(func):
                return func
            return decorator
        tenacity.retry = _retry
    if not hasattr(tenacity, "stop_after_attempt"):
        tenacity.stop_after_attempt = lambda *args, **kwargs: None
    if not hasattr(tenacity, "wait_exponential"):
        tenacity.wait_exponential = lambda *args, **kwargs: None
    if not hasattr(tenacity, "retry_if_exception_type"):
        tenacity.retry_if_exception_type = lambda *args, **kwargs: None

    _install_stub("audit_module", {
        "auditar_consistencia_legal": lambda *args, **kwargs: None,
    })
    _install_stub("audit_fidelity_preventive", {
        "auditar_fidelidade_preventiva": lambda *args, **kwargs: None,
        "gerar_relatorio_markdown_completo": lambda *args, **kwargs: None,
    })
    _install_stub("auto_fix_apostilas", {
        "analyze_structural_issues": lambda *args, **kwargs: {
            "total_issues": 0,
            "duplicate_sections": [],
            "duplicate_paragraphs": [],
        },
        "apply_structural_fixes_to_file": lambda *args, **kwargs: {"fixes_applied": []},
    })


@pytest.fixture(scope="module")
def mlx_vomo_module():
    _install_external_stubs()
    # Pytest import mode can vary; ensure repo root is on sys.path for `import mlx_vomo`.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return importlib.import_module("mlx_vomo")


def test_renumerar_secoes_sequencial(mlx_vomo_module):
    texto = "\n".join([
        "## 1. Intro",
        "Texto A",
        "### 1.1. Sub",
        "Texto B",
        "### 1.1. Sub again",
        "Texto C",
        "## 3. Next",
        "Texto D",
        "",
    ])
    result = mlx_vomo_module.renumerar_secoes(texto)
    assert "### 1.2. Sub again" in result
    assert "## 2. Next" in result


def test_renumber_headings_demotes_h2_decimal_to_h3(mlx_vomo_module):
    # Regression: evitar que um subtópico "5.5" (deveria ser H3) vire um novo tópico H2 "6".
    vomo = mlx_vomo_module.VomoMLX.__new__(mlx_vomo_module.VomoMLX)
    texto = "\n".join(
        [
            "## 1. Seção 1",
            "## 2. Seção 2",
            "## 3. Seção 3",
            "## 4. Seção 4",
            "## 5. Seção 5",
            "### 5.1. Sub 1",
            "### 5.2. Sub 2",
            "### 5.3. Sub 3",
            "### 5.4. Sub 4",
            "## 5.5. Sub 5 (nível incorreto)",
            "",
        ]
    )
    result = vomo.renumber_headings(texto)
    assert "### 5.5. Sub 5 (nível incorreto)" in result
    assert "## 6. Sub 5 (nível incorreto)" not in result


def test_renumber_headings_does_not_demote_without_parent_prefix(mlx_vomo_module):
    # Se não houver seção H2 prévia com o mesmo prefixo, não rebaixa.
    vomo = mlx_vomo_module.VomoMLX.__new__(mlx_vomo_module.VomoMLX)
    texto = "\n".join(
        [
            "## 9.20. Tema Avançado",
            "Texto A",
            "",
        ]
    )
    result = vomo.renumber_headings(texto)
    # Mantém como H2 (vira 1.) em sequência, não rebaixa para H3.
    assert "## 1. Tema Avançado" in result
    assert "### 1.1. Tema Avançado" not in result


def test_audit_heading_levels_flags_decimal_h2(mlx_vomo_module):
    texto = "\n".join(
        [
            "## 1. Tema Principal",
            "## 1.2. Subtema com nível errado",
            "Texto A",
            "",
        ]
    )
    out, issues = mlx_vomo_module.audit_heading_levels(texto, apply_fixes=False)
    assert out == texto
    assert any("Subtópico numerado em H2" in i for i in issues)


def test_audit_heading_levels_fix_decimal_h2(mlx_vomo_module):
    texto = "\n".join(
        [
            "## 1. Tema Principal",
            "## 1.2. Subtema com nível errado",
            "Texto A",
            "",
        ]
    )
    out, issues = mlx_vomo_module.audit_heading_levels(texto, apply_fixes=True)
    assert any("Subtópico numerado em H2" in i for i in issues)
    assert "### 1.2. Subtema com nível errado" in out


def test_audit_heading_levels_fix_h4_without_h3(mlx_vomo_module):
    texto = "\n".join(
        [
            "## 1. Tema Principal",
            "#### 1.1.1. Subsubtema sem H3",
            "Texto A",
            "",
        ]
    )
    out, issues = mlx_vomo_module.audit_heading_levels(texto, apply_fixes=True)
    assert any("H4 sem H3 anterior" in i for i in issues)
    assert "### 1.1.1. Subsubtema sem H3" in out


def test_reatribuir_tabelas_por_topico_moves_to_parent(mlx_vomo_module):
    texto = "\n".join(
        [
            "## 26. Tema Geral",
            "Texto A sobre saúde complementar e MROSC.",
            "### 26.3. Polêmica do Artigo 3º",
            "Texto B sobre artigo 3º.",
            "#### 📋 Quadro-síntese — Saúde Complementar e MROSC",
            "| Item | Regra |",
            "| --- | --- |",
            "| Saúde Complementar | MROSC não se aplica |",
            "",
            "### 26.4. Outro ponto",
            "Texto C",
            "",
        ]
    )
    out, issues = mlx_vomo_module.reatribuir_tabelas_por_topico(texto, apply_fixes=True)
    assert any("Tabela reatribuída" in i for i in issues)
    # A tabela deve aparecer antes do heading 26.3 (movida para o tópico pai)
    pos_table = out.find("#### 📋 Quadro-síntese")
    pos_sub = out.find("### 26.3. Polêmica do Artigo 3º")
    assert pos_table < pos_sub


def test_dividir_por_blocos_markdown_groups_blocks(mlx_vomo_module):
    texto = "\n".join(
        [
            "## Bloco 01 — pergunta (SPEAKER 1)",
            "**A**: [00:00] Pergunta curta.",
            "",
            "## Bloco 02 — resposta (SPEAKER 2)",
            "**B**: [00:05] Resposta curta.",
            "",
            "## Bloco 03 — esclarecimento (SPEAKER 1)",
            "**A**: [00:10] Esclarecimento curto.",
            "",
        ]
    )
    chunks = mlx_vomo_module.dividir_por_blocos_markdown(texto, max_chars=120)
    assert chunks, "deve gerar chunks por blocos"
    # Deve cobrir o texto inteiro sem gaps.
    assert chunks[0]["inicio"] == 0
    assert chunks[-1]["fim"] == len(texto)
    for i in range(1, len(chunks)):
        assert chunks[i]["inicio"] == chunks[i - 1]["fim"]


def test_dividir_por_blocos_markdown_custom_prefix(mlx_vomo_module):
    texto = "\n".join(
        [
            "## Ato 1 — abertura",
            "**A**: [00:00] Início.",
            "",
            "## Ato 2 — instrução",
            "**B**: [00:10] Continuação.",
            "",
        ]
    )
    chunks = mlx_vomo_module.dividir_por_blocos_markdown(
        texto,
        max_chars=200,
        block_prefix_pattern="Ato",
    )
    assert chunks, "deve reconhecer prefixo customizado"
    assert chunks[0]["inicio"] == 0
    assert chunks[-1]["fim"] == len(texto)


def test_normalize_headings_removes_continuacao(mlx_vomo_module):
    texto = "\n".join([
        "## 1. Conceito (Continuação)",
        "Texto A",
        "## 2. Conceito",
        "Texto B",
        "",
    ])
    result = mlx_vomo_module.normalize_headings(texto)
    assert "(Continuação)" not in result
    assert "## 1. Conceito" in result
    assert "## 2. Conceito" in result


def test_remover_marcadores_continua_removes_inline_and_line_markers(mlx_vomo_module):
    texto = "\n".join(
        [
            "Texto A... [continua] Texto B.",
            "",
            "(continuação)",
            "",
            "Texto C.",
            "",
            "[CONTINUACAO]",
            "Texto D.",
            "",
        ]
    )
    out = mlx_vomo_module.remover_marcadores_continua(texto)
    lowered = out.lower()
    assert "[continua]" not in lowered
    assert "[continuacao]" not in lowered
    assert "(continuação)" not in lowered
    assert "texto a" in lowered
    assert "texto b" in lowered
    assert "texto c" in lowered
    assert "texto d" in lowered


def test_remover_overlap_duplicado_merges_unique_paragraphs(mlx_vomo_module):
    comum = "Texto comum. " * 6
    chunk1 = "\n\n".join([
        "## 1. Intro",
        comum,
        "Paragrafo unico A longo o bastante para entrar.",
    ])
    chunk2 = "\n\n".join([
        "## 1. Intro",
        comum,
        "Paragrafo unico B longo o bastante para entrar.",
    ])
    result = mlx_vomo_module.remover_overlap_duplicado([chunk1, chunk2], mode="APOSTILA")
    assert result.count("## 1. Intro") == 1
    assert "Paragrafo unico A longo" in result
    assert "Paragrafo unico B longo" in result


def test_split_long_paragraphs_markdown_splits_plain_paragraphs(mlx_vomo_module):
    texto = (
        "Este é um parágrafo muito longo. " * 20
        + "Ele deve ser quebrado naturalmente em parágrafos menores. " * 10
        + "Fim."
    )
    out, changed = mlx_vomo_module._split_long_paragraphs_markdown(texto, max_paragraph_chars=160)
    assert changed >= 1
    assert "\n\n" in out
    # Conteúdo preservado (apenas quebras)
    assert out.replace("\n", " ").count("parágrafo") >= 1


def test_split_long_paragraphs_markdown_skips_timestamped_when_configured(mlx_vomo_module):
    for ts in ("[00:10:00] ", "[00:10] "):
        texto = ts + ("Conteúdo muito longo. " * 30) + "Fim."
        out, changed = mlx_vomo_module._split_long_paragraphs_markdown(
            texto,
            max_paragraph_chars=120,
            skip_timestamped=True,
        )
        assert changed == 0
        assert out == texto


def test_aplicar_correcoes_automaticas_splits_in_fidelidade_when_enabled(mlx_vomo_module, monkeypatch):
    monkeypatch.setenv("IUDEX_FIDELIDADE_MAX_PARAGRAPH_CHARS", "140")
    texto = (
        "Parágrafo muito longo. " * 20
        + "Deve ser quebrado em modo fidelidade também. " * 10
        + "Fim."
    )
    out, correcoes = mlx_vomo_module.aplicar_correcoes_automaticas(texto, mode="FIDELIDADE")
    assert any("Parágrafos longos quebrados" in c for c in correcoes)
    assert "\n\n" in out


def test_extract_style_context_includes_recent_table(mlx_vomo_module):
    texto = "\n".join([
        "Linha 1",
        "Linha 2",
        "#### Tabela",
        "| A | B |",
        "| --- | --- |",
        "| 1 | 2 |",
    ])
    result = mlx_vomo_module._extract_style_context(texto, max_chars=80)
    assert "| A | B |" in result
    assert "| 1 | 2 |" in result


def test_build_system_prompt_apostila_custom_affects_only_tables_and_extras(mlx_vomo_module):
    # Avoid running VomoMLX.__init__ (would require external credentials).
    vomo = mlx_vomo_module.VomoMLX.__new__(mlx_vomo_module.VomoMLX)
    custom = "No final de cada tópico, adicione um questionário com 5 questões e gabarito."
    prompt = vomo._build_system_prompt(mode="APOSTILA", custom_style_override=custom)

    # Default style rules must remain present (custom should not replace tone/style).
    assert mlx_vomo_module.VomoMLX.PROMPT_STYLE_APOSTILA in prompt
    # Default table rules must remain present; custom is appended as table/extras customization.
    assert mlx_vomo_module.VomoMLX.PROMPT_TABLE_APOSTILA in prompt
    assert "PERSONALIZAÇÕES (TABELAS / EXTRAS)" in prompt
    assert custom in prompt


def test_build_system_prompt_non_apostila_keeps_legacy_override(mlx_vomo_module):
    vomo = mlx_vomo_module.VomoMLX.__new__(mlx_vomo_module.VomoMLX)
    custom = "Apenas limpe muletas e mantenha falas em parágrafos separados."
    prompt = vomo._build_system_prompt(mode="FIDELIDADE", custom_style_override=custom)

    # In non-APOSTILA modes, custom overrides STYLE+TABLE (legacy behavior).
    assert custom in prompt
    assert mlx_vomo_module.VomoMLX.PROMPT_STYLE_FIDELIDADE not in prompt


def test_normalizar_temas_markdown_is_conservative_with_parentheses(mlx_vomo_module):
    texto = "\n".join(
        [
            "Tema 1.234 (art. 234) – exemplo didático.",
            "Tema 234 (ou 234) aparece como variante de ASR.",
            "Tema 1.033 (ano 1933) – ano histórico.",
            "Tema 1933 (ou 1.933) aparece como variante de ASR.",
        ]
    )
    out = mlx_vomo_module.normalizar_temas_markdown(texto)
    # Keeps unrelated parentheses.
    assert "(art. 234)" in out
    assert "(ano 1933)" in out
    # Removes only typical alias parentheses and normalizes.
    assert "(ou 234)" not in out
    assert "(ou 1.933)" not in out
    assert "Tema 1.234" in out
    assert "Tema 1.033" in out


def test_normalize_asr_temas_consistency_fixes_234_to_1234_when_canonical_present(mlx_vomo_module):
    vomo = mlx_vomo_module.VomoMLX.__new__(mlx_vomo_module.VomoMLX)
    texto = "Trecho A. Tema 1.234 é citado. Depois aparece Tema 234 por erro. Fim."
    out, stats = vomo._normalize_asr_temas_consistency(texto)
    assert "Tema 234" not in out
    assert "Tema 1234" in out
    assert stats["changed"] >= 1


def test_normalize_asr_temas_consistency_unifies_suffix_variants_when_dominant(mlx_vomo_module):
    vomo = mlx_vomo_module.VomoMLX.__new__(mlx_vomo_module.VomoMLX)
    # Ex.: erro de ASR no dígito mais à esquerda (1234 vs 2234), mantendo o mesmo sufixo "234".
    texto = "Tema 1234 aparece. Tema 1234 aparece de novo. Tema 2234 aparece uma vez."
    out, _ = vomo._normalize_asr_temas_consistency(texto)
    assert "Tema 2234" not in out
    assert out.count("Tema 1234") >= 3


def test_normalize_asr_temas_consistency_override_matches_dotted(monkeypatch, mlx_vomo_module):
    vomo = mlx_vomo_module.VomoMLX.__new__(mlx_vomo_module.VomoMLX)
    monkeypatch.setenv("VOMO_ASR_TEMA_OVERRIDES", "1933=1033")
    texto = "Tema 1.933 foi transcrito com separador. Tema 1933 também."
    out, _ = vomo._normalize_asr_temas_consistency(texto)
    assert "Tema 1.933" not in out
    assert "Tema 1933" not in out
    assert out.count("Tema 1033") == 2
