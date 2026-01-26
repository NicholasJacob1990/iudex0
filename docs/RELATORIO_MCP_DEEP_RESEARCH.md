# Relatório: Integração de Deep Research com MCP (Model Context Protocol)

> Gerado em: 2026-01-24

## 2025-2026: Estado da Arte e Oportunidades para o Iudex

---

## 1. Panorama do MCP em 2025-2026

### 1.1 O que é o MCP

O [Model Context Protocol (MCP)](https://en.wikipedia.org/wiki/Model_Context_Protocol) é um padrão aberto introduzido pela Anthropic em novembro de 2024 que padroniza a integração entre LLMs e ferramentas/dados externos. Utiliza mensagens JSON-RPC 2.0 para comunicação entre:

- **Hosts**: Aplicações LLM que iniciam conexões
- **Clients**: Conectores dentro da aplicação host
- **Servers**: Serviços que fornecem contexto e capacidades

### 1.2 Adoção Massiva

Em 2025, o MCP tornou-se o padrão de facto para integração de IA:

- **Março 2025**: OpenAI adotou oficialmente o MCP
- **Maio 2025**: Google anunciou suporte nativo no Gemini SDK (I/O 2025)
- **Dezembro 2025**: Anthropic doou o MCP para a [Agentic AI Foundation (AAIF)](https://thenewstack.io/why-the-model-context-protocol-won/) sob a Linux Foundation
- **2026**: Mercado projetado para $1.8B, com expansão para multimídia (imagens, vídeo, áudio)

### 1.3 Primitivas do MCP

De acordo com a [especificação 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25):

| Primitiva | Direção | Descrição |
|-----------|---------|-----------|
| **Resources** | Server -> Client | Dados somente-leitura (arquivos, DBs, APIs) |
| **Tools** | Server -> Client | Funções executáveis pelo modelo |
| **Prompts** | Server -> Client | Templates de instrução |
| **Sampling** | Client -> Server | Requisições de inferência LLM |
| **Elicitation** | Server -> Client | Requisições de informação ao usuário |

---

## 2. OpenAI + MCP

### 2.1 Responses API com MCP

A [documentação da OpenAI](https://platform.openai.com/docs/guides/tools-connectors-mcp) mostra integração nativa:

```json
{
  "model": "gpt-4.1",
  "tools": [
    {
      "type": "mcp",
      "server_label": "legal_knowledge",
      "server_url": "https://mcp.iudex.app/sse",
      "allowed_tools": ["search_legislation", "search_jurisprudence"],
      "require_approval": "never"
    }
  ]
}
```

### 2.2 Deep Research API + MCP

Lançado em [junho de 2025](https://openai.com/index/introducing-deep-research/), o Deep Research API permite:

```python
from agents import Agent, HostedMCPTool, WebSearchTool

research_agent = Agent(
    name="Research Agent",
    model="o3-deep-research-2025-06-26",
    tools=[
        WebSearchTool(),
        HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "file_search",
                "server_url": "https://mcp.example.com/sse",
                "require_approval": "never",
            }
        )
    ]
)
```

Conforme o [OpenAI Cookbook](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents), a arquitetura usa 4 agentes:
1. **Triage Agent** - Avalia queries
2. **Clarifier Agent** - Solicita contexto
3. **Instruction Builder Agent** - Gera briefings
4. **Research Agent** - Executa pesquisa com MCP + Web Search

### 2.3 Custo e Transporte

- Sem taxa adicional por tool call - apenas tokens consumidos
- Suporta transporte Streamable HTTP e SSE
- Caching automático de tool definitions com `previous_response_id`

---

## 3. Anthropic Claude + MCP

### 3.1 Claude Code e MCP Tool Search

A partir de [janeiro 2025](https://analyticsindiamag.com/ai-news-updates/claude-code-finally-fixes-the-huge-issue-with-mcps/), o Claude Code implementou **MCP Tool Search**:

> "Claude Code detecta quando suas descrições de ferramentas MCP usariam mais de 10% do contexto... ferramentas são carregadas via busca em vez de pré-carregadas."

### 3.2 Suporte a Servidores Remotos

Desde [março 2025](https://www.infoq.com/news/2025/06/anthropic-claude-remote-mcp/), Claude Code suporta servidores MCP remotos via Streamable HTTP.

### 3.3 Skills como RAG para Ferramentas

As [Skills do Claude](https://claude.com/blog/skills-explained) funcionam como RAG para procedimentos:

> "Em RAG, você não coloca toda a base de conhecimento no contexto. Armazena separadamente, usa um índice para recuperar o relevante. Skills fazem o mesmo para ferramentas e conhecimento procedural."

---

## 4. Google Gemini + MCP

### 4.1 Suporte Oficial (Dezembro 2025)

O [Google Cloud anunciou](https://cloud.google.com/blog/products/ai-machine-learning/announcing-official-mcp-support-for-google-services) servidores MCP gerenciados:

**Serviços disponíveis no lançamento:**
- Google Maps
- BigQuery
- Compute Engine
- Kubernetes Engine

**Planejados para 2026:**
- Cloud Run, Cloud Storage
- AlloyDB, Cloud SQL, Spanner
- Looker, Pub/Sub, Dataplex

### 4.2 Gemini CLI + MCP

O [Gemini CLI](https://geminicli.com/docs/tools/mcp-server/) suporta MCP via `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "legal-rag": {
      "command": "uvx",
      "args": ["mcp-server-legal-rag"]
    }
  }
}
```

---

## 5. MCP Servers para RAG e Vector Search

### 5.1 Qdrant MCP Server (Oficial)

O [mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) (v0.6.0, março 2025):

```bash
uvx mcp-server-qdrant \
  --qdrant-url http://localhost:6333 \
  --collection-name legal_docs \
  --embedding-model text-embedding-3-large \
  --transport sse
```

**Ferramentas expostas:**
- `qdrant-store`: Armazena documentos com embeddings
- `qdrant-find`: Busca semântica por query natural

### 5.2 OpenSearch MCP Server

O [OpenSearch 3.0](https://opensearch.org/blog/introducing-mcp-in-opensearch/) inclui MCP nativo:

- Suporte a GPU (Nvidia cuVS) com 9.3x speedup
- Autenticação enterprise integrada
- Busca vetorial e analytics unificados

**MCP de terceiros**: [elasticsearch-mcp-server](https://github.com/cr7258/elasticsearch-mcp-server) suporta ES 7.x/8.x/9.x e OpenSearch.

### 5.3 Neo4j GraphRAG MCP

O [Neo4j GraphRAG MCP](https://neo4j.com/blog/developer/neo4j-graphrag-retrievers-as-mcp-server/) combina busca vetorial com Cypher:

```python
from neo4j_graphrag.retrievers import VectorCypherRetriever

retriever = VectorCypherRetriever(
    driver=driver,
    index_name="legal_chunks",
    embedder=init_embeddings("openai:text-embedding-3-large"),
    retrieval_query="MATCH (n)-[:CITA]->(lei) RETURN n, lei"
)
```

---

## 6. MCP Servers para Contexto Jurídico

### 6.1 Legal-MCP

O [legal-mcp](https://github.com/agentic-ops/legal-mcp) oferece:

- Integração com PACER, Westlaw, LexisNexis
- Gerenciamento de casos e prazos
- Análise de documentos e contratos
- Verificação de citações legais
- Suporte multi-jurisdicional

### 6.2 Cerebra Legal MCP

O [cerebra-legal](https://github.com/yoda-digital/mcp-cerebra-legal-server) fornece:

- `legal_think`: Raciocínio estruturado jurídico
- `legal_ask_followup_question`: Perguntas de esclarecimento
- `legal_attempt_completion`: Formatação de análises com citações

Detecta automaticamente domínios: contestação ANSC, proteção ao consumidor, análise contratual.

### 6.3 PJE MCP Server

Existe um servidor MCP para o sistema [PJE brasileiro](https://glama.ai/mcp/servers/categories/legal-and-compliance) com suporte a certificados digitais A1 e A3.

---

## 7. Análise do Iudex: Estado Atual e Oportunidades

### 7.1 Arquitetura Atual de Deep Research

Analisando `/apps/api/app/services/ai/deep_research_service.py`:

**Providers suportados:**
- Google GenAI (deep-research-pro-preview-12-2025, gemini-3-flash)
- Perplexity Sonar Deep Research

**Limitações atuais:**
- Sem integração MCP - depende apenas de web search externa
- Cache local por query string
- Não acessa bases internas (Qdrant/OpenSearch) durante deep research

### 7.2 Arquitetura Atual de RAG

Analisando `/apps/api/app/services/rag/`:

**Componentes:**
- **OpenSearch**: Busca lexical BM25 (índices: lei, juris, pecas, doutrina, sei, local)
- **Qdrant**: Busca vetorial (text-embedding-3-large, 3072 dims)
- **Neo4j**: Grafo de conhecimento jurídico (opcional)
- **CRAG Gate**: Controle de qualidade com retry
- **Reranker**: Cross-encoder multilingual

**Pipeline:**
```
Query -> Lexical -> Vector (condicional) -> RRF Merge
     -> CRAG Gate -> Rerank -> Expand -> Compress
     -> Graph Enrich -> Trace -> Response
```

### 7.3 Gap: Deep Research sem Acesso a Dados Internos

Atualmente, quando o Deep Research executa:
1. Faz web search (Google/Perplexity)
2. NÃO consulta bases internas do caso (documentos SEI, perícias, etc.)
3. NÃO consulta base jurídica local (legislação, jurisprudência indexada)

**Resultado**: Pesquisa genérica sem contexto do processo específico.

---

## 8. Proposta de Integração MCP para o Iudex

### 8.1 MCP Servers a Implementar

#### 8.1.1 `iudex-rag-mcp` - Acesso ao RAG Pipeline

```python
# apps/api/mcp_servers/rag_server.py
from fastmcp import FastMCP

mcp = FastMCP("iudex-rag")

@mcp.tool()
async def search_legislation(query: str, top_k: int = 10) -> list[dict]:
    """Busca legislação relevante (leis, decretos, resoluções)."""
    from app.services.rag.pipeline.rag_pipeline import RAGPipeline
    pipeline = RAGPipeline()
    results = await pipeline.search(
        query=query,
        indices=["rag-lei"],
        top_k=top_k
    )
    return [{"text": r.text, "source": r.metadata} for r in results]

@mcp.tool()
async def search_jurisprudence(query: str, courts: list[str] = None) -> list[dict]:
    """Busca jurisprudência (STF, STJ, TRFs, TJs)."""
    ...

@mcp.tool()
async def search_doctrine(query: str) -> list[dict]:
    """Busca doutrina jurídica indexada."""
    ...

@mcp.tool()
async def search_case_documents(case_id: str, query: str) -> list[dict]:
    """Busca documentos do processo específico (SEI, perícias, etc.)."""
    ...
```

#### 8.1.2 `iudex-graph-mcp` - Acesso ao Knowledge Graph

```python
@mcp.tool()
async def get_legal_entity(entity_id: str) -> dict:
    """Obtém entidade jurídica (lei, artigo, súmula, parte)."""
    from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
    neo4j = get_neo4j_mvp()
    return await neo4j.get_entity(entity_id)

@mcp.tool()
async def find_related_laws(article_ref: str, hops: int = 2) -> list[dict]:
    """Encontra leis relacionadas a um artigo."""
    ...

@mcp.tool()
async def get_citation_chain(sumula_num: str) -> list[dict]:
    """Obtém cadeia de citações de uma súmula."""
    ...
```

#### 8.1.3 `iudex-case-mcp` - Contexto do Processo

```python
@mcp.tool()
async def get_case_summary(case_id: str) -> dict:
    """Obtém resumo do caso (partes, pedidos, valores)."""
    ...

@mcp.tool()
async def get_case_timeline(case_id: str) -> list[dict]:
    """Obtém linha do tempo processual."""
    ...

@mcp.tool()
async def get_expert_reports(case_id: str) -> list[dict]:
    """Obtém laudos periciais do processo."""
    ...
```

### 8.2 Modificação do Deep Research Service

```python
# Proposta de modificação em deep_research_service.py

async def run_research_with_mcp(
    self,
    query: str,
    case_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> DeepResearchResult:
    """
    Deep Research com acesso a dados internos via MCP.
    """
    # 1. Buscar contexto interno primeiro
    internal_context = ""
    if case_id:
        # Documentos do caso via MCP
        case_docs = await self.mcp_client.call_tool(
            "iudex-case-mcp",
            "search_case_documents",
            {"case_id": case_id, "query": query}
        )
        internal_context += self._format_case_docs(case_docs)

    # Legislação relevante via MCP
    laws = await self.mcp_client.call_tool(
        "iudex-rag-mcp",
        "search_legislation",
        {"query": query, "top_k": 5}
    )
    internal_context += self._format_laws(laws)

    # Jurisprudência via MCP
    juris = await self.mcp_client.call_tool(
        "iudex-rag-mcp",
        "search_jurisprudence",
        {"query": query}
    )
    internal_context += self._format_jurisprudence(juris)

    # 2. Enriquecer query com contexto interno
    enriched_query = f"""
    ## Contexto do Processo e Base Jurídica:
    {internal_context}

    ## Pergunta de Pesquisa:
    {query}

    Realize pesquisa aprofundada considerando o contexto acima.
    """

    # 3. Executar deep research (Google/Perplexity) com query enriquecida
    return await self.run_research_task(enriched_query, config)
```

### 8.3 Integração com OpenAI Deep Research API

Para usar o [Deep Research API da OpenAI](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents):

```python
# Novo provider em deep_research_service.py

async def _run_openai_deep_research(
    self,
    query: str,
    case_id: Optional[str] = None
) -> DeepResearchResult:
    """
    Deep Research via OpenAI com MCP para dados internos.
    """
    from agents import Agent, HostedMCPTool, WebSearchTool

    tools = [
        WebSearchTool(),
        # MCP Server do Iudex para RAG
        HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "iudex_rag",
                "server_url": os.getenv("IUDEX_MCP_URL", "https://api.iudex.app/mcp/sse"),
                "allowed_tools": [
                    "search_legislation",
                    "search_jurisprudence",
                    "search_doctrine"
                ],
                "require_approval": "never",
            }
        ),
    ]

    # Adicionar MCP do caso se especificado
    if case_id:
        tools.append(
            HostedMCPTool(
                tool_config={
                    "type": "mcp",
                    "server_label": "iudex_case",
                    "server_url": f"https://api.iudex.app/mcp/case/{case_id}/sse",
                    "allowed_tools": ["search_case_documents", "get_case_summary"],
                    "require_approval": "never",
                }
            )
        )

    research_agent = Agent(
        name="Legal Research Agent",
        model="o3-deep-research-2025-06-26",
        instructions=LEGAL_RESEARCH_INSTRUCTIONS,
        tools=tools
    )

    result = await research_agent.run(query)
    return self._parse_openai_result(result)
```

---

## 9. Roadmap de Implementação

### Fase 1: MVP (2-3 semanas)

| Tarefa | Esforço | Prioridade |
|--------|---------|------------|
| Criar `iudex-rag-mcp` com FastMCP | 3 dias | Alta |
| Expor search_legislation, search_jurisprudence | 2 dias | Alta |
| Integrar com deep_research_service.py | 2 dias | Alta |
| Testes com Claude Desktop | 1 dia | Média |
| Deploy como endpoint SSE | 2 dias | Alta |

**Dependências:**
```bash
pip install fastmcp>=2.0
```

### Fase 2: Integração Completa (3-4 semanas)

| Tarefa | Esforço | Prioridade |
|--------|---------|------------|
| Criar `iudex-case-mcp` para documentos do processo | 3 dias | Alta |
| Criar `iudex-graph-mcp` para Neo4j | 3 dias | Média |
| Integrar com OpenAI Deep Research API | 4 dias | Alta |
| Implementar autenticação (OAuth2/API Keys) | 3 dias | Alta |
| Streaming de progresso via SSE | 2 dias | Média |
| Observabilidade (OpenTelemetry) | 2 dias | Média |

### Fase 3: Otimização (2-3 semanas)

| Tarefa | Esforço | Prioridade |
|--------|---------|------------|
| MCP Tool Search (carregar tools sob demanda) | 3 dias | Média |
| Caching de tool definitions | 2 dias | Média |
| Rate limiting por usuário/case | 2 dias | Alta |
| Integração com Gemini CLI | 2 dias | Baixa |
| Métricas de uso e custo | 2 dias | Média |

---

## 10. Considerações de Segurança

### 10.1 Riscos Identificados

Pesquisa da Knostic (julho 2025) encontrou [falhas críticas](https://www.theregister.com/2026/01/20/anthropic_prompt_injection_flaws/):

- 2.000 servidores MCP expostos sem autenticação
- Vulnerabilidades de prompt injection no mcp-server-git

### 10.2 Recomendações para o Iudex

1. **Autenticação Obrigatória**: Usar OAuth2 ou API Keys em todos os endpoints MCP
2. **Validação de Input**: Sanitizar queries antes de enviar ao RAG
3. **Rate Limiting**: Limitar chamadas por usuário/processo
4. **Audit Logging**: Registrar todas as tool calls
5. **Escopo Mínimo**: Usar `allowed_tools` para limitar ferramentas expostas
6. **TLS Obrigatório**: Apenas HTTPS para endpoints remotos

---

## 11. Conclusão

### Benefícios da Integração MCP

1. **Deep Research Contextualizado**: Pesquisa web + dados internos do caso
2. **Interoperabilidade**: Claude, GPT e Gemini acessando mesmas ferramentas
3. **Padrão de Mercado**: Alinhamento com tendência da indústria
4. **Extensibilidade**: Fácil adição de novas fontes (PJE, tribunais, etc.)

### Próximos Passos Recomendados

1. **Imediato**: Criar `iudex-rag-mcp` com FastMCP
2. **Curto Prazo**: Integrar ao Deep Research Service existente
3. **Médio Prazo**: Adicionar OpenAI Deep Research API como provider
4. **Longo Prazo**: Expor MCP público para integração com ferramentas externas

---

## Fontes

- [Model Context Protocol - Wikipedia](https://en.wikipedia.org/wiki/Model_Context_Protocol)
- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [One Year of MCP: November 2025 Spec Release](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)
- [OpenAI Connectors and MCP servers](https://platform.openai.com/docs/guides/tools-connectors-mcp)
- [Guide to Using the Responses API's MCP Tool](https://cookbook.openai.com/examples/mcp/mcp_tool_guide)
- [Deep Research API with the Agents SDK](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents)
- [OpenAI Agents SDK - MCP](https://openai.github.io/openai-agents-python/mcp/)
- [Introducing deep research | OpenAI](https://openai.com/index/introducing-deep-research/)
- [Claude Code Gets Support for Remote MCP Servers](https://thenewstack.io/anthropics-claude-code-gets-support-for-remote-mcp-servers/)
- [Skills explained | Claude](https://claude.com/blog/skills-explained)
- [Google Cloud Announces MCP Support](https://cloud.google.com/blog/products/ai-machine-learning/announcing-official-mcp-support-for-google-services)
- [Gemini CLI MCP Servers](https://geminicli.com/docs/tools/mcp-server/)
- [Qdrant MCP Server](https://github.com/qdrant/mcp-server-qdrant)
- [OpenSearch MCP Server](https://opensearch.org/blog/introducing-mcp-in-opensearch/)
- [Neo4j GraphRAG MCP Server](https://neo4j.com/blog/developer/neo4j-graphrag-retrievers-as-mcp-server/)
- [Legal-MCP](https://github.com/agentic-ops/legal-mcp)
- [Cerebra Legal MCP Server](https://github.com/yoda-digital/mcp-cerebra-legal-server)
- [FastMCP Documentation](https://gofastmcp.com/tutorials/create-mcp-server)
- [FastMCP GitHub](https://github.com/jlowin/fastmcp)
- [elasticsearch-mcp-server](https://github.com/cr7258/elasticsearch-mcp-server)
- [MCP vs RAG | Contentful](https://www.contentful.com/blog/mcp-vs-rag/)
