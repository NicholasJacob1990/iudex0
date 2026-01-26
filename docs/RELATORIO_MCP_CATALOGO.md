# Relatório: MCP (Model Context Protocol) - Catálogo de Servers 2025-2026

> Gerado em: 2026-01-24

## Sumário Executivo

O Model Context Protocol (MCP) é um padrão aberto introduzido pela Anthropic em novembro de 2024 que padroniza como modelos de IA interagem com ferramentas externas, sistemas e fontes de dados. Em dezembro de 2025, a Anthropic doou o MCP para a Agentic AI Foundation (AAIF), uma fundação dirigida sob a Linux Foundation, co-fundada por Anthropic, Block e OpenAI.

---

## 1. Registro Oficial e Ecossistema

### [Registro Oficial MCP](https://registry.modelcontextprotocol.io/)

O registro oficial foi lançado em preview em setembro de 2025 e serve como fonte única de verdade para servidores MCP disponíveis. Atualmente conta com quase 2.000 servidores registrados, representando um crescimento de 407% desde o lançamento.

**Características:**
- API pública para busca de servidores
- Suporte para sub-registros privados/internos
- Neutralidade de vendor
- Código aberto (OpenAPI specification)

### Principais Diretórios

| Diretório | URL | Servidores |
|-----------|-----|------------|
| [PulseMCP](https://www.pulsemcp.com/servers) | pulsemcp.com | 7.900+ |
| [Glama](https://glama.ai/mcp/servers) | glama.ai | ~10.000 |
| [MCP.so](https://mcp.so) | mcp.so | - |

---

## 2. Servidores Oficiais de Referência

Mantidos pelo MCP Steering Group em [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers):

| Servidor | Descrição |
|----------|-----------|
| **Everything** | Servidor de teste/referência com prompts, resources e tools |
| **Fetch** | Busca e conversão de conteúdo web |
| **Filesystem** | Operações seguras de arquivos |
| **Git** | Leitura, busca e manipulação de repositórios Git |
| **Memory** | Sistema de memória persistente baseado em knowledge graph |
| **Sequential Thinking** | Resolução de problemas por sequências de pensamento |
| **Time** | Conversão de tempo e fusos horários |

---

## 3. Catálogo de MCP Servers Relevantes para o Iudex

### 3.1 Vector Stores (RAG)

| Servidor | Repositório | Características |
|----------|-------------|-----------------|
| **Qdrant** (Oficial) | [qdrant/mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) | Tools: `qdrant-store`, `qdrant-find`. Suporta FastEmbed. MIT License. |
| **Pinecone** (Oficial) | [@pinecone-database/mcp](https://www.pinecone.io/blog/first-MCPs/) | Tools: search, upsert, rerank, cascading-search. Requer Node.js. |
| **Weaviate** (Oficial) | [weaviate/mcp-server-weaviate](https://github.com/weaviate/mcp-server-weaviate) | Hybrid search, inserção de objetos. |
| **ChromaDB** (Oficial) | [chroma-core/chroma-mcp](https://github.com/chroma-core/chroma-mcp) | Suporta ephemeral, persistent e cloud. Python. |

### 3.2 Bancos de Dados

| Servidor | Repositório | Notas |
|----------|-------------|-------|
| **PostgreSQL** | [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) | Read/write, análise de performance, recomendações de índices. |
| **SQLite** | Deprecado/Arquivado | Tinha vulnerabilidade SQL Injection. Usar alternativas. |
| **Neo4j** (Knowledge Graph) | [neo4j-contrib/mcp-neo4j](https://github.com/neo4j-contrib/mcp-neo4j) | Cypher queries, memory server, data modeling. |
| **Elasticsearch/OpenSearch** | [cr7258/elasticsearch-mcp-server](https://github.com/cr7258/elasticsearch-mcp-server) | Busca, análise de índices, gerenciamento de cluster. |

### 3.3 Busca Web

| Servidor | Descrição | Vantagens |
|----------|-----------|-----------|
| **[Brave Search](https://github.com/brave/brave-search-mcp-server)** (Oficial) | Web, local, images, news, videos | Free tier generoso, privacidade |
| **[Perplexity](https://docs.perplexity.ai/guides/mcp-server)** (Oficial) | Deep research, reasoning | sonar-deep-research, sonar-reasoning-pro |
| **Google Search** | [mixelpixx/Google-Search-MCP-Server](https://github.com/mixelpixx/Google-Search-MCP-Server) | Setup complexo (GCP, CSE ID) |

### 3.4 Documentos e Arquivos

| Servidor | Funcionalidades |
|----------|-----------------|
| **[Filesystem](https://www.pulsemcp.com/servers/modelcontextprotocol-filesystem)** (Oficial) | Read, write, create directories, search. Versão 2025.7.1 corrige CVEs. |
| **[PDF Reader](https://github.com/SylphxAI/pdf-reader-mcp)** | 5-10x mais rápido com processamento paralelo. |
| **Document Operations** | Word, Excel, PDF - criar, editar, converter. |

### 3.5 Domínio Jurídico

| Servidor | Descrição | URL |
|----------|-----------|-----|
| **Legal MCP** | Workflows jurídicos, integração com PACER, Westlaw | [agentic-ops/legal-mcp](https://github.com/agentic-ops/legal-mcp) |
| **Legifrance** | Direito francês - códigos, jurisprudência | [mcp-server-legifrance](https://mcp.so/server/mcp-server-legifrance/rdassignies) |
| **Cerebra Legal** | Análise jurídica estruturada, detecção de domínio | [yoda-digital/mcp-cerebra-legal-server](https://github.com/yoda-digital/mcp-cerebra-legal-server) |
| **CanLII** | Jurisprudência canadense | Comunidade |

---

## 4. Comparativo de Servers para Vector Search

| Critério | Qdrant | Pinecone | Weaviate | Chroma |
|----------|--------|----------|----------|--------|
| **Tipo** | Self-hosted / Cloud | Cloud | Self-hosted / Cloud | Self-hosted / Cloud |
| **SDK** | Python (PyPI) | Node.js (npm) | Python | Python |
| **Embedding Nativo** | Sim (FastEmbed) | Sim (integrated models) | Sim (modules) | Não (externo) |
| **Hybrid Search** | Sim | Sim | Sim | Não |
| **Licença** | MIT | Proprietário | BSD-3 | Apache 2.0 |
| **Melhor Para** | RAG local, alta performance | Escala enterprise | GraphQL fans, multi-modal | Prototipagem rápida |
| **Integração Iudex** | Já em uso | Alternativa | Boa opção | Simples |

### Recomendação para Iudex:
**Qdrant** é a melhor escolha dado que:
1. Já está integrado no projeto
2. Servidor MCP oficial e mantido
3. Suporta embeddings locais (FastEmbed)
4. MIT License
5. Ótimo para RAG jurídico com metadados ricos

---

## 5. SDKs para Criar MCP Servers Customizados

### Python SDK

```bash
# Instalação
pip install mcp
# ou com CLI
pip install 'mcp[cli]'
```

**Exemplo básico:**
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("juridico-rag")

@mcp.tool()
async def buscar_jurisprudencia(query: str, tribunal: str = "STJ") -> str:
    """Busca jurisprudência no tribunal especificado."""
    # Implementação RAG aqui
    results = await rag_pipeline.search(query, filters={"tribunal": tribunal})
    return format_results(results)

@mcp.tool()
async def analisar_documento(documento_id: str) -> dict:
    """Analisa documento jurídico e extrai entidades."""
    doc = await get_document(documento_id)
    return await extract_entities(doc)
```

### TypeScript SDK

```bash
npm install @modelcontextprotocol/sdk zod
```

**Exemplo:**
```typescript
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server({
  name: "juridico-rag",
  version: "1.0.0"
}, {
  capabilities: { tools: {} }
});

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [{
    name: "buscar_jurisprudencia",
    description: "Busca jurisprudência",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        tribunal: { type: "string", default: "STJ" }
      },
      required: ["query"]
    }
  }]
}));
```

### Frameworks Recomendados

| Framework | Linguagem | Vantagem |
|-----------|-----------|----------|
| **[FastMCP](https://github.com/punkpeye/fastmcp)** | Python/TS | Decoradores simples, zero-config |
| **fastapi_mcp** | Python | Integração com FastAPI existente |
| **Gradio** | Python | `mcp_server=True` em demos |

---

## 6. Guia: MCP Server Customizado para RAG Jurídico

### Arquitetura Proposta

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code / IDE                        │
└─────────────────────────────────────────────────────────────┘
                              │ MCP Protocol
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  MCP Server: iudex-rag                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Tools:                                               │    │
│  │  - buscar_jurisprudencia                            │    │
│  │  - buscar_doutrina                                  │    │
│  │  - buscar_legislacao                                │    │
│  │  - analisar_documento                               │    │
│  │  - gerar_minuta                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Resources:                                           │    │
│  │  - case://current                                   │    │
│  │  - template://peticao                               │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │  Qdrant  │        │  Neo4j   │        │ OpenSearch│
    │ (vectors)│        │ (graph)  │        │  (hybrid) │
    └──────────┘        └──────────┘        └──────────┘
```

### Implementação

```python
# apps/api/mcp/iudex_server.py
from mcp.server.fastmcp import FastMCP
from app.services.rag.pipeline.rag_pipeline import RAGPipeline
from app.services.rag.core.neo4j_mvp import Neo4jClient

mcp = FastMCP("iudex-rag", dependencies=["qdrant", "neo4j"])

# Injetar dependências
rag = RAGPipeline()
neo4j = Neo4jClient()

@mcp.tool()
async def buscar_jurisprudencia(
    query: str,
    tribunal: str = None,
    data_inicio: str = None,
    data_fim: str = None,
    limit: int = 10
) -> dict:
    """
    Busca jurisprudência nos tribunais brasileiros.

    Args:
        query: Texto da busca semântica
        tribunal: Filtro por tribunal (STF, STJ, TRF1-5, TJ*)
        data_inicio: Data mínima (YYYY-MM-DD)
        data_fim: Data máxima (YYYY-MM-DD)
        limit: Número máximo de resultados

    Returns:
        Lista de acórdãos com citações e metadados
    """
    filters = {}
    if tribunal:
        filters["tribunal"] = tribunal
    if data_inicio:
        filters["data_julgamento"] = {"$gte": data_inicio}
    if data_fim:
        filters["data_julgamento"] = {"$lte": data_fim}

    results = await rag.search(
        query=query,
        collection="jurisprudencia",
        filters=filters,
        top_k=limit
    )

    return {
        "results": results,
        "total": len(results),
        "query": query
    }

@mcp.tool()
async def buscar_relacoes_juridicas(entidade: str, tipo: str = None) -> dict:
    """
    Busca relações entre entidades jurídicas no grafo de conhecimento.

    Args:
        entidade: Nome da entidade (lei, artigo, tribunal)
        tipo: Tipo de relação (cita, revoga, interpreta)
    """
    cypher = """
    MATCH (e:Entidade {nome: $entidade})-[r]->(relacionado)
    WHERE $tipo IS NULL OR type(r) = $tipo
    RETURN e, r, relacionado
    LIMIT 50
    """
    return await neo4j.execute(cypher, {"entidade": entidade, "tipo": tipo})

@mcp.resource("case://current")
async def get_current_case() -> str:
    """Retorna o caso jurídico atual em análise."""
    # Integrar com estado da aplicação
    return current_case_context

# Configuração para Claude Desktop
if __name__ == "__main__":
    mcp.run()
```

### Configuração Claude Desktop

```json
{
  "mcpServers": {
    "iudex-rag": {
      "command": "python",
      "args": ["-m", "app.mcp.iudex_server"],
      "cwd": "/path/to/iudex/apps/api",
      "env": {
        "QDRANT_URL": "http://localhost:6333",
        "NEO4J_URI": "bolt://localhost:7687"
      }
    }
  }
}
```

---

## 7. Hosting e Deployment

### Opções de Produção

| Plataforma | Transporte | Vantagens | Custo |
|------------|------------|-----------|-------|
| **[Cloudflare Workers](https://developers.cloudflare.com/agents/guides/remote-mcp-server/)** | Streamable HTTP | Edge global, rápido | Pay-per-use |
| **[Google Cloud Run](https://cloud.google.com/blog/topics/developers-practitioners/build-and-deploy-a-remote-mcp-server-to-google-cloud-run-in-under-10-minutes)** | Streamable HTTP | Escala automática, IAM | Pay-per-use |
| **[AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)** | Streamable HTTP | Integração AWS | Enterprise |
| **[Fly.io](https://fly.io/docs/blueprints/remote-mcp-servers/)** | Streamable HTTP | VMs isoladas, simples | $5+/mês |

### Recomendação para Iudex
Para integração com a API FastAPI existente, recomendo:

1. **Desenvolvimento**: STDIO local com Claude Desktop
2. **Produção**: Streamable HTTP no mesmo deploy da API FastAPI

---

## 8. Integração com Frameworks de Agentes

### LangChain

```python
from langchain_mcp_adapters import MCPToolkit

# Conectar ao servidor MCP
toolkit = MCPToolkit(server_params={"command": ["python", "-m", "iudex_mcp"]})
tools = toolkit.get_tools()

# Usar com agente LangChain
agent = create_react_agent(llm, tools)
```

### LlamaIndex

```python
from llama_index.tools.mcp import McpToolSpec

tool_spec = McpToolSpec(server_params={"url": "http://localhost:8080/mcp"})
tools = tool_spec.to_tool_list()
```

---

## 9. Considerações de Segurança

1. **Autenticação**: MCP 2025-06-18 inclui OAuth 2.1 para servidores remotos
2. **Sandboxing**: Servidores locais executam com permissões do usuário
3. **Validação**: Sempre validar inputs com Pydantic
4. **Credenciais**: Nunca expor API keys em logs
5. **SQL Injection**: O servidor SQLite oficial tinha vulnerabilidade - sempre sanitizar queries

---

## 10. Próximos Passos para o Iudex

1. **Curto Prazo**:
   - Criar MCP server básico com `buscar_jurisprudencia` usando Qdrant existente
   - Testar com Claude Desktop localmente

2. **Médio Prazo**:
   - Adicionar tools para Neo4j knowledge graph
   - Integrar com pipeline RAG existente
   - Publicar como Desktop Extension (.mcpb)

3. **Longo Prazo**:
   - Deploy remoto em Cloud Run
   - Submeter ao registro oficial
   - Criar sub-registro privado para clientes enterprise

---

## Fontes

### Documentação Oficial
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Registry](https://registry.modelcontextprotocol.io/)
- [MCP GitHub](https://github.com/modelcontextprotocol)

### Vector Stores
- [Qdrant MCP Server](https://github.com/qdrant/mcp-server-qdrant)
- [Pinecone MCP Docs](https://docs.pinecone.io/guides/operations/mcp-server)
- [Weaviate MCP Server](https://github.com/weaviate/mcp-server-weaviate)
- [ChromaDB MCP](https://github.com/chroma-core/chroma-mcp)

### Databases
- [Neo4j MCP](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/)
- [PostgreSQL MCP](https://github.com/crystaldba/postgres-mcp)
- [Elasticsearch MCP](https://github.com/cr7258/elasticsearch-mcp-server)

### Search
- [Brave Search MCP](https://github.com/brave/brave-search-mcp-server)
- [Perplexity MCP](https://docs.perplexity.ai/guides/mcp-server)

### Legal
- [Legal MCP Server](https://github.com/agentic-ops/legal-mcp)
- [Cerebra Legal](https://github.com/yoda-digital/mcp-cerebra-legal-server)

### Deployment
- [Cloudflare Remote MCP](https://developers.cloudflare.com/agents/guides/remote-mcp-server/)
- [Google Cloud Run MCP](https://cloud.google.com/blog/topics/developers-practitioners/build-and-deploy-a-remote-mcp-server-to-google-cloud-run-in-under-10-minutes)
- [AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)

### Tutoriais
- [Build MCP Server - Official](https://modelcontextprotocol.io/docs/develop/build-server)
- [MCP Python Guide](https://scrapfly.io/blog/posts/how-to-build-an-mcp-server-in-python-a-complete-guide)
- [RAG MCP Tutorial](https://medium.com/data-science-in-your-pocket/rag-mcp-server-tutorial-89badff90c00)

### Curated Lists
- [Awesome MCP Servers (punkpeye)](https://github.com/punkpeye/awesome-mcp-servers)
- [Awesome MCP Servers (wong2)](https://github.com/wong2/awesome-mcp-servers)
