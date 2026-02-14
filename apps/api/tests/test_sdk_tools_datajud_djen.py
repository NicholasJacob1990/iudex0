import json
from types import SimpleNamespace

import pytest

from app.services.ai.claude_agent import sdk_tools
from app.services.djen_service import DatajudMovementData, DatajudProcessData, DjenIntimationData


def _parse_tool_text(response: dict) -> dict:
    text = response["content"][0]["text"]
    return json.loads(text)


@pytest.mark.asyncio
async def test_consultar_processo_datajud_success(monkeypatch):
    result = DatajudProcessData(
        numero_processo="123",
        tribunal_sigla="TJSP",
        classe="Procedimento Comum Cível",
        orgao_julgador="1 Vara",
        sistema="PJe",
        formato="Eletrônico",
        grau="G1",
        nivel_sigilo="0",
        data_ajuizamento="2024-01-01",
        data_ultima_atualizacao="2024-01-10T10:00:00",
        assuntos=["Responsabilidade Civil"],
        ultimo_movimento=DatajudMovementData(
            nome="Conclusos para decisão",
            data_hora="2024-01-10T10:00:00",
            codigo="51",
        ),
        movimentos=[],
    )

    class DummyDjenService:
        datajud = SimpleNamespace(api_key="cnj-key")

        async def fetch_metadata(self, npu: str, tribunal_sigla: str):
            assert npu == "0001234-56.2024.8.26.0100"
            assert tribunal_sigla == "TJSP"
            return [result]

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )

    response = await sdk_tools.consultar_processo_datajud(
        {"numero_processo": "0001234-56.2024.8.26.0100", "tribunal": "tjsp"}
    )
    payload = _parse_tool_text(response)

    assert payload["total"] == 1
    assert payload["tribunal"] == "TJSP"
    assert payload["results"][0]["classe"] == "Procedimento Comum Cível"
    assert payload["results"][0]["ultimo_movimento"]["codigo"] == "51"


@pytest.mark.asyncio
async def test_consultar_processo_datajud_infers_tribunal(monkeypatch):
    captured = {}

    class DummyDjenService:
        datajud = SimpleNamespace(api_key="cnj-key")

        async def fetch_metadata(self, npu: str, tribunal_sigla: str):
            captured["npu"] = npu
            captured["tribunal"] = tribunal_sigla
            return []

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )
    monkeypatch.setattr(
        "app.services.djen_service.extract_tribunal_from_npu",
        lambda _: "TJMG",
    )

    response = await sdk_tools.consultar_processo_datajud(
        {"numero_processo": "1234567-89.2024.8.13.0001"}
    )
    payload = _parse_tool_text(response)

    assert payload["total"] == 0
    assert payload["tribunal"] == "TJMG"
    assert captured["npu"] == "1234567-89.2024.8.13.0001"
    assert captured["tribunal"] == "TJMG"


@pytest.mark.asyncio
async def test_consultar_processo_datajud_requires_tribunal_when_not_inferable(monkeypatch):
    class DummyDjenService:
        datajud = SimpleNamespace(api_key="cnj-key")

        async def fetch_metadata(self, npu: str, tribunal_sigla: str):
            raise AssertionError("fetch_metadata should not be called")

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )
    monkeypatch.setattr(
        "app.services.djen_service.extract_tribunal_from_npu",
        lambda _: None,
    )

    response = await sdk_tools.consultar_processo_datajud(
        {"numero_processo": "numero-invalido"}
    )
    payload = _parse_tool_text(response)

    assert "Tribunal nao identificado" in payload["error"]


@pytest.mark.asyncio
async def test_consultar_processo_datajud_requires_api_key(monkeypatch):
    class DummyDjenService:
        datajud = SimpleNamespace(api_key="")

        async def fetch_metadata(self, npu: str, tribunal_sigla: str):
            raise AssertionError("fetch_metadata should not be called without api_key")

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )

    response = await sdk_tools.consultar_processo_datajud(
        {"numero_processo": "1234567-89.2024.8.13.0001", "tribunal": "TJMG"}
    )
    payload = _parse_tool_text(response)
    assert payload["error"] == "CNJ_API_KEY not configured"


@pytest.mark.asyncio
async def test_buscar_publicacoes_djen_success(monkeypatch):
    intimation = DjenIntimationData(
        id=99,
        hash="hash-1",
        numero_processo="123",
        numero_processo_mascara="0001234-56.2024.8.26.0100",
        tribunal_sigla="TJSP",
        tipo_comunicacao="INTIMACAO",
        nome_orgao="1 Vara",
        texto="Texto da publicacao",
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
            return [intimation]

    monkeypatch.setattr(
        "app.services.djen_service.get_djen_service",
        lambda: DummyDjenService(),
    )

    response = await sdk_tools.buscar_publicacoes_djen(
        {
            "numero_processo": "0001234-56.2024.8.26.0100",
            "tribunal": "TJSP",
            "data_inicio": "2024-02-01",
            "data_fim": "2024-02-10",
            "meio": "D",
            "max_pages": 3,
        }
    )
    payload = _parse_tool_text(response)

    assert payload["total"] == 1
    assert payload["results"][0]["hash"] == "hash-1"
    assert payload["results"][0]["tipo_documento"] == "DESPACHO"


def test_sdk_tool_registry_includes_datajud_and_djen_tools():
    assert sdk_tools.consultar_processo_datajud in sdk_tools._ALL_TOOLS
    assert sdk_tools.buscar_publicacoes_djen in sdk_tools._ALL_TOOLS
