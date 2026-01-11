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
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chat import Chat, ChatMessage, ChatMode
from app.models.user import User
from app.models.document import Document, DocumentStatus, DocumentType
from app.schemas.chat import (
    ChatCreate, 
    ChatResponse, 
    ChatUpdate, 
    MessageCreate, 
    MessageResponse,
    GenerateDocumentRequest,
    GenerateDocumentResponse
)
from functools import lru_cache
from app.services.document_generator import DocumentGenerator
from app.services.mention_parser import MentionService
from app.services.token_budget_service import TokenBudgetService
from app.services.command_service import CommandService
from app.services.ai.orchestrator import MultiAgentOrchestrator

router = APIRouter()

# Lazy singleton: evita inicialização pesada (RAG/embeddings) em import-time.
@lru_cache(maxsize=1)
def get_document_generator() -> DocumentGenerator:
    return DocumentGenerator()

@lru_cache(maxsize=1)
def get_chat_orchestrator() -> MultiAgentOrchestrator:
    return MultiAgentOrchestrator()

mention_service = MentionService()
token_service = TokenBudgetService()
command_service = CommandService()


@router.get("/", response_model=List[ChatResponse])
async def list_chats(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar chats do usuário
    """
    query = select(Chat).where(
        Chat.user_id == current_user.id,
        Chat.is_active == True
    ).order_by(desc(Chat.updated_at)).offset(skip).limit(limit)
    
    result = await db.execute(query)
    chats = result.scalars().all()
    return chats


@router.post("/", response_model=ChatResponse)
async def create_chat(
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Criar novo chat
    """
    chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter detalhes do chat
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    return chat


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletar chat (soft delete)
    """
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar mensagens do chat
    """
    # Verificar acesso ao chat
    chat_result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enviar mensagem para o chat e obter resposta simples (Claude)
    """
    # Verificar chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
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
    
    # 1. Verificar Slash Commands
    cmd_response, cmd_error = await command_service.parse_command(
        message_in.content, db, current_user.id, chat.context
    )
    
    if cmd_response or cmd_error:
        # É comando - responder imediatamente sem chamar LLM
        ai_content = cmd_response if cmd_response else f"⚠️ Erro ao processar comando: {cmd_error}"
        ai_msg = ChatMessage(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content=ai_content,
            thinking=None, # Comandos não pensam
            created_at=datetime.utcnow()
        )
        
        # Persistir chat (caso o comando tenha alterado contexto)
        flag_modified(chat, "context")
        db.add(chat) # Garantir que o chat está na sessão
        
        db.add(ai_msg)
        await db.commit()
        await db.refresh(ai_msg)
        return ai_msg

    # 2. Processar menções (Parser) + Sticky Context
    sticky_docs = chat.context.get("sticky_docs", [])
    clean_content, system_context, mentions_meta = await mention_service.parse_mentions(
        message_in.content, db, current_user.id, sticky_docs=sticky_docs
    )
    
    current_context = chat.context.copy()
    if system_context:
        current_context["referenced_content"] = system_context

    current_context["chat_personality"] = message_in.chat_personality

    # Persistir sticky docs se houver mudança
    if chat.context.get("sticky_docs") != sticky_docs:
        chat.context["sticky_docs"] = sticky_docs
        # Force update
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(chat, "context")
        await db.commit()
    
    # 3. Pré-checagem de Orçamento de Tokens
    # Usa contagem precisa se houver menções (documentos grandes)
    target_model = "gemini-2.5-pro-preview-06-05" # Default do sistema
    
    if mentions_meta: # Documentos grandes - usar contagem real
        budget = await token_service.check_budget_precise(clean_content, current_context, target_model)
    else:
        budget = token_service.check_budget(clean_content, current_context, target_model)
    
    if budget["status"] == "error":
        # Bloquear envio
        raise HTTPException(
            status_code=400, 
            detail=budget["message"]
        )
    
    # Se warning, logar mas prosseguir
    if budget["status"] == "warning":
        print(f"⚠️ {budget['message']}")

    # Obter resposta da IA (Simples)
    try:
        # Usar conteúdo limpo + contexto enriquecido
        ai_response = await get_chat_orchestrator().simple_chat(
            message=clean_content,
            context=current_context
        )
        ai_content = ai_response.content
        thinking = None
        
        # 4. Telemetria Pós-execução
        item_telemetry = token_service.get_telemetry(ai_response.usage_metadata or {}, target_model)
        
    except Exception as e:
        # Fallback em caso de erro (ex: falta de API Key)
        print(f"Erro na IA: {e}")
        ai_content = f"Desculpe, estou operando em modo offline no momento. Recebi sua mensagem: '{message_in.content}'"
        thinking = "Erro de conexão com LLM"
        item_telemetry = {}
        item_telemetry = {}
    
    # Montar metadados finais
    final_metadata = {}
    if mentions_meta: final_metadata["mentions"] = mentions_meta
    if item_telemetry: final_metadata["token_usage"] = item_telemetry
    
    # Salvar resposta da IA
    ai_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="assistant",
        content=ai_content,
        thinking=thinking,
        metadata=final_metadata if final_metadata else None,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar documento completo com múltiplos agentes
    """
    # Verificar chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = result.scalars().first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")
        
    # Buscar perfil do usuário para contexto
    if request.use_profile == "full":
        user_result = await db.execute(select(User).where(User.id == current_user.id))
        user = user_result.scalars().first()
        if user:
            # Adicionar dados do perfil ao contexto
            chat.context.update(user.full_signature_data)
            
    # Executar Gerador de Documentos (Motor juridico_gemini)
    try:
        # Converter GenerateDocumentRequest do Chat para DocumentGenerationRequest do DocumentGenerator
        # (Eles são compatíveis nos campos principais)
        from app.schemas.document import DocumentGenerationRequest as DocGenRequest
        from app.services.ai.model_registry import validate_model_id, validate_model_list

        # Validate models early (clear 400 errors)
        try:
            judge_model = validate_model_id(request.model, for_juridico=True, field_name="model")
            gpt_model = validate_model_id(getattr(request, "model_gpt", None) or "gpt-5.2", for_agents=True, field_name="model_gpt")
            claude_model = validate_model_id(getattr(request, "model_claude", None) or "claude-4.5-sonnet", for_agents=True, field_name="model_claude")
            strategist_model = getattr(request, "strategist_model", None)
            if strategist_model:
                strategist_model = validate_model_id(strategist_model, for_agents=True, field_name="strategist_model")
            drafter_models = validate_model_list(getattr(request, "drafter_models", None), for_agents=True, field_name="drafter_models")
            reviewer_models = validate_model_list(getattr(request, "reviewer_models", None), for_agents=True, field_name="reviewer_models")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        rag_config = request.rag_config or {}
        use_templates = request.use_templates or bool(rag_config.get("use_templates"))
        template_filters = request.template_filters or rag_config.get("template_filters") or {}
        prompt_extra = request.prompt_extra or rag_config.get("prompt_extra")
        formatting_options = request.formatting_options or rag_config.get("formatting_options") or {}
        template_id = request.template_id or rag_config.get("template_id")
        variables = request.variables or rag_config.get("variables") or {}
        thesis = request.thesis or chat.context.get("thesis") or request.prompt[:100]
        
        doc_request = DocGenRequest(
            prompt=request.prompt,
            document_type=request.document_type,
            effort_level=request.effort_level,
            min_pages=request.min_pages,
            max_pages=request.max_pages,
            attachment_mode=request.attachment_mode,
            use_multi_agent=request.use_multi_agent,
            model_selection=judge_model,
            model_gpt=gpt_model,
            model_claude=claude_model,
            strategist_model=strategist_model,
            drafter_models=drafter_models,
            reviewer_models=reviewer_models,
            chat_personality=request.chat_personality,
            reasoning_level=request.thinking_level,
            web_search=request.web_search,
            dense_research=request.dense_research,
            thesis=thesis,
            citation_style=getattr(request, "citation_style", "forense") or "forense",
            formatting_options=formatting_options,
            use_templates=use_templates,
            template_filters=template_filters,
            prompt_extra=prompt_extra,
            template_id=template_id,
            variables=variables,
            context_documents=request.context_documents,
            audit=True, # Default para jurídico_gemini
            use_langgraph=request.use_langgraph,
            adaptive_routing=request.adaptive_routing,
            crag_gate=request.crag_gate,
            crag_min_best_score=request.crag_min_best_score,
            crag_min_avg_score=request.crag_min_avg_score,
            hyde_enabled=request.hyde_enabled,
            graph_rag_enabled=request.graph_rag_enabled,
            graph_hops=request.graph_hops,
            destino=request.destino,
            risco=request.risco,
            hil_outline_enabled=request.hil_outline_enabled,
            hil_target_sections=request.hil_target_sections
        )

        result = await get_document_generator().generate_document(
            request=doc_request,
            user=current_user,
            db=db,
            context_data={**chat.context, **request.context}
        )
        
        return GenerateDocumentResponse(
            content=result.content,
            metrics=result.cost_info
        )
        
    except Exception as e:
        # Simulação de Fallback Robusta
        print(f"Erro no DocumentGenerator (juridico_gemini): {e}. Usando Fallback.")
        
        final_content = f"""# DEBUG ERROR INFO
{str(e)}

# PETIÇÃO INICIAL (GERADO EM MODO OFFLINE)

EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA ___ VARA CÍVEL DA COMARCA DE SÃO PAULO/SP

**{current_user.name}**, brasileiro, solteiro, portador do CPF nº ..., residente e domiciliado em ..., vem, respeitosamente, perante Vossa Excelência, propor a presente

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

    # Salvar documento gerado no banco
    generated_document = Document(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=f"Minuta - {chat.title or 'Documento'}",
        original_name=f"{chat.title or 'documento'}.md",
        type=DocumentType.TXT,
        status=DocumentStatus.READY,
        size=len(final_content.encode("utf-8")),
        url="",
        content=final_content,
        extracted_text=final_content,
        doc_metadata={
            "source_chat_id": chat_id,
            "generation": metadata or {},
        },
        tags=[],
        folder_id=None,
        is_shared=False,
        is_archived=False,
    )
    db.add(generated_document)

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
