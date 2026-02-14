"""
Tests for deterministic text utilities in mlx_vomo.py.
Run with: pytest tests/test_mlx_vomo_text_utils.py -v
"""
import importlib
import importlib.machinery
import os
import sys
import types

import pytest


def _install_stub(name, attrs=None):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        # Set __spec__ to avoid ValueError in importlib.util.find_spec
        module.__spec__ = importlib.machinery.ModuleSpec(name, None)
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

    # Stub openai de forma que importlib.util.find_spec não quebre
    # (faster_whisper → transformers verifica openai.__spec__)
    if "openai" not in sys.modules:
        openai = _install_stub("openai")
    else:
        openai = sys.modules["openai"]
    class DummyOpenAI:
        pass
    if not hasattr(openai, "OpenAI"):
        openai.OpenAI = DummyOpenAI
    if not hasattr(openai, "AsyncOpenAI"):
        openai.AsyncOpenAI = DummyOpenAI

    # Stub faster_whisper/mlx_whisper para evitar cadeia de imports pesados
    _install_stub("faster_whisper", {"WhisperModel": type("WhisperModel", (), {})})
    _install_stub("mlx_whisper")

    # Stub audit_unified
    _install_stub("audit_unified", {
        "UnifiedAuditEngine": type("UnifiedAuditEngine", (), {}),
        "generate_unified_markdown": lambda *a, **k: "",
        "UnifiedReport": type("UnifiedReport", (), {}),
        "compare_reports": lambda *a, **k: {},
    })

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


def _install_gemini_stubs():
    """Stubs para permitir import de format_transcription_gemini sem google-genai instalado."""
    google = _install_stub("google")
    genai = _install_stub("google.genai")
    types_mod = _install_stub("google.genai.types")
    if not hasattr(google, "genai"):
        google.genai = genai
    if not hasattr(genai, "types"):
        genai.types = types_mod
    if not hasattr(types_mod, "GenerateContentConfig"):
        types_mod.GenerateContentConfig = type("GenerateContentConfig", (), {})
    if not hasattr(types_mod, "SafetySetting"):
        types_mod.SafetySetting = type("SafetySetting", (), {})
    if not hasattr(types_mod, "CreateCachedContentConfig"):
        types_mod.CreateCachedContentConfig = type("CreateCachedContentConfig", (), {})
    if not hasattr(genai, "Client"):
        genai.Client = type("Client", (), {})

    _install_stub("tqdm", {"tqdm": None})
    _install_stub("docx")
    _install_stub("docx.shared")
    _install_stub("docx.enum")
    _install_stub("docx.enum.text")
    _install_stub("docx.enum.table")
    _install_stub("docx.oxml")
    _install_stub("docx.oxml.ns")


@pytest.fixture(scope="module")
def mlx_vomo_module():
    _install_external_stubs()
    # Pytest import mode can vary; ensure repo root is on sys.path for `import mlx_vomo`.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return importlib.import_module("mlx_vomo")


@pytest.fixture(scope="module")
def gemini_module():
    _install_external_stubs()
    _install_gemini_stubs()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return importlib.import_module("format_transcription_gemini")


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
            "## 1. Competência",
            "## 2. Partes e Litisconsórcio",
            "## 3. Citação e Intimação",
            "## 4. Contestação",
            "## 5. Tutela Provisória",
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


def test_simplificar_estrutura_preserva_nivel3_quando_permitido(mlx_vomo_module):
    estrutura = "\n".join(
        [
            "1. Processo de Conhecimento",
            "1.1. Fase Postulatória",
            "1.1.1. Petição Inicial",
            "1.1.2. Emenda da Inicial",
            "1.2. Saneamento",
            "1.2.1. Delimitação de Provas",
            "1.2.2. Decisão de Organização",
            "2. Recursos",
            "2.1. Apelação",
            "2.1.1. Juízo de Admissibilidade",
            "2.1.2. Efeitos",
        ]
    )

    out = mlx_vomo_module.simplificar_estrutura_se_necessario(
        estrutura,
        max_linhas=8,
        max_nivel=3,
    )
    assert "1.1.1. Petição Inicial" in out or "2.1.1. Juízo de Admissibilidade" in out


