"""
Unified Tools - Integração de todas as tools para LangGraph e Claude Agent.

Este módulo unifica:
1. Tools jurídicas do Claude Agent (legal_research, document_editor, etc.)
2. Tools do SDK adaptadas (read, write, edit, glob, grep)
3. MCP tools (via mcp_hub)
4. Web tools (search, fetch)

Todas as tools ficam disponíveis no ToolRegistry global.
"""

import asyncio
import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from loguru import logger

from app.services.ai.shared.tool_registry import (
    ToolRegistry,
    ToolDefinition,
    ToolCategory,
    get_global_registry,
)
from app.services.ai.shared.sse_protocol import ToolApprovalMode


# =============================================================================
# TOOL PERMISSION LEVELS
# =============================================================================

class ToolRiskLevel(str, Enum):
    """Nível de risco da tool para definir permissões padrão."""
    LOW = "low"          # Leitura, busca - Allow por padrão
    MEDIUM = "medium"    # Edição, criação - Ask por padrão
    HIGH = "high"        # Delete, bash - Deny por padrão


# Mapeamento de risco para permissão padrão
RISK_TO_PERMISSION = {
    ToolRiskLevel.LOW: ToolApprovalMode.ALLOW,
    ToolRiskLevel.MEDIUM: ToolApprovalMode.ALLOW,
    ToolRiskLevel.HIGH: ToolApprovalMode.ALLOW,
}


# =============================================================================
# TOOL DEFINITIONS - SDK ADAPTED
# =============================================================================

@dataclass
class UnifiedTool:
    """
    Definição unificada de tool compatível com Claude e OpenAI.
    """
    name: str
    description: str
    category: ToolCategory
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    is_async: bool = True
    requires_context: bool = False  # Se precisa de case_id, user_id, etc.
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_tool_definition(self) -> ToolDefinition:
        """Converte para ToolDefinition do registry."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            category=self.category,
            parameters=self.parameters,
            handler=self.handler,
            requires_approval=self.risk_level != ToolRiskLevel.LOW,
            is_async=self.is_async,
            metadata={
                **self.metadata,
                "risk_level": self.risk_level.value,
                "requires_context": self.requires_context,
            }
        )


# =============================================================================
# SDK TOOLS - Adaptados para contexto Iudex
# =============================================================================

# --- READ TOOL ---
READ_TOOL = UnifiedTool(
    name="read_document",
    description="""Lê o conteúdo de um documento do caso.

Use para:
- Ler documentos anexados ao processo
- Consultar petições, contratos, laudos
- Extrair texto de PDFs processados

Retorna o conteúdo em texto/markdown.""",
    category=ToolCategory.DOCUMENT,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "ID do documento a ler"
            },
            "section": {
                "type": "string",
                "description": "Seção específica (opcional). Ex: 'DOS FATOS', página 5"
            },
            "format": {
                "type": "string",
                "enum": ["text", "markdown", "html"],
                "default": "markdown",
                "description": "Formato de retorno"
            }
        },
        "required": ["document_id"]
    }
)


# --- WRITE TOOL ---
WRITE_TOOL = UnifiedTool(
    name="write_document",
    description="""Cria um novo documento ou sobrescreve existente.

Use para:
- Criar nova minuta/petição
- Salvar versão final de documento
- Gerar relatórios

ATENÇÃO: Sobrescreve documento existente se mesmo ID.""",
    category=ToolCategory.DOCUMENT,
    risk_level=ToolRiskLevel.MEDIUM,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "ID do documento (novo ou existente)"
            },
            "content": {
                "type": "string",
                "description": "Conteúdo do documento"
            },
            "title": {
                "type": "string",
                "description": "Título do documento"
            },
            "document_type": {
                "type": "string",
                "enum": ["minuta", "peticao", "parecer", "relatorio", "outro"],
                "description": "Tipo do documento"
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "html", "docx"],
                "default": "markdown"
            }
        },
        "required": ["content", "title"]
    }
)


# --- EDIT TOOL ---
EDIT_TOOL = UnifiedTool(
    name="edit_document",
    description="""Edita uma seção específica de um documento existente.

Use para:
- Atualizar seção 'DOS FATOS' com novos dados
- Corrigir citações
- Adicionar fundamentação
- Fazer substituições no texto

