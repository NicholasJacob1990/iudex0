"""
Adaptador para usar juridico_gemini.py como biblioteca no backend.

Este módulo permite que o backend FastAPI use o motor de geração avançado
do juridico_gemini.py (com RAG, Agent Mode, Auditoria, etc.)
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger
import asyncio
from app.services.ai.model_registry import get_api_model_name

# Adicionar diretório raiz do Iudex ao path para importar juridico_gemini
IUDEX_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent  # apps/api/app/services/ai → root
sys.path.insert(0, str(IUDEX_ROOT))

try:
    from juridico_gemini import generate_document_programmatic, LegalDrafter, PROMPT_MAP
    JURIDICO_AVAILABLE = True
    logger.info(f"✅ juridico_gemini importado de {IUDEX_ROOT}")
except ImportError as e:
    logger.warning(f"⚠️ juridico_gemini não disponível: {e}")
    JURIDICO_AVAILABLE = False


class JuridicoGeminiAdapter:
    """
    Adaptador que mapeia DocumentGenerationRequest para os parâmetros
    de generate_document_programmatic() do juridico_gemini.py.
    """
    
    def __init__(self, rag_manager=None):
        """
        Args:
            rag_manager: Instância de RAGManager pré-inicializada (opcional)
        """
        self.rag_manager = rag_manager
        
        if not JURIDICO_AVAILABLE:
            logger.error("JuridicoGeminiAdapter inicializado mas juridico_gemini não disponível!")
    
    async def generate(
        self,
        prompt: str,
        document_type: str = "PETICAO_INICIAL",
        thesis: str = "A favor do cliente",
        model: str = None,
        target_pages: int = 0,
        min_pages: int = 0,
        max_pages: int = 0,
        local_files: List[str] = None,
        use_rag: bool = True,
        rag_sources: List[str] = None,
        processo_local_path: str = None,
        processo_id: str = None,
        tenant_id: str = "default",
        use_multi_agent: bool = False,
        gpt_model: str = "gpt-4o",
        claude_model: str = "claude-sonnet-4-20250514",
        run_audit: bool = True,
        include_toc: bool = False,
        context_files: List[str] = None,
        cache_ttl: int = 60,
        # v4.0: Adaptive RAG & CRAG Gate
        adaptive_routing: bool = False,
        crag_gate: bool = False,
        crag_min_best: float = 0.45,
        crag_min_avg: float = 0.35,
        verbose_rag: bool = False,
        # v4.1: Deep Research & Web Search
        deep_research: bool = False,
        web_search: bool = False,
        reasoning_level: str = "medium",
        # v5.0: GraphRAG & HyDE
        hyde_enabled: bool = False,
        graph_rag_enabled: bool = False,
        graph_hops: int = 2,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Gera documento usando juridico_gemini.py.
        
        Args:
            prompt: Texto de entrada (fatos, notas, descrição do caso)
            document_type: Tipo de peça (PETICAO_INICIAL, CONTESTACAO, etc.)
            thesis: Tese central
            model: Modelo Gemini a usar
            target_pages: Número alvo de páginas
            min_pages: Mínimo de páginas (0 = auto)
            max_pages: Máximo de páginas (0 = auto)
            local_files: Lista de arquivos para RAG Local
            use_rag: Habilitar RAG
            rag_sources: Fontes RAG ["lei", "juris", "pecas_modelo"]
            processo_local_path: Pasta local dos autos (RAG Local)
            processo_id: ID do processo
            tenant_id: Tenant ID para RBAC
            use_multi_agent: Habilitar modo agente (GPT + Claude)
            gpt_model: Modelo GPT
            claude_model: Modelo Claude
            run_audit: Executar auditoria jurídica
            include_toc: Incluir sumário
            adaptive_routing: v4.0 - Roteamento adaptativo por seção
            crag_gate: v4.0 - Gate de qualidade CRAG
            hyde_enabled: v5.0 - HyDE para busca semântica aprimorada
            graph_rag_enabled: v5.0 - GraphRAG para raciocínio multi-hop
        
        Returns:
            Dict com:
                - markdown: str
                - docx_bytes: bytes ou None
                - audit: Dict ou None
                - citations_log: List
                - metrics: Dict
                - outline: List[str]
        """
        
        if not JURIDICO_AVAILABLE:
            raise RuntimeError("juridico_gemini não está disponível")

        # Normalizar modelos (aceitar ids canônicos)
        model = get_api_model_name(model) if model else model
        gpt_model = get_api_model_name(gpt_model) if gpt_model else gpt_model
        claude_model = get_api_model_name(claude_model) if claude_model else claude_model
        
        # Normalizar document_type para formato esperado
        mode = document_type.upper().replace(" ", "_")
        if mode not in PROMPT_MAP and mode != "CHAT":
            logger.warning(f"Tipo de documento '{mode}' não reconhecido, usando PETICAO_INICIAL")
            mode = "PETICAO_INICIAL"
        
        # Executar em thread separada para não bloquear o event loop
        result = await asyncio.to_thread(
            generate_document_programmatic,
            input_text=prompt,
            mode=mode,
            tese=thesis,
            model=model,
            target_pages=target_pages,
            min_pages=min_pages,
            max_pages=max_pages,
            local_files=local_files or [],
            rag_enabled=use_rag,
            rag_sources=rag_sources or ["lei", "juris", "pecas_modelo"],
            rag_manager=self.rag_manager,
            processo_local_path=processo_local_path,
            processo_id=processo_id,
            tenant_id=tenant_id,
            agent_mode=use_multi_agent,
            gpt_model=gpt_model,
            claude_model=claude_model,
            run_audit=run_audit,
            include_toc=include_toc,
            context_files=context_files,
            cache_ttl=cache_ttl,
            # v4.0: Adaptive RAG & CRAG Gate
            adaptive_routing=adaptive_routing,
            crag_gate=crag_gate,
            crag_min_best=crag_min_best,
            crag_min_avg=crag_min_avg,
            verbose_rag=verbose_rag,
            # v4.1: Research flags
            deep_research=deep_research,
            web_search=web_search,
            reasoning_level=reasoning_level,
            # v5.0: GraphRAG & HyDE
            hyde_enabled=hyde_enabled,
            graph_rag_enabled=graph_rag_enabled,
            graph_hops=graph_hops
        )
        
        return result
    
    async def chat(
        self,
        message: str,
        history: List[Dict[str, str]] = None,
        context_files: List[str] = None,
        cache_ttl: int = 60,
        model: str = None,
        tenant_id: str = "default",
        custom_prompt: str = None,
        rag_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Interage com o chat jurídico via juridico_gemini.py.
        """
        if not JURIDICO_AVAILABLE:
            raise RuntimeError("juridico_gemini não está disponível")
            
        try:
            from juridico_gemini import chat_programmatic

            # Normalizar modelo (aceitar id canônico)
            model = get_api_model_name(model) if model else model

            result = await asyncio.to_thread(
                chat_programmatic,
                message=message,
                history=history,
                context_files=context_files,
                cache_ttl=cache_ttl,
                model=model,
                tenant_id=tenant_id,
                custom_prompt=custom_prompt,
                rag_config=rag_config
            )
            return result
        except ImportError:
            logger.error("chat_programmatic não encontrado em juridico_gemini.py")
            raise NotImplementedError("Chat function not available")
        except Exception as e:
            logger.error(f"Erro no chat adapter: {e}")
            raise
    
    def get_available_modes(self) -> List[str]:
        """Retorna lista de tipos de documento suportados"""
        if JURIDICO_AVAILABLE:
            return list(PROMPT_MAP.keys())
        return []
    
    def is_available(self) -> bool:
        """Verifica se o adaptador está funcional"""
        return JURIDICO_AVAILABLE


# Singleton para reutilização
_adapter_instance: Optional[JuridicoGeminiAdapter] = None


def get_juridico_adapter(rag_manager=None) -> JuridicoGeminiAdapter:
    """
    Retorna instância singleton do adaptador.
    
    Args:
        rag_manager: RAGManager a injetar (só usado na primeira chamada)
    """
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = JuridicoGeminiAdapter(rag_manager=rag_manager)
    return _adapter_instance
