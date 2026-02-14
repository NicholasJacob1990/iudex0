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
    ToolRiskLevel.MEDIUM: ToolApprovalMode.ASK,
    ToolRiskLevel.HIGH: ToolApprovalMode.DENY,
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


SEARCH_JUSBRASIL_TOOL = UnifiedTool(
    name="search_jusbrasil",
    description="""Pesquisa conteudo juridico no JusBrasil.

Use para:
- Encontrar jurisprudencia e publicacoes de tribunais
- Localizar pecas e noticias juridicas indexadas
- Acelerar descoberta de precedentes com filtro por tribunal""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termos de busca"
            },
            "tribunal": {
                "type": "string",
                "description": "Sigla opcional do tribunal (ex: STJ, TJSP)"
            },
            "tipo": {
                "type": "string",
                "description": "Tipo de conteudo (ex: jurisprudencia, noticia, doutrina)"
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
            "max_results": {
                "type": "integer",
                "default": 10,
                "description": "Numero maximo de resultados (1-30)"
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


VALIDATE_CPC_COMPLIANCE_TOOL = UnifiedTool(
    name="validate_cpc_compliance",
    description="""Valida conformidade processual basica com o CPC.

Checks:
- Requisitos formais por tipo de peca (peticao inicial, contestacao, recursos)
- Alertas de base legal (ex: referencia a CPC/73)
- Verificacao heuristica de prazo processual quando datas sao informadas

Retorna checklist estruturado com pass/warning/fail e score.""",
    category=ToolCategory.ANALYSIS,
    risk_level=ToolRiskLevel.LOW,
    parameters={
        "type": "object",
        "properties": {
            "document_text": {
                "type": "string",
                "description": "Texto integral da peca juridica.",
            },
            "document_type": {
                "type": "string",
                "enum": [
                    "auto",
                    "peticao_inicial",
                    "contestacao",
                    "apelacao",
                    "agravo_instrumento",
                    "embargos_declaracao",
                    "generic",
                ],
                "default": "auto",
                "description": "Tipo da peca para aplicar regras especificas.",
            },
            "reference_date": {
                "type": "string",
                "description": "Data inicial de contagem de prazo (YYYY-MM-DD ou DD/MM/YYYY).",
            },
            "filing_date": {
                "type": "string",
                "description": "Data de protocolo/apresentacao (YYYY-MM-DD ou DD/MM/YYYY).",
            },
            "strict_mode": {
                "type": "boolean",
                "default": False,
                "description": "Se true, warnings viram falhas no resumo final.",
            },
        },
        "required": ["document_text"],
    },
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

6. **link_entities** - Cria relação entre duas entidades existentes no grafo
   - params: {source_id, target_id, relation_type?, properties?, confirm?, preflight_token?}
   - **IMPORTANTE (workflow recomendado):**
     1) Use **search** para resolver `entity_id` (NÃO invente IDs).
     2) Se a busca retornar mais de um candidato plausível, **peça confirmação** ao usuário.
     3) Faça um **preflight** com `confirm=false` (o servidor retorna preview + `preflight_token`).
     4) Só então chame **link_entities** com `confirm=true` + `preflight_token`.
   - **REGRA:** Nunca envie `confirm=true` sem o usuário ter confirmado explicitamente na conversa.
   - relation_type válidos: REMETE_A, INTERPRETA, APLICA, APLICA_SUMULA, PERTENCE_A,
     FUNDAMENTA, FIXA_TESE, JULGA_TEMA, CITA, CONFIRMA, SUPERA, DISTINGUE,
     COMPLEMENTA, EXCEPCIONA, REGULAMENTA, ESPECIALIZA, REVOGA, ALTERA,
     CANCELA, SUBSTITUI, PROFERIDA_POR, PARTICIPA_DE, REPRESENTA, RELATED_TO
   - Se relation_type inválido, será usado RELATED_TO como fallback.
   - `properties` é opcional; campos de auditoria (`source`, `layer`, `verified`, `created_by`, `created_via`)
     são forçados pelo servidor e não podem ser sobrescritos.
   - Ex: "Conecte Art. 5 CF com Súmula 473 STF via INTERPRETA"

7. **discover_hubs** - Identifica os nós mais conectados (hubs) do grafo
   - params: {top_n?}
   - Retorna categorias: artigos mais referenciados, artigos que mais referenciam,
     artigos mais conectados, decisões com mais teses, leis com mais artigos
   - Ex: "Quais são os artigos mais centrais do grafo?"

8. **text2cypher** - Converte pergunta em linguagem natural para Cypher
   - params: {question}
   - Usa LLM para gerar Cypher read-only com 3 camadas de segurança
   - Use quando nenhuma outra operação atende (perguntas complexas/agregações)
   - Ex: "Quantos artigos da CF são referenciados por mais de 3 decisões?"

9. **legal_chain** - Cadeia semântica multi-hop entre dispositivos legais
   - params: {source_id, target_id? (opcional), max_hops?, limit?}
   - Percorre REMETE_A, INTERPRETA, APLICA etc. entre entidades
   - Ex: "Qual a cadeia entre Art. 37 CF e Lei 14133?"

10. **precedent_network** - Rede de precedentes que influenciam uma decisão
    - params: {decision_id, limit?}
    - Segue CITA, FUNDAMENTA, APLICA, INTERPRETA
    - Ex: "Quais precedentes influenciam ADI 5432?"

11. **related_entities** - Entidades conectadas por arestas DIRETAS do grafo
    - params: {entity_id, relation_filter? (ex: REMETE_A), limit?}
    - Diferente de neighbors (co-ocorrência): percorre relações reais do grafo
    - Ex: "Quais artigos o Art. 5 CF referencia diretamente?"

12. **entity_stats** - Estatísticas gerais do grafo (contagens por tipo, tipos de relação)
    - params: {} (nenhum obrigatório)
    - Retorna visão geral: total de entidades, distribuição por tipo, tipos de relação
    - Ex: "Quantas entidades existem no grafo?" / "Qual o tamanho do grafo?"

**GDS (Graph Data Science) - Algoritmos Avançados:**

13. **betweenness_centrality** - Identifica nós-ponte (conectam áreas distintas)
    - params: {entity_type?, limit?}
    - Calcula betweenness centrality: nós que aparecem em muitos caminhos curtos
    - Útil para: "Artigos que conectam direito civil e tributário"
    - Ex: "Quais artigos servem de ponte entre temas diferentes?"

14. **community_detection** - Detecta comunidades temáticas (Louvain)
    - params: {entity_type?, limit?}
    - Agrupa entidades por conexões implícitas (clusters automáticos)
    - Útil para: "Agrupar artigos por tema sem rotular manualmente"
    - Ex: "Quais são as comunidades de artigos no grafo?"

15. **node_similarity** - Encontra entidades similares (vizinhos compartilhados)
    - params: {entity_type?, entity_id?, top_k?, limit?}
    - Calcula similaridade baseada em conexões compartilhadas
    - Útil para: "Decisões parecidas com X", "Artigos relacionados a Y"
    - Ex: "Quais decisões são similares ao Acórdão 123?"

16. **pagerank_personalized** - Ranking de importância com viés (sementes)
    - params: {source_ids (array), entity_type?, limit?}
    - PageRank personalizado: nós mais relevantes a partir de sementes
    - Útil para: "Artigos mais importantes conectados à CF/88 Art. 5"
    - Ex: "Qual a rede de influência a partir desses 3 artigos?"

17. **weakly_connected_components** - Componentes desconectados (ilhas)
    - params: {entity_type?, limit?}
    - Identifica subgrafos isolados (WCC)
    - Útil para: "Existem artigos órfãos?", "Quais ilhas no grafo?"
    - Ex: "Há temas isolados sem conexão com jurisprudência?"

18. **shortest_path_weighted** - Caminho mais curto ponderado (Dijkstra)
    - params: {source_id, target_id, weight_property?, direction?, limit?}
    - Dijkstra com pesos personalizados (ex: co-ocorrência, relevância)
    - direction: "OUTGOING" (padrão), "INCOMING", "BOTH"
    - Útil para: "Caminho mais forte entre Art. X e Súmula Y"
    - Ex: "Qual o caminho com maior co-ocorrência entre esses 2 artigos?"

19. **triangle_count** - Contagem de triângulos (clustering)
    - params: {entity_type?, limit?}
    - Conta triângulos: nós com alto clustering coefficient
    - Útil para: "Artigos mais interligados em grupos", "Núcleos densos"
    - Ex: "Quais artigos formam triângulos (rede densa)?"

20. **degree_centrality** - Centralidade por grau (conexões diretas)
    - params: {entity_type?, direction?, limit?}
    - Conta conexões diretas (in-degree, out-degree ou total)
    - direction: "OUTGOING" (mais citações), "INCOMING" (mais citado), "BOTH" (total)
    - Útil para: "Artigos mais citados", "Artigos que mais citam"
    - Ex: "Quais súmulas são mais referenciadas?"

**GDS Fase 1 - Prioridade Máxima:**

21. **closeness_centrality** - Centralidade por proximidade
    - params: {entity_type?, limit?}
    - Mede distância média de um nó a todos os outros
    - Nós com maior closeness são "hubs" de acesso rápido
    - Útil para: "Artigos que conectam rapidamente toda a rede"
    - Ex: "Quais artigos estão mais perto de todos os outros?"

22. **eigenvector_centrality** - Centralidade por conexões importantes
    - params: {entity_type?, limit?, max_iterations?}
    - Similar ao PageRank, mas sem damping factor
    - Mede importância baseada em conexões com outros nós importantes (recursivo)
    - Útil para: "Artigos centrais em redes de prestígio"
    - Ex: "Quais artigos são conectados a outros artigos importantes?"

23. **leiden** - Detecção de comunidades (sucessor do Louvain)
    - params: {entity_type?, limit?}
    - Agrupa nós em comunidades maximizando modularidade
    - Melhor qualidade de particionamento que Louvain
    - Útil para: "Descobrir clusters temáticos no grafo jurídico"
    - Ex: "Quais grupos de artigos formam temas coesos?"

24. **k_core_decomposition** - Núcleos densos (k-core)
    - params: {entity_type?, limit?}
    - Identifica subgrafos onde cada nó tem pelo menos k conexões
    - coreValue maior = nó em núcleos mais densos/coesos
    - Útil para: "Identificar clusters fortemente conectados"
    - Ex: "Quais artigos estão em núcleos altamente interconectados?"

25. **knn** - K-Nearest Neighbors (vizinhos mais similares)
    - params: {entity_type?, top_k?, limit?}

25. **adamic_adar** - Predição de links via vizinhos comuns ponderados
    - params: {node1_id, node2_id}
    - Calcula score de "força" de ligação potencial entre dois nós
    - Vizinhos comuns raros = score mais alto (mais indicativo de link)
    - Útil para: "Qual a probabilidade de Art. X e Art. Y estarem relacionados?"
    - Ex: "Score de conexão potencial entre Art. 5º CF e Art. 93 Lei 8.213"

26. **node2vec** - Embeddings vetoriais para machine learning
    - params: {entity_type?, embedding_dimension?, iterations?, limit?}
    - Gera vetores (embeddings) de nós via random walks
    - embedding_dimension: tamanho do vetor (padrão 128)
    - Útil para: similaridade, classificação, clustering de entidades
    - Ex: "Gerar embeddings de artigos da CF para análise de similaridade"

27. **all_pairs_shortest_path** - Matriz de distâncias completa
    - params: {entity_type?, limit?}
    - Calcula caminho mais curto entre TODOS os pares de nós
    - Pode retornar muitos pares (limit alto recomendado: 1000+)
    - Útil para: análise de conectividade global, grafos de distâncias
    - Ex: "Matriz de distâncias entre todos os artigos da Lei 8.112"

28. **harmonic_centrality** - Closeness robusta para grafos desconectados
    - params: {entity_type?, limit?}
    - Variante de closeness que funciona em grafos com componentes desconexos
    - Usa média harmônica (distância infinita → contribuição 0)
    - Útil para: "Artigos mais centrais mesmo em grafo fragmentado"
    - Ex: "Quais artigos são mais centrais considerando componentes isolados?"
    - Encontra os top-K nós mais similares a cada nó
    - Baseado em similaridade de vizinhança
    - Útil para: "Recomendações e descoberta de entidades relacionadas"
    - Ex: "Quais artigos são mais similares entre si por suas conexões?"

**GDS Fase 2 - Casos Específicos:**

26. **bridges** - Identifica arestas críticas (pontes)
    - params: {entity_type?, limit?}
    - Detecta arestas cuja remoção desconecta o grafo (bridge edges)
    - Útil para: "Quais relações são indispensáveis para conectividade?"
    - Ex: "Quais conexões, se removidas, isolam partes do grafo jurídico?"

27. **articulation_points** - Identifica nós críticos (pontos de articulação)
    - params: {entity_type?, limit?}
    - Detecta nós cuja remoção aumenta componentes desconexos
    - Útil para: "Quais artigos são pontos únicos de falha?"
    - Ex: "Sem quais artigos a rede jurídica se fragmenta?"

28. **strongly_connected_components** - Detecta ciclos de referência mútua (SCCs)
    - params: {entity_type?, limit?}
    - Identifica subgrafos onde qualquer nó alcança qualquer outro (direcionado)
    - Útil para: "Quais artigos formam ciclos de citação mútua?"
    - Ex: "Artigos que se referenciam mutuamente (Art. A → B → C → A)?"

29. **yens_k_shortest_paths** - K caminhos alternativos mais curtos (Yen)
    - params: {source_id, target_id, k?, entity_type?}
    - Retorna múltiplos caminhos (não apenas 1) entre dois nós
    - k: número de caminhos alternativos (padrão 3, máx 10)
    - Útil para: "Quais são as 3 rotas mais curtas entre Art. X e Art. Y?"
    - Ex: "Existem caminhos alternativos entre Lei 14.133 e Súmula 331?"

**Tipos de entidade válidos:**
lei, artigo, sumula, tema, tribunal, tese, conceito, principio, instituto

**IMPORTANTE:**
- Para perguntas complexas ou agregações que não se encaixam nas operações 1-28, use text2cypher (operação 8)
- Operações GDS (13-28) requerem NEO4J_GDS_ENABLED=true e plugin GDS instalado""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["path", "neighbors", "cooccurrence", "search", "count", "link_entities", "discover_hubs", "text2cypher", "legal_chain", "precedent_network", "related_entities", "entity_stats", "betweenness_centrality", "community_detection", "node_similarity", "pagerank_personalized", "weakly_connected_components", "shortest_path_weighted", "triangle_count", "degree_centrality", "closeness_centrality", "eigenvector_centrality", "leiden", "k_core_decomposition", "knn", "bridges", "articulation_points", "strongly_connected_components", "yens_k_shortest_paths", "adamic_adar", "node2vec", "all_pairs_shortest_path", "harmonic_centrality"],
                "description": "Operação a executar no grafo"
            },
            "params": {
                "type": "object",
                "description": "Parâmetros específicos da operação",
                "properties": {
                    "source_id": {
                        "type": "string",
                        "description": "Entity ID de origem (para path/link_entities/legal_chain)"
                    },
                    "target_id": {
                        "type": "string",
                        "description": "Entity ID de destino (para path/link_entities/legal_chain, opcional em legal_chain)"
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "Entity ID (para neighbors/related_entities)"
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
                    },
                    "relation_type": {
                        "type": "string",
                        "description": "Tipo de relação para link_entities (ex: INTERPRETA, REMETE_A, APLICA_SUMULA)"
                    },
                    "confirm": {
                        "type": "boolean",
                        "default": False,
                        "description": "Para link_entities: se true, confirma a escrita no grafo (sem isso o servidor pode responder em modo preflight)."
                    },
                    "preflight_token": {
                        "type": "string",
                        "description": "Token assinado retornado no preflight. Obrigatório quando confirm=true."
                    },
                    "top_n": {
                        "type": "integer",
                        "default": 10,
                        "description": "Quantidade de hubs a retornar por categoria (para discover_hubs, máx 50)"
                    },
                    "question": {
                        "type": "string",
                        "description": "Pergunta em linguagem natural (para text2cypher)"
                    },
                    "decision_id": {
                        "type": "string",
                        "description": "Entity ID da decisão (para precedent_network)"
                    },
                    "relation_filter": {
                        "type": "string",
                        "description": "Filtrar por tipo de relação (para related_entities, ex: REMETE_A, INTERPRETA)"
                    },
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de entity IDs sementes (para pagerank_personalized)"
                    },
                    "weight_property": {
                        "type": "string",
                        "description": "Nome da propriedade de peso nas arestas (para shortest_path_weighted, ex: 'cooccurrence_count')"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["OUTGOING", "INCOMING", "BOTH"],
                        "default": "BOTH",
                        "description": "Direção das arestas (para shortest_path_weighted, degree_centrality)"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 10,
                        "description": "Top K resultados (para node_similarity, knn)"
                    },
                    "k": {
                        "type": "integer",
                        "default": 3,
                        "description": "Número de caminhos alternativos (para yens_k_shortest_paths, máx 10)"
                    },
                    "node1_id": {
                        "type": "string",
                        "description": "Primeiro nó (para adamic_adar)"
                    },
                    "node2_id": {
                        "type": "string",
                        "description": "Segundo nó (para adamic_adar)"
                    },
                    "embedding_dimension": {
                        "type": "integer",
                        "default": 128,
                        "description": "Dimensão dos embeddings (para node2vec, padrão 128)"
                    },
                    "iterations": {
                        "type": "integer",
                        "default": 10,
                        "description": "Número de iterações (para node2vec, padrão 10)"
                    },
                    "properties": {
                        "type": "object",
                        "description": (
                            "Propriedades adicionais da relação (opcional). "
                            "Campos de auditoria (source, layer, verified, created_by, created_via) "
                            "são geridos pelo servidor e não podem ser sobrescritos."
                        )
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
# GRAPH RISK / AUDIT TOOLS (READ-ONLY, deterministic)
# =============================================================================

SCAN_GRAPH_RISK_TOOL = UnifiedTool(
    name="scan_graph_risk",
    description="""Executa um scan determinístico de risco/fraude no grafo (multi-cenário) e retorna sinais ranqueados.

Use quando o usuário pedir: "descobrir fraudes", "auditar conexões", "sinais de risco", "todos os cenários".

Perfis:
- precision: menos falsos positivos (thresholds mais altos, menos candidates)
- balanced: default
- recall: mais cobertura (inclui candidates, thresholds mais baixos)

Retorna:
- signals[] com score, entidades foco e evidências (co-menções e/ou arestas existentes)
- report_id quando persist=true (histórico por 30 dias)
""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "profile": {"type": "string", "enum": ["precision", "balanced", "recall"], "default": "balanced"},
            "scenarios": {"type": "array", "items": {"type": "string"}, "description": "Lista de cenários (omitir = todos)"},
            "include_candidates": {"type": "boolean", "description": "Override do include_candidates"},
            "limit": {"type": "integer", "default": 30, "description": "Max sinais por detector (1-200)"},
            "min_shared_docs": {"type": "integer", "default": 2, "description": "Threshold de co-menções (1-20)"},
            "max_hops": {"type": "integer", "default": 4, "description": "Para auditorias/cadeias (1-6)"},
            "scope": {"type": "string", "enum": ["global", "private", "local"], "description": "Escopo (group bloqueado)"},
            "include_global": {"type": "boolean", "default": True, "description": "Inclui corpus global além do tenant"},
            "case_id": {"type": "string", "description": "Filtro por caso (quando scope=local)"},
            "persist": {"type": "boolean", "default": True, "description": "Persistir relatório por 30 dias"},
        },
    },
)