Substitui old_text por new_text mantendo resto do documento.""",
    category=ToolCategory.DOCUMENT,
    risk_level=ToolRiskLevel.MEDIUM,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "ID do documento a editar"
            },
            "section": {
                "type": "string",
                "description": "Nome da seção (ex: 'DOS FATOS', 'DO DIREITO')"
            },
            "old_text": {
                "type": "string",
                "description": "Texto a ser substituído"
            },
            "new_text": {
                "type": "string",
                "description": "Novo texto"
            },
            "replace_all": {
                "type": "boolean",
                "default": False,
                "description": "Substituir todas as ocorrências"
            }
        },
        "required": ["document_id", "old_text", "new_text"]
    }
)


# --- GLOB TOOL ---
GLOB_TOOL = UnifiedTool(
    name="find_documents",
    description="""Busca documentos por padrão de nome/tipo.

Use para:
- Listar todos os contratos do caso
- Encontrar petições iniciais
- Buscar documentos por extensão

Retorna lista de documentos que correspondem ao padrão.""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Padrão de busca. Ex: 'contrato*', '*.pdf', 'peticao_inicial*'"
            },
            "document_type": {
                "type": "string",
                "enum": ["all", "peticao", "contrato", "laudo", "procuracao", "outros"],
                "default": "all",
                "description": "Filtrar por tipo"
            },
            "limit": {
                "type": "integer",
                "default": 20,
                "description": "Número máximo de resultados"
            }
        },
        "required": ["pattern"]
    }
)


# --- GREP TOOL ---
GREP_TOOL = UnifiedTool(
    name="search_in_documents",
    description="""Busca texto/padrão dentro dos documentos do caso.

Use para:
- Encontrar menções a valores (R$ 100.000)
- Buscar nomes de partes
- Localizar datas específicas
- Encontrar cláusulas

Suporta regex para buscas avançadas.""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Texto ou regex a buscar"
            },
            "document_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs dos documentos para buscar (vazio = todos)"
            },
            "case_sensitive": {
                "type": "boolean",
                "default": False
            },
            "regex": {
                "type": "boolean",
                "default": False,
                "description": "Tratar pattern como regex"
            },
            "context_lines": {
                "type": "integer",
                "default": 2,
                "description": "Linhas de contexto antes/depois do match"
            }
        },
        "required": ["pattern"]
    }
)


# --- WEB SEARCH TOOL ---
WEB_SEARCH_TOOL = UnifiedTool(
    name="web_search",
    description="""Pesquisa na web usando motores de busca.

Use para:
- Buscar jurisprudência recente
- Pesquisar notícias sobre tema
- Encontrar doutrina
- Verificar informações atuais

Integra com Perplexity, Tavily, ou Google.""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query de busca"
            },
            "search_type": {
                "type": "string",
                "enum": ["general", "news", "academic", "legal"],
                "default": "general"
            },
            "recency": {
                "type": "string",
                "enum": ["any", "day", "week", "month", "year"],
                "default": "any"
            },
            "max_results": {
                "type": "integer",
                "default": 10
            }
        },
        "required": ["query"]
    }
)


# --- WEB FETCH TOOL ---
WEB_FETCH_TOOL = UnifiedTool(
    name="web_fetch",
    description="""Busca conteúdo de uma URL específica.

Use para:
- Acessar página de tribunal
- Ler artigo citado
- Consultar legislação online
- Extrair dados de site

Retorna conteúdo em markdown.""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "format": "uri",
                "description": "URL a buscar"
            },
            "extract_mode": {
                "type": "string",
                "enum": ["full", "article", "main_content"],
                "default": "main_content",
                "description": "O que extrair da página"
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "description": "Timeout em segundos"
            }
        },
        "required": ["url"]
    }
)


# --- TASK/SUBAGENT TOOL ---
SUBAGENT_TOOL = UnifiedTool(
    name="delegate_research",
    description="""Delega pesquisa paralela para subagentes especializados.

Use para:
- Pesquisar múltiplas fontes simultaneamente
- Dividir pesquisa complexa
- Consultar diferentes bases

Executa em paralelo e consolida resultados.""",
    category=ToolCategory.ANALYSIS,
    risk_level=ToolRiskLevel.MEDIUM,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "research_queries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "enum": ["jurisprudencia", "legislacao", "doutrina", "rag", "web"]
                        },
                        "query": {"type": "string"}
                    },
                    "required": ["source", "query"]
                },
                "description": "Lista de pesquisas a executar em paralelo"
            },
            "consolidate": {
                "type": "boolean",
                "default": True,
                "description": "Consolidar resultados em resumo"
            },
            "max_results_per_source": {
                "type": "integer",
                "default": 5
            }
        },
        "required": ["research_queries"]
    }
)


# =============================================================================
# LEGAL DOMAIN TOOLS
# =============================================================================

SEARCH_JURISPRUDENCIA_TOOL = UnifiedTool(
    name="search_jurisprudencia",
    description="""Pesquisa jurisprudência em tribunais.

Fontes: STF, STJ, TRFs, TJs estaduais.

Use para:
- Encontrar precedentes
- Buscar decisões similares
- Verificar entendimento consolidado""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termos de busca"
            },
            "tribunais": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["STF", "STJ", "TRF1", "TRF2", "TRF3", "TRF4", "TRF5", "TJSP", "TJRJ", "TJMG", "todos"]
                },
                "default": ["todos"]
            },
            "data_inicio": {
                "type": "string",
                "format": "date",
                "description": "Data inicial (YYYY-MM-DD)"
            },
            "data_fim": {
                "type": "string",
                "format": "date",
                "description": "Data final (YYYY-MM-DD)"
            },
            "tipo_decisao": {
                "type": "string",
                "enum": ["acordao", "decisao_monocratica", "sumula", "todos"],
                "default": "todos"
            },
            "max_results": {
                "type": "integer",
                "default": 10
            }
        },
        "required": ["query"]
    }
)


