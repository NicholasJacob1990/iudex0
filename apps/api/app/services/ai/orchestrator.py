"""
Orquestrador de múltiplos agentes de IA
Sistema que coordena Claude, Gemini e GPT trabalhando juntos
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger

from app.services.ai.agents import ClaudeAgent, GeminiAgent, GPTAgent
from app.services.ai.base_agent import AgentResponse, AgentReview
from app.services.ai.langgraph_workflow import MinutaWorkflow
from app.services.legal_prompts import LegalPrompts
from app.services.web_search_service import web_search_service, is_breadth_first
from app.services.ai.deep_research_service import deep_research_service
from app.services.ai.model_registry import get_api_model_name
from app.services.ai.perplexity_config import normalize_perplexity_search_mode


@dataclass
class MultiAgentResult:
    """Resultado do processamento multi-agente"""
    final_content: str
    reviews: List[AgentReview]
    consensus: bool
    conflicts: List[str]
    total_tokens: int
    total_cost: float
    processing_time_seconds: float
    metadata: Dict[str, Any]


class MultiAgentOrchestrator:
    """
    Orquestrador que coordena múltiplos agentes de IA (Versão 2.1 Async)
    
    Fluxo:
    1. Recebe Prompt e Contexto (CaseBundle)
    2. Executa debate assíncrono (GPT vs Claude)
    3. Juiz (Gemini) consolida
    """
    
    def __init__(self):
        logger.info("Inicializando Multi-Agent Orchestrator (v2.1 Async)")
        
        # Importar clientes compartilhados
        from app.services.ai.agent_clients import (
            init_openai_client, 
            init_anthropic_client,
            CaseBundle
        )
        
        self.gpt_client = init_openai_client()
        self.claude_client = init_anthropic_client()
        
        # Manter agentes antigos apenas se necessário para fallback (por enquanto não usa)
        # self.prompts = LegalPrompts() 
        # self.workflow = MinutaWorkflow()
        
        # Inicializar Drafter para o Juiz (Gemini)
        # Precisamos de um wrapper simples para o drafter._generate_with_retry
        try:
           from app.services.ai.gemini_drafter import GeminiDrafterWrapper
           self.drafter = GeminiDrafterWrapper() 
        except ImportError:
           # Fallback local mock se não tiver wrapper ainda (será criado na sequencia)
           self.drafter = None
           
        # Inicializar Serviço de Auditoria e RAG
        try:
            from app.services.ai.audit_service import AuditService
            self.audit_service = AuditService()
        except ImportError:
            logger.warning("⚠️ AuditService não disponível.")
            self.audit_service = None
            
        # RAG Manager para checagem de alucinação
        try:
            from app.services.rag_module import create_rag_manager
            # Usar diretório padrão definido no script
            self.rag_manager = create_rag_manager()
        except ImportError:
            logger.warning("⚠️ RAG Manager não disponível.")
            self.rag_manager = None

        logger.info(f"✅ Agentes Inicializados: GPT={bool(self.gpt_client)}, Claude={bool(self.claude_client)}, Audit={bool(self.audit_service)}, RAG={bool(self.rag_manager)}")
    
    async def generate_document(
        self,
        prompt: str,
        context: Dict[str, Any],
        effort_level: int = 3,
        use_multi_agent: bool = True,
        # IDs canônicos (mapeados para api_model dentro de agent_clients)
        model: str = "gemini-3-flash",
        model_gpt: str = "gpt-5.2",
        model_claude: str = "claude-4.5-sonnet",
        drafter_models: Optional[List[str]] = None,
        reviewer_models: Optional[List[str]] = None,
        reasoning_level: str = "medium",
        temperature: float = 0.3,
        num_committee_rounds: int = 1,
        web_search: bool = False,
        search_mode: str = "hybrid",
        perplexity_search_mode: Optional[str] = None,
        multi_query: bool = True,
        breadth_first: bool = False,
        thesis: Optional[str] = None,
        formatting_options: Dict[str, bool] = None,
        run_audit: bool = True,
        dense_research: bool = False,
        deep_research_effort: Optional[str] = None,
        deep_research_points_multiplier: Optional[float] = None,
    ) -> MultiAgentResult:
        """
        Gera documento usando o modo Agente (Debate + Juiz) com rodadas configuráveis
        """
        import time
        from app.services.ai.agent_clients import (
            generate_section_agent_mode_async,
            CaseBundle,
            build_system_instruction
        )
        
        start_time = time.time()
        logger.info(f"🚀 Iniciando geração AGENT MODE (Async)...")

        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            temperature = 0.3
        temperature = max(0.0, min(1.0, temperature))
        try:
            num_committee_rounds = int(num_committee_rounds)
        except (TypeError, ValueError):
            num_committee_rounds = 1
        num_committee_rounds = max(1, min(6, num_committee_rounds))
        normalized_perplexity_search_mode = normalize_perplexity_search_mode(perplexity_search_mode)
        
        # 1. Preparar CaseBundle
        # O bundle deve vir no context ou ser criado aqui
        case_bundle = context.get('case_bundle')
        if not case_bundle:
            # Criar bundle vazio se não vier
            case_bundle = CaseBundle(processo_id="N/A")

        chat_personality = (context.get("chat_personality") or "juridico").lower()
        system_instruction = build_system_instruction(chat_personality)
            
        # 2. Executar Geração
        # TODO: Implementar outline splitting para documentos longos
        
        try:
            if use_multi_agent:
                # MODO AGENTE V2.5 (Debate 2025: GPT-5.2 vs Claude Sonnet 4.5)
                # Atualizando modelos para versão mais recente
                final_text, divergencias_md, drafts = await generate_section_agent_mode_async(
                    section_title="Documento Jurídico",
                    prompt_base=prompt,
                    case_bundle=case_bundle,
                    rag_local_context=context.get('rag_context', ''),
                    drafter=self.drafter,
                    gpt_client=self.gpt_client,
                    claude_client=self.claude_client,
                    gpt_model=model_gpt,
                    claude_model=model_claude,
                    drafter_models=drafter_models or [],
                    reviewer_models=reviewer_models or [],
                    judge_model=model,
                    reasoning_level=reasoning_level,
                    temperature=temperature,
                    num_committee_rounds=num_committee_rounds,
                    web_search=web_search,
                    search_mode=search_mode,
                    perplexity_search_mode=normalized_perplexity_search_mode,
                    multi_query=multi_query,
                    breadth_first=breadth_first,
                    thesis=thesis,
                    formatting_options=formatting_options,
                    template_structure=context.get('template_structure'),
                    extra_agent_instructions=context.get('extra_agent_instructions'),
                    mode=context.get('document_type') or context.get('mode'),
                    previous_sections=context.get('previous_sections', []),
                    system_instruction=system_instruction
                )
                
                processing_time = time.time() - start_time
                
                # Mapear resultados...
                reviews_list = []
                # ... (manter lógica existente de reviews/conflicts)
                if 'critica_gpt_on_claude' in drafts:
                    reviews_list.append(AgentReview(
                        agent_name="GPT-5.2 (Crítico)",
                        score=9.0, 
                        approved=True, 
                        suggested_changes=drafts['critica_gpt_on_claude'], 
                        metadata={}
                    ))
                
                conflicts = []
                if divergencias_md:
                    conflicts.append("Divergências resolvidas pelo Juiz (ver dashboard)")



                # Executar Auditoria Final (Pós-Consenso)
                audit_metadata = {}
                # Only run if service exists AND requested
                if self.audit_service and run_audit:
                    import asyncio
                    logger.info("⚖️ Executando Auditoria Jurídica Final...")
                    # Executar em thread separada para não bloquear loop
                    audit_result = await asyncio.to_thread(
                        self.audit_service.audit_document, 
                        final_text, 
                        "gemini-1.5-pro-002",
                        self.rag_manager
                    )
                    audit_metadata = audit_result

                return MultiAgentResult(
                    final_content=final_text,
                    reviews=reviews_list,
                    consensus=True,
                    conflicts=conflicts,
                    total_tokens=0, 
                    total_cost=0.0,
                    processing_time_seconds=processing_time,
                    metadata={
                        "mode": "agent_v2.5_async_2025",
                        "drafts": drafts,
                        "divergencias": divergencias_md,
                        "audit": audit_metadata
                    }
                )
            else:
                # MODO SIMPLES (Single Shot) - Roteamento de Modelos 2025
                logger.info(f"⚡ Modo Simples: Usando {model} (Raciocínio: {reasoning_level})")
                
                # Preparar prompt com contexto e instruções de raciocínio e Web Search
                bundle_context = case_bundle.to_agent_context()
                
                reasoning_instruction = ""
                if reasoning_level == "high":
                    reasoning_instruction = "\n\n[INSTRUÇÃO DE RACIOCÍNIO]: Analise profundamente todos os ângulos jurídicos, doutrina e jurisprudência antes de redigir. Seja exaustivo."
                elif reasoning_level == "low":
                    reasoning_instruction = "\n\n[INSTRUÇÃO DE RACIOCÍNIO]: Seja direto e conciso. Foque na resposta rápida."
                
                web_search_instruction = ""
                web_search_instruction = ""
                
                # HYBRID STRATEGY: Dense Research > Web Search
                if dense_research:
                   web_search_instruction = "\n\n[INFO]: Deep Research Agent ativado. Baseando-se em relatório aprofundado."
                   try:
                       search_term = prompt[:300].replace('\n', ' ')
                       logger.info(f"🧠 [Simple Mode] Iniciando DEEP RESEARCH para: {search_term[:50]}...")
                       
                       # Call Autonomous Agent
                       deep_config: Optional[Dict[str, Any]] = None
                       if deep_research_effort or deep_research_points_multiplier is not None:
                           deep_config = {}
                           if deep_research_effort:
                               deep_config["effort"] = deep_research_effort
                           if deep_research_points_multiplier is not None:
                               deep_config["points_multiplier"] = deep_research_points_multiplier
                       dr_result = await deep_research_service.run_research_task(search_term, config=deep_config)
                       
                       if dr_result.success:
                           web_context = f"\n\n## RELATÓRIO DE PESQUISA PROFUNDA (Deep Research Agent - 12-2025):\n{dr_result.text}\n"
                           if dr_result.log:
                               web_context += f"\n### Raciocínio do Agente:\n{dr_result.log[:2000]}...\n"
                               
                           web_search_instruction += web_context
                           logger.info(f"✅ [Simple Mode] Deep Research report injected.")
                       else:
                           logger.warning(f"⚠️ Deep Research falhou, caindo para busca padrão: {dr_result.error}")
                           # Fallback to standard search logic below if needed or just log error
                           web_search = True # Fallback enabling
                           
                   except Exception as e:
                       logger.error(f"❌ [Simple Mode] Deep Research critical failure: {e}")
                       web_search = True # Fallback

                if web_search and not web_search_instruction: # Only run if Deep Research didn't already populate
                    search_mode = (search_mode or "hybrid").lower()
                    if search_mode not in ("shared", "native", "hybrid", "perplexity"):
                        search_mode = "hybrid"
                    if search_mode != "native":
                        web_search_instruction = "\n\n[INFO]: Pesquisa na Web ativada. Considere fatos recentes."
                        # Execute Web Search Injection (Unified)
                        try:
                            search_term = prompt[:200].replace('\n', ' ')
                            logger.info(f"🔍 [Simple Mode] Searching web for: {search_term[:50]}...")
                            breadth_first = bool(breadth_first) or is_breadth_first(search_term)
                            use_multi_query = bool(multi_query) or breadth_first
                            if use_multi_query:
                                results = await web_search_service.search_multi(
                                    search_term,
                                    num_results=10,
                                    search_mode=normalized_perplexity_search_mode,
                                )
                            else:
                                results = await web_search_service.search(
                                    search_term,
                                    num_results=10,
                                    search_mode=normalized_perplexity_search_mode,
                                )
                            if results.get('success') and results.get('results'):
                                web_context = "\n\n## PESQUISA WEB RECENTE (Contexto Adicional):\n"
                                for res in results['results']:
                                    web_context += f"- [{res['title']}]({res['url']}): {res['snippet']}\n"
                                web_search_instruction += web_context
                                logger.info(f"✅ [Simple Mode] Web context injected.")
                        except Exception as e:
                            logger.error(f"❌ [Simple Mode] Web search failed: {e}")
                
                enhanced_prompt = f"{prompt}\n\n{bundle_context}{reasoning_instruction}{web_search_instruction}"
                
                # Injetar Contexto RAG e Template também no modo simples
                rag_context = context.get('rag_context', '')
                if rag_context:
                    enhanced_prompt += f"\n\n## FONTES RAG:\n{rag_context}"
                
                template_structure = context.get('template_structure')
                if template_structure:
                    enhanced_prompt += f"\n\n## ESTRUTURA SUGERIDA:\n{template_structure}"
                    
                extra_instr = context.get('extra_agent_instructions')
                if extra_instr:
                    enhanced_prompt += f"\n\n{extra_instr}"
                
                final_text = ""
                
                # 1. Roteamento CLAUDE (Sonnet 4.5)
                if "claude" in model.lower():
                    from app.services.ai.agent_clients import call_anthropic_async
                    # Determine if extended thinking should be enabled
                    # Claude Sonnet 4.5 supports thinking_budget 0-63999
                    extended_thinking = reasoning_level in ("medium", "high", "xhigh")
                    if reasoning_level == "xhigh":
                        thinking_budget = 48000  # ~75% of max for complex analysis
                    elif reasoning_level == "high":
                        thinking_budget = 24000  # ~37% of max for deep reasoning
                    else:
                        thinking_budget = 10000  # ~15% of max for medium reasoning
                    final_text = await call_anthropic_async(
                        self.claude_client,
                        enhanced_prompt,
                        model=get_api_model_name(model_claude),
                        temperature=temperature,
                        web_search=web_search,
                        system_instruction=system_instruction,
                        extended_thinking=extended_thinking,
                        thinking_budget=thinking_budget if extended_thinking else None,
                    )
                
                # 2. Roteamento GEMINI (3 Flash / 3 Pro)
                elif "gemini" in model.lower():
                    from app.services.ai.agent_clients import call_vertex_gemini_async
                    # Map reasoning_level to thinking_mode
                    thinking_mode = None
                    if reasoning_level == "none":
                        thinking_mode = None
                    elif reasoning_level in ("minimal", "low"):
                        thinking_mode = reasoning_level
                    elif reasoning_level in ("medium", "high", "xhigh"):
                        thinking_mode = "high"
                    
                    final_text = await call_vertex_gemini_async(
                        None, 
                        enhanced_prompt,
                        model=get_api_model_name(model),
                        temperature=temperature,
                        web_search=web_search,
                        system_instruction=system_instruction,
                        thinking_mode=thinking_mode,
                    )
                
                # 3. Roteamento GPT (5.2)
                elif "gpt" in model.lower():
                    from app.services.ai.agent_clients import call_openai_async
                    # Map reasoning_level to reasoning_effort
                    reasoning_effort = reasoning_level if reasoning_level != "xhigh" else "high"
                    final_text = await call_openai_async(
                        self.gpt_client,
                        enhanced_prompt,
                        model=get_api_model_name(model_gpt),
                        temperature=temperature,
                        web_search=web_search,
                        system_instruction=system_instruction,
                        reasoning_effort=reasoning_effort,
                    )
                
                # Fallback Padrão (Gemini Flash)
                if not final_text:
                    logger.warning(f"⚠️ Modelo {model} não retornou, usando fallback Gemini Flash")
                    from app.services.ai.agent_clients import call_vertex_gemini_async
                    final_text = await call_vertex_gemini_async(
                        None,
                        enhanced_prompt,
                        model=get_api_model_name("gemini-3-flash"),
                        temperature=temperature,
                        system_instruction=system_instruction
                    ) or "Erro na geração."
                
                processing_time = time.time() - start_time
                
                return MultiAgentResult(
                    final_content=final_text,
                    reviews=[],
                    consensus=True,
                    conflicts=[],
                    total_tokens=0,
                    total_cost=0.0,
                    processing_time_seconds=processing_time,
                    metadata={"mode": f"simple_{model}", "reasoning": reasoning_level}
                )

        except Exception as e:
            logger.error(f"❌ Erro na geração: {e}")
            raise
    
    def _enhance_prompt_for_document_type(
        self,
        prompt: str,
        context: Dict[str, Any],
        document_type: str
    ) -> str:
        """
        Aprimora prompt de acordo com o tipo de documento
        """
        doc_type_lower = document_type.lower()
        
        # Mapear tipos de documento para prompts especializados
        if doc_type_lower in ['petition', 'petição', 'ação']:
            case_details = {
                'action_type': context.get('action_type', 'Não especificado'),
                'case_description': prompt,
                'requests': context.get('requests', ''),
                'case_value': context.get('case_value', ''),
                'attached_docs': context.get('attached_docs', 'Nenhum')
            }
            return self.prompts.get_petition_generation_prompt(case_details)
        
        elif doc_type_lower in ['contract', 'contrato']:
            contract_details = {
                'contract_type': context.get('contract_type', 'Prestação de Serviços'),
                'contractor_info': context.get('contractor_info', ''),
                'contractee_info': context.get('contractee_info', ''),
                'object': prompt,
                'special_conditions': context.get('special_conditions', ''),
                'value': context.get('value', ''),
                'duration': context.get('duration', '')
            }
            return self.prompts.get_contract_generation_prompt(contract_details)
        
        elif doc_type_lower in ['opinion', 'parecer']:
            opinion_details = {
                'question': prompt,
                'context': context.get('background', ''),
                'documents': context.get('documents', 'Nenhum')
            }
            return self.prompts.get_opinion_generation_prompt(opinion_details)
        
        elif doc_type_lower in ['appeal', 'recurso', 'apelação']:
            appeal_details = {
                'appeal_type': context.get('appeal_type', 'APELAÇÃO'),
                'decision': context.get('decision', ''),
                'decision_grounds': context.get('decision_grounds', ''),
                'contested_points': prompt
            }
            return self.prompts.get_appeal_generation_prompt(appeal_details)
        
        elif doc_type_lower in ['defense', 'contestação', 'defesa']:
            defense_details = {
                'action_type': context.get('action_type', ''),
                'plaintiff_claims': context.get('plaintiff_claims', ''),
                'contested_facts': prompt
            }
            return self.prompts.get_defense_generation_prompt(defense_details)
        
        else:
            # Usar prompt genérico melhorado
            user_context = context.get('user_info', {})
            return self.prompts.enhance_prompt_with_context(prompt, user_context, context)
    
    async def simple_chat(
        self,
        message: str,
        context: Dict[str, Any],
        conversation_history: Optional[List[Dict]] = None
    ) -> AgentResponse:
        """
        Chat com suporte a roteamento de modelos 2025 e @GroupChat
        Comandos: @gpt, @claude, @gemini, @todos
        """
        logger.info(f"💬 Chat Message: {message[:50]}...")

        def _format_history_block(history: Optional[List[Dict[str, Any]]], summary_text: Optional[str]) -> str:
            parts: List[str] = []
            if summary_text:
                parts.append("### RESUMO DA CONVERSA")
                parts.append(str(summary_text).strip())
            if history:
                parts.append("### ÚLTIMAS MENSAGENS")
                for item in history[-12:]:
                    role = str(item.get("role") or "").strip().lower()
                    content = str(item.get("content") or "").strip()
                    if not content:
                        continue
                    label = "Usuário" if role == "user" else "Assistente"
                    parts.append(f"{label}: {content}")
            if not parts:
                return ""
            return "\n".join(parts).strip()

        # 1. Detectar Menções
        message_lower = message.lower()
        target_models = []

        chat_personality = (context.get("chat_personality") or "juridico").lower()

        if "@todos" in message_lower or "@all" in message_lower:
            target_models = ["gpt", "claude", "gemini"]
        else:
            if "@gpt" in message_lower: target_models.append("gpt")
            if "@claude" in message_lower: target_models.append("claude")
            if "@gemini" in message_lower: target_models.append("gemini")
            
        # Default se ninguém for mencionado
        if not target_models:
            if chat_personality == "geral":
                if self.gpt_client:
                    target_models = ["gpt"]
                elif self.claude_client:
                    target_models = ["claude"]
                else:
                    target_models = ["gemini"]
            else:
                if self.claude_client:
                    target_models = ["claude"]
                elif self.gpt_client:
                    target_models = ["gpt"]
                else:
                    target_models = ["gemini"]

        # 2. Extrair configs do contexto
        reasoning_level = context.get("reasoning_level", "medium")
        web_search = context.get("web_search", False)

        from app.services.ai.agent_clients import build_system_instruction
        system_instruction = build_system_instruction(chat_personality)
        if reasoning_level == "high":
            system_instruction += "\n- Aprofunde a análise e considere nuances importantes."
        elif reasoning_level == "low":
            system_instruction += "\n- Seja direto e conciso."
        if web_search:
            system_instruction += "\n- Considere que há pesquisa recente disponível quando pertinente."

        summary_text = context.get("conversation_summary")
        history_block = _format_history_block(conversation_history, summary_text)
        enhanced_message = f"{history_block}\n\n### MENSAGEM ATUAL\n{message}" if history_block else message
        max_tokens = 700 if chat_personality == "geral" else 1800
        raw_temperature = context.get("temperature")
        try:
            temperature = float(raw_temperature) if raw_temperature is not None else (
                0.6 if chat_personality == "geral" else 0.3
            )
        except (TypeError, ValueError):
            temperature = 0.6 if chat_personality == "geral" else 0.3
        temperature = max(0.0, min(1.0, temperature))
        
        # 3. Executar chamadas (Sequencial para simplificar, idealmente Paralelo)
        responses = []
        
        from app.services.ai.agent_clients import (
            call_openai_async, call_anthropic_async, call_vertex_gemini_async
        )
        
        for model_key in target_models:
            response_text = ""
            agent_name = ""
            
            try:
                if model_key == "gpt":
                    agent_name = "GPT-5.2"
                    response_text = await call_openai_async(
                        self.gpt_client,
                        enhanced_message,
                        model=get_api_model_name("gpt-5.2"),
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system_instruction=system_instruction
                    )
                elif model_key == "claude":
                    agent_name = "Claude 4.5"
                    response_text = await call_anthropic_async(
                        self.claude_client,
                        enhanced_message,
                        model=get_api_model_name("claude-4.5-sonnet"),
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system_instruction=system_instruction
                    )
                elif model_key == "gemini":
                    agent_name = "Gemini 3 Flash"
                    response_text = await call_vertex_gemini_async(
                        None,
                        enhanced_message,
                        model=get_api_model_name("gemini-3-flash"),
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system_instruction=system_instruction
                    )
                
                if response_text:
                    if len(target_models) > 1:
                        responses.append(f"🤖 **{agent_name}**:\n{response_text}")
                    else:
                        responses.append(response_text)
                        
            except Exception as e:
                logger.error(f"Erro no chat com {model_key}: {e}")
                responses.append(f"⚠️ Erro com {model_key}")

        final_response = "\n\n---\n\n".join(responses)

        # Gemini failsafe: if no useful response was generated, try Gemini directly
        if not final_response or all(r.startswith("⚠️") for r in responses):
            logger.warning("⚠️ Todos os modelos falharam, tentando Gemini como fallback final...")
            try:
                fallback_text = await call_vertex_gemini_async(
                    None,
                    enhanced_message,
                    model=get_api_model_name("gemini-3-flash"),
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_instruction=system_instruction
                )
                if fallback_text:
                    final_response = fallback_text
                    logger.info("✅ Gemini fallback successful")
            except Exception as e:
                logger.error(f"❌ Gemini fallback also failed: {e}")
                final_response = "Desculpe, não foi possível processar sua mensagem no momento. Todos os modelos estão indisponíveis."
        
        return AgentResponse(content=final_response, metadata={"models": target_models})
