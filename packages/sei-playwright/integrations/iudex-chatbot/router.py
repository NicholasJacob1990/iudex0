"""
FastAPI Router para SEI Tools
Endpoint para executar ferramentas SEI chamadas pelo chat do Iudex

Integre no Iudex:
    from integrations.sei_tools.router import router as sei_router
    app.include_router(sei_router, prefix="/api/sei")
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import os

from .sei_tools import SEIToolExecutor, SEI_TOOLS, SEI_FUNCTIONS, SEI_SYSTEM_PROMPT

router = APIRouter(tags=["SEI Tools"])

# Configuração
SEI_API_URL = os.getenv("SEI_API_URL", "http://localhost:3001")
SEI_API_KEY = os.getenv("SEI_API_KEY", "")

# Executor singleton
_executor: Optional[SEIToolExecutor] = None


def get_executor() -> SEIToolExecutor:
    global _executor
    if _executor is None:
        _executor = SEIToolExecutor(
            sei_api_url=SEI_API_URL,
            sei_api_key=SEI_API_KEY
        )
    return _executor


class ToolCallRequest(BaseModel):
    """Request para executar uma tool"""
    user_id: str
    function_name: str
    arguments: dict[str, Any]


class ToolCallResponse(BaseModel):
    """Response da execução"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


@router.get("/tools")
async def list_tools():
    """
    Lista todas as ferramentas SEI disponíveis

    Retorna no formato compatível com OpenAI/Anthropic/Google tools
    """
    return {
        "tools": SEI_TOOLS,
        "system_prompt": SEI_SYSTEM_PROMPT
    }


@router.get("/tools/openai")
async def list_tools_openai():
    """
    Lista ferramentas no formato OpenAI functions (legado)
    """
    return {
        "functions": SEI_FUNCTIONS
    }


@router.post("/execute", response_model=ToolCallResponse)
async def execute_tool(request: ToolCallRequest):
    """
    Executa uma ferramenta SEI

    Chamado pelo chat do Iudex quando o LLM decide usar uma função SEI.

    Exemplo:
        POST /api/sei/execute
        {
            "user_id": "user123",
            "function_name": "sei_login",
            "arguments": {
                "seiUrl": "https://sei.mg.gov.br",
                "usuario": "joao.silva",
                "senha": "123456"
            }
        }
    """
    executor = get_executor()

    try:
        result = await executor.execute(
            user_id=request.user_id,
            function_name=request.function_name,
            arguments=request.arguments
        )

        return ToolCallResponse(
            success=result.get("success", False),
            data=result.get("data"),
            error=result.get("error")
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/session/{user_id}")
async def check_session(user_id: str):
    """Verifica se usuário tem sessão SEI ativa"""
    executor = get_executor()
    return {
        "active": executor.has_session(user_id),
        "session_id": executor.get_session(user_id)
    }


@router.delete("/session/{user_id}")
async def end_session(user_id: str):
    """Encerra sessão SEI do usuário"""
    executor = get_executor()

    if not executor.has_session(user_id):
        return {"success": False, "message": "Nenhuma sessão ativa"}

    result = await executor.execute(
        user_id=user_id,
        function_name="sei_logout",
        arguments={}
    )

    return {
        "success": result.get("success", False),
        "message": "Sessão encerrada" if result.get("success") else result.get("error")
    }
