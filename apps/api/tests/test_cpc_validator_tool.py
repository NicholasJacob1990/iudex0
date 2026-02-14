import json

import pytest

from app.services.ai.claude_agent import sdk_tools
from app.services.ai.claude_agent.tools.cpc_validator import validate_cpc_compliance
from app.services.ai.shared.sse_protocol import ToolApprovalMode
from app.services.ai.shared.tool_handlers import ToolHandlers
from app.services.ai.shared.unified_tools import TOOLS_BY_NAME, get_default_permissions


def _parse_tool_text(response: dict) -> dict:
    text = response["content"][0]["text"]
    return json.loads(text)


@pytest.mark.asyncio
async def test_cpc_validator_peticao_inicial_compliant():
    text = """
    Excelentissimo Senhor Doutor Juiz de Direito da 1a Vara Civel.
    Autor: Joao Silva, CPF 000.000.000-00, profissao advogado, endereco nesta cidade.
    Reu: Empresa X LTDA, CNPJ 00.000.000/0001-00, endereco conhecido.
    DOS FATOS
    O autor narra os fatos da relacao contratual.
    DO DIREITO
    Com fundamento no art. 319 do CPC.
    DOS PEDIDOS
    Requer a procedencia dos pedidos e condenacao.
    Valor da causa: R$ 10.000,00.
    Protesta por provas documental e testemunhal.
    Pede deferimento.
    """

    result = await validate_cpc_compliance(
        document_text=text,
        document_type="peticao_inicial",
    )

    assert result["success"] is True
    assert result["document_type"] == "peticao_inicial"
    assert result["summary"]["overall_status"] == "compliant"
    assert result["summary"]["counts"]["fail"] == 0


@pytest.mark.asyncio
async def test_cpc_validator_deadline_overdue_marks_non_compliant():
    text = """
    Contestacao apresentada com impugnacao especifica dos fatos (art. 341).
    Ha preliminar de inepcia (art. 337) e pedido de improcedencia.
    Contestacao tempestiva em tese, com referencia ao art. 335 do CPC.
    """

    result = await validate_cpc_compliance(
        document_text=text,
        document_type="contestacao",
        reference_date="2026-01-01",
        filing_date="2026-01-30",
    )

    deadline = next(check for check in result["checks"] if check["id"] == "deadline_check")
    assert deadline["status"] == "fail"
    assert result["summary"]["overall_status"] == "non_compliant"


@pytest.mark.asyncio
async def test_cpc_validator_detects_legacy_cpc_reference():
    result = await validate_cpc_compliance(
        document_text="A peca menciona dispositivos do CPC/73 sem justificativa historica.",
        document_type="generic",
    )

    legacy = next(check for check in result["checks"] if check["id"] == "legacy_cpc_reference")
    assert legacy["status"] == "warning"


@pytest.mark.asyncio
async def test_sdk_validate_cpc_compliance_tool_registered_and_runs():
    assert sdk_tools.validate_cpc_compliance in sdk_tools._ALL_TOOLS

    response = await sdk_tools.validate_cpc_compliance(
        {
            "document_text": (
                "Contestacao com impugnacao especifica, preliminar e pedido de improcedencia "
                "com base no art. 337 e art. 341 do CPC."
            ),
            "document_type": "contestacao",
            "reference_date": "2026-01-10",
            "filing_date": "2026-01-20",
        }
    )
    payload = _parse_tool_text(response)

    assert payload["success"] is True
    assert payload["document_type"] == "contestacao"
    assert "summary" in payload


@pytest.mark.asyncio
async def test_unified_tool_and_handler_validate_cpc_compliance():
    assert "validate_cpc_compliance" in TOOLS_BY_NAME

    permissions = get_default_permissions()
    assert permissions["validate_cpc_compliance"] == ToolApprovalMode.ALLOW

    handlers = ToolHandlers()
    execution = await handlers.execute(
        "validate_cpc_compliance",
        {
            "document_text": (
                "Embargos de declaracao por omissao (art. 1022), com pedido de integracao da decisao."
            ),
            "document_type": "embargos_declaracao",
            "reference_date": "2026-01-01",
            "filing_date": "2026-01-05",
        },
    )

    assert execution["success"] is True
    assert execution["result"]["success"] is True
    assert execution["result"]["document_type"] == "embargos_declaracao"