SEARCH_LEGISLACAO_TOOL = UnifiedTool(
    name="search_legislacao",
    description="""Pesquisa legislação federal, estadual e municipal.

Fontes: Planalto, assembleias, câmaras.

Use para:
- Encontrar leis aplicáveis
- Verificar vigência
- Consultar regulamentos""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termos de busca ou número da lei"
            },
            "tipo": {
                "type": "string",
                "enum": ["lei", "decreto", "portaria", "resolucao", "instrucao_normativa", "todos"],
                "default": "todos"
            },
            "esfera": {
                "type": "string",
                "enum": ["federal", "estadual", "municipal", "todos"],
                "default": "federal"
            },
            "vigente": {
                "type": "boolean",
                "default": True,
                "description": "Apenas legislação vigente"
            }
        },
        "required": ["query"]
    }
)


VERIFY_CITATION_TOOL = UnifiedTool(
    name="verify_citation",
    description="""Verifica se uma citação jurisprudencial é válida.

Valida:
- Número do processo
- Relator
- Data do julgamento
- Ementa/texto citado

Retorna status de verificação e fonte.""",
    category=ToolCategory.CITATION,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "citation_text": {
                "type": "string",
                "description": "Texto da citação a verificar"
            },
            "expected_source": {
                "type": "string",
                "description": "Fonte esperada (ex: 'STJ, REsp 1.234.567')"
            },
            "strict_mode": {
                "type": "boolean",
                "default": False,
                "description": "Verificação rigorosa de todos os elementos"
            }
        },
        "required": ["citation_text"]
    }
)


SEARCH_RAG_TOOL = UnifiedTool(
    name="search_rag",
    description="""Busca no RAG (base de conhecimento interna).

Fontes:
- Documentos do caso atual
- Base global de templates
- Conhecimento jurídico indexado

Use para consultar documentos já carregados.""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query de busca semântica"
            },
            "scope": {
                "type": "string",
                "enum": ["case", "global", "both"],
                "default": "case",
                "description": "Escopo: caso atual, global, ou ambos"
            },
            "document_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tipos de documento para filtrar"
            },
            "max_results": {
                "type": "integer",
                "default": 10
            },
            "min_score": {
                "type": "number",
                "default": 0.7,
                "description": "Score mínimo de relevância (0-1)"
            }
        },
        "required": ["query"]
    }
)


CREATE_SECTION_TOOL = UnifiedTool(
    name="create_section",
    description="""Cria uma nova seção em documento existente.

Use para:
- Adicionar seção 'DAS PROVAS' a petição
- Inserir fundamentação adicional
- Criar nova parte do documento""",
    category=ToolCategory.DOCUMENT,
    risk_level=ToolRiskLevel.MEDIUM,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "ID do documento"
            },
            "section_title": {
                "type": "string",
                "description": "Título da seção (ex: 'III - DAS PROVAS')"
            },
            "content": {
                "type": "string",
                "description": "Conteúdo da seção"
            },
            "position": {
                "type": "string",
                "enum": ["before", "after", "end"],
                "default": "end",
                "description": "Onde inserir"
            },
            "reference_section": {
                "type": "string",
                "description": "Seção de referência para before/after"
            }
        },
        "required": ["document_id", "section_title", "content"]
    }
)


# =============================================================================
# GRAPH ASK TOOL — Consultas tipadas ao knowledge graph
# =============================================================================