def test_simplificar_estrutura_amostra_distribuida(mlx_vomo_module):
    linhas = [f"{i}. Tópico {i}" for i in range(1, 101)]
    estrutura = "\n".join(linhas)

    out = mlx_vomo_module.simplificar_estrutura_se_necessario(
        estrutura,
        max_linhas=10,
        max_nivel=3,
    )
    out_lines = [l.strip() for l in out.split("\n") if l.strip()]
    assert len(out_lines) == 10
    assert "1. Tópico 1" in out
    assert "100. Tópico 100" in out
    assert "10. Tópico 10" not in out  # evita corte puro no começo


def test_sample_with_parents_preserva_ancestrais(mlx_vomo_module):
    itens = [
        "1. Processo",
        "1.1. Fase Postulatória",
        "1.1.1. Petição Inicial",
        "2. Recursos",
        "2.1. Apelação",
        "2.1.1. Efeitos",
    ]
    sampled = mlx_vomo_module._sample_with_parents(itens, limit=4)
    sampled_set = set(sampled)
    for line in sampled:
        key = mlx_vomo_module._extract_outline_key(line)
        if not key or "." not in key:
            continue
        parent_key = ".".join(key.split(".")[:-1])
        parent = next(
            (
                it
                for it in itens
                if mlx_vomo_module._extract_outline_key(it) == parent_key
            ),
            None,
        )
        if parent:
            assert parent in sampled_set


def test_simplificar_estrutura_nao_deixa_filho_orfao(mlx_vomo_module):
    estrutura = "\n".join(
        [
            "1. Processo",
            "1.1. Fase Postulatória",
            "1.1.1. Petição Inicial",
            "1.1.2. Emenda",
            "1.2. Saneamento",
            "1.2.1. Provas",
            "2. Recursos",
            "2.1. Apelação",
            "2.1.1. Efeitos",
            "2.1.2. Juízo de admissibilidade",
            "2.2. Agravo",
            "2.2.1. Cabimento",
        ]
    )
    out = mlx_vomo_module.simplificar_estrutura_se_necessario(
        estrutura,
        max_linhas=6,
        max_nivel=3,
    )
    linhas = [l.strip() for l in out.split("\n") if l.strip()]
    sampled_set = set(linhas)
    for line in linhas:
        key = mlx_vomo_module._extract_outline_key(line)
        if not key or key.count(".") < 2:
            continue
        parent_key = ".".join(key.split(".")[:-1])
        parent = next(
            (
                it
                for it in linhas
                if mlx_vomo_module._extract_outline_key(it) == parent_key
            ),
            None,
        )
        assert parent is not None
        assert parent in sampled_set


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


# ---------------------------------------------------------------------------
# _sanitize_mapped_structure (v2.47)
# ---------------------------------------------------------------------------