AUDIT_GRAPH_EDGE_TOOL = UnifiedTool(
    name="audit_graph_edge",
    description="""Audita a relação entre duas entidades: arestas diretas + co-menções (chunks/docs).

Use quando o usuário pedir: "qual a evidência", "mostre o trecho", "tem ligação direta?", "audite esse link".
""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "source_id": {"type": "string", "description": "Entity ID origem"},
            "target_id": {"type": "string", "description": "Entity ID destino"},
            "include_candidates": {"type": "boolean", "default": False},
            "limit_docs": {"type": "integer", "default": 5, "description": "Max docs/chunks amostrados (1-20)"},
            "scope": {"type": "string", "enum": ["global", "private", "local"]},
            "include_global": {"type": "boolean", "default": True},
            "case_id": {"type": "string"},
        },
        "required": ["source_id", "target_id"],
    },
)


AUDIT_GRAPH_CHAIN_TOOL = UnifiedTool(
    name="audit_graph_chain",
    description="""Audita caminho(s) entre duas entidades (multi-hop) com tipos de relação e evidências quando disponíveis.

Use quando o usuário pedir: "cadeia entre X e Y", "como conecta?", "mostre o caminho".
""",
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
    requires_context=True,
    parameters={
        "type": "object",
        "properties": {
            "source_id": {"type": "string", "description": "Entity ID origem"},
            "target_id": {"type": "string", "description": "Entity ID destino"},
            "max_hops": {"type": "integer", "default": 4, "description": "Max hops (1-6)"},
            "include_candidates": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "default": 5, "description": "Max caminhos (1-20)"},
            "scope": {"type": "string", "enum": ["global", "private", "local"]},
            "include_global": {"type": "boolean", "default": True},
            "case_id": {"type": "string"},
        },
        "required": ["source_id", "target_id"],
    },
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
    SEARCH_JUSBRASIL_TOOL,
    SEARCH_LEGISLACAO_TOOL,
    VERIFY_CITATION_TOOL,
    VALIDATE_CPC_COMPLIANCE_TOOL,
    SEARCH_RAG_TOOL,
    CREATE_SECTION_TOOL,
    # Graph
    ASK_GRAPH_TOOL,
    SCAN_GRAPH_RISK_TOOL,
    AUDIT_GRAPH_EDGE_TOOL,
    AUDIT_GRAPH_CHAIN_TOOL,
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