ASK_GRAPH_TOOL = UnifiedTool(
    name="ask_graph",
    description="""Consulta o grafo de conhecimento jurídico usando operações tipadas.

Use para descobrir conexões entre entidades jurídicas (leis, artigos, súmulas,
teses, conceitos), encontrar caminhos semânticos, ou buscar co-ocorrências.

**Operações disponíveis:**

1. **path** - Encontra caminho entre duas entidades
   - params: {source_id, target_id, max_hops?}
   - Ex: "Qual a conexão entre Art. 5º CF e Súmula 473 STF?"

2. **neighbors** - Retorna vizinhos semânticos de uma entidade
   - params: {entity_id, limit?}
   - Ex: "Quais entidades estão relacionadas à Lei 8.666?"

3. **cooccurrence** - Encontra co-ocorrências entre duas entidades
   - params: {entity1_id, entity2_id}
   - Ex: "Quantas vezes Lei 8.666 e licitação aparecem juntas?"

4. **search** - Busca entidades por nome
   - params: {query, entity_type?, limit?}
   - Ex: "Buscar súmulas sobre terceirização"

5. **count** - Conta entidades com filtros
   - params: {entity_type?, query?}

**Tipos de entidade válidos:**
lei, artigo, sumula, tema, tribunal, tese, conceito, principio, instituto

**IMPORTANTE:** Esta tool NÃO aceita Cypher arbitrário. Use as operações acima.""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["path", "neighbors", "cooccurrence", "search", "count"],
                "description": "Operação a executar no grafo"
            },
            "params": {
                "type": "object",
                "description": "Parâmetros específicos da operação",
                "properties": {
                    "source_id": {
                        "type": "string",
                        "description": "Entity ID de origem (para path)"
                    },
                    "target_id": {
                        "type": "string",
                        "description": "Entity ID de destino (para path)"
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "Entity ID (para neighbors)"
                    },
                    "entity1_id": {
                        "type": "string",
                        "description": "Primeiro entity ID (para cooccurrence)"
                    },
                    "entity2_id": {
                        "type": "string",
                        "description": "Segundo entity ID (para cooccurrence)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Termo de busca (para search)"
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ["lei", "artigo", "sumula", "tema", "tribunal", "tese", "conceito", "principio", "instituto"],
                        "description": "Filtrar por tipo de entidade"
                    },
                    "max_hops": {
                        "type": "integer",
                        "default": 4,
                        "description": "Máximo de hops no caminho (1-6)"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Número máximo de resultados"
                    }
                }
            },
            "scope": {
                "type": "string",
                "enum": ["global", "private", "group", "local"],
                "description": "Escopo de acesso"
            },
            "include_global": {
                "type": "boolean",
                "default": True,
                "description": "Se true, permite considerar conteúdo do corpus global (além do tenant)."
            }
        },
        "required": ["operation"]
    }
)


# =============================================================================
# MCP INTEGRATION TOOLS
# =============================================================================

MCP_SEARCH_TOOL = UnifiedTool(
    name="mcp_tool_search",
    description="""Pesquisa tools disponíveis nos servidores MCP.

Use para descobrir ferramentas externas disponíveis antes de usá-las.
Retorna lista de tools com descrições.""",
    category=ToolCategory.SYSTEM,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Busca por nome/descrição da tool"
            },
            "server_labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrar por servidores MCP específicos"
            },
            "limit": {
                "type": "integer",
                "default": 20
            }
        },
        "required": ["query"]
    }
)


MCP_CALL_TOOL = UnifiedTool(
    name="mcp_tool_call",
    description="""Executa uma tool em servidor MCP.

Use após descobrir a tool com mcp_tool_search.
Permite integrar ferramentas externas.""",
    category=ToolCategory.SYSTEM,
    risk_level=ToolRiskLevel.MEDIUM,  # Depende da tool MCP
    parameters={
        "type": "object",
        "properties": {
            "server_label": {
                "type": "string",
                "description": "Label do servidor MCP"
            },
            "tool_name": {
                "type": "string",
                "description": "Nome da tool a chamar"
            },
            "arguments": {
                "type": "object",
                "description": "Argumentos para a tool"
            }
        },
        "required": ["server_label", "tool_name", "arguments"]
    }
)


# =============================================================================
# TOOL COLLECTION
# =============================================================================

# Todas as tools disponíveis
ALL_UNIFIED_TOOLS: List[UnifiedTool] = [
    # SDK Adapted
    READ_TOOL,
    WRITE_TOOL,
    EDIT_TOOL,
    GLOB_TOOL,
    GREP_TOOL,
    WEB_SEARCH_TOOL,
    WEB_FETCH_TOOL,
    SUBAGENT_TOOL,
    # Legal Domain
    SEARCH_JURISPRUDENCIA_TOOL,
    SEARCH_LEGISLACAO_TOOL,
    VERIFY_CITATION_TOOL,
    SEARCH_RAG_TOOL,
    CREATE_SECTION_TOOL,
    # Graph
    ASK_GRAPH_TOOL,
    # MCP
    MCP_SEARCH_TOOL,
    MCP_CALL_TOOL,
]

# Mapeamento por nome para acesso rápido
TOOLS_BY_NAME: Dict[str, UnifiedTool] = {tool.name: tool for tool in ALL_UNIFIED_TOOLS}


# =============================================================================
# REGISTRY INITIALIZATION
# =============================================================================

def register_all_tools(registry: Optional[ToolRegistry] = None) -> ToolRegistry:
    """
    Registra todas as tools no registry.

    Args:
        registry: Registry a usar (cria global se None)

    Returns:
        Registry com tools registradas
    """
    if registry is None:
        registry = get_global_registry()

    for tool in ALL_UNIFIED_TOOLS:
        registry.register(tool.to_tool_definition())
        logger.info(f"Tool registrada: {tool.name} (risk={tool.risk_level.value})")

    logger.info(f"Total de {len(ALL_UNIFIED_TOOLS)} tools registradas")
    return registry


def get_tools_for_claude(
    tool_names: Optional[List[str]] = None,
    include_mcp: bool = True,
    risk_level_max: ToolRiskLevel = ToolRiskLevel.HIGH,
) -> List[Dict[str, Any]]:
    """
    Retorna tools no formato Claude API.

    Args:
        tool_names: Filtrar por nomes (None = todas)
        include_mcp: Incluir tools MCP
        risk_level_max: Nível máximo de risco a incluir

    Returns:
        Lista de tool definitions para Claude
    """
    tools = []
    risk_order = [ToolRiskLevel.LOW, ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH]
    max_idx = risk_order.index(risk_level_max)

    for tool in ALL_UNIFIED_TOOLS:
        # Filtrar por nome
        if tool_names and tool.name not in tool_names:
            continue

        # Filtrar MCP
        if not include_mcp and tool.name.startswith("mcp_"):
            continue

        # Filtrar por risco
        if risk_order.index(tool.risk_level) > max_idx:
            continue

        tools.append(tool.to_tool_definition().to_claude_format())

    return tools


def get_tools_for_openai(
    tool_names: Optional[List[str]] = None,
    include_mcp: bool = True,
    risk_level_max: ToolRiskLevel = ToolRiskLevel.HIGH,
) -> List[Dict[str, Any]]:
    """
    Retorna tools no formato OpenAI API.

    Args:
        tool_names: Filtrar por nomes (None = todas)
        include_mcp: Incluir tools MCP
        risk_level_max: Nível máximo de risco a incluir

    Returns:
        Lista de function definitions para OpenAI
    """
    tools = []
    risk_order = [ToolRiskLevel.LOW, ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH]
    max_idx = risk_order.index(risk_level_max)

    for tool in ALL_UNIFIED_TOOLS:
        if tool_names and tool.name not in tool_names:
            continue
        if not include_mcp and tool.name.startswith("mcp_"):
            continue
        if risk_order.index(tool.risk_level) > max_idx:
            continue

        tools.append(tool.to_tool_definition().to_openai_format())

    return tools


def get_default_permissions() -> Dict[str, ToolApprovalMode]:
    """
    Retorna permissões padrão baseadas no nível de risco.

    Returns:
        Dict de tool_name -> ToolApprovalMode
    """
    return {
        tool.name: RISK_TO_PERMISSION[tool.risk_level]
        for tool in ALL_UNIFIED_TOOLS
    }


def get_tool_risk_level(tool_name: str) -> ToolRiskLevel:
    """Retorna nível de risco de uma tool."""
    tool = TOOLS_BY_NAME.get(tool_name)
    return tool.risk_level if tool else ToolRiskLevel.HIGH


def list_tools_by_category(category: ToolCategory) -> List[str]:
    """Lista nomes de tools por categoria."""
    return [tool.name for tool in ALL_UNIFIED_TOOLS if tool.category == category]


def list_tools_by_risk(risk_level: ToolRiskLevel) -> List[str]:
    """Lista nomes de tools por nível de risco."""
    return [tool.name for tool in ALL_UNIFIED_TOOLS if tool.risk_level == risk_level]
