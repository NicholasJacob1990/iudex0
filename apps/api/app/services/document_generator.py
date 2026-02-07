"""
Serviço de Geração de Documentos com Assinatura
Integra IA multi-agente com templates e dados do usuário
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import time
import uuid
import json
from datetime import datetime
from loguru import logger
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.services.ai.orchestrator import MultiAgentOrchestrator
from app.services.rag_module_old import RAGManager
from app.models.user import User
from app.models.document import Document, DocumentType
from app.models.library import LibraryItem, LibraryItemType
from app.schemas.document import DocumentGenerationRequest, DocumentGenerationResponse
from app.services.ai.quality_pipeline import apply_quality_pipeline, get_quality_summary
from app.services.ai.quality_profiles import resolve_quality_profile
from app.services.ai.checklist_parser import (
    parse_document_checklist_from_prompt,
    merge_document_checklist_hints,
)
from app.services.context_strategy import summarize_documents
from app.core.config import settings
from app.core.time_utils import utcnow
from app.services.web_search_service import web_search_service, build_web_context, is_breadth_first
from app.services.legal_templates import legal_template_library
from app.services.model_registry import get_model_config as get_budget_model_config
from app.services.token_budget_service import TokenBudgetService
from app.services.api_call_tracker import job_context
from app.services.job_manager import job_manager
from app.services.billing_service import (
    resolve_plan_key,
    resolve_deep_research_billing,
    get_plan_cap,
    get_deep_research_monthly_status,
)
from app.services.ai.perplexity_config import (
    normalize_perplexity_search_mode,
    normalize_perplexity_recency,
    normalize_perplexity_date,
    parse_csv_list,
    normalize_float,
)
from app.services.ai.citations.style_registry import normalize_citation_style

# Import JuridicoGeminiAdapter (primary generation engine)
try:
    from app.services.ai.juridico_adapter import JuridicoGeminiAdapter, get_juridico_adapter
    JURIDICO_ENGINE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ JuridicoGeminiAdapter não disponível, usando Orchestrator como fallback")
    JURIDICO_ENGINE_AVAILABLE = False

token_budget_service = TokenBudgetService()


def _pick_smallest_context_model(model_ids: List[str]) -> str:
    if not model_ids:
        return "gpt-5.2"
    selected = model_ids[0]
    min_ctx = get_budget_model_config(selected).get("context_window", 0)
    for model_id in model_ids[1:]:
        ctx = get_budget_model_config(model_id).get("context_window", 0)
        if min_ctx <= 0 or (ctx > 0 and ctx < min_ctx):
            selected = model_id
            min_ctx = ctx
    return selected


def _should_use_precise_budget(model_id: str) -> bool:
    provider = (get_budget_model_config(model_id) or {}).get("provider") or ""
    return provider in ("vertex", "google")


def _estimate_attachment_stats(docs: List[Document]) -> tuple[int, int]:
    total_tokens = 0
    total_chars = 0
    for doc in docs:
        text = (getattr(doc, "extracted_text", "") or "").strip()
        if not text:
            continue
        total_chars += len(text)
        total_tokens += token_budget_service.estimate_tokens(text)
    return total_tokens, total_chars


def _estimate_available_tokens(model_id: str, prompt: str, base_context: str) -> int:
    config = get_budget_model_config(model_id) or {}
    limit = config.get("context_window", 0)
    max_output = config.get("max_output", 4096)
    if limit <= 0:
        return 0
    buffer = 1000
    base_tokens = token_budget_service.estimate_tokens(base_context or "")
    prompt_tokens = token_budget_service.estimate_tokens(prompt or "")
    return limit - base_tokens - prompt_tokens - max_output - buffer


def _join_context_parts(*parts: Optional[str]) -> str:
    filtered = [part for part in parts if part]
    return "\n\n".join(filtered).strip()


class DocumentGenerator:
    """
    Serviço que gera documentos jurídicos usando IA e templates,
    incluindo dados de assinatura do usuário.
    
    Usa juridico_gemini.py como motor principal (com RAG, Agent Mode, Auditoria).
    MultiAgentOrchestrator é mantido como fallback.
    """
    
    def __init__(self):
        # RAG Manager compartilhado
        try:
            from app.services.rag_module_old import create_rag_manager
            self.rag_manager = create_rag_manager()
        except Exception as e:
            logger.warning(f"⚠️ RAGManager não pôde ser inicializado: {e}")
            self.rag_manager = None
        
        # Motor Principal: JuridicoGeminiAdapter
        self.juridico_adapter = None
        if JURIDICO_ENGINE_AVAILABLE:
            try:
                self.juridico_adapter = get_juridico_adapter(rag_manager=self.rag_manager)
                logger.info("✅ JuridicoGeminiAdapter inicializado como motor principal")
            except Exception as e:
                logger.error(f"❌ Falha ao inicializar JuridicoGeminiAdapter: {e}")
        
        # Fallback: MultiAgentOrchestrator
        self.orchestrator = MultiAgentOrchestrator()
        
        logger.info(f"DocumentGenerator inicializado (Juridico={'✅' if self.juridico_adapter else '❌'}, Orchestrator=✅)")
    
    async def generate_document(
        self,
        request: DocumentGenerationRequest,
        user: User,
        db: Optional[AsyncSession] = None,
        context_data: Optional[Dict[str, Any]] = None
    ) -> DocumentGenerationResponse:
        """
        Gera documento completo com assinatura
        
        Args:
            request: Dados da requisição de geração
            user: Usuário que está gerando o documento
            db: Sessão do banco de dados (opcional)
            context_data: Dados de contexto adicionais (documentos, etc.)
        
        Returns:
            Resposta com documento gerado
        """
        effective_doc_type = getattr(request, "doc_subtype", None) or request.document_type
        doc_kind = getattr(request, "doc_kind", None)
        doc_subtype = getattr(request, "doc_subtype", None) or effective_doc_type
        request_context = getattr(request, "context", None) or {}
        request_id = getattr(request, "request_id", None)
        if not request_id and isinstance(request_context, dict):
            request_id = request_context.get("request_id")
        if not request_id:
            request_id = f"docgen:{uuid.uuid4().hex}"
        scope_groups = request_context.get("rag_groups") if isinstance(request_context, dict) else None
        if isinstance(scope_groups, str):
            scope_groups = [g.strip() for g in scope_groups.split(",") if g.strip()]
        if not isinstance(scope_groups, list):
            scope_groups = []
        allow_global_scope = request_context.get("rag_allow_global") if isinstance(request_context, dict) else None
        if allow_global_scope is None:
            allow_global_scope = False
        allow_group_scope = request_context.get("rag_allow_groups") if isinstance(request_context, dict) else None
        if allow_group_scope is None:
            allow_group_scope = bool(scope_groups)

        logger.info(f"Gerando documento para usuário {user.id}, tipo: {effective_doc_type}")
        
        # 0. Pré-processamento do Prompt (Variáveis no prompt do usuário)
        raw_prompt = request.prompt
        request.prompt = self._process_prompt_variables(request.prompt, request.variables, user)
        if request.prompt != raw_prompt:
            logger.info("Prompt pré-processado com variáveis")

        # 0.1 Busca Antecipada de Template (para injeção no contexto)
        template_structure = None
        template_meta = None
        template_body = None
        if request.template_id and db:
             try:
                from app.models.library import LibraryItem, LibraryItemType
                result = await db.execute(
                    select(LibraryItem).where(
                        LibraryItem.id == request.template_id,
                        LibraryItem.type == LibraryItemType.MODEL
                    )
                )
                template_item = result.scalars().first()
                if template_item and template_item.description:
                    template_meta, template_body = self._parse_template_frontmatter(template_item.description)
                    if not template_body:
                        template_body = template_item.description
                    template_body = self._process_prompt_variables(template_body, request.variables, user)
                    template_structure = self._build_template_structure_from_meta(
                        template_meta,
                        template_body,
                        request.variables,
                        user
                    )
                    logger.info(f"Template '{template_item.name}' carregado como referência estrutural")
             except Exception as e:
                logger.error(f"Erro ao buscar template antecipadamente: {e}")

        # 0.1.1 Fallback: Verificar se template_id é um template legal pré-definido
        # NOTA: Templates legais usam {var} que não é compatível com {{var}} do motor.
        # O usuário deve importar via POST /templates/legal/{id}/import primeiro.
        if not template_structure and request.template_id:
            legal_template = legal_template_library.get_template(request.template_id)
            if legal_template:
                logger.warning(
                    f"Template legal '{request.template_id}' detectado mas NÃO IMPORTADO. "
                    f"Use POST /templates/legal/{request.template_id}/import para importar primeiro. "
                    f"Aplicando conversão automática de '{{var}}' por best effort."
                )
                # Tentar usar mesmo assim (best effort) - converte {var} para {{var}}
                template_body = legal_template.structure
                # Converter {var} → {{var}}
                template_body = re.sub(r'(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})', r'{{\1}}', template_body)
                template_body = self._process_prompt_variables(template_body, request.variables, user)
                template_structure = template_body
                template_meta = {
                    "id": legal_template.id,
                    "document_type": legal_template.document_type.value,
                    "instructions": legal_template.instructions,
                }
                logger.info(f"Template legal '{legal_template.name}' usado com conversão automática (fallback)")

        if not template_structure and request.template_document_id and db:
            try:
                result = await db.execute(
                    select(Document).where(
                        Document.id == request.template_document_id,
                        Document.user_id == user.id
                    )
                )
                template_doc = result.scalars().first()
                if template_doc:
                    raw_text = template_doc.extracted_text or template_doc.content or ""
                    if raw_text.strip():
                        template_structure = self._process_prompt_variables(raw_text, request.variables, user)
                        logger.info(f"Documento '{template_doc.name}' carregado como modelo estrutural")
                    else:
                        logger.warning("Documento de modelo sem texto extraído ou conteúdo disponível")
                else:
                    logger.warning("Documento de modelo não encontrado ou sem acesso")
            except Exception as e:
                logger.error(f"Erro ao buscar documento modelo: {e}")

        if template_structure:
            template_structure = template_structure.strip()[:12000]

        # Preparar contexto completo
        context = self._prepare_context(request, user, context_data)
        if template_structure:
            context["template_structure"] = template_structure

        template_pref = self._get_template_preferences(user, request.template_id, template_meta)
        locked_blocks_pref = template_pref.get("locked_blocks") if isinstance(template_pref, dict) else None
        if not isinstance(locked_blocks_pref, list):
            locked_blocks_pref = []
        locked_blocks_req = request.variables.get("locked_blocks") if isinstance(request.variables, dict) else None
        if not isinstance(locked_blocks_req, list):
            locked_blocks_req = []
        locked_blocks_hint = list(dict.fromkeys(locked_blocks_pref + locked_blocks_req))

        block_output_instructions = self._build_block_output_instructions(
            template_meta,
            template_body,
            locked_blocks_hint
        )
        if block_output_instructions:
            existing_instr = (context.get("extra_agent_instructions") or "").strip()
            if existing_instr:
                context["extra_agent_instructions"] = existing_instr + "\n" + block_output_instructions
            else:
                context["extra_agent_instructions"] = block_output_instructions

        target_pages, min_pages, max_pages = self._resolve_page_range(request)

        # Resolver aliases de prompt do sistema para manter UI limpa
        from app.services.legal_prompts import LegalPrompts
        if request.prompt == "PROMPT_APOSTILA" or request.template_id == "vomo_apostila":
            request.prompt = LegalPrompts.PROMPT_APOSTILA
            logger.info("Alias PROMPT_APOSTILA resolvido")
        elif request.prompt == "PROMPT_FIDELIDADE" or request.template_id == "vomo_fidelidade":
            request.prompt = LegalPrompts.PROMPT_FIDELIDADE
            logger.info("Alias PROMPT_FIDELIDADE resolvido")

        # 1. Instanciar CaseBundle com documentos de contexto (Novo Agent Mode)
        from app.services.ai.agent_clients import CaseBundle
        
        docs: List[Document] = []
        pdf_paths: List[str] = []
        doc_file_paths: List[str] = []
        if request.context_documents and db:
            try:
                # Buscar documentos no banco
                result = await db.execute(
                    select(Document).where(Document.id.in_(request.context_documents))
                )
                docs = result.scalars().all()

                for doc in docs:
                    path = doc.url
                    if path and os.path.exists(path):
                        doc_file_paths.append(path)
                        if path.lower().endswith('.pdf'):
                            pdf_paths.append(path)
                            logger.info(f"📄 PDF adicionado ao CaseBundle: {path}")
            except Exception as e:
                logger.error(f"Erro ao buscar documentos de contexto: {e}")

        # 0.2 RAG Global (pecas_modelo / lei / juris)
        rag_context = ""
        audit_mode = getattr(request, "audit_mode", "sei_only")
        raw_rag_sources = request.rag_sources or []
        rag_sources = [str(src).strip() for src in raw_rag_sources if str(src).strip()]
        if audit_mode == "sei_only":
            rag_sources = []
        else:
            if not rag_sources:
                rag_sources = ["lei", "juris", "pecas_modelo"]
            if request.use_templates and "pecas_modelo" not in rag_sources:
                rag_sources.append("pecas_modelo")
            rag_sources = list(dict.fromkeys(rag_sources))
        rag_top_k = request.rag_top_k if request.rag_top_k else 8
        rag_top_k = max(1, min(int(rag_top_k), 50))

        if audit_mode != "sei_only" and self.rag_manager and rag_sources and (request.use_templates or request.context_documents):
            try:
                logger.info(f"🔍 Executando RAG Global (use_templates={request.use_templates})")
                
                # Traduzir filtros para pecas_modelo (normaliza CamelCase -> snake_case)
                pecas_filter = {}
                if request.use_templates:
                    tf = request.template_filters
                    # Normalizar chaves: aceita ambos os formatos
                    area = tf.get("area") or tf.get("area", "")
                    rito = tf.get("rito") or tf.get("rito", "")
                    apenas_clause = tf.get("apenas_clause_bank") or tf.get("apenasClauseBank", False)
                    tipo_peca = tf.get("tipo_peca") or tf.get("tipoPeca", "")
                    
                    if area:
                        pecas_filter["area"] = area
                    if rito:
                        pecas_filter["rito"] = rito
                    if tipo_peca:
                        pecas_filter["tipo_peca"] = tipo_peca
                    if apenas_clause:
                        pecas_filter["source_type"] = "clause_bank"
                
                # Query baseada no prompt + tipo de peça
                rag_query = f"{effective_doc_type}: {request.prompt[:500]}"
                
                # Determinar fontes
                results = self.rag_manager.hybrid_search(
                    query=rag_query,
                    sources=rag_sources,
                    top_k=rag_top_k,
                    filters={"pecas_modelo": pecas_filter} if pecas_filter else None,
                    tenant_id="default", # Ajustar se necessário
                    group_ids=scope_groups,
                    include_global=bool(allow_global_scope),
                    allow_group_scope=bool(allow_group_scope),
                    request_id=request_id,
                )
                
                if results:
                    rag_context = self.rag_manager.format_sources_for_prompt(results)
                    logger.info(f"✅ RAG Global retornou {len(results)} fontes")
            except Exception as e:
                logger.error(f"Erro no RAG Global: {e}")

        attachment_mode = (getattr(request, "attachment_mode", "auto") or "auto").lower()
        if attachment_mode not in ["auto", "rag_local", "prompt_injection"]:
            attachment_mode = "rag_local"

        attachment_prompt_context = ""
        if attachment_mode == "auto" and docs:
            budget_models = [
                getattr(request, "model_selection", None) or getattr(request, "model", None),
                getattr(request, "model_gpt", None),
                getattr(request, "model_claude", None),
                getattr(request, "strategist_model", None),
            ]
            budget_models.extend(getattr(request, "drafter_models", []) or [])
            budget_models.extend(getattr(request, "reviewer_models", []) or [])
            budget_model_id = _pick_smallest_context_model([m for m in budget_models if m])

            base_context = _join_context_parts(rag_context)
            attachment_tokens, attachment_chars = _estimate_attachment_stats(docs)
            if attachment_tokens > 0:
                available_tokens = _estimate_available_tokens(budget_model_id, request.prompt, base_context)
                available_chars = max(0, int(available_tokens * 3.5))
                if available_tokens > 0 and attachment_chars > 0 and attachment_chars <= available_chars:
                    max_chars = min(attachment_chars, available_chars)
                    attachment_prompt_context = self._build_attachment_prompt_context(
                        docs,
                        max_chars=max_chars,
                        per_doc_chars=max_chars,
                    )

            if not attachment_prompt_context:
                attachment_mode = "rag_local"
            else:
                budget_context = _join_context_parts(base_context, attachment_prompt_context)
                if _should_use_precise_budget(budget_model_id):
                    budget = await token_budget_service.check_budget_precise(
                        request.prompt,
                        {"system": budget_context},
                        budget_model_id,
                    )
                else:
                    budget = token_budget_service.check_budget(
                        request.prompt,
                        {"system": budget_context},
                        budget_model_id,
                    )
                if budget["status"] == "error":
                    attachment_mode = "rag_local"
                    attachment_prompt_context = ""
                else:
                    attachment_mode = "prompt_injection"

            stats = summarize_documents(docs)
            logger.info(
                "Auto attachment_mode=%s (files=%s, text_chars=%s, bytes=%s, budget_model=%s)",
                attachment_mode,
                stats.file_count,
                stats.text_chars,
                stats.total_bytes,
                budget_model_id,
            )
        elif attachment_mode == "auto":
            attachment_mode = "rag_local"

        if attachment_mode == "prompt_injection" and docs and not attachment_prompt_context:
            attachment_prompt_context = self._build_attachment_prompt_context(docs)
        if attachment_mode == "prompt_injection" and not attachment_prompt_context:
            attachment_mode = "rag_local"

        local_rag_context = ""
        if attachment_mode == "rag_local" and docs:
            local_rag_context = self._build_local_rag_context(
                docs=docs,
                query=f"{effective_doc_type}: {request.prompt[:800]}",
                tenant_id="default"
            )
            if local_rag_context:
                rag_context = f"{local_rag_context}\n\n{rag_context}".strip()

        search_mode = (getattr(request, "search_mode", "hybrid") or "hybrid").lower()
        if search_mode not in ("shared", "native", "hybrid", "perplexity"):
            search_mode = "hybrid"
        perplexity_search_mode = normalize_perplexity_search_mode(
            getattr(request, "perplexity_search_mode", None)
        )
        search_domain_filter = parse_csv_list(
            getattr(request, "perplexity_search_domain_filter", None),
            max_items=20,
        )
        search_language_filter = parse_csv_list(
            getattr(request, "perplexity_search_language_filter", None),
            max_items=10,
        )
        search_recency_filter = normalize_perplexity_recency(
            getattr(request, "perplexity_search_recency_filter", None)
        )
        search_after_date = normalize_perplexity_date(
            getattr(request, "perplexity_search_after_date", None)
        )
        search_before_date = normalize_perplexity_date(
            getattr(request, "perplexity_search_before_date", None)
        )
        last_updated_after = normalize_perplexity_date(
            getattr(request, "perplexity_last_updated_after", None)
        )
        last_updated_before = normalize_perplexity_date(
            getattr(request, "perplexity_last_updated_before", None)
        )
        try:
            search_max_results = int(getattr(request, "perplexity_search_max_results", None))
        except (TypeError, ValueError):
            search_max_results = None
        if search_max_results is not None and search_max_results <= 0:
            search_max_results = None
        if search_max_results is not None and search_max_results > 20:
            search_max_results = 20
        try:
            search_max_tokens = int(getattr(request, "perplexity_search_max_tokens", None))
        except (TypeError, ValueError):
            search_max_tokens = None
        if search_max_tokens is not None and search_max_tokens <= 0:
            search_max_tokens = None
        if search_max_tokens is not None and search_max_tokens > 1_000_000:
            search_max_tokens = 1_000_000
        try:
            search_max_tokens_per_page = int(
                getattr(request, "perplexity_search_max_tokens_per_page", None)
            )
        except (TypeError, ValueError):
            search_max_tokens_per_page = None
        if search_max_tokens_per_page is not None and search_max_tokens_per_page <= 0:
            search_max_tokens_per_page = None
        if search_max_tokens_per_page is not None and search_max_tokens_per_page > 1_000_000:
            search_max_tokens_per_page = 1_000_000
        search_country = (getattr(request, "perplexity_search_country", None) or "").strip() or None
        search_latitude = normalize_float(getattr(request, "perplexity_search_latitude", None))
        search_longitude = normalize_float(getattr(request, "perplexity_search_longitude", None))
        return_images = bool(getattr(request, "perplexity_return_images", False))
        return_videos = bool(getattr(request, "perplexity_return_videos", False))
        max_results = search_max_results or 8
        breadth_first = bool(getattr(request, "breadth_first", False)) or (
            request.web_search and is_breadth_first(request.prompt)
        )
        multi_query = bool(getattr(request, "multi_query", True)) or breadth_first
        allow_native_search = bool(request.web_search) and search_mode in ("native", "hybrid")
        use_shared_search = bool(request.web_search) and search_mode in ("shared", "hybrid", "perplexity")
        if audit_mode == "sei_only":
            allow_native_search = False
            use_shared_search = False

        shared_web_context = ""
        if use_shared_search and request.web_search:
            try:
                search_query = request.thesis or request.prompt[:300]
                search_query = f"{effective_doc_type} {search_query}".strip()
                logger.info(f"🔎 Busca web compartilhada (doc): {search_query[:80]}")
                if multi_query:
                    search_payload = await web_search_service.search_multi(
                        search_query,
                        num_results=max_results,
                        search_mode=perplexity_search_mode,
                        country=search_country,
                        domain_filter=search_domain_filter,
                        language_filter=search_language_filter,
                        recency_filter=search_recency_filter,
                        search_after_date=search_after_date,
                        search_before_date=search_before_date,
                        last_updated_after=last_updated_after,
                        last_updated_before=last_updated_before,
                        max_tokens=search_max_tokens,
                        max_tokens_per_page=search_max_tokens_per_page,
                        return_images=return_images,
                        return_videos=return_videos,
                    )
                else:
                    search_payload = await web_search_service.search(
                        search_query,
                        num_results=max_results,
                        search_mode=perplexity_search_mode,
                        country=search_country,
                        domain_filter=search_domain_filter,
                        language_filter=search_language_filter,
                        recency_filter=search_recency_filter,
                        search_after_date=search_after_date,
                        search_before_date=search_before_date,
                        last_updated_after=last_updated_after,
                        last_updated_before=last_updated_before,
                        max_tokens=search_max_tokens,
                        max_tokens_per_page=search_max_tokens_per_page,
                        return_images=return_images,
                        return_videos=return_videos,
                    )
                results = search_payload.get("results") or []
                if search_payload.get("success") and results:
                    shared_web_context = build_web_context(search_payload, max_items=max_results)
            except Exception as e:
                logger.error(f"Erro na busca web compartilhada: {e}")

        if shared_web_context:
            rag_context = f"{shared_web_context}\n\n{rag_context}".strip()

        engine_web_search = allow_native_search

        # Criar CaseBundle que passará para o orchestrator
        case_bundle = CaseBundle(
            processo_id=f"UserRequest-{user.id[:8]}",
            pdf_paths=pdf_paths,
            # Se houver texto extraído, podemos concatenar no text_pack 
            # (mas agent_clients usa pdf_paths prioritariamente se native_pdf)
            text_pack="\n\n".join([d.extracted_text for d in docs if d.extracted_text]) if 'docs' in locals() else ""
        )
        context["case_bundle"] = case_bundle
        context["rag_context"] = rag_context
        context["chat_personality"] = getattr(request, "chat_personality", "juridico")
        sei_context = ""
        if attachment_mode == "prompt_injection":
            if attachment_prompt_context:
                sei_context = attachment_prompt_context
            elif docs:
                sei_context = self._build_attachment_prompt_context(
                    docs,
                    max_chars=settings.ATTACHMENT_INJECTION_MAX_CHARS,
                    per_doc_chars=settings.ATTACHMENT_INJECTION_MAX_CHARS_PER_DOC,
                )
            elif case_bundle and getattr(case_bundle, "text_pack", ""):
                sei_context = (case_bundle.text_pack or "")[:settings.ATTACHMENT_INJECTION_MAX_CHARS]
        elif attachment_mode == "rag_local" and local_rag_context:
            sei_context = local_rag_context
        
        # Adicionar Prompt Extra e Instruções de Uso de Modelos se habilitado
        if request.use_templates:
            prompt_extra_instr = f"\n## INSTRUÇÃO ADICIONAL DE ESTILO/MODELO:\n{request.prompt_extra}\n" if request.prompt_extra else ""
            regra_modelos = """
