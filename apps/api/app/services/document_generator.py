"""
Serviço de Geração de Documentos com Assinatura
Integra IA multi-agente com templates e dados do usuário
"""

from typing import Dict, Any, Optional, List
import os
import time
import uuid
from datetime import datetime
from loguru import logger
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.services.ai.orchestrator import MultiAgentOrchestrator
from app.services.rag_module import RAGManager
from app.models.user import User
from app.models.document import Document
from app.models.library import LibraryItem, LibraryItemType
from app.schemas.document import DocumentGenerationRequest, DocumentGenerationResponse
from app.services.ai.quality_pipeline import apply_quality_pipeline, get_quality_summary

# Import JuridicoGeminiAdapter (primary generation engine)
try:
    from app.services.ai.juridico_adapter import JuridicoGeminiAdapter, get_juridico_adapter
    JURIDICO_ENGINE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ JuridicoGeminiAdapter não disponível, usando Orchestrator como fallback")
    JURIDICO_ENGINE_AVAILABLE = False


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
            from app.services.rag_module import create_rag_manager
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
        logger.info(f"Gerando documento para usuário {user.id}, tipo: {request.document_type}")
        
        # 0. Pré-processamento do Prompt (Variáveis no prompt do usuário)
        raw_prompt = request.prompt
        request.prompt = self._process_prompt_variables(request.prompt, request.variables, user)
        if request.prompt != raw_prompt:
            logger.info("Prompt pré-processado com variáveis")

        # 0.1 Busca Antecipada de Template (para injeção no contexto)
        template_structure = None
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
                    # Também processar variáveis na estrutura do template
                    template_structure = self._process_prompt_variables(template_item.description, request.variables, user)
                    logger.info(f"Template '{template_item.name}' carregado como referência estrutural")
             except Exception as e:
                logger.error(f"Erro ao buscar template antecipadamente: {e}")

        # Preparar contexto completo
        context = self._prepare_context(request, user, context_data)
        if template_structure:
            context["template_structure"] = template_structure

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
        if self.rag_manager and (request.use_templates or request.context_documents):
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
                rag_query = f"{request.document_type}: {request.prompt[:500]}"
                
                # Determinar fontes
                rag_sources = ["pecas_modelo", "lei", "juris"]
                
                results = self.rag_manager.hybrid_search(
                    query=rag_query,
                    sources=rag_sources,
                    top_k=8,
                    filters={"pecas_modelo": pecas_filter} if pecas_filter else None,
                    tenant_id="default" # Ajustar se necessário
                )
                
                if results:
                    rag_context = self.rag_manager.format_sources_for_prompt(results)
                    logger.info(f"✅ RAG Global retornou {len(results)} fontes")
            except Exception as e:
                logger.error(f"Erro no RAG Global: {e}")

        attachment_mode = (getattr(request, "attachment_mode", "rag_local") or "rag_local").lower()
        if attachment_mode not in ["rag_local", "prompt_injection"]:
            attachment_mode = "rag_local"

        if attachment_mode == "rag_local" and docs:
            local_rag_context = self._build_local_rag_context(
                docs=docs,
                query=f"{request.document_type}: {request.prompt[:800]}",
                tenant_id="default"
            )
            if local_rag_context:
                rag_context = f"{local_rag_context}\n\n{rag_context}".strip()

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
            context["extra_agent_instructions"] = prompt_extra_instr + regra_modelos
        
        # Preparar prompt com informações do usuário
        enhanced_prompt = self._enhance_prompt_with_user_data(
            request.prompt,
            user,
            request.document_type
        )

        if attachment_mode == "prompt_injection" and docs:
            attachment_text = self._build_attachment_prompt_context(docs)
            if attachment_text:
                enhanced_prompt += "\n\n" + attachment_text

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

        # Estilo de citação (ABNT/Híbrido) — instruções para o gerador
        citation_style = (getattr(request, "citation_style", None) or "forense").lower()
        if citation_style in ("abnt", "hibrido"):
            enhanced_prompt += "\n\n" + (
                "## ESTILO DE CITAÇÃO (ABNT/HÍBRIDO)\n"
                "- Autos/peças: ao citar fatos dos autos, mantenha [TIPO - Doc. X, p. Y].\n"
                "- Jurisprudência: inclua tribunal/classe/número/UF quando houver no contexto.\n"
                "- Fontes acadêmicas/doutrina (quando presentes no RAG): use (AUTOR, ano) no texto e inclua ao final uma seção 'REFERÊNCIAS (ABNT NBR 6023)'.\n"
                "- Se faltar metadado (autor/ano), não invente: use [[PENDENTE: completar referência ABNT]].\n"
            )
            # Também deixa disponível para o modo multi-agente
            context["extra_agent_instructions"] = (context.get("extra_agent_instructions") or "") + "\n" + (
                "## ESTILO DE CITAÇÃO (ABNT/HÍBRIDO)\n"
                "Autos: preserve [TIPO - Doc. X, p. Y].\n"
                "Acadêmico: (AUTOR, ano) + REFERÊNCIAS ABNT ao final.\n"
            )
        
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

                initial_state = {
                    "input_text": input_text,
                    "mode": request.document_type,
                    "tese": request.thesis or "",
                    "job_id": document_id,
                    "deep_research_enabled": bool(getattr(request, "dense_research", False)),
                    "web_search_enabled": bool(request.web_search),
                    "use_multi_agent": bool(request.use_multi_agent),
                    "thinking_level": request.reasoning_level,
                    "chat_personality": personality,
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
                    "crag_min_best_score": float(getattr(request, "crag_min_best_score", 0.45)),
                    "crag_min_avg_score": float(getattr(request, "crag_min_avg_score", 0.35)),
                    "hyde_enabled": bool(getattr(request, "hyde_enabled", False)),
                    "graph_rag_enabled": bool(getattr(request, "graph_rag_enabled", False)),
                    "graph_hops": int(getattr(request, "graph_hops", 1) or 1),
                    "outline": [],
                    "processed_sections": [],
                    "full_document": "",
                    "research_context": rag_context or None,
                    "research_sources": [],
                    "deep_research_thinking_steps": [],
                    "deep_research_from_cache": False,
                    "has_any_divergence": False,
                    "divergence_summary": "",
                    "audit_status": "aprovado",
                    "audit_report": None,
                    "audit_issues": [],
                    "hil_checklist": None,
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
                    "hil_target_sections": getattr(request, "hil_target_sections", []) or [],
                    "hil_section_payload": None,
                    "hil_outline_enabled": bool(getattr(request, "hil_outline_enabled", False)),
                    "hil_outline_payload": None,
                    "judge_model": request.model_selection or "gemini-3-pro",
                    "gpt_model": request.model_gpt or "gpt-5.2",
                    "claude_model": request.model_claude or "claude-4.5-sonnet",
                    "strategist_model": getattr(request, "strategist_model", None),
                    "drafter_models": getattr(request, "drafter_models", []) or [],
                    "reviewer_models": getattr(request, "reviewer_models", []) or [],
                    "auto_approve_hil": True
                }

                config = {"configurable": {"thread_id": document_id}}
                result = await legal_workflow_app.ainvoke(initial_state, config)
                snapshot = legal_workflow_app.get_state(config)
                state_values = {}
                if snapshot and snapshot.values:
                    state_values = snapshot.values
                elif isinstance(result, dict):
                    state_values = result

                content = state_values.get("final_markdown") or state_values.get("full_document") or ""
                audit_data = state_values.get("audit_report")
                citations_log = (audit_data or {}).get("citations", [])

                agents_used = self._infer_agents_from_langgraph(state_values, request)

                cost_info = {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "processing_time": time.time() - start_time,
                    "agents_used": agents_used,
                    "effort_level": request.effort_level,
                    "target_pages": target_pages,
                    "min_pages": min_pages,
                    "max_pages": max_pages,
                    "engine": "langgraph"
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
                    document_type=request.document_type,
                    thesis=request.thesis or "A favor do cliente",
                    model=request.model_selection,
                    target_pages=target_pages,
                    min_pages=min_pages,
                    max_pages=max_pages,
                    local_files=local_files,
                    use_rag=request.use_templates,
                    rag_sources=["lei", "juris", "pecas_modelo"],
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
                    web_search=request.web_search,
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
                web_search=request.web_search,
                dense_research=request.dense_research,
                thesis=request.thesis,
                formatting_options=request.formatting_options,
                run_audit=request.audit
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
                    mode=request.document_type,
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
                "document_type": request.document_type,
                "language": request.language,
                "tone": request.tone,
                "template_id": request.template_id,
                "user_id": user.id,
                "user_account_type": user.account_type.value,
                "generated_at": datetime.utcnow().isoformat(),
                "engine": cost_info.get("engine", "unknown"),
                "audit": audit_data,
                "citations_log": citations_log,
                "agents_used": agents_used or cost_info.get("agents_used", []),
                "fallback_reason": fallback_reason,
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
        max_chars: int = 12000,
        per_doc_chars: int = 3000
    ) -> str:
        if not docs:
            return ""
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
        top_k: int = 5
    ) -> str:
        try:
            from rag_local import LocalProcessIndex
        except Exception as e:
            logger.warning(f"RAG Local indisponível: {e}")
            return ""

        file_paths = self._filter_local_rag_files(docs)
        if not file_paths:
            return ""

        try:
            index = LocalProcessIndex(
                processo_id=f"upload-{uuid.uuid4()}",
                sistema="UPLOAD",
                tenant_id=tenant_id
            )
            for path in file_paths[:10]:
                index.index_documento(path)
            results = index.search(query, top_k=top_k)
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
            "document_type": request.document_type,
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
            if "(minuta)" in template_content:
                content = template_content.replace("(minuta)", content)
                logger.info("Template aplicado usando marcador (minuta)")
            elif "{{CONTENT}}" in template_content:
                content = template_content.replace("{{CONTENT}}", content)
                logger.info("Template aplicado usando marcador {{CONTENT}}")
            elif "{{minuta}}" in template_content:
                content = template_content.replace("{{minuta}}", content)
                logger.info("Template aplicado usando marcador {{minuta}}")
            else:
                content = template_content + "\n\n" + content
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
