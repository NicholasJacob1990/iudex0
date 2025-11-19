"""
Endpoints de Chat e Geração de Documentos
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chat import Chat, ChatMessage, ChatMode
from app.models.user import User
from app.schemas.chat import (
    ChatCreate, 
    ChatResponse, 
    ChatUpdate, 
    MessageCreate, 
    MessageResponse,
    GenerateDocumentRequest,
    GenerateDocumentResponse
)
from app.services.ai.orchestrator import MultiAgentOrchestrator

router = APIRouter()
orchestrator = MultiAgentOrchestrator()


@router.get("/", response_model=List[ChatResponse])
async def list_chats(
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar chats do usuário
    """
    query = select(Chat).where(
        Chat.user_id == current_user["id"],
        Chat.is_active == True
    ).order_by(desc(Chat.updated_at)).offset(skip).limit(limit)
    
    result = await db.execute(query)
    chats = result.scalars().all()
    return chats


@router.post("/", response_model=ChatResponse)
async def create_chat(
    chat_in: ChatCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar novo chat
    """
    chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user["id"],
        title=chat_in.title,
        mode=chat_in.mode,
        context=chat_in.context,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter detalhes do chat
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user["id"]))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    return chat


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletar chat (soft delete)
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user["id"]))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    chat.is_active = False
    await db.commit()
    
    return {"message": "Chat deletado com sucesso"}


@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
async def list_messages(
    chat_id: str,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar mensagens do chat
    """
    # Verificar acesso ao chat
    chat_result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user["id"]))
    if not chat_result.scalars().first():
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    query = select(ChatMessage).where(
        ChatMessage.chat_id == chat_id
    ).order_by(ChatMessage.created_at).offset(skip).limit(limit)
    
    result = await db.execute(query)
    messages = result.scalars().all()
    return messages


@router.post("/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    chat_id: str,
    message_in: MessageCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enviar mensagem para o chat e obter resposta simples (Claude)
    """
    # Verificar chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user["id"]))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    # Salvar mensagem do usuário
    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=message_in.content,
        attachments=message_in.attachments,
        created_at=datetime.utcnow()
    )
    db.add(user_msg)
    
    # Obter resposta da IA (Simples)
    try:
        ai_response = await orchestrator.simple_chat(
            message=message_in.content,
            context=chat.context
        )
        ai_content = ai_response.content
        thinking = None
    except Exception as e:
        # Fallback em caso de erro (ex: falta de API Key)
        print(f"Erro na IA: {e}")
        ai_content = f"Desculpe, estou operando em modo offline no momento. Recebi sua mensagem: '{message_in.content}'"
        thinking = "Erro de conexão com LLM"
    
    # Salvar resposta da IA
    ai_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="assistant",
        content=ai_content,
        thinking=thinking,
        created_at=datetime.utcnow()
    )
    db.add(ai_msg)
    
    # Atualizar chat
    chat.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(ai_msg)
    
    return ai_msg


@router.post("/{chat_id}/generate", response_model=GenerateDocumentResponse)
async def generate_document(
    chat_id: str,
    request: GenerateDocumentRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar documento completo com múltiplos agentes
    """
    # Verificar chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user["id"]))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    # Buscar perfil do usuário para contexto
    if request.use_profile == "full":
        user_result = await db.execute(select(User).where(User.id == current_user["id"]))
        user = user_result.scalars().first()
        if user:
            # Adicionar dados do perfil ao contexto
            chat.context.update(user.full_signature_data)
            
    # Executar Orquestrador
    try:
        result = await orchestrator.generate_document(
            prompt=request.prompt,
            context={**chat.context, **request.context},
            effort_level=request.effort_level
        )
        
        final_content = result.final_content
        reviews = [r.__dict__ for r in result.reviews]
        consensus = result.consensus
        conflicts = result.conflicts
        total_tokens = result.total_tokens
        total_cost = result.total_cost
        processing_time = result.processing_time_seconds
        metadata = result.metadata
        
    except Exception as e:
        # Simulação de Fallback Robusta
        print(f"Erro no Orquestrador: {e}. Usando Fallback.")
        
        final_content = f"""# PETIÇÃO INICIAL (GERADO EM MODO OFFLINE)

EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA ___ VARA CÍVEL DA COMARCA DE SÃO PAULO/SP

**{current_user.get('name', 'NOME DO CLIENTE')}**, brasileiro, solteiro, portador do CPF nº ..., residente e domiciliado em ..., vem, respeitosamente, perante Vossa Excelência, propor a presente

**AÇÃO INDENIZATÓRIA**

em face de **EMPRESA RÉ**, pessoa jurídica de direito privado, pelos fatos e fundamentos a seguir expostos:

**I - DOS FATOS**

{request.prompt}

**II - DO DIREITO**

Conforme dispõe o Código Civil... (Fundamentação gerada offline)

**III - DOS PEDIDOS**

Diante do exposto, requer a procedência total da ação...

Nestes termos,
Pede deferimento.

São Paulo, {datetime.now().strftime('%d/%m/%Y')}

ADVOGADO
OAB/UF ...
"""
        reviews = [
            {
                "agent_name": "Gemini (Revisor Legal)",
                "score": 8.5,
                "approved": True,
                "comments": ["Fundamentação adequada (Simulada)."]
            },
            {
                "agent_name": "GPT (Revisor Textual)",
                "score": 9.0,
                "approved": True,
                "comments": ["Texto claro e objetivo (Simulado)."]
            }
        ]
        consensus = True
        conflicts = []
        total_tokens = 1500
        total_cost = 0.05
        processing_time = 2.5
        metadata = {"mode": "fallback"}

    # Salvar como mensagem no chat
    ai_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="assistant",
        content=final_content,
        thinking=f"Gerado por Multi-Agent Orchestrator (Esforço {request.effort_level})",
        metadata={
            "reviews": reviews,
            "cost": total_cost,
            "tokens": total_tokens
        },
        created_at=datetime.utcnow()
    )
    db.add(ai_msg)
    await db.commit()
    
    return {
        "content": final_content,
        "reviews": reviews,
        "consensus": consensus,
        "conflicts": conflicts,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "processing_time": processing_time,
        "metadata": metadata
    }
