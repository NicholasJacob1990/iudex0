"""
Tests for deterministic text utilities in mlx_vomo.py.
Run with: pytest tests/test_mlx_vomo_text_utils.py -v
"""
import importlib
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