REGRA ESPECIAL – USO DE MODELOS / CLAUSE BANK:
1. Priorize os trechos marcados como "📝 Modelo" (coleção pecas_modelo) ao estruturar esta seção.
2. Se houver blocos (Clause Bank) com metadados de tipo_bloco/subtipo, utilize-os como BASE, adaptando a redação aos fatos concretos do caso.
3. NÃO copie trechos que entrem em conflito com os fatos dos autos. Adapte sempre que necessário.
4. Mantenha a coerência com o tipo de peça solicitada.
"""
            existing_instr = (context.get("extra_agent_instructions") or "").strip()
            merged = (prompt_extra_instr + regra_modelos).strip()
            if existing_instr:
                context["extra_agent_instructions"] = existing_instr + "\n" + merged
            else:
                context["extra_agent_instructions"] = merged
        
        # Preparar prompt com informações do usuário
        enhanced_prompt = self._enhance_prompt_with_user_data(
            request.prompt,
            user,
            effective_doc_type
        )

        if attachment_mode == "prompt_injection" and docs:
            attachment_text = attachment_prompt_context or self._build_attachment_prompt_context(docs)
            if attachment_text:
                enhanced_prompt += "\n\n" + attachment_text

        if block_output_instructions:
            enhanced_prompt += "\n\n" + block_output_instructions

        langgraph_input_text = enhanced_prompt

        personality = (getattr(request, "chat_personality", "juridico") or "juridico").lower()
        personality_instr = self._build_personality_instructions(personality)
        if personality_instr:
            enhanced_prompt += "\n\n" + personality_instr
            existing_instr = (context.get("extra_agent_instructions") or "").strip()
            if existing_instr:
                context["extra_agent_instructions"] = existing_instr + "\n" + personality_instr
            else:
                context["extra_agent_instructions"] = personality_instr

        evidence_policy = ""
        if audit_mode == "research":
            evidence_policy = (
                "## POLÍTICA DE EVIDÊNCIA (PESQUISA)\n"
                "- SEI/autos do caso (RAG local + anexos) são a fonte de verdade para fatos administrativos.\n"
                "- Fontes externas servem apenas para fundamentação normativa/jurisprudencial.\n"
                "- Nunca trate fonte externa como prova de fato do processo.\n"
                "- Separe claramente 'fato dos autos' vs 'fundamentação externa'.\n"
            )
        else:
            evidence_policy = (
                "## POLÍTICA DE EVIDÊNCIA (AUDITORIA - SOMENTE SEI)\n"
                "- Use exclusivamente o SEI/autos do caso (RAG local + anexos) para fatos e eventos administrativos.\n"
                "- Não cite nem invente fontes externas para comprovar fatos.\n"
                "- Se faltar prova no SEI, marque como [[PENDENTE: confirmar no SEI]].\n"
            )
        if evidence_policy:
            enhanced_prompt += "\n\n" + evidence_policy
            existing_instr = (context.get("extra_agent_instructions") or "").strip()
            if existing_instr:
                context["extra_agent_instructions"] = existing_instr + "\n" + evidence_policy
            else:
                context["extra_agent_instructions"] = evidence_policy

        # Estilo de citação (ABNT/Híbrido) — instruções para o gerador
        citation_style = (getattr(request, "citation_style", None) or "forense").lower()
        citation_style_normalized = normalize_citation_style(citation_style, default="forense_br")
        if citation_style_normalized != "forense_br":
            enhanced_prompt += "\n\n" + (
                "## ESTILO DE CITAÇÃO (ABNT/HÍBRIDO)\n"
                "- Autos/peças: ao citar fatos dos autos, mantenha [TIPO - Doc. X, p. Y].\n"
                "- Jurisprudência: inclua tribunal/classe/número/UF quando houver no contexto.\n"
                "- Use notas de rodapé numeradas [n] no texto e inclua ao final a seção 'NOTAS DE RODAPÉ (ABNT NBR 6023)' com a referência completa de cada nota.\n"
                "- Fontes acadêmicas/doutrina (quando presentes no RAG): use (AUTOR, ano) no texto e detalhe a referência completa nas notas ABNT.\n"
                "- Se faltar metadado (autor/ano), não invente: use [[PENDENTE: completar referência ABNT]].\n"
            )
            # Também deixa disponível para o modo multi-agente
            context["extra_agent_instructions"] = (context.get("extra_agent_instructions") or "") + "\n" + (
                "## ESTILO DE CITAÇÃO (ABNT/HÍBRIDO)\n"
                "Autos: preserve [TIPO - Doc. X, p. Y].\n"
                "Notas: use [n] no texto e liste as notas ABNT ao final.\n"
                "Acadêmico: (AUTOR, ano) + notas ABNT completas.\n"
            )

        if shared_web_context:
            if citation_style_normalized != "forense_br":
                search_instruction = (
                    "## ORIENTAÇÕES PARA FONTES DA WEB (ABNT)\n"
                    "- Use notas de rodapé [n] no texto.\n"
                    "- Ao final, inclua 'NOTAS DE RODAPÉ (ABNT NBR 6023)' com a referência completa de cada nota.\n"
                )
            else:
                search_instruction = (
                    "## ORIENTAÇÕES PARA FONTES DA WEB\n"
                    "- Use as fontes numeradas quando relevante.\n"
                    "- Cite no texto com [n] e finalize com uma seção 'Fontes:' listando apenas URLs citadas.\n"
                )
            enhanced_prompt += "\n\n" + search_instruction + "\n" + shared_web_context
            existing_instr = (context.get("extra_agent_instructions") or "").strip()
            context["extra_agent_instructions"] = (existing_instr + "\n" + search_instruction).strip()
        
        # =====================================================================
        # GERAÇÃO: LangGraph (prioritário), JuridicoGeminiAdapter ou Orchestrator (fallback)
        # =====================================================================
        document_id = str(uuid.uuid4())

        content = ""
        audit_data = None
        citations_log = []
        cost_info = {}
        quality_payload = None
        fallback_reasons: List[str] = []
        agents_used: List[str] = []

        raw_temperature = getattr(request, "temperature", None)
        try:
            temperature = float(raw_temperature) if raw_temperature is not None else 0.3
        except (TypeError, ValueError):
            temperature = 0.3
        temperature = max(0.0, min(1.0, temperature))
        fallback_profile = resolve_quality_profile(
            getattr(request, "quality_profile", "padrao"),
            {
                "max_rounds": getattr(request, "max_rounds", None),
            }
        )
        fallback_max_rounds = int(fallback_profile.get("max_rounds", 1))
        fallback_max_rounds = max(1, min(6, fallback_max_rounds))

        # LangGraph (Legal Workflow) — usar se habilitado
        use_langgraph = getattr(request, "use_langgraph", False)
        env_langgraph = os.getenv("ENABLE_LANGGRAPH_WORKFLOW")
        if env_langgraph is not None:
            use_langgraph = env_langgraph.lower() == "true"

        if use_langgraph:
            logger.info("🔗 Usando LangGraph Legal Workflow como motor principal")
            try:
                from app.services.ai.langgraph_legal_workflow import legal_workflow_app

                start_time = time.time()
                input_text = langgraph_input_text
                case_text = ""
                if case_bundle and getattr(case_bundle, "text_pack", ""):
                    case_text = case_bundle.text_pack.strip()
                if case_text:
                    input_text += "\n\n--- CONTEXTO DOS AUTOS (DOCUMENTOS) ---\n" + case_text[:6000]

                profile_config = resolve_quality_profile(
                    getattr(request, "quality_profile", "padrao"),
                    {
                        "target_section_score": getattr(request, "target_section_score", None),
                        "target_final_score": getattr(request, "target_final_score", None),
                        "max_rounds": getattr(request, "max_rounds", None),
                        "strict_document_gate": getattr(request, "strict_document_gate", None),
                        "hil_section_policy": getattr(request, "hil_section_policy", None),
                        "hil_final_required": getattr(request, "hil_final_required", None),
                        "recursion_limit": getattr(request, "recursion_limit", None),
                        "style_refine_max_rounds": getattr(request, "style_refine_max_rounds", None),
                        "max_research_verifier_attempts": getattr(request, "max_research_verifier_attempts", None),
                        "max_rag_retries": getattr(request, "max_rag_retries", None),
                        "rag_retry_expand_scope": getattr(request, "rag_retry_expand_scope", None),
                        "crag_min_best_score": getattr(request, "crag_min_best_score", None),
                        "crag_min_avg_score": getattr(request, "crag_min_avg_score", None),
                    }
                )
                prompt_checklist_hint = parse_document_checklist_from_prompt(request.prompt or "")
                merged_checklist_hint = merge_document_checklist_hints(
                    getattr(request, "document_checklist_hint", []) or [],
                    prompt_checklist_hint,
                )

                chat_history = []
                chat_id = getattr(request, "chat_id", None)
                if chat_id and db:
                    try:
                        from app.services.chat_history import fetch_chat_history
                        chat_history = await fetch_chat_history(db, chat_id)
                    except Exception as e:
                        logger.warning(f"⚠️ Falha ao carregar historico do chat {chat_id}: {e}")

                plan_key = resolve_plan_key(getattr(user, "plan", None))
                deep_effort, deep_multiplier = resolve_deep_research_billing(
                    plan_key,
                    getattr(request, "deep_research_effort", None),
                )
                deep_enabled = bool(getattr(request, "dense_research", False)) and bool(deep_effort)
                if deep_enabled and db and getattr(user, "id", None):
                    status = await get_deep_research_monthly_status(
                        db,
                        user_id=str(user.id),
                        plan_key=plan_key,
                    )
                    if not status.get("allowed", True):
                        logger.warning(
                            "⚠️ Deep research monthly cap reached (plan=%s used=%s cap=%s); disabling deep research.",
                            plan_key,
                            status.get("used"),
                            status.get("cap"),
                        )
                        deep_enabled = False
                        deep_effort = None
                        deep_multiplier = 1.0
                max_web_search_requests = get_plan_cap(plan_key, "max_web_search_requests", default=5)
                max_hil_iterations = get_plan_cap(plan_key, "max_hil_iterations", default=0)
                max_final_review_loops = get_plan_cap(
                    plan_key,
                    "max_final_review_loops",
                    default=profile_config.get("max_rounds", 0),
                )
                max_style_loops = get_plan_cap(
                    plan_key,
                    "max_style_loops",
                    default=profile_config.get("style_refine_max_rounds", 2),
                )
                max_granular_passes = get_plan_cap(plan_key, "max_granular_passes", default=2)
                style_refine_max_rounds = int(profile_config.get("style_refine_max_rounds", 2))
                if max_style_loops is not None:
                    style_refine_max_rounds = min(style_refine_max_rounds, max_style_loops)
                final_review_loops = int(profile_config.get("max_rounds", 0))
                if max_final_review_loops is not None:
                    final_review_loops = min(final_review_loops, max_final_review_loops)
                web_enabled = bool(engine_web_search)
                if max_web_search_requests is not None and max_web_search_requests <= 0:
                    web_enabled = False

                initial_state = {
                    "input_text": input_text,
                    "mode": effective_doc_type,
                    "doc_kind": doc_kind,
                    "doc_subtype": doc_subtype,
                    "tese": request.thesis or "",
                    "job_id": document_id,
                    "request_id": request_id,
                    "tenant_id": getattr(user, "id", None),
                    "rag_scope_groups": scope_groups,
                    "rag_allow_global": allow_global_scope,
                    "rag_allow_groups": allow_group_scope,
                    "messages": chat_history,
                    "deep_research_enabled": deep_enabled,
                    "deep_research_effort": deep_effort,
                    "deep_research_points_multiplier": deep_multiplier,
                    "web_search_enabled": web_enabled,
                    "search_mode": search_mode,
                    "perplexity_search_mode": getattr(request, "perplexity_search_mode", None),
                    "perplexity_search_type": getattr(request, "perplexity_search_type", None),
                    "perplexity_search_context_size": getattr(request, "perplexity_search_context_size", None),
                    "perplexity_search_classifier": bool(getattr(request, "perplexity_search_classifier", False)),
                    "perplexity_disable_search": bool(getattr(request, "perplexity_disable_search", False)),
                    "perplexity_stream_mode": getattr(request, "perplexity_stream_mode", None),
                    "perplexity_search_domain_filter": getattr(request, "perplexity_search_domain_filter", None),
                    "perplexity_search_language_filter": getattr(request, "perplexity_search_language_filter", None),
                    "perplexity_search_recency_filter": getattr(request, "perplexity_search_recency_filter", None),
                    "perplexity_search_after_date": getattr(request, "perplexity_search_after_date", None),
                    "perplexity_search_before_date": getattr(request, "perplexity_search_before_date", None),
                    "perplexity_last_updated_after": getattr(request, "perplexity_last_updated_after", None),
                    "perplexity_last_updated_before": getattr(request, "perplexity_last_updated_before", None),
                    "perplexity_search_country": getattr(request, "perplexity_search_country", None),
                    "perplexity_search_region": getattr(request, "perplexity_search_region", None),
                    "perplexity_search_city": getattr(request, "perplexity_search_city", None),
                    "perplexity_search_latitude": getattr(request, "perplexity_search_latitude", None),
                    "perplexity_search_longitude": getattr(request, "perplexity_search_longitude", None),
                    "perplexity_return_images": bool(getattr(request, "perplexity_return_images", False)),
                    "perplexity_return_videos": bool(getattr(request, "perplexity_return_videos", False)),
                    "research_policy": getattr(request, "research_policy", "auto"),
                    "research_mode": "none",
                    "last_research_step": "none",
                    "web_search_insufficient": False,
                    "need_juris": False,
                    "planning_reasoning": None,
                    "planned_queries": [],
                    "multi_query": bool(multi_query),
                    "breadth_first": bool(breadth_first),
                    "use_multi_agent": bool(request.use_multi_agent),
                    "thinking_level": request.reasoning_level,
                    "chat_personality": personality,
                    "temperature": temperature,
                    "deep_research_search_focus": getattr(request, "deep_research_search_focus", None),
                    "deep_research_domain_filter": getattr(request, "deep_research_domain_filter", None),
                    "deep_research_search_after_date": getattr(request, "deep_research_search_after_date", None),
                    "deep_research_search_before_date": getattr(request, "deep_research_search_before_date", None),
                    "deep_research_last_updated_after": getattr(request, "deep_research_last_updated_after", None),
                    "deep_research_last_updated_before": getattr(request, "deep_research_last_updated_before", None),
                    "deep_research_country": getattr(request, "deep_research_country", None),
                    "deep_research_latitude": getattr(request, "deep_research_latitude", None),
                    "deep_research_longitude": getattr(request, "deep_research_longitude", None),
                    "destino": getattr(request, "destino", "uso_interno"),
                    "risco": getattr(request, "risco", "baixo"),
                    "formatting_options": request.formatting_options,
                    "template_structure": template_structure,
                    "citation_style": request.citation_style,
                    "target_pages": target_pages,
                    "min_pages": min_pages,
                    "max_pages": max_pages,
                    "crag_gate_enabled": bool(getattr(request, "crag_gate", False)),
                    "adaptive_routing_enabled": bool(getattr(request, "adaptive_routing", False)),
                    "crag_min_best_score": float(profile_config.get("crag_min_best_score", 0.45)),
                    "crag_min_avg_score": float(profile_config.get("crag_min_avg_score", 0.35)),
                    "rag_sources": rag_sources,
                    "rag_top_k": rag_top_k,
                    "max_web_search_requests": max_web_search_requests,
                    "max_granular_passes": max_granular_passes,
                    "max_final_review_loops": final_review_loops,
                    "hil_iterations_cap": max_hil_iterations,
                    "hil_iterations_count": 0,
                    "hil_iterations_by_checkpoint": {},
                    "max_research_verifier_attempts": int(profile_config.get("max_research_verifier_attempts", 1)),
                    "max_rag_retries": int(profile_config.get("max_rag_retries", 1)),
                    "rag_retry_expand_scope": bool(profile_config.get("rag_retry_expand_scope", False)),
                    "case_bundle_text_pack": case_bundle.text_pack if case_bundle else "",
                    "case_bundle_pdf_paths": case_bundle.pdf_paths if case_bundle else [],
                    "case_bundle_processo_id": case_bundle.processo_id if case_bundle else None,
                    "hyde_enabled": bool(getattr(request, "hyde_enabled", False)),
                    "graph_rag_enabled": bool(getattr(request, "graph_rag_enabled", False)),
                    "graph_hops": int(getattr(request, "graph_hops", 1) or 1),
                    "argument_graph_enabled": bool((context_data or {}).get("argument_graph_enabled", False)),
                    "messages": getattr(request, "messages", None) or [],
                    "section_routing_reasons": {},
                    "outline": [],
                    "processed_sections": [],
                    "full_document": "",
                    "research_context": rag_context or None,
                    "research_sources": [],
                    "research_notes": None,
                    "citations_map": {},
                    "deep_research_thinking_steps": [],
                    "deep_research_from_cache": False,
                    "deep_research_streamed": False,
                    "verifier_attempts": 0,
                    "verification_retry": False,
                    "verification_retry_reason": None,
                    "has_any_divergence": False,
                    "divergence_summary": "",
                    "audit_status": "aprovado",
                    "audit_report": None,
                    "audit_issues": [],
                    "hil_checklist": None,
                    "audit_mode": audit_mode,
                    "sei_context": sei_context or None,
                    "document_checklist_hint": merged_checklist_hint,
                    "document_checklist": None,
                    "document_gate_status": None,
                    "document_gate_missing": [],
                    "style_report": None,
                    "style_score": None,
                    "style_tone": None,
                    "style_issues": [],
                    "style_term_variations": [],
                    "style_check_status": None,
                    "style_check_payload": None,
                    "style_instruction": None,
                    "style_refine_round": 0,
                    "style_refine_max_rounds": style_refine_max_rounds,
                    "style_min_score": 8.0,
                    "quality_profile": getattr(request, "quality_profile", "padrao"),
                    "target_section_score": float(profile_config["target_section_score"]),
                    "target_final_score": float(profile_config["target_final_score"]),
                    "max_rounds": int(profile_config["max_rounds"]),
                    "recursion_limit": int(profile_config.get("recursion_limit", 160)),
                    "refinement_round": 0,
                    "strict_document_gate": bool(profile_config.get("strict_document_gate", False)),
                    "hil_section_policy": profile_config.get("hil_section_policy", "optional"),
                    "force_final_hil": bool(profile_config.get("hil_final_required", True)),
                    "proposed_corrections": None,
                    "corrections_diff": None,
                    "human_approved_corrections": False,
                    "quality_gate_passed": True,
                    "quality_gate_results": [],
                    "quality_gate_force_hil": False,
                    "structural_fix_result": None,
                    "patch_result": None,
                    "patches_applied": [],
                    "targeted_patch_used": False,
                    "quality_report": None,
                    "quality_report_markdown": None,
                    "human_approved_divergence": False,
                    "human_approved_final": False,
                    "human_edits": None,
                    "final_markdown": "",
                    "final_decision": None,
                    "final_decision_reasons": [],
	                    "final_decision_score": None,
	                    "final_decision_target": None,
	                    "hil_target_sections": getattr(request, "hil_target_sections", []) or [],
	                    "outline_override": getattr(request, "outline_override", []) or [],
	                    "hil_section_payload": None,
	                    "hil_outline_enabled": bool(getattr(request, "hil_outline_enabled", False)),
	                    "hil_outline_payload": None,
                    "judge_model": request.model_selection or "gemini-3-flash",
                    "gpt_model": request.model_gpt or "gpt-5.2",
                    "claude_model": request.model_claude or "claude-4.5-sonnet",
                    "strategist_model": getattr(request, "strategist_model", None),
                    "drafter_models": getattr(request, "drafter_models", []) or [],
                    "reviewer_models": getattr(request, "reviewer_models", []) or [],
                    "auto_approve_hil": True
                }
                # Billing / Budget (soft caps): propagated from endpoint quote when available.
                budget_approved_points = None
                budget_estimate_points = None
                for source in (context_data, request_context):
                    if isinstance(source, dict):
                        if budget_approved_points is None:
                            budget_approved_points = source.get("budget_approved_points")
                        if budget_estimate_points is None:
                            budget_estimate_points = source.get("budget_estimate_points")
                try:
                    if budget_approved_points is not None:
                        initial_state["budget_approved_points"] = int(budget_approved_points)
                except (TypeError, ValueError):
                    pass
                try:
                    if budget_estimate_points is not None:
                        initial_state["budget_estimate_points"] = int(budget_estimate_points)
                except (TypeError, ValueError):
                    pass

                config = {
                    "configurable": {"thread_id": document_id},
                    "recursion_limit": int(profile_config.get("recursion_limit", 160))
                }
                with job_context(document_id, user_id=user.id):
                    result = await legal_workflow_app.ainvoke(initial_state, config)
                snapshot = legal_workflow_app.get_state(config)
                state_values = {}
                if snapshot and snapshot.values:
                    state_values = snapshot.values
                elif isinstance(result, dict):
                    state_values = result

                from app.services.ai.document_store import resolve_full_document
                content = state_values.get("final_markdown") or resolve_full_document(state_values) or ""
                audit_data = state_values.get("audit_report")
                citations_log = (audit_data or {}).get("citations", [])

                agents_used = self._infer_agents_from_langgraph(state_values, request)
                api_counters = job_manager.get_api_counters(document_id) if document_id else {}
                decision_payload = {
                    "final_decision": state_values.get("final_decision"),
                    "final_decision_reasons": state_values.get("final_decision_reasons", []),
                    "final_decision_score": state_values.get("final_decision_score"),
                    "final_decision_target": state_values.get("final_decision_target"),
                }

                cost_info = {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "processing_time": time.time() - start_time,
                    "agents_used": agents_used,
                    "effort_level": request.effort_level,
                    "target_pages": target_pages,
                    "min_pages": min_pages,
                    "max_pages": max_pages,
                    "engine": "langgraph",
                    "api_calls": api_counters,
                    "points_total": int(api_counters.get("points_total") or 0) if isinstance(api_counters, dict) else 0,
                    **decision_payload
                }

                quality_payload = {
                    "summary": state_values.get("quality_report"),
                    "quality_report_markdown": state_values.get("quality_report_markdown"),
                    "quality_gate": {
                        "passed": state_values.get("quality_gate_passed", True),
                        "results": state_values.get("quality_gate_results", []),
                        "force_hil": state_values.get("quality_gate_force_hil", False),
                    },
                    "structural_fix": state_values.get("structural_fix_result"),
                    "patch_result": state_values.get("patch_result"),
                    "targeted_patch_used": state_values.get("targeted_patch_used", False),
                    "hil_checklist": state_values.get("hil_checklist"),
                }

                logger.info("✅ Geração via LangGraph concluída")
            except Exception as e:
                logger.error(f"❌ Erro no LangGraph: {e}, usando fallback")
                fallback_reasons.append(f"langgraph_error: {e}")
                content = ""
                quality_payload = None

        if not content and self.juridico_adapter and self.juridico_adapter.is_available():
            # Motor Principal: juridico_gemini.py
            logger.info("🚀 Usando JuridicoGeminiAdapter como motor de geração")

            try:
                local_files = self._filter_local_rag_files(docs) if attachment_mode == "rag_local" else []
                juridico_result = await self.juridico_adapter.generate(
                    prompt=enhanced_prompt,
                    document_type=effective_doc_type,
                    thesis=request.thesis or "A favor do cliente",
                    model=request.model_selection,
                    target_pages=target_pages,
                    min_pages=min_pages,
                    max_pages=max_pages,
                    local_files=local_files,
                    use_rag=request.use_templates,
                    rag_sources=rag_sources,
                    tenant_id="default",
                    use_multi_agent=request.use_multi_agent,
                    gpt_model=request.model_gpt or "gpt-5.2",
                    claude_model=request.model_claude or "claude-4.5-sonnet",
                    run_audit=request.audit,
                    include_toc=request.formatting_options.get("includeToc", False) if request.formatting_options else False,
                    reasoning_level=request.reasoning_level,
                    adaptive_routing=request.adaptive_routing,
                    crag_gate=request.crag_gate,
                    crag_min_best=request.crag_min_best_score,
                    crag_min_avg=request.crag_min_avg_score,
                    deep_research=request.dense_research,
                    web_search=engine_web_search,
                    hyde_enabled=request.hyde_enabled,
                    graph_rag_enabled=request.graph_rag_enabled,
                    graph_hops=request.graph_hops
                )

                content = juridico_result.get("markdown", "")
                audit_data = juridico_result.get("audit")
                citations_log = juridico_result.get("citations_log", [])
                agents_used = juridico_result.get("agents_used") or []

                # Métricas
                metrics = juridico_result.get("metrics", {})
                if not agents_used:
                    agents_used = ["gemini"]
                cost_info = {
                    "total_tokens": metrics.get("total_prompt_tokens", 0) + metrics.get("total_completion_tokens", 0),
                    "total_cost": 0.0,  # Calcular baseado em tokens
                    "processing_time": metrics.get("total_time_seconds", 0),
                    "agents_used": agents_used,
                    "effort_level": request.effort_level,
                    "target_pages": target_pages,
                    "min_pages": min_pages,
                    "max_pages": max_pages,
                    "engine": "juridico_gemini"
                }

                # Guardar docx_bytes no contexto para download posterior
                if juridico_result.get("docx_bytes"):
                    context["docx_bytes"] = juridico_result["docx_bytes"]

                logger.info("✅ Geração via JuridicoGeminiAdapter concluída")

            except Exception as e:
                logger.error(f"❌ Erro no JuridicoGeminiAdapter: {e}, usando fallback")
                fallback_reasons.append(f"juridico_error: {e}")
                content = ""  # Força fallback
        elif not content and (not self.juridico_adapter or not self.juridico_adapter.is_available()):
            fallback_reasons.append("juridico_unavailable")

        # Fallback: MultiAgentOrchestrator (caso juridico_adapter falhe ou não esteja disponível)
        if not content:
            logger.info("🔄 Usando MultiAgentOrchestrator como fallback")
            result = await self.orchestrator.generate_document(
                prompt=enhanced_prompt,
                context=context,
                effort_level=request.effort_level,
                use_multi_agent=request.use_multi_agent,
                model=request.model_selection,
                    model_gpt=request.model_gpt,
                    model_claude=request.model_claude,
                    drafter_models=getattr(request, "drafter_models", []) or [],
                    reviewer_models=getattr(request, "reviewer_models", []) or [],
                    reasoning_level=request.reasoning_level,
                    temperature=temperature,
                    num_committee_rounds=fallback_max_rounds,
                    web_search=engine_web_search,
                    search_mode=search_mode,
                    perplexity_search_mode=perplexity_search_mode,
                    multi_query=multi_query,
                    breadth_first=breadth_first,
                    dense_research=deep_enabled,
                    deep_research_effort=deep_effort,
                    deep_research_points_multiplier=deep_multiplier,
                    thesis=request.thesis,
                    formatting_options=request.formatting_options,
                    run_audit=request.audit,
                )

            content = result.final_content
            audit_data = result.metadata.get("audit")
            agents_used = result.metadata.get("agents_used", []) or []

            cost_info = {
                "total_tokens": result.total_tokens,
                "total_cost": result.total_cost,
                "processing_time": result.processing_time_seconds,
                "agents_used": agents_used,
                "effort_level": request.effort_level,
                "engine": "orchestrator"
            }
        
        # =====================================================================
        # PÓS-PROCESSAMENTO
        # =====================================================================
        
        # Aplicar template se fornecido
        if request.template_id and db:
            content = await self._apply_template(
                content,
                request.template_id,
                request.variables,
                user,
                db
            )

        # Quality Pipeline (v2.25) — aplica no fluxo fora do LangGraph também
        # Regra: sem dependência do mlx_vomo.py (pipeline independente).
        try:
            enable_quality = os.getenv("ENABLE_QUALITY_PIPELINE", "true").lower() == "true"
            if enable_quality and quality_payload is None:
                input_context = enhanced_prompt
                if rag_context:
                    input_context += f"\n\n--- CONTEXTO RAG ---\n{rag_context}"
                qp = apply_quality_pipeline(
                    input_context=input_context,
                    generated_document=content,
                    mode=effective_doc_type,
                    job_id=document_id,
                    sections=None
                )
                content = qp.document
                quality_payload = {
                    "summary": get_quality_summary(qp),
                    "needs_hil": qp.needs_hil,
                    "safe_mode": qp.safe_mode,
                    "quality_gate": qp.quality_gate.to_dict(),
                    "structural_fix": qp.structural_fix.to_dict(),
                    "quality_report": qp.quality_report.to_dict(),
                }
                logger.info(f"✅ Quality Pipeline aplicado: {quality_payload['summary']}")
        except Exception as e:
            logger.warning(f"⚠️ Falha ao aplicar Quality Pipeline (ignorado): {e}")
        
        # Adicionar assinatura se solicitado
        signature_data = None
        if request.include_signature:
            content, signature_data = self._add_signature(content, user)
        
        # Converter para HTML
        content_html = self._markdown_to_html(content)
        
        # Calcular estatísticas
        statistics = self._calculate_statistics(content)
        
        fallback_reason = "; ".join(fallback_reasons) if fallback_reasons else None
        if fallback_reason:
            cost_info["fallback_reason"] = fallback_reason
        cost_info["agents_used"] = agents_used or cost_info.get("agents_used", [])

        logger.info(f"Documento gerado com sucesso: {document_id} (engine={cost_info.get('engine', 'unknown')})")
        
        return DocumentGenerationResponse(
            document_id=document_id,
            content=content,
            content_html=content_html,
            metadata={
                "document_type": effective_doc_type,
                "language": request.language,
                "tone": request.tone,
                "template_id": request.template_id,
                "user_id": user.id,
                "user_account_type": user.account_type.value,
                "generated_at": utcnow().isoformat(),
                "engine": cost_info.get("engine", "unknown"),
                "request_id": request_id,
                "audit": audit_data,
                "citations_log": citations_log,
                "agents_used": agents_used or cost_info.get("agents_used", []),
                "fallback_reason": fallback_reason,
                "decision": {
                    "final_decision": cost_info.get("final_decision"),
                    "final_decision_reasons": cost_info.get("final_decision_reasons", []),
                    "final_decision_score": cost_info.get("final_decision_score"),
                    "final_decision_target": cost_info.get("final_decision_target"),
                },
                # Quality Pipeline (v2.25)
                "quality": quality_payload
            },
            statistics=statistics,
            cost_info=cost_info,
            signature_data=signature_data
        )

    def _resolve_page_range(self, request: DocumentGenerationRequest) -> tuple[int, int, int]:
        min_pages = int(getattr(request, "min_pages", 0) or 0)
        max_pages = int(getattr(request, "max_pages", 0) or 0)

        if min_pages < 0:
            min_pages = 0
        if max_pages < 0:
            max_pages = 0
        if min_pages and max_pages and max_pages < min_pages:
            max_pages = min_pages
        if max_pages and not min_pages:
            min_pages = 1
        if min_pages and not max_pages:
            max_pages = min_pages

        if min_pages or max_pages:
            target_pages = (min_pages + max_pages) // 2
        else:
            effort_level = int(getattr(request, "effort_level", 0) or 0)
            target_pages = effort_level * 3 if effort_level else 0

        return target_pages, min_pages, max_pages

    def _filter_local_rag_files(self, docs: List[Document]) -> List[str]:
        allowed_exts = {".pdf", ".txt", ".md"}
        paths: List[str] = []
        for doc in docs:
            path = getattr(doc, "url", None)
            if not path or not os.path.exists(path):
                continue
            _, ext = os.path.splitext(path)
            if ext.lower() in allowed_exts:
                paths.append(path)
        return paths

    def _build_attachment_prompt_context(
        self,
        docs: List[Document],
        max_chars: Optional[int] = None,
        per_doc_chars: Optional[int] = None
    ) -> str:
        if not docs:
            return ""
        if max_chars is None:
            max_chars = settings.ATTACHMENT_INJECTION_MAX_CHARS
        if per_doc_chars is None:
            per_doc_chars = settings.ATTACHMENT_INJECTION_MAX_CHARS_PER_DOC
        remaining = max_chars
        blocks: List[str] = []
        for doc in docs:
            text = (getattr(doc, "extracted_text", "") or "").strip()
            if not text:
                continue
            chunk = text[: min(per_doc_chars, remaining)]
            if not chunk:
                break
            blocks.append(f"[{doc.name}]\n{chunk}")
            remaining -= len(chunk)
            if remaining <= 0:
                break
        if not blocks:
            return ""
        return (
            "## CONTEXTO DOS ANEXOS (INJEÇÃO DIRETA)\n"
            "Use apenas fatos explícitos nos trechos abaixo. Não invente informações.\n\n"
            + "\n\n".join(blocks)
            + "\n\n## FIM DO CONTEXTO DOS ANEXOS"
        )

    def _build_local_rag_context(
        self,
        docs: List[Document],
        query: str,
        tenant_id: str = "default",
        top_k: Optional[int] = None,
        max_files: Optional[int] = None,
        *,
        queries: Optional[List[str]] = None,
        query_override: Optional[str] = None,
        multi_query: bool = False,
        crag_gate: bool = False,
        graph_rag_enabled: bool = False,
        argument_graph_enabled: bool = False,
        graph_hops: int = 2,
    ) -> str:
        try:
            from rag_local import LocalProcessIndex
        except Exception as e:
            logger.warning(f"RAG Local indisponível: {e}")
            return ""

        if top_k is None:
            top_k = settings.ATTACHMENT_RAG_LOCAL_TOP_K
        if max_files is None:
            max_files = settings.ATTACHMENT_RAG_LOCAL_MAX_FILES
        max_files = max(1, int(max_files))
        allowed_exts = {".pdf", ".txt", ".md"}
        file_paths: List[str] = []
        inline_docs: List[tuple[Document, str]] = []
        for doc in docs:
            path = getattr(doc, "url", None)
            text = (getattr(doc, "extracted_text", None) or getattr(doc, "content", None) or "").strip()
            meta = getattr(doc, "doc_metadata", {}) or {}
            ocr_applied = bool(meta.get("ocr_applied")) or meta.get("ocr_status") == "completed"
            ext = os.path.splitext(path)[1].lower() if path else ""

            prefer_inline = False
            if text:
                if not path or not os.path.exists(path):
                    prefer_inline = True
                elif ext not in allowed_exts:
                    prefer_inline = True
                elif doc.type == DocumentType.PDF and ocr_applied:
                    prefer_inline = True

            if prefer_inline:
                inline_docs.append((doc, text))
            elif path and os.path.exists(path) and ext in allowed_exts:
                file_paths.append(path)

        if not file_paths and not inline_docs:
            return ""

        try:
            index = LocalProcessIndex(
                processo_id=f"upload-{uuid.uuid4()}",
                sistema="UPLOAD",
                tenant_id=tenant_id
            )
            index.enable_graph(
                graph_rag_enabled=bool(graph_rag_enabled),
                argument_graph_enabled=bool(argument_graph_enabled),
            )
            remaining = max_files
            for path in file_paths:
                if remaining <= 0:
                    break
                index.index_documento(path)
                remaining -= 1
            for doc, text in inline_docs:
                if remaining <= 0:
                    break
                filename = doc.name or doc.original_name or doc.id or "documento"
                index.index_text(
                    text,
                    filename=filename,
                    doc_id=doc.id,
                    source_path=getattr(doc, "url", None) or filename,
                )
                remaining -= 1
            search_query = (query_override or query or "").strip()
            results, graph_ctx = index.search_advanced(
                search_query,
                top_k=top_k,
                multi_query=bool(multi_query),
                queries=queries,
                compression_enabled=bool(crag_gate),
                neighbor_expand=bool(crag_gate),
                corrective_rag=bool(crag_gate),
                graph_rag_enabled=bool(graph_rag_enabled),
                graph_hops=int(graph_hops or 2),
                argument_graph_enabled=bool(argument_graph_enabled),
            )
        except Exception as e:
            logger.warning(f"Falha ao indexar anexos no RAG Local: {e}")
            return ""

        if not results:
            return ""

        lines = ["### 📁 FATOS DO PROCESSO (ANEXOS)"]
        for r in results:
            snippet = (r.get("text") or "")[:300].strip()
            citation = r.get("citacao") or "Documento"
            if snippet:
                lines.append(f"- {citation}: \"{snippet}...\"")
        if graph_ctx:
            lines.append("")
            lines.append("### 🔗 CONTEXTO RELACIONAL (GRAPH)")
            lines.append((graph_ctx or "").strip()[:2000])
        return "\n".join(lines)

    def _build_personality_instructions(self, personality: str) -> str:
        if personality == "geral":
            return (
                "## ESTILO DE RESPOSTA (MODO LIVRE)\n"
                "- Use linguagem clara e acessível, sem jargões jurídicos.\n"
                "- Explique conceitos quando necessário, de forma objetiva.\n"
                "- Mantenha a precisão do conteúdo, mas com tom mais conversacional.\n"
            )
        if personality == "juridico":
            return (
                "## ESTILO DE RESPOSTA (MODO JURÍDICO)\n"
                "- Use linguagem técnica e formal, com termos jurídicos adequados.\n"
                "- Estruture o texto conforme práticas forenses e normas aplicáveis.\n"
            )
        return ""
    
    def _prepare_context(
        self,
        request: DocumentGenerationRequest,
        user: User,
        context_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prepara contexto completo para geração"""
        context = {
            "document_type": effective_doc_type,
            "language": request.language,
            "tone": request.tone,
            "user_info": {
                "account_type": user.account_type.value,
                "name": user.name,
                "email": user.email,
            },
            "variables": request.variables,
            "max_length": request.max_length
        }
        
        # Adicionar dados específicos do tipo de conta
        if user.account_type.value == "INDIVIDUAL":
            context["user_info"].update({
                "oab": user.oab,
                "oab_state": user.oab_state,
                "cpf": user.cpf,
                "phone": user.phone
            })
        else:
            context["user_info"].update({
                "institution_name": user.institution_name,
                "cnpj": user.cnpj,
                "position": user.position,
                "department": user.department,
                "institution_address": user.institution_address,
                "institution_phone": user.institution_phone
            })
        
        # Adicionar contexto adicional se fornecido
        if context_data:
            context.update(context_data)
        
        return context

    def _infer_agents_from_langgraph(
        self,
        state_values: Dict[str, Any],
        request: DocumentGenerationRequest
    ) -> List[str]:
        agents: List[str] = []

        processed = state_values.get("processed_sections", []) or []
        first_section = None
        for section in processed:
            if isinstance(section, dict):
                first_section = section
                break

        drafts = {}
        if first_section and isinstance(first_section.get("drafts"), dict):
            drafts = first_section.get("drafts", {}) or {}

        def draft_ok(key: str) -> bool:
            val = drafts.get(key)
            if not val:
                return False
            text = str(val).lower()
            if "não disponível" in text or "not available" in text:
                return False
            return True

        if draft_ok("gpt_v1") or draft_ok("gpt_v2"):
            agents.append("gpt")
        if draft_ok("claude_v1") or draft_ok("claude_v2"):
            agents.append("claude")
        if draft_ok("gemini_v1"):
            agents.append("gemini")

        if not agents:
            agents.append("gemini" if not request.use_multi_agent else "langgraph")

        return agents
    
    def _enhance_prompt_with_user_data(
        self,
        prompt: str,
        user: User,
        document_type: str
    ) -> str:
        """Aprimora o prompt com informações contextuais do usuário"""
        
        user_context = f"\n\n--- INFORMAÇÕES DO AUTOR ---\n"
        user_context += f"Nome: {user.name}\n"
        
        if user.account_type.value == "INDIVIDUAL":
            if user.oab and user.oab_state:
                user_context += f"OAB: {user.oab}/{user.oab_state}\n"
        else:
            user_context += f"Instituição: {user.institution_name}\n"
            if user.position:
                user_context += f"Cargo: {user.position}\n"
        
        user_context += f"\n--- TIPO DE DOCUMENTO ---\n{document_type}\n"
        user_context += f"\n--- REQUISIÇÃO ---\n{prompt}\n"
        
        return user_context
    
    def _process_prompt_variables(
        self,
        text: str,
        variables: Dict[str, Any],
        user: User
    ) -> str:
        """Processa variáveis {{chave}} em um texto"""
        content = text
        
        # Substituir variáveis do request
        for key, value in variables.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
        
        # Substituir variáveis automáticas do usuário
        user_vars = {
            "user_name": user.name,
            "user_email": user.email,
            "user_oab": f"{user.oab}/{user.oab_state}" if user.oab else "",
            "user_institution": user.institution_name or "",
            "user_position": user.position or "",
            "user_cnpj": user.cnpj or "",
            "date": datetime.now().strftime("%d/%m/%Y"),
            "datetime": datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        
        for key, value in user_vars.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
            
        return content

    def _parse_template_frontmatter(self, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Extrai frontmatter JSON e retorna (meta, corpo)."""
        if not text:
            return None, ""

        match = re.match(
            r"\s*<!--\s*IUDX_TEMPLATE_V1(?P<json>.*?)-->\s*(?P<body>.*)",
            text,
            flags=re.S
        )
        if not match:
            return None, text

        raw_json = (match.group("json") or "").strip()
        body = match.group("body") or ""

        if not raw_json:
            return None, body

        if raw_json.startswith("{") and raw_json.endswith("}"):
            try:
                meta = json.loads(raw_json)
                if isinstance(meta, dict):
                    return meta, body
            except Exception as e:
                logger.warning(f"Frontmatter invalido (ignorado): {e}")
                return None, text

        return None, text

    def _strip_template_placeholders(self, text: str) -> str:
        if not text:
            return text
        stripped = re.sub(r"{{\s*BLOCK:[^}]+}}", "", text)
        stripped = stripped.replace("{{CONTENT}}", "")
        stripped = stripped.replace("{{minuta}}", "")
        stripped = stripped.replace("(minuta)", "")
        return stripped

    def _build_template_structure_from_meta(
        self,
        meta: Optional[Dict[str, Any]],
        body: str,
        variables: Dict[str, Any],
        user: User
    ) -> str:
        if not meta:
            return body

        parts: List[str] = []
        system_instructions = meta.get("system_instructions") or meta.get("instructions") or ""
        output_format = meta.get("output_format") or meta.get("structure") or ""
        user_template_v1 = meta.get("user_template_v1") or meta.get("user_template") or None

        if system_instructions:
            parts.append(str(system_instructions).strip())
        if output_format:
            parts.append("FORMATO DE SAIDA:\n" + str(output_format).strip())

        if user_template_v1:
            try:
                from app.schemas.smart_template import UserTemplateV1
                from app.services.ai.nodes.catalogo_documentos import (
                    TemplateSpec,
                    get_template,
                    merge_user_template,
                    build_default_outline,
                    get_numbering_instruction,
                )
                parsed = UserTemplateV1.model_validate(user_template_v1)
                base_spec = get_template(parsed.doc_kind, parsed.doc_subtype)
                user_dict = parsed.model_dump()
                if base_spec:
                    merged = merge_user_template(base_spec, user_dict)
                else:
                    merged = TemplateSpec(
                        name=parsed.name,
                        doc_kind=parsed.doc_kind,
                        doc_subtype=parsed.doc_subtype,
                        numbering=parsed.format.numbering,
                        style={
                            "tone": parsed.format.tone,
                            "verbosity": parsed.format.verbosity,
                            "voice": parsed.format.voice,
                        },
                        sections=[s.title for s in parsed.sections],
                        required_fields=[f.name for f in parsed.required_fields],
                        checklist_base=[],
                        forbidden_sections=[],
                    )

                outline = build_default_outline(merged)
                if outline:
                    parts.append("ESTRUTURA BASE (TEMPLATE DO USUARIO):\n" + "\n".join(f"- {s}" for s in outline))
                if merged.required_fields:
                    parts.append("CAMPOS OBRIGATORIOS:\n" + "\n".join(f"- {f}" for f in merged.required_fields))
                if merged.style:
                    parts.append(
                        "REGRAS DE ESTILO:\n"
                        + f"- tom: {merged.style.get('tone')}\n"
                        + f"- voz: {merged.style.get('voice')}\n"
                        + f"- extensao: {merged.style.get('verbosity')}\n"
                        + f"- numeracao: {get_numbering_instruction(merged.numbering)}"
                    )
            except Exception as e:
                logger.warning(f"Falha ao interpretar user_template_v1: {e}")

        blocks = meta.get("blocks") or []
        if isinstance(blocks, list) and blocks:
            lines = ["BLOCOS DISPONIVEIS:"]
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                block_id = str(block.get("id") or "").strip()
                if not block_id:
                    continue
                title = block.get("title") or block.get("titulo") or block_id
                lines.append(f"- {block_id}: {title}")
            parts.append("\n".join(lines))

        combined = "\n\n".join([p for p in parts if p])
        if not combined:
            combined = body

        combined = self._process_prompt_variables(combined, variables, user)
        return self._strip_template_placeholders(combined)

    def _template_body_has_blocks(self, body: Optional[str]) -> bool:
        if not body:
            return False
        return bool(re.search(r"{{\s*BLOCK:", body))

    def _normalize_block_kind(self, block: Dict[str, Any]) -> str:
        raw_kind = block.get("kind") or block.get("type") or block.get("block_type") or ""
        kind = str(raw_kind).strip().lower()
        if kind in ("fixed_text", "fixed"):
            return "fixed"
        if kind in ("llm_generated", "llm", "llm_assisted"):
            return "llm"
        if kind in ("clause_reference", "clause", "clause_ref"):
            return "clause"
        if kind in ("variable", "editable"):
            return "variable"
        return kind or "variable"

    def _build_block_output_instructions(
        self,
        meta: Optional[Dict[str, Any]],
        body: Optional[str],
        locked_blocks: Optional[List[str]] = None
    ) -> str:
        if not meta:
            return ""

        blocks = meta.get("blocks") or []
        if not isinstance(blocks, list) or not blocks:
            return ""

        output_mode = str(meta.get("output_mode") or "").strip().lower()
        if output_mode != "blocks" and not self._template_body_has_blocks(body):
            return ""

        locked_set = set(locked_blocks or [])
        llm_blocks = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("id") or "").strip()
            kind = self._normalize_block_kind(block)
            lockable = block.get("lockable")
            if lockable is None:
                lockable = block.get("user_can_lock")
            if lockable is None:
                lockable = kind in ("llm", "variable", "clause")
            lockable = bool(lockable)
            if block_id and block_id in locked_set and lockable:
                continue
            if kind in ("llm", "variable"):
                llm_blocks.append(block)

        if not llm_blocks:
            return ""

        lines = [
            "## SAIDA POR BLOCOS (OBRIGATORIO)",
            "Responda exatamente neste formato:",
            "[BLOCK:identificador]",
            "conteudo do bloco",
            "[/BLOCK:identificador]",
            "",
            "BLOCOS A PREENCHER:"
        ]
        for block in llm_blocks:
            block_id = str(block.get("id") or "").strip()
            if not block_id:
                continue
            title = block.get("title") or block.get("titulo") or block_id
            hint = block.get("prompt_fragment") or block.get("ai_instructions") or ""
            line = f"- {block_id}: {title}"
            if hint:
                line += f" | {hint}"
            lines.append(line)

        return "\n".join(lines)

    def _parse_block_output(self, text: str) -> Dict[str, str]:
        blocks: Dict[str, str] = {}
        if not text:
            return blocks

        pattern = re.compile(
            r"\[BLOCK:(?P<id>[A-Za-z0-9_-]+)\](?P<content>.*?)\[/BLOCK:\s*(?P=id)\]",
            flags=re.S
        )
        for match in pattern.finditer(text):
            block_id = match.group("id")
            content = (match.group("content") or "").strip()
            if block_id:
                blocks[block_id] = content
        return blocks

    def _get_template_preferences(
        self,
        user: User,
        template_id: Optional[str],
        meta: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        prefs = user.preferences or {}
        template_prefs = prefs.get("template_prefs") or prefs.get("templates") or {}
        if not isinstance(template_prefs, dict):
            return {}

        merged: Dict[str, Any] = {}

        def merge_pref(data: Any) -> None:
            if not isinstance(data, dict):
                return
            for key, value in data.items():
                if key == "locked_blocks":
                    existing = merged.get(key)
                    if not isinstance(existing, list):
                        existing = []
                    if isinstance(value, list):
                        merged[key] = list(dict.fromkeys(existing + value))
                    continue
                if key == "block_overrides":
                    existing = merged.get(key)
                    if not isinstance(existing, dict):
                        existing = {}
                    if isinstance(value, dict):
                        merged[key] = {**existing, **value}
                    continue
                merged[key] = value

        if template_id and template_id in template_prefs:
            merge_pref(template_prefs.get(template_id))

        meta_id = None
        if isinstance(meta, dict):
            meta_id = meta.get("id") or meta.get("template_id")
        if meta_id and meta_id in template_prefs and meta_id != template_id:
            merge_pref(template_prefs.get(meta_id))

        return merged

    def _apply_block_placeholders(self, body: str, block_context: Dict[str, str]) -> str:
        if not body:
            return ""

        def replace_block(match: re.Match) -> str:
            block_id = match.group(1).strip()
            return str(block_context.get(block_id, ""))

        return re.sub(r"{{\s*BLOCK:([\w\-]+)\s*}}", replace_block, body)

    def _evaluate_block_condition(self, condition: Any, variables: Dict[str, Any]) -> bool:
        if condition is None:
            return True
        if isinstance(condition, bool):
            return condition
        cond = str(condition).strip()
        if not cond:
            return True

        if "==" in cond:
            left, right = cond.split("==", 1)
            left = left.strip()
            right = right.strip().strip("'\"")
            return str(variables.get(left, "")) == right
        if "!=" in cond:
            left, right = cond.split("!=", 1)
            left = left.strip()
            right = right.strip().strip("'\"")
            return str(variables.get(left, "")) != right

        return bool(variables.get(cond))

    async def _resolve_clause_text(
        self,
        clause_id: Optional[str],
        user: User,
        db: Optional[AsyncSession]
    ) -> str:
        if not clause_id or not db:
            return ""

        try:
            result = await db.execute(
                select(LibraryItem).where(
                    LibraryItem.id == clause_id,
                    LibraryItem.type == LibraryItemType.CLAUSE,
                    LibraryItem.user_id == user.id
                )
            )
            item = result.scalars().first()
            if not item:
                result = await db.execute(
                    select(LibraryItem).where(
                        LibraryItem.name == clause_id,
                        LibraryItem.type == LibraryItemType.CLAUSE,
                        LibraryItem.user_id == user.id
                    )
                )
                item = result.scalars().first()
            return item.description if item and item.description else ""
        except Exception as e:
            logger.warning(f"Falha ao resolver clausula {clause_id}: {e}")
            return ""

    async def _build_block_context(
        self,
        meta: Optional[Dict[str, Any]],
        variables: Dict[str, Any],
        user: User,
        db: Optional[AsyncSession],
        generated_blocks: Dict[str, str],
        template_id: Optional[str] = None
    ) -> Dict[str, str]:
        block_context: Dict[str, str] = {}
        if not meta:
            return block_context

        blocks = meta.get("blocks") or []
        if not isinstance(blocks, list):
            return block_context

        block_permissions: Dict[str, Dict[str, bool]] = {}
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("id") or "").strip()
            if not block_id:
                continue
            kind = self._normalize_block_kind(block)
            lockable = block.get("lockable")
            if lockable is None:
                lockable = block.get("user_can_lock")
            if lockable is None:
                lockable = kind in ("llm", "variable", "clause")
            lockable = bool(lockable)

            editable = block.get("editable")
            if editable is None:
                editable = block.get("user_can_edit") if block.get("user_can_edit") is not None else None
            if editable is None:
                editable = block.get("user_can_edit_text")
            if editable is None:
                editable = kind in ("llm", "variable")
            editable = bool(editable)

            block_permissions[block_id] = {"lockable": lockable, "editable": editable}

        template_pref = self._get_template_preferences(user, template_id, meta)
        pref_locked = template_pref.get("locked_blocks") if isinstance(template_pref, dict) else None
        if not isinstance(pref_locked, list):
            pref_locked = []
        pref_overrides = template_pref.get("block_overrides") if isinstance(template_pref, dict) else None
        if not isinstance(pref_overrides, dict):
            pref_overrides = {}

        overrides = variables.get("blocks") or variables.get("block_overrides") or {}
        if not isinstance(overrides, dict):
            overrides = {}

        locked_blocks = variables.get("locked_blocks") or []
        if not isinstance(locked_blocks, list):
            locked_blocks = []

        default_locked = meta.get("default_locked_blocks") or []
        if not isinstance(default_locked, list):
            default_locked = []

        def is_lockable(block_id: str) -> bool:
            return bool(block_permissions.get(block_id, {}).get("lockable"))

        def is_editable(block_id: str) -> bool:
            return bool(block_permissions.get(block_id, {}).get("editable"))

        pref_locked = [block_id for block_id in pref_locked if is_lockable(block_id)]
        locked_blocks = [block_id for block_id in locked_blocks if is_lockable(block_id)]
        default_locked = [block_id for block_id in default_locked if is_lockable(block_id)]
        pref_overrides = {key: value for key, value in pref_overrides.items() if is_editable(key)}
        overrides = {key: value for key, value in overrides.items() if is_editable(key)}

        merged_locked = list(dict.fromkeys(default_locked + pref_locked + locked_blocks))
        merged_overrides: Dict[str, Any] = dict(pref_overrides)
        merged_overrides.update(overrides)

        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("id") or "").strip()
            if not block_id:
                continue

            if not self._evaluate_block_condition(block.get("condition"), variables):
                block_context[block_id] = ""
                continue

            kind = self._normalize_block_kind(block)
            permissions = block_permissions.get(block_id) or {}
            lockable = bool(permissions.get("lockable"))
            editable = bool(permissions.get("editable"))

            is_locked = block_id in merged_locked and lockable

            if block_id in merged_overrides and editable:
                block_context[block_id] = str(merged_overrides[block_id])
                continue

            clause_id = block.get("clause_id") or block.get("clause_ref") or block.get("clause")

            if kind == "clause" or clause_id:
                clause_text = await self._resolve_clause_text(str(clause_id), user, db)
                if clause_text:
                    block_context[block_id] = clause_text
                    continue

            if kind == "fixed":
                fixed_text = block.get("text") or block.get("content") or ""
                block_context[block_id] = str(fixed_text)
                continue

            if block_id in generated_blocks and not is_locked and kind in ("llm", "variable"):
                block_context[block_id] = generated_blocks[block_id]
                continue

            content_template = block.get("content_template") or block.get("text") or ""
            block_context[block_id] = str(content_template)

        return block_context

    async def _apply_template(
        self,
        content: str,
        template_id: str,
        variables: Dict[str, Any],
        user: User,
        db: Optional[AsyncSession] = None
    ) -> str:
        """Aplica template ao conteúdo"""
        
        template_content = None
        template_meta = None
        
        # Buscar template do banco de dados se db for fornecido
        if db:
            try:
                result = await db.execute(
                    select(LibraryItem).where(
                        LibraryItem.id == template_id,
                        LibraryItem.type == LibraryItemType.MODEL
                    )
                )
                template_item = result.scalars().first()
                
                if template_item and template_item.description:
                    template_content = template_item.description
                    logger.info(f"Template encontrado: {template_item.name}")
            except Exception as e:
                logger.error(f"Erro ao buscar template {template_id}: {e}")
        
        # Se encontrou template, usa ele como base e insere o conteúdo gerado
        if template_content:
            template_meta, template_body = self._parse_template_frontmatter(template_content)
            if not template_body:
                template_body = template_content

            generated_blocks = self._parse_block_output(content)
            block_context = await self._build_block_context(
                template_meta,
                variables,
                user,
                db,
                generated_blocks,
                template_id
            )

            if self._template_body_has_blocks(template_body):
                assembled = self._apply_block_placeholders(template_body, block_context)
                if "{{CONTENT}}" in assembled or "(minuta)" in assembled or "{{minuta}}" in assembled:
                    assembled = (
                        assembled.replace("{{CONTENT}}", content)
                        .replace("{{minuta}}", content)
                        .replace("(minuta)", content)
                    )
                content = assembled
                logger.info("Template aplicado via blocos {{BLOCK:id}}")
            else:
                if "(minuta)" in template_body:
                    content = template_body.replace("(minuta)", content)
                    logger.info("Template aplicado usando marcador (minuta)")
                elif "{{CONTENT}}" in template_body:
                    content = template_body.replace("{{CONTENT}}", content)
                    logger.info("Template aplicado usando marcador {{CONTENT}}")
                elif "{{minuta}}" in template_body:
                    content = template_body.replace("{{minuta}}", content)
                    logger.info("Template aplicado usando marcador {{minuta}}")
                else:
                    content = template_body + "\n\n" + content
                    logger.warning("Template sem marcador identificado, conteúdo anexado ao final")
        
        # Processar variáveis (agora centralizado)
        return self._process_prompt_variables(content, variables, user)
    
    def _add_signature(self, content: str, user: User) -> tuple[str, Dict[str, Any]]:
        """Adiciona assinatura ao documento"""
        
        signature_data = user.full_signature_data
        
        # Criar bloco de assinatura
        signature_block = "\n\n---\n\n"
        
        if user.account_type.value == "INDIVIDUAL":
            signature_block += f"**{user.name}**\n"
            if user.oab and user.oab_state:
                signature_block += f"OAB/{user.oab_state} {user.oab}\n"
            if user.cpf:
                signature_block += f"CPF: {self._format_cpf(user.cpf)}\n"
            if user.email:
                signature_block += f"Email: {user.email}\n"
            if user.phone:
                signature_block += f"Tel: {user.phone}\n"
        else:
            signature_block += f"**{user.name}**\n"
            if user.position:
                signature_block += f"{user.position}\n"
            if user.department:
                signature_block += f"{user.department}\n"
            if user.institution_name:
                signature_block += f"{user.institution_name}\n"
            if user.cnpj:
                signature_block += f"CNPJ: {self._format_cnpj(user.cnpj)}\n"
            if user.institution_address:
                signature_block += f"{user.institution_address}\n"
            if user.email:
                signature_block += f"Email: {user.email}\n"
            if user.institution_phone:
                signature_block += f"Tel: {user.institution_phone}\n"
        
        # Adicionar imagem de assinatura se disponível
        if user.signature_image:
            signature_block += f"\n![Assinatura]({user.signature_image})\n"
        
        content_with_signature = content + signature_block
        
        return content_with_signature, signature_data
    
    def _markdown_to_html(self, markdown: str) -> str:
        """Converte markdown para HTML"""
        # Conversão básica de markdown
        # Em produção, use uma biblioteca como python-markdown
        
        html = markdown
        
        # Headers
        html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # Bold
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        
        # Italic
        html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
        
        # Links
        html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html)
        
        # Images
        html = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" />', html)
        
        # Paragraphs
        html = re.sub(r'\n\n', '</p><p>', html)
        html = f'<p>{html}</p>'
        
        # Line breaks
        html = html.replace('\n', '<br />')
        
        return html
    
    def _calculate_statistics(self, content: str) -> Dict[str, Any]:
        """Calcula estatísticas do documento"""
        words = len(content.split())
        chars = len(content)
        chars_no_spaces = len(content.replace(" ", ""))
        lines = len(content.split("\n"))
        paragraphs = len([p for p in content.split("\n\n") if p.strip()])
        
        return {
            "words": words,
            "characters": chars,
            "characters_no_spaces": chars_no_spaces,
            "lines": lines,
            "paragraphs": paragraphs,
            "estimated_pages": max(1, words // 250)  # ~250 palavras por página
        }
    
    def _format_cpf(self, cpf: str) -> str:
        """Formata CPF"""
        if len(cpf) == 11:
            return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        return cpf
    
    def _format_cnpj(self, cnpj: str) -> str:
        """Formata CNPJ"""
        if len(cnpj) == 14:
            return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        return cnpj