class TestSanitizeMappedStructure:
    """Testes para sanitização de títulos de estrutura mapeada."""

    def test_speech_fragment_replaced_by_canonical_label(self, mlx_vomo_module):
        """Título que é frase literal do professor → rótulo canônico."""
        estrutura = "1. Já estávamos conversando aqui antes de começar a transmissão"
        result = mlx_vomo_module._sanitize_mapped_structure(estrutura)
        assert "Já estávamos" not in result
        assert "Introdução" in result

    def test_greeting_replaced_by_canonical_label(self, mlx_vomo_module):
        """Saudação como título → 'Introdução e Contextualização'."""
        estrutura = "1. Bom dia pessoal vamos começar falando sobre licitações e contratos"
        result = mlx_vomo_module._sanitize_mapped_structure(estrutura)
        assert "Bom dia" not in result
        assert "Introdução" in result

    def test_good_title_preserved(self, mlx_vomo_module):
        """Título técnico curto não é alterado."""
        estrutura = "2. Licitações e Contratos"
        result = mlx_vomo_module._sanitize_mapped_structure(estrutura)
        assert "Licitações e Contratos" in result

    def test_subtopic_greeting_becomes_abertura(self, mlx_vomo_module):
        """Saudação em subtópico → 'Abertura' (não 'Introdução')."""
        estrutura = "   1.1. Bom dia a todos os presentes nesta sala"
        result = mlx_vomo_module._sanitize_mapped_structure(estrutura)
        assert "Bom dia" not in result
        assert "Abertura" in result

    def test_abre_fecha_anchors_preserved(self, mlx_vomo_module):
        """Âncoras ABRE/FECHA devem ser preservadas intactas."""
        estrutura = '1. Já estávamos conversando antes | ABRE: "já estávamos conversando" | FECHA: "vamos ao tema"'
        result = mlx_vomo_module._sanitize_mapped_structure(estrutura)
        assert "Já estávamos" not in result.split("| ABRE:")[0]
        assert '| ABRE: "já estávamos conversando"' in result
        assert '| FECHA: "vamos ao tema"' in result

    def test_too_long_title_without_conversation_prefix(self, mlx_vomo_module):
        """Título longo sem prefixo conversacional → rótulo canônico."""
        title_words = " ".join(["palavra"] * 15)
        estrutura = f"3. {title_words}"
        result = mlx_vomo_module._sanitize_mapped_structure(estrutura)
        assert title_words not in result

    def test_mixed_structure_selective_fix(self, mlx_vomo_module):
        """Estrutura mista: apenas títulos ruins são corrigidos."""
        estrutura = "\n".join([
            "1. Pessoal antes de começar eu queria dizer que estamos atrasados",
            "   1.1. Licitações — Lei 14.133/2021",
            "   1.2. Contratos Administrativos",
            "2. Bom dia a todos vamos começar a aula",
        ])
        result = mlx_vomo_module._sanitize_mapped_structure(estrutura)
        # Títulos ruins foram sanitizados
        assert "Pessoal antes" not in result
        assert "Bom dia a todos" not in result
        # Títulos bons preservados
        assert "Licitações — Lei 14.133/2021" in result
        assert "Contratos Administrativos" in result

    def test_empty_string_returns_empty(self, mlx_vomo_module):
        assert mlx_vomo_module._sanitize_mapped_structure("") == ""

    def test_none_returns_none(self, mlx_vomo_module):
        assert mlx_vomo_module._sanitize_mapped_structure(None) is None


# ---------------------------------------------------------------------------
# _sanitize_structure_titles (format_transcription_gemini.py, v2.47)
# ---------------------------------------------------------------------------

class TestSanitizeStructureTitlesGemini:
    """Testes para _sanitize_structure_titles de format_transcription_gemini.py."""

    def test_speech_fragment_replaced(self, gemini_module):
        estrutura = "1. Já estávamos conversando aqui antes de começar a transmissão"
        result = gemini_module._sanitize_structure_titles(estrutura)
        assert "Já estávamos" not in result
        assert "Introdução" in result

    def test_greeting_replaced(self, gemini_module):
        estrutura = "1. Bom dia pessoal vamos começar a aula de hoje sobre licitações"
        result = gemini_module._sanitize_structure_titles(estrutura)
        assert "Bom dia" not in result
        assert "Introdução" in result

    def test_good_title_preserved(self, gemini_module):
        estrutura = "2. Licitações e Contratos"
        result = gemini_module._sanitize_structure_titles(estrutura)
        assert "Licitações e Contratos" in result

    def test_subtopic_greeting_becomes_abertura(self, gemini_module):
        estrutura = "   1.1. Bom dia a todos os presentes nesta sala"
        result = gemini_module._sanitize_structure_titles(estrutura)
        assert "Bom dia" not in result
        assert "Abertura" in result

    def test_abre_fecha_anchors_preserved(self, gemini_module):
        estrutura = '1. Pessoal vamos começar | ABRE: "pessoal vamos começar" | FECHA: "agora sim"'
        result = gemini_module._sanitize_structure_titles(estrutura)
        assert "Pessoal vamos" not in result.split("| ABRE:")[0]
        assert '| ABRE: "pessoal vamos começar"' in result
        assert '| FECHA: "agora sim"' in result

    def test_mixed_structure_selective(self, gemini_module):
        estrutura = "\n".join([
            "1. Olha pessoal antes de começar vou me apresentar",
            "   1.1. Direito Administrativo",
            "   1.2. Contratos Administrativos",
            "2. Bom dia vamos ao tema principal da aula de hoje",
        ])
        result = gemini_module._sanitize_structure_titles(estrutura)
        assert "Olha pessoal" not in result
        assert "Bom dia" not in result
        assert "Direito Administrativo" in result
        assert "Contratos Administrativos" in result

    def test_empty_returns_empty(self, gemini_module):
        assert gemini_module._sanitize_structure_titles("") == ""

    def test_none_returns_none(self, gemini_module):
        assert gemini_module._sanitize_structure_titles(None) is None
