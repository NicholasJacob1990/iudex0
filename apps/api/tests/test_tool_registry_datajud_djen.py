from types import SimpleNamespace

import pytest

from app.services.ai.tool_gateway.tool_registry import ToolCategory, ToolPolicy, tool_registry
from app.services.djen_service import DatajudProcessData, DjenIntimationData


@pytest.fixture(autouse=True)
def reset_registry_state():
    tool_registry.reset()
    yield
    tool_registry.reset()


def test_unified_risk_policy_mapping_is_not_all_allow(monkeypatch):
    from app.services.ai.shared import unified_tools
    from app.services.ai.shared.unified_tools import ToolRiskLevel
    from app.services.ai.shared.tool_registry import ToolCategory as UnifiedToolCategory

    monkeypatch.setattr(
        unified_tools,
        "ALL_UNIFIED_TOOLS",
        [
            SimpleNamespace(
                name="risk-low-tool",
                description="",
                category=UnifiedToolCategory.SEARCH,
                parameters={},
                handler=lambda **kwargs: {"ok": True},
                risk_level=ToolRiskLevel.LOW,
                requires_context=False,
            ),
            SimpleNamespace(
                name="risk-medium-tool",
                description="",
                category=UnifiedToolCategory.SEARCH,
                parameters={},
                handler=lambda **kwargs: {"ok": True},
                risk_level=ToolRiskLevel.MEDIUM,
                requires_context=False,
            ),
            SimpleNamespace(
                name="risk-high-tool",
                description="",
                category=UnifiedToolCategory.SEARCH,
                parameters={},
                handler=lambda **kwargs: {"ok": True},
                risk_level=ToolRiskLevel.HIGH,
                requires_context=False,
            ),
        ],
    )

    tool_registry.initialize()

    assert tool_registry.get("risk-low-tool").policy == ToolPolicy.ALLOW
    assert tool_registry.get("risk-medium-tool").policy == ToolPolicy.ASK
    assert tool_registry.get("risk-high-tool").policy == ToolPolicy.DENY


@pytest.mark.asyncio
async def test_register_datajud_tools_with_expected_metadata():
    tool_registry._register_datajud_tools()

    datajud_tool = tool_registry.get("consultar_processo_datajud")
    djen_tool = tool_registry.get("buscar_publicacoes_djen")

    assert datajud_tool is not None
    assert datajud_tool.policy == ToolPolicy.ALLOW
    assert datajud_tool.category == ToolCategory.DATAJUD

    assert djen_tool is not None
    assert djen_tool.policy == ToolPolicy.ALLOW
    assert djen_tool.category == ToolCategory.DATAJUD


@pytest.mark.asyncio
async def test_consultar_processo_datajud_tool_success(monkeypatch):
    tool_registry._register_datajud_tools()
    tool = tool_registry.get("consultar_processo_datajud")
    assert tool is not None

    class DummyDjenService:
        datajud = SimpleNamespace(api_key="cnj-key")

        async def fetch_metadata(self, npu: str, tribunal_sigla: str):
            assert npu == "0001234-56.2024.8.26.0100"
            assert tribunal_sigla == "TJSP"
            return [
                DatajudProcessData(
                    numero_processo=npu,
                    tribunal_sigla=tribunal_sigla,
                    classe="Procedimento Comum Cível",
                    orgao_julgador=None,
                    sistema=None,
                    formato=None,
                    grau=None,
                    nivel_sigilo=None,
                    data_ajuizamento=None,
                    data_ultima_atualizacao=None,
                    assuntos=["Responsabilidade Civil"],
                    ultimo_movimento=None,
                    movimentos=[],
                )
            ]

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )

    result = await tool.function(numero_processo="0001234-56.2024.8.26.0100", tribunal="tjsp")

    assert result["success"] is True
    assert result["total"] == 1
    assert result["tribunal"] == "TJSP"
    assert result["results"][0]["classe"] == "Procedimento Comum Cível"


@pytest.mark.asyncio
async def test_consultar_processo_datajud_tool_requires_api_key(monkeypatch):
    tool_registry._register_datajud_tools()
    tool = tool_registry.get("consultar_processo_datajud")
    assert tool is not None

    class DummyDjenService:
        datajud = SimpleNamespace(api_key="")

        async def fetch_metadata(self, npu: str, tribunal_sigla: str):
            raise AssertionError("fetch_metadata should not be called without api_key")

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )

    result = await tool.function(numero_processo="1234567-89.2024.8.13.0001", tribunal="TJMG")
    assert result["success"] is False
    assert result["error"] == "CNJ_API_KEY not configured"


@pytest.mark.asyncio
async def test_consultar_processo_datajud_tool_requires_tribunal_if_not_inferable(monkeypatch):
    tool_registry._register_datajud_tools()
    tool = tool_registry.get("consultar_processo_datajud")
    assert tool is not None

    class DummyDjenService:
        datajud = SimpleNamespace(api_key="cnj-key")

        async def fetch_metadata(self, npu: str, tribunal_sigla: str):
            raise AssertionError("fetch_metadata should not be called when tribunal is missing")

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )
    monkeypatch.setattr(
        "app.services.djen_service.extract_tribunal_from_npu",
        lambda _: None,
    )

    result = await tool.function(numero_processo="numero-invalido")
    assert result["success"] is False
    assert "Tribunal nao identificado" in result["error"]


@pytest.mark.asyncio
async def test_buscar_publicacoes_djen_tool_success(monkeypatch):
    tool_registry._register_datajud_tools()
    tool = tool_registry.get("buscar_publicacoes_djen")
    assert tool is not None

    class DummyDjenService:
        async def search_by_process(
            self,
            numero_processo: str,
            tribunal_sigla: str,
            data_inicio: str,
            data_fim: str,
            meio: str,
            max_pages: int,
        ):
            assert numero_processo == "0001234-56.2024.8.26.0100"
            assert tribunal_sigla == "TJSP"
            assert data_inicio == "2024-02-01"
            assert data_fim == "2024-02-10"
            assert meio == "D"
            assert max_pages == 3
            return [
                DjenIntimationData(
                    id=1,
                    hash="abc123",
                    numero_processo="123",
                    numero_processo_mascara="0001234-56.2024.8.26.0100",
                    tribunal_sigla="TJSP",
                    tipo_comunicacao="INTIMACAO",
                    nome_orgao="1 Vara",
                    texto="Publicação teste",
                    data_disponibilizacao="2024-02-01",
                    meio="D",
                    link="https://example.com",
                    tipo_documento="DESPACHO",
                    nome_classe="Procedimento Comum Cível",
                    numero_comunicacao=1,
                    ativo=True,
                    destinatarios=[],
                    advogados=[],
                )
            ]

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )

    result = await tool.function(
        numero_processo="0001234-56.2024.8.26.0100",
        tribunal="TJSP",
        data_inicio="2024-02-01",
        data_fim="2024-02-10",
        meio="D",
        max_pages=3,
    )

    assert result["success"] is True
    assert result["total"] == 1
    assert result["results"][0]["hash"] == "abc123"
