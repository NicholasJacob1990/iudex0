"""Tests for custom_prompt_scope uniformization (Fase 2).

Verifica que _build_system_prompt() respeita custom_prompt_scope:
- tables_only (padrão): custom_prompt afeta SOMENTE tabelas/extras em TODOS os modos
- style_and_tables (opt-in): custom_prompt substitui STYLE+TABLE layers (legacy)
"""

import sys
import os
import re
import pytest
from unittest.mock import patch, MagicMock

# Precisamos importar mlx_vomo de forma especial (está na raiz do monorepo)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture
def vomo_instance():
    """Cria instância mínima de VomoTranscriber para testar _build_system_prompt."""
    # Import com stubs para evitar dependências pesadas
    with patch.dict("os.environ", {
        "VOMO_LLM_MODEL": "test-model",
        "VOMO_WHISPER_MODEL": "tiny",
    }):
        try:
            from mlx_vomo import VomoMLX
            vomo = VomoMLX.__new__(VomoMLX)
            # Setar atributos mínimos necessários
            vomo.model_name = "tiny"
            vomo.llm_model = "test-model"
            vomo.thinking_level = "medium"
            vomo._current_mode = "APOSTILA"
            vomo._current_language = "pt"
            return vomo
        except Exception:
            pytest.skip("mlx_vomo não disponível para testes")


class TestFidelidadeTablesOnlyDefault:
    def test_fidelidade_tables_only_uses_safe_sandwich(self, vomo_instance):
        """FIDELIDADE sem scope explícito usa tables_only (safe sandwich)."""
        result = vomo_instance._build_system_prompt(
            mode="FIDELIDADE",
            custom_style_override="Adicionar resumo ao final",
            custom_prompt_scope="tables_only",
        )
        # Deve conter o bloco de PERSONALIZAÇÕES (tables_only)
        assert "PERSONALIZAÇÕES (TABELAS / EXTRAS)" in result
        # Deve conter as regras de segurança
        assert "NÃO altere o tom/estilo" in result
        # Deve conter o override do usuário
        assert "Adicionar resumo ao final" in result

    def test_fidelidade_default_scope_is_tables_only(self, vomo_instance):
        """Sem scope explícito, o default é tables_only."""
        result = vomo_instance._build_system_prompt(
            mode="FIDELIDADE",
            custom_style_override="Custom instructions",
        )
        # Default é tables_only, então deve ter o sandwich seguro
        assert "PERSONALIZAÇÕES (TABELAS / EXTRAS)" in result


class TestFidelidadeStyleAndTablesExplicit:
    def test_style_and_tables_uses_legacy_override(self, vomo_instance):
        """scope=style_and_tables substitui STYLE+TABLE (comportamento legacy)."""
        result = vomo_instance._build_system_prompt(
            mode="FIDELIDADE",
            custom_style_override="Override de estilo completo",
            custom_prompt_scope="style_and_tables",
        )
        # Deve conter o override diretamente (sem sandwich)
        assert "Override de estilo completo" in result
        # NÃO deve conter o bloco de PERSONALIZAÇÕES
        assert "PERSONALIZAÇÕES (TABELAS / EXTRAS)" not in result


class TestApostilaUnchanged:
    def test_apostila_tables_only_unchanged(self, vomo_instance):
        """APOSTILA com tables_only continua funcionando como antes."""
        result = vomo_instance._build_system_prompt(
            mode="APOSTILA",
            custom_style_override="Customizar quadro-síntese",
            custom_prompt_scope="tables_only",
        )
        assert "PERSONALIZAÇÕES (TABELAS / EXTRAS)" in result
        assert "Customizar quadro-síntese" in result


class TestAudienciaUnchanged:
    def test_audiencia_tables_only_unchanged(self, vomo_instance):
        """AUDIENCIA com tables_only continua funcionando como antes."""
        result = vomo_instance._build_system_prompt(
            mode="AUDIENCIA",
            custom_style_override="Personalizar tabela de decisões",
            custom_prompt_scope="tables_only",
        )
        assert "PERSONALIZAÇÕES (TABELAS / EXTRAS)" in result
        assert "Personalizar tabela de decisões" in result


class TestNoCustomPromptNoEffect:
    def test_no_custom_prompt_ignores_scope(self, vomo_instance):
        """Sem custom_prompt, o scope não importa."""
        result_tables = vomo_instance._build_system_prompt(
            mode="FIDELIDADE",
            custom_style_override=None,
            custom_prompt_scope="tables_only",
        )
        result_style = vomo_instance._build_system_prompt(
            mode="FIDELIDADE",
            custom_style_override=None,
            custom_prompt_scope="style_and_tables",
        )
        # Ambos devem produzir o mesmo resultado (sem custom override)
        assert result_tables == result_style
        assert "PERSONALIZAÇÕES" not in result_tables


class TestDisableTablesInteraction:
    def test_disable_tables_ignores_custom_prompt_in_tables_only(self, vomo_instance):
        """Com disable_tables=True e scope=tables_only, custom_prompt é ignorado."""
        result = vomo_instance._build_system_prompt(
            mode="FIDELIDADE",
            custom_style_override="Não deve aparecer",
            custom_prompt_scope="tables_only",
            disable_tables=True,
        )
        assert "Não deve aparecer" not in result
