# Relatório: Implementação de MCP no Projeto Iudex

> Gerado em: 2026-01-24

## Sumário Executivo

O **Model Context Protocol (MCP)** é um padrão aberto criado pela Anthropic em novembro de 2024 que se tornou o protocolo de facto para conectar sistemas de IA a ferramentas e dados externos. Em dezembro de 2025, o MCP foi doado para a [Agentic AI Foundation (AAIF)](https://en.wikipedia.org/wiki/Model_Context_Protocol) sob a Linux Foundation, com co-fundadores incluindo Anthropic, Block e OpenAI.

O Iudex, como plataforma jurídica multi-agente, pode se beneficiar enormemente do MCP para:
- Expor suas capacidades (RAG, geração de documentos, pesquisa jurídica) como ferramentas padronizadas
- Consumir MCP servers externos (acesso a bases de dados jurídicas, tribunais)
- Facilitar integração com IDEs e agentes de IA

---

## 1. Arquitetura MCP - Conceitos Fundamentais

### 1.1 Componentes Principais

Segundo a [documentação oficial](https://modelcontextprotocol.io/docs/learn/architecture) e a [IBM](https://www.ibm.com/think/topics/model-context-protocol):

| Componente | Descrição | Exemplo no Iudex |
|------------|-----------|------------------|
| **Host** | Aplicação que o usuário interage (Claude Desktop, IDE, agente) | Frontend Next.js + agentes internos |
| **Client** | Gerencia conexão 1:1 com um MCP Server | Biblioteca cliente no backend |
| **Server** | Expõe Tools, Resources e Prompts via API padronizada | FastAPI expondo endpoints como MCP tools |

### 1.2 Transport Layers

Conforme a [especificação 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25):

| Transport | Uso | Produção |
|-----------|-----|----------|
| **stdio** | Processos locais, desenvolvimento | Não recomendado para produção |
| **Streamable HTTP** | Remoto, escalável, bidirecional | **Recomendado para produção** |
| **SSE (deprecado)** | Substituído por Streamable HTTP | Evitar em novas implementações |

O Streamable HTTP [suporta deploy em serverless](https://zuplo.com/mcp-report) (AWS Lambda, Cloudflare Workers) sem conexões de longa duração.

### 1.3 Camada de Dados

O MCP usa [JSON-RPC 2.0](https://www.analytical-software.de/en/the-model-context-protocol-mcp-deep-dive-into-structure-and-concepts/) para troca de mensagens:
- **Lifecycle**: `initialize` -> capability negotiation -> `ready`
- **Primitivas**: `tools`, `resources`, `prompts`
- **Schemas**: Validados com Zod (TypeScript) ou Pydantic (Python)

---

## 2. Segurança e Autenticação

### 2.1 OAuth 2.1 Obrigatório

A [especificação de junho 2025](https://auth0.com/blog/mcp-specs-update-all-about-auth/) exige OAuth 2.1:

- MCP servers são classificados como **OAuth 2.0 Resource Servers**
- Devem servir documento `/.well-known/oauth-protected-resource`
- **PKCE é obrigatório** para clientes públicos
- **Resource Indicators (RFC 8707)** para binding de tokens

Segundo a [Scalekit](https://www.scalekit.com/blog/implement-oauth-for-mcp-servers):

```
Implementação OAuth em 4 passos:
1. Registrar MCP Server com scopes apropriados
2. Implementar metadata protegida (/.well-known/oauth-protected-resource)
3. Validar JWT tokens (signature, issuer, audience, expiry)
4. Enforcar permissões granulares por scope
```

### 2.2 Validação de Tokens

Conforme [Aembit](https://aembit.io/blog/mcp-oauth-2-1-pkce-and-the-future-of-ai-authorization/):
- Validar assinatura, issuer e audience
- Verificar expiração e replay
- Enforcar scopes específicos
- **Nunca confiar em tokens sem validação completa**

### 2.3 Gap de Autenticação

Um [risco identificado](https://aembit.io/blog/mcp-oauth-2-1-pkce-and-ai-authorization/): PKCE garante integridade da troca mas não prova quem está fazendo a requisição. Workloads autônomos precisam autenticação de cliente adicional.

---

## 3. Performance e Escalabilidade

### 3.1 Estratégia de Caching Multi-Tier

Segundo o [Medium](https://abvijaykumar.medium.com/model-context-protocol-deep-dive-part-2-3-architecture-53fe35b75684):

| Nível | Implementação | Capacidade | TTL | Uso |
|-------|---------------|------------|-----|-----|
| **L1** | In-process (RAM) | 100MB-1GB | 30s-5min | Config, sessões ativas |
| **L2** | Redis Cluster | 10GB-100GB+ | 5min-1h | Respostas API, rate limiting |
| **L3** | Semantic Cache | Variável | 1h-24h | Embeddings, queries similares |

### 3.2 Rate Limiting

Conforme [MCP Best Practices](https://modelcontextprotocol.info/docs/best-practices/):
- Rate limiting per-tenant, per-tool
- Surfacing "try later" semantics (429 com Retry-After)
- Centralizado no gateway para consistência

### 3.3 Horizontal Scaling

Recomendações da [NearForm](https://nearform.com/digital-community/implementing-model-context-protocol-mcp-tips-tricks-and-pitfalls/):
- Requests concorrentes e short-lived
- Operações idempotentes para safe retries
- Stateless servers atrás de load balancer
- Health checks e failover automático

---

## 4. Padrões de Implementação

### 4.1 MCP + FastAPI (Python)

Duas opções principais:

#### Opção A: FastMCP (Recomendado)

[FastMCP](https://github.com/jlowin/fastmcp) é o framework mais popular, usado em 70% dos MCP servers:

```python
from fastmcp import FastMCP

mcp = FastMCP("iudex-legal-tools")

@mcp.tool()
async def search_legislation(query: str, limit: int = 10) -> dict:
    """Busca legislação brasileira relevante."""
    results = await rag_pipeline.search(query, sources=["lei"])
    return {"results": results[:limit]}

@mcp.tool()
async def generate_legal_document(
    doc_type: str,
    case_data: dict
) -> dict:
    """Gera documento jurídico a partir de dados do caso."""
    document = await document_generator.generate(doc_type, case_data)
    return {"content": document.content, "format": "markdown"}

# Iniciar server
mcp.run()
```

#### Opção B: FastAPI-MCP (Nativo)

[FastAPI-MCP](https://github.com/tadata-org/fastapi_mcp) converte endpoints existentes:

```python
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

app = FastAPI()
mcp = FastApiMCP(app)
mcp.mount()  # Disponível em /mcp
```

Vantagens:
- Zero configuração
- Preserva schemas Pydantic
- ASGI transport (sem HTTP calls internos)
- Integra com FastAPI Depends() para auth

### 4.2 MCP + Next.js (TypeScript)

Usando o [SDK oficial](https://github.com/modelcontextprotocol/typescript-sdk) e [Vercel MCP Adapter](https://vercel.com/templates/next.js/model-context-protocol-mcp-with-next-js):

```typescript
// app/mcp/[transport]/route.ts
import { createMCPHandler } from '@vercel/mcp-adapter';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';

const handler = createMCPHandler({
  tools: {
    'case-search': {
      description: 'Busca casos no sistema',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string' },
          status: { type: 'string', enum: ['open', 'closed', 'pending'] }
        }
      },
      execute: async (params) => {
        const response = await fetch('/api/cases/search', {
          method: 'POST',
          body: JSON.stringify(params)
        });
        return response.json();
      }
    }
  }
});

export { handler as GET, handler as POST };
```

### 4.3 Múltiplos MCP Servers

Para gerenciar múltiplos servers, usar um **MCP Gateway** conforme [AWS AgentCore](https://aws.amazon.com/blogs/machine-learning/transform-your-mcp-architecture-unite-mcp-servers-through-agentcore-gateway/):

```
       +------------------+
       |   AI Client      |
       +--------+---------+
                |
       +--------v---------+
       |   MCP Gateway    |  <- Auth, Rate Limit, Routing
       +--------+---------+
                |
    +-----------+------------+
    |           |            |
+---v---+  +----v----+  +----v----+
| RAG   |  | Docs    |  | Legal   |
| Server|  | Server  |  | APIs    |
+-------+  +---------+  +---------+
```

---

## 5. Anti-Patterns a Evitar

Segundo a [Docker](https://www.docker.com/blog/mcp-misconceptions-tools-agents-not-api/) e [MCP Best Practices](https://mcp-best-practice.github.io/mcp-best-practice/best-practice/):

| Anti-Pattern | Problema | Solução |
|--------------|----------|---------|
| Tratar MCP como REST | MCP é para LLMs, não humanos | Design domain-aware, não CRUD |
| One-shot calls | Sem retries, sem checkpoints | Loops com retries e HIL |
| Sem resource model | Agente thrashing | Context durável e versionado |
| Prompt sprawl | Prompts inconsistentes | Versionar, A/B testing |
| Operações opacas | Impossível debugar | Traces obrigatórios |
| Tools sem guardrails | Mudanças de estado perigosas | Preconditions/postconditions |

---

## 6. Observabilidade e Debugging

### 6.1 Ferramentas

Conforme [Moesif](https://www.moesif.com/blog/monitoring/model-context-protocol/How-to-Setup-Observability-For-Your-MCP-Server-with-Moesif/):

- **MCP Inspector**: Interface visual para testar servers
- **OpenTelemetry**: Traces distribuídos
- **Sentry**: Erros em tempo real
- **Datadog**: Métricas e logs centralizados

### 6.2 Problema Comum: STDIO Logging

[Suparna](https://medium.com/@ssuparnataneja/debugging-mcp-model-context-protocol-server-bd312e86a132) alerta: print/console.log para stdout quebra o protocolo. Redirecionar para stderr ou logger dedicado.

---

## 7. Casos de Uso em Produção

### 7.1 Empresas Usando MCP

Segundo [Cloudflare](https://blog.cloudflare.com/mcp-demo-day/), [Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/mcp-deepdive) e [StackGen](https://stackgen.com/blog/the-10-best-mcp-servers-for-platform-engineers-in-2025):

| Empresa | Caso de Uso | Resultado |
|---------|-------------|-----------|
| Intercom | MCP Server para Fin AI | Produção em < 1 dia |
| Blade | Figma-to-Code | 70% engenheiros usando, 75% accuracy |
| Gradient Labs | Testing workflow | Tickets automáticos via Linear MCP |
| HashiCorp | Terraform/Vault automation | Interface linguagem natural |

### 7.2 Resultados Reportados

Após 3 meses em produção ([The New Stack](https://thenewstack.io/15-best-practices-for-building-mcp-servers-in-production/)):
- 60% redução em tempo de resolução de incidentes
- 40% menos tempo em tarefas repetitivas
- $15K/mês economizados em infraestrutura
- Zero alertas 3AM para config issues

---

## 8. Arquitetura Recomendada para Iudex

### 8.1 Visão Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                         IUDEX MCP LAYER                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │ Next.js Web  │     │ Claude Code  │     │ IDE Plugins  │    │
│  │   (Host)     │     │   (Client)   │     │   (Client)   │    │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘    │
│         │                    │                    │             │
│         └────────────┬───────┴────────────────────┘             │
│                      │                                          │
│              ┌───────v────────┐                                 │
│              │  MCP Gateway   │ <- Auth, Rate Limit, Routing   │
│              │  (FastAPI)     │                                 │
│              └───────┬────────┘                                 │
│                      │                                          │
│    ┌─────────────────┼─────────────────┐                       │
│    │                 │                 │                        │
│ ┌──v───┐        ┌────v────┐      ┌─────v─────┐                 │
│ │ RAG  │        │  Docs   │      │  Legal    │                 │
│ │Server│        │ Server  │      │  APIs     │                 │
│ └──┬───┘        └────┬────┘      └─────┬─────┘                 │
│    │                 │                 │                        │
├────┼─────────────────┼─────────────────┼────────────────────────┤
│    │                 │                 │                        │
│ ┌──v─────────────────v─────────────────v──────┐                │
│ │            IUDEX BACKEND (FastAPI)           │                │
│ │  - Qdrant/OpenSearch (RAG)                   │                │
│ │  - Neo4j (Graph)                             │                │
│ │  - PostgreSQL (Data)                         │                │
│ │  - Multi-LLM (Gemini/Claude/GPT)             │                │
│ └─────────────────────────────────────────────┘                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 MCP Servers Propostos

#### Server 1: `iudex-rag` (Pesquisa Jurídica)

```python
# apps/api/app/mcp/rag_server.py
from fastmcp import FastMCP

mcp = FastMCP("iudex-rag", version="1.0.0")

@mcp.tool()
async def search_legislation(
    query: str,
    sources: list[str] = ["lei", "juris", "doutrina"],
    top_k: int = 10
) -> dict:
    """Busca em bases jurídicas brasileiras."""
    from app.services.rag.pipeline.rag_pipeline import RAGPipeline
    pipeline = RAGPipeline()
    results = await pipeline.search(query, sources=sources, top_k=top_k)
    return {"results": results, "sources": sources}

@mcp.tool()
async def search_jurisprudence(
    query: str,
    courts: list[str] = ["STF", "STJ", "TST"],
    date_from: str | None = None
) -> dict:
    """Busca jurisprudência nos tribunais superiores."""
    ...

@mcp.resource("legal-bases")
async def list_legal_bases() -> dict:
    """Lista todas as bases jurídicas disponíveis."""
    return {
        "bases": [
            {"id": "lei", "name": "Legislação Federal", "count": 50000},
            {"id": "juris", "name": "Jurisprudência", "count": 2000000},
            {"id": "doutrina", "name": "Doutrina", "count": 10000},
        ]
    }
```

#### Server 2: `iudex-docs` (Geração de Documentos)

```python
# apps/api/app/mcp/docs_server.py
from fastmcp import FastMCP

mcp = FastMCP("iudex-docs", version="1.0.0")

@mcp.tool()
async def generate_petition(
    case_id: str,
    petition_type: str,  # inicial, contestacao, recurso
    style: str = "formal"
) -> dict:
    """Gera petição jurídica baseada no caso."""
    ...

@mcp.tool()
async def generate_contract(
    contract_type: str,
    parties: list[dict],
    clauses: list[str]
) -> dict:
    """Gera contrato a partir de templates."""
    ...

@mcp.prompt("legal-analysis")
async def legal_analysis_prompt(case_summary: str) -> str:
    """Prompt otimizado para análise jurídica."""
    return f"""
    Você é um advogado especialista brasileiro.
    Analise o seguinte caso:

    {case_summary}

    Forneça análise em formato estruturado com:
    1. Fatos relevantes
    2. Questões jurídicas
    3. Fundamentação legal
    4. Recomendações
    """
```

#### Server 3: `iudex-case` (Gestão de Casos)

```python
# apps/api/app/mcp/case_server.py
from fastmcp import FastMCP

mcp = FastMCP("iudex-case", version="1.0.0")

@mcp.tool()
async def search_cases(
    query: str,
    status: str | None = None,
    user_id: str | None = None
) -> dict:
    """Busca casos no sistema."""
    ...

@mcp.tool()
async def get_case_timeline(case_id: str) -> dict:
    """Retorna timeline completa do caso."""
    ...

@mcp.tool()
async def add_case_event(
    case_id: str,
    event_type: str,
    description: str,
    metadata: dict | None = None
) -> dict:
    """Adiciona evento ao caso."""
    ...
```

### 8.3 Integração com Estrutura Existente

Baseado na análise dos arquivos:

| Componente Existente | Integração MCP |
|---------------------|----------------|
| `/apps/api/app/main.py` | Montar MCP gateway como sub-app |
| `/apps/api/app/services/rag/` | Expor como tools do rag_server |
| `/apps/api/app/services/ai/` | Expor geração de docs como tools |
| `/apps/api/app/api/endpoints/` | Converter endpoints críticos para MCP |
| `/apps/web/` | Cliente MCP para IDEs e agentes |

---

## 9. Checklist de Implementação

### Fase 1: Setup Básico (1-2 semanas)

- [ ] Adicionar dependências: `fastmcp>=2.0`, `@modelcontextprotocol/sdk`
- [ ] Criar estrutura `/apps/api/app/mcp/`
- [ ] Implementar primeiro MCP server (RAG search)
- [ ] Testar com MCP Inspector
- [ ] Configurar logging para stderr (evitar STDIO issues)

### Fase 2: Segurança (1 semana)

- [ ] Implementar OAuth 2.1 com PKCE
- [ ] Configurar `/.well-known/oauth-protected-resource`
- [ ] Validação JWT completa (signature, issuer, audience)
- [ ] Rate limiting per-tenant
- [ ] Audit logging de tool calls

### Fase 3: MCP Gateway (2 semanas)

- [ ] Criar gateway centralizado (FastAPI middleware)
- [ ] Routing para múltiplos MCP servers
- [ ] Caching L1/L2 (Redis)
- [ ] Health checks e failover
- [ ] Métricas OpenTelemetry

### Fase 4: Ferramentas Adicionais (2-3 semanas)

- [ ] `iudex-docs` server (geração de documentos)
- [ ] `iudex-case` server (gestão de casos)
- [ ] Resources: templates, bases jurídicas
- [ ] Prompts: análise jurídica, pesquisa

### Fase 5: Cliente MCP no Frontend (1-2 semanas)

- [ ] Integrar `@modelcontextprotocol/sdk` no Next.js
- [ ] Conectar com AI SDK do Vercel
- [ ] Interface para tool discovery
- [ ] Streaming de resultados

### Fase 6: Produção (1 semana)

- [ ] Deploy Streamable HTTP (não SSE)
- [ ] Horizontal scaling config
- [ ] Monitoring Datadog/Sentry
- [ ] Documentação para desenvolvedores

---

## 10. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| **Token mis-redemption** | Média | Alto | Resource Indicators (RFC 8707) |
| **Prompt injection via tools** | Alta | Alto | Input validation rigorosa, sandboxing |
| **Rate limit bypass** | Média | Médio | Rate limit no gateway, não nos servers |
| **Latência elevada** | Média | Médio | Caching agressivo, preload de modelos |
| **Vendor lock-in** | Baixa | Médio | MCP é padrão aberto, múltiplos providers |
| **Breaking changes spec** | Média | Médio | Pinning de versão, testes de regressão |
| **STDIO debugging** | Alta | Baixo | Logging para stderr, não stdout |
| **Custo de tokens** | Alta | Médio | Budget caps, caching semântico |

---

## 11. Estimativa de Esforço

| Fase | Duração | Recursos | Dependências |
|------|---------|----------|--------------|
| **1. Setup Básico** | 1-2 semanas | 1 dev backend | Nenhuma |
| **2. Segurança** | 1 semana | 1 dev backend | Fase 1 |
| **3. MCP Gateway** | 2 semanas | 1-2 devs backend | Fases 1-2 |
| **4. Ferramentas** | 2-3 semanas | 2 devs | Fase 3 |
| **5. Cliente Frontend** | 1-2 semanas | 1 dev frontend | Fase 3 |
| **6. Produção** | 1 semana | 1 dev ops | Fases 1-5 |
| **Total** | **8-11 semanas** | **2-3 devs** | |

---

## 12. Próximos Passos Recomendados

1. **POC Imediato**: Implementar um MCP server simples com FastMCP expondo o endpoint de RAG search existente

2. **Validar com Claude Code**: Testar integração local usando Claude Code como cliente

3. **Definir escopo MVP**: Escolher 3-5 tools mais valiosos para primeira versão

4. **Arquitetura de auth**: Decidir entre auth próprio vs integração com Auth0/WorkOS

5. **Métricas de sucesso**: Definir KPIs (latência, taxa de uso, economia de tempo)

---

## Sources

- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [MCP Architecture Overview](https://modelcontextprotocol.io/docs/learn/architecture)
- [MCP Best Practices](https://modelcontextprotocol.info/docs/best-practices/)
- [FastMCP GitHub](https://github.com/jlowin/fastmcp)
- [FastAPI-MCP GitHub](https://github.com/tadata-org/fastapi_mcp)
- [TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Vercel MCP Template](https://vercel.com/templates/next.js/model-context-protocol-mcp-with-next-js)
- [MCP Auth Spec Updates June 2025](https://auth0.com/blog/mcp-specs-update-all-about-auth/)
- [OAuth 2.1 for MCP](https://www.scalekit.com/blog/implement-oauth-for-mcp-servers)
- [MCP Gateway Explained](https://www.gravitee.io/blog/mcp-api-gateway-explained-protocols-caching-and-remote-server-integration)
- [AWS AgentCore Gateway](https://aws.amazon.com/blogs/machine-learning/transform-your-mcp-architecture-unite-mcp-servers-through-agentcore-gateway/)
- [15 Best Practices for MCP in Production](https://thenewstack.io/15-best-practices-for-building-mcp-servers-in-production/)
- [MCP Debugging Guide](https://medium.com/@ssuparnataneja/debugging-mcp-model-context-protocol-server-bd312e86a132)
- [MCP Misconceptions](https://www.docker.com/blog/mcp-misconceptions-tools-agents-not-api/)
- [A Year of MCP Review](https://www.pento.ai/blog/a-year-of-mcp-2025-review)
- [State of MCP Report](https://zuplo.com/mcp-report)
