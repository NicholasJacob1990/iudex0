
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import ChatWithDocsRequest, ChatWithDocsResponse
from app.services.ai.juridico_adapter import get_juridico_adapter
from app.services.case_service import CaseService

router = APIRouter()

@router.post("/message", response_model=ChatWithDocsResponse)
async def chat_message(
    request: ChatWithDocsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint dedicado para Chat com Documentos.
    Utiliza o JuridicoGeminiAdapter para processar a mensagem com contexto.
    """
    adapter = get_juridico_adapter()
    
    if not adapter.is_available():
        raise HTTPException(status_code=503, detail="Serviço de IA Jurídica indisponível")

    # Se tiver case_id, podemos buscar documentos do caso (feature futura)
    # Por enquanto, confiamos nos context_files passados ou document_ids
    
    # Resolver caminhos de arquivos se document_ids forem passados (mock logic for now)
    # Na prática, buscaríamos no DB os caminhos dos documentos
    files_to_use = request.context_files
    if request.case_id:
        # TODO: Carregar documentos do caso via CaseService
        pass

    try:
        result = await adapter.chat(
            message=request.message,
            history=request.conversation_history,
            context_files=files_to_use,
            cache_ttl=request.cache_ttl,
            tenant_id=current_user.id,
            custom_prompt=request.custom_prompt,
            rag_config=request.rag_config
        )
        
        return ChatWithDocsResponse(
            reply=result.get("reply", ""),
            sources_used=result.get("sources", []),
            conversation_id="temp_conv_id" # Placeholder
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no chat: {str(e)}")

@router.post("/export-to-case")
async def export_to_case(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Exporta histórico do chat para resumo e tese do caso.
    (Placeholder para implementação futura)
    """
    return {"message": "Not implemented yet"}
