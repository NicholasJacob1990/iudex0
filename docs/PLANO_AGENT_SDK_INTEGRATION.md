# Plano de Integração: Claude Agent SDK + LangGraph no Iudex

> Análise comparativa entre as estratégias propostas no documento de referência (Neo4j Aura Agent / Claude Agent SDK) e a implementação atual do Iudex. Plano de ação faseado.

---

## 1. Mapa de Cobertura

| Área | Implementado | Gap | Prioridade |
|------|:---:|-----|:---:|
| Agent SDK core (Claude/OpenAI/Google) | 70% | Subagentes com modelos diferentes (Opus 4.6→Haiku 4.5). 3 agents no router com executors dedicados. **Atualizar base models**: Claude Agent → Opus 4.6, OpenAI Agent → GPT-5.2, Google Agent → Gemini 3 Pro. Adicionar modelos ausentes (Opus 4.6, GPT-5.2 Pro/Codex, GPT-5.1 family, GPT-5 Nano). Foco inicial: Claude Agent SDK | **Alta** |
| Skills System | 30% | Proto-skill existe (`LibraryItem` + `template_loader.py`). Faltam triggers, matcher, registry, builtin `.md` | **Alta** |
| MCP Server Legal | 65% | DataJud/DJEN já no Tool Gateway. Faltam: CPC, JusBrasil, exposição no SDK path | Média |
| Skill Builder UI | 5% | Feature inteira (wizard + visual canvas) | Baixa |
| LangGraph + SDK Integration | 80% | Agent como LangGraph node nativo | Média |
| Citation Formatting | 85% | ABNT completo + subagent validator | Baixa |
| Document Size Routing | 40% | Router ativo + multi-pass >500pg | **Alta** |
| Multi-part Generation | 50% | Prompt caching Anthropic | **Alta** |
| LangSmith Observability | 10% | Integração completa | Média |
| Dynamic Skill Creation | 0% | Feature inteira | Baixa |

---

## 2. O Que Já Existe (Pontos Fortes)

### 2.1 Backend (`apps/api/`)

| Componente | Arquivo | Linhas | Status |
|-----------|---------|--------|--------|
| **ClaudeAgentExecutor** | `services/ai/claude_agent/executor.py` | ~1247 | Agentic loop completo, dual-mode (SDK + API), SSE, billing |
| **SDK Tools** | `claude_agent/sdk_tools.py` | ~300 | 7 tools: search_jurisprudencia, search_legislacao, web_search, search_rag, verify_citation, run_workflow, ask_graph |
| **LangGraph Legal Workflow** | `langgraph_legal_workflow.py` | ~7200 | 27+ nós: outline→research→debate→audit→finalize |
| **Orchestration Router** | `orchestration/router.py` | — | 5 executors: LANGGRAPH, CLAUDE_AGENT, OPENAI_AGENT, GOOGLE_AGENT, PARALLEL. 3 agents com env flags |
| **Parallel Executor** | `orchestration/parallel_executor.py` | — | Agent + Debate em paralelo, LLM judge merge |
| **MCP Hub** | `mcp_tools.py` + `tool_gateway/` | — | mcp_tool_search, mcp_tool_call, policy engine |
| **Unified Tools** | `shared/unified_tools.py` | ~328KB | Categorias (search/document/citation/analysis/system), risk levels |
| **Cognitive RAG** | `langgraph/cognitive_rag.py` | — | CogRAG: planner→retriever→reasoner→verifier→integrator |
| **Parallel Research** | `langgraph/subgraphs/parallel_research.py` | — | Fan-out: RAG local + global + web + jurisprudência |
| **Workflow Compiler** | `workflow_compiler.py` | ~43KB | React Flow JSON → LangGraph StateGraph |
| **Citations** | `citations/base.py` + `abnt_classifier.py` | — | ABNT, inline, footnote. CiterVerifier no workflow |

### 2.2 Frontend (`apps/web/`)

| Componente | Arquivo | Status |
|-----------|---------|--------|
| **Chat Store** | `stores/chat-store.ts` (6786 linhas) | `startAgentGeneration`, `startLangGraphJob`, 100+ params |
| **Agent Orchestrator** | `services/agents/agent-orchestrator.ts` | 4 AgentSteps visuais |
| **SSE Streaming** | `attachLangGraphStream()` | token, outline, artifact, job_event |
| **Model Registry** | `config/models.ts` | 26+ modelos + 3 agents com `AGENT_REGISTRY` separado. **⚠️ AÇÃO REQUERIDA — Atualizar para modelos mais atuais**: (1) Adicionar Claude Opus 4.6, GPT-5.2 Pro/Codex, GPT-5.1 family, GPT-5 Nano. (2) Agents: `claude-agent` → Opus 4.6, `openai-agent` → GPT-5.2, `google-agent` → Gemini 3 Pro. Ver seção "Decisão: Model Registry" |
| **Hard Research Viewer** | `components/chat/hard-research-viewer.tsx` | Tracking em tempo real de providers paralelos |
| **Tool Approval Modal** | — | Permission allow/ask/deny |
| **Workflow Builder** | React Flow canvas | Visual → LangGraph compilation |

---

## 3. Gaps Detalhados

### 3.1 Subagentes com Modelos Diferentes (Gap: 30%)

**Problema**: O `ClaudeAgentExecutor` usa sempre o mesmo modelo. Não há lógica de "Opus orquestra, Haiku extrai metadados, Sonnet redige".

**Proposta**: Novo tool `delegate_subtask` no SDK que o agent pode invocar para spawnar um subagente com modelo diferente:

```python
# sdk_tools.py — novo tool
from app.services.ai.claude_agent.executor import ClaudeAgentExecutor, AgentConfig
from app.services.ai.shared.sse_protocol import SSEEventType

async def delegate_subtask(
    task: str,
    model: str = "claude-haiku-4-5",  # default barato
    tool_names: list[str] | None = None,
    max_tokens: int = 4096
) -> str:
    """Delega subtarefa a um subagente com modelo específico."""
    config = AgentConfig(model=model, max_tokens=max_tokens, max_iterations=5)
    sub = ClaudeAgentExecutor(config=config)

    # Carregar tools do registry unificado (mesmo mecanismo do executor principal)
    sub.load_unified_tools(
        include_mcp=False,
        tool_names=tool_names,  # None = todas; ou ["search_rag", "search_legislacao"]
    )

    # Coletar resultado via async generator
    result = ""
    async for event in sub.run(task, system_prompt="Você é um assistente jurídico auxiliar."):
        if event.type == SSEEventType.TOKEN:  # TOKEN é o evento de streaming de texto
            result += event.data.get("text", "")
    return result
```

> **Notas técnicas**:
> - `ClaudeAgentExecutor` NÃO é context manager — instanciação direta + `async for` no generator `run()`
> - Evento de texto é `SSEEventType.TOKEN` (não existe `CONTENT` no enum `sse_protocol.py`)
> - Usar `load_unified_tools()` (método existente em `executor.py:399`) em vez de `resolve_tools()` (inexistente)

**Benefício**: Redução de ~60% em custo para tarefas simples (metadata, classificação, sumarização).

### 3.2 Skills System (Gap: 80%)

**Problema**: Não existe conceito de "Skill" como `.md` auto-descoberto com triggers. **Porém**, já existe infraestrutura parcial: `LibraryItem` (model `library.py`) com `type=PROMPT` + `tag="agent_template"` funciona como proto-skill. O `template_loader.py` carrega esses itens como system instructions para o executor.

**Estado atual do proto-skill:**
- Storage: `LibraryItem(type=PROMPT, tags=["agent_template"])` no banco
- Loader: `template_loader.py` → `load_agent_templates(user_id, db)` → string injetada no system prompt
- **Faltam**: triggers, tools_required, subagent_model, matcher automático

**Proposta**: **Evoluir** o sistema existente (não criar do zero):

```
apps/api/app/services/ai/skills/
├── loader.py          # Evolui template_loader.py — indexa por trigger patterns
├── matcher.py         # Match input do usuário → skill relevante (novo)
├── registry.py        # Registry centralizado (novo)
└── builtin/
    ├── petition-analysis.md
    ├── contract-review.md
    ├── compliance-check.md
    ├── document-drafting.md
    └── case-summarization.md
```

**Storage e Identidade de Domínio**:

Skills reutilizam o modelo `LibraryItem` existente, mas com **identidade própria** distinta dos agent templates:

| Aspecto | Agent Template (atual) | Skill (proposta) |
|---------|----------------------|------------------|
| **type** | `PROMPT` | `PROMPT` |
| **tag** | `"agent_template"` | `"skill"` (nova tag) |
| **description** | Texto livre (instruções gerais) | Frontmatter YAML obrigatório + instruções estruturadas |
| **Schema** | Nenhum | Campos obrigatórios: `name`, `triggers`, `tools_required` |
| **Loader** | `template_loader.py` (concatena todas) | `skills/loader.py` (parseia frontmatter, indexa por trigger) |

> **Contrato de domínio**: `tag="agent_template"` = templates de sistema/instruções livres (injetados sempre). `tag="skill"` = capacidades com triggers (injetados sob demanda quando matched). O `SkillRegistry` NÃO mistura os dois.

**Formato de Skill** (frontmatter YAML obrigatório):

```markdown
---
name: petition-analysis
description: Analisa petições jurídicas integralmente
triggers: ["analisar petição", "análise de petição", "revisar petição"]
tools_required: [Read, search_jurisprudencia, verify_citation]
subagent_model: claude-haiku-4-5
prefer_workflow: false
prefer_agent: true
---

## Instructions
### 1. Avaliar Tamanho
...
### 2. Extrair Metadados
...
### 3. Análise de Mérito
...

## Examples
...
```

**Validação**: O `skills/loader.py` valida schema do frontmatter ao carregar. LibraryItems com `tag="skill"` que não tenham frontmatter válido são ignorados com warning.

> **Nota**: Skills builtin são arquivos `.md` no repo (versionados). Skills do usuário são `LibraryItem(type=PROMPT, tag="skill")` no banco. O `SkillRegistry` unifica ambos via mesma interface.

**Integração**: O `SkillMatcher` analisa input do usuário, match por triggers → o executor injeta a skill matched no system prompt antes da primeira chamada. Agent templates (`tag="agent_template"`) continuam sendo injetados sempre, como hoje via `template_loader.py`.

### 3.3 Document Size Routing Ativo (Gap: 60%)

**Problema**: O sistema emite warning quando documento é grande, mas não roteia automaticamente.

**Proposta**: Converter `_validate_document_size` em router ativo:

```python
def _route_by_document_size(pages: int, context_window: int) -> str:
    if pages <= 100:
        return "direct"           # Context window direto
    elif pages <= 500:
        return "rag_enhanced"     # RAG + geração por seção
    elif pages <= 2000:
        return "chunked_rag"     # Chunked RAG + multi-pass
    else:
        return "multi_pass"       # Multi-pass summarization
```

### 3.4 Prompt Caching Anthropic (Gap: 50%)

**Problema**: System prompt + contexto RAG são re-enviados em cada seção durante multi-part generation. Custo desnecessário.

**Proposta**: Adicionar `cache_control` blocks nas chamadas Anthropic. **Atenção**: o executor envia system prompt como campo separado `system=` (não dentro de `messages`). O `cache_control` deve ser aplicado no formato correto:

```python
# Em _call_claude() do executor.py (linha 606-632)
# Assinatura: _call_claude(self, messages, system_prompt, container_id=None)
#
# PASSO 1: System prompt (campo separado kwargs["system"]) — cachear
# Hoje: kwargs["system"] = system_prompt  (string)
# Proposta: converter para content blocks com cache_control
kwargs["system"] = [
    {
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"}  # Cacheia entre iterações do loop
    }
]

# PASSO 2: RAG context — injetado por _build_system_prompt() (linha 588-604)
# que concatena no system_prompt ANTES de _call_claude ser chamada.
# Para cachear RAG separadamente do system prompt base, dividir em 2 blocks:
if context:
    kwargs["system"] = [
        {
            "type": "text",
            "text": base_system_prompt,  # Instruções base (muda raramente)
            "cache_control": {"type": "ephemeral"}
        },
        {
            "type": "text",
            "text": f"## CONTEXTO DISPONÍVEL\n\n{context}",  # RAG (muda por request)
            "cache_control": {"type": "ephemeral"}
        },
    ]
```

> **Notas de implementação**:
> - `_call_claude(messages, system_prompt, ...)` recebe o system prompt já montado via `_build_system_prompt()` (linha 588). O RAG context é concatenado **dentro** do system prompt, não como mensagem separada.
> - Para caching eficaz, separar `_build_system_prompt()` em dois retornos: `base` (cacheável entre requests) + `context` (cacheável entre iterações).
> - `kwargs["system"]` aceita string OU array de content blocks — a mudança é retrocompatível.

**Benefício**: Economia de 40-60% em tokens para documentos multi-seção.

### 3.5 Tools Jurídicos Faltantes

| Tool | Status | Proposta |
|------|--------|---------|
| `consultar_processo_datajud` / `buscar_publicacoes_djen` | Já existem no Tool Gateway (`tool_registry.py:248-317`, policy ALLOW). **Não** expostos no caminho SDK (`sdk_tools.py`). | Criar wrappers em `sdk_tools.py` que delegam para `djen_service` — espelhando os tools do Tool Gateway |
| `validate_cpc_compliance` | Não existe | Novo: regras CPC + LLM para validação |
| `search_jusbrasil` | Não existe | Integração API JusBrasil (se disponível) |
| `vector_search_jurisprudence` | RAG faz, mas não como tool dedicado | Wrapper com reranking específico |

### 3.6 LangSmith Observability (Gap: 90%)

**Problema**: Observabilidade apenas via SSE events no frontend. Sem traces unificados.

**Proposta**:
```python
# config.py
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = "iudex-legal-ai"

# Em langgraph_legal_workflow.py
from langsmith import trace

@trace
async def run_legal_workflow(state):
    ...
```

---

## 4. Plano de Implementação Faseado

### FASE 0: Correções de Integridade (48h) ⚠️ BLOQUEANTE

Bugs reais identificados por code review cruzado (Claude + GPT). **Devem ser corrigidos ANTES de qualquer feature nova** — código quebrado em runtime.

| # | Item | Bug | Arquivos | Fix |
|---|------|-----|----------|-----|
| 0.1 | **MCP Hub naming mismatch** | `tool_handlers.py:824` chama `mcp_hub.search_tools()` mas o método real é `tool_search()`. Idem `call_tool` vs `tool_call`. `AttributeError` em runtime. | `shared/tool_handlers.py` | Renomear chamadas: `search_tools()` → `tool_search()`, `call_tool()` → `tool_call()` |
| 0.2 | **Startup chama método inexistente** | `startup.py:100` chama `await mcp_hub.initialize()` mas `MCPHub` não tem método `initialize()`. Erro silenciado por `try/except`. | `shared/startup.py`, `mcp_hub.py` | Criar `async def initialize()` no MCPHub (warm cache de tools) OU remover chamada do startup |
| 0.3 | **Política de risco toda ALLOW** | `unified_tools.py:46-50` mapeia `LOW/MEDIUM/HIGH` → `ALLOW`. Tools de risco alto (bash, delete) nunca pedem aprovação neste caminho. | `shared/unified_tools.py` | Corrigir: `LOW→ALLOW`, `MEDIUM→ASK`, `HIGH→DENY` |
| 0.4 | **delegate_research signature mismatch** | `tool_handlers.py:670` chama `run_parallel_research(queries=...)` mas a função espera `query: str` (singular). `TypeError` em runtime. | `shared/tool_handlers.py` | Iterar queries e chamar `run_parallel_research(query=q)` para cada, ou criar wrapper que aceita lista |

**Critérios de aceite:**
- Startup sem warning MCP; `mcp_tool_search`/`mcp_tool_call` funcionando em smoke test
- `MEDIUM` tools pedem aprovação; `HIGH` tools são negados por padrão
- `delegate_research` executa sem `TypeError`

**Rollback:** Feature flags `IUDEX_MCP_TOOL_CALLING=false` com fallback para fluxo sem MCP.

### FASE 1: Quick Wins + Segurança (2-3 semanas)

Aprimorar o que já existe. Custo baixo, impacto imediato.

| # | Item | Arquivos | Esforço | Impacto |
|---|------|----------|:-------:|:-------:|
| 1.1 | **Prompt Caching Anthropic** — Adicionar `cache_control` nos system blocks das chamadas multi-seção | `claude_agent/executor.py`, `langgraph_legal_workflow.py` | S | **Alto** |
| 1.2 | **Document Size Router ativo** — Converter warning passivo em roteamento automático por tamanho | `langgraph_legal_workflow.py`, `orchestration/router.py` | M | **Alto** |
| 1.3 | **Subagente com modelo diferente** — `delegate_subtask` tool que usa Haiku para tarefas simples | `claude_agent/executor.py`, `sdk_tools.py` | M | **Alto** |
| 1.4 | **Expor DataJud/CNJ no caminho SDK** — Tools `consultar_processo_datajud` e `buscar_publicacoes_djen` já existem no Tool Gateway (`tool_registry.py:248-317`, policy ALLOW). Criar wrappers em `sdk_tools.py` que delegam para `djen_service` para que o executor SDK também acesse | `sdk_tools.py`, `djen_service.py` | S | Médio |
| 1.5 | **Citações multi-estilo** — Interface `CitationFormatter` com 12 estilos (ABNT, Forense BR, Bluebook, APA, Chicago, Harvard, OSCOLA, ECLI, Vancouver, Inline, Numérico, ALWD). `citation_style` param fim-a-fim: UI dropdown → prompt → subagente validador → `format_reference(style=)`. Rollout: ABNT default (F1) → Forense+Bluebook+Harvard (F2) → APA+OSCOLA+Chicago (F3) → restantes (F4). Ver Seção 8.5.5 | `citations/base.py`, `citations/abnt_classifier.py`, novo: `citations/{bluebook,apa,harvard,oscola,forense_br,...}_formatter.py` | M→G | Médio |
| 1.6 | **Unificação de Permissões** — Conectar `PermissionManager` a **ambos** os caminhos. Hoje: modo SDK usa `permission_mode="default"` hardcoded (`executor.py:1048`); modo raw API usa `DEFAULT_TOOL_PERMISSIONS` dict local flat (`executor.py:130-150`) via `_get_tool_permission()` (linha 548). **Nenhum dos dois** consulta o `PermissionManager` hierárquico (`permissions.py`). Ambos devem ser migrados para consultar PM (session→project→global→system). | `claude_agent/executor.py` (substituir dict local por PM), `claude_agent/permissions.py`, `shared/unified_tools.py` | M | **Alto** |
| 1.7 | **Quick Agent Bridge (modo Rápido → executor dedicado)** — Quando `model` for `claude-agent`/`openai-agent`/`google-agent`, chamar `OrchestrationRouter` com perfil quick (`max_iterations` baixo, timeout curto, HIL OFF, checkpoint OFF por default) sem alterar o fluxo de modelos normais | `api/endpoints/chats.py`, `services/ai/orchestration/router.py`, `services/ai/orchestration/types.py` | M | **Alto** |
| 1.8 | **Contrato `lite`/`full` + fallback transparente** — Padronizar SSE/metadata com `execution_mode`, adicionar fallback automático do executor dedicado para loop nativo do chat, e expor badge Lite/Full no frontend | `api/endpoints/chats.py`, `services/chat_service.py`, `web/src/components/chat/*`, `web/src/types/*` | M | **Alto** |
| 1.9 | **Adaptive Thinking (Claude Opus 4.6)** — Habilitar explicitamente `thinking={"type":"adaptive"}` nas chamadas Anthropic do caminho agentic, com `output_config.effort` por perfil (`high/max` para análise complexa; `low/medium` para subtarefas) e fallback para comportamento legado em modelos sem suporte | `claude_agent/executor.py`, `chat_service.py`, `model_registry.py`, `api/endpoints/chats.py` | S→M | **Alto** |

### FASE 2: Core Gaps (4-6 semanas)

Novas capacidades que fecham os gaps principais.

| # | Item | Arquivos | Esforço | Impacto |
|---|------|----------|:-------:|:-------:|
| 2.1 | **Skills System v1** — Evoluir proto-skills existente. Nova tag `"skill"` (distinta de `"agent_template"`), schema frontmatter obrigatório (name, triggers, tools_required), loader com matcher. Skills builtin como `.md` no repo; skills do usuário como `LibraryItem(type=PROMPT, tag="skill")` no banco. | Novo: `services/ai/skills/` (loader, matcher, registry, builtin/*.md). Evoluir: `template_loader.py`, `executor.py`. Storage: `LibraryItem` existente com nova tag | G | **Alto** |
| 2.2 | **Claude Agent como LangGraph node** — `ClaudeAgentNode` que wrapa executor como nó do grafo | Novo: `langgraph/nodes/claude_agent_node.py`. Editar: `workflow_compiler.py` | M | **Alto** |
| 2.3 | **validate_cpc_compliance tool** — Validação de conformidade CPC (prazos, admissibilidade, formatação) | Novo: `claude_agent/tools/cpc_validator.py`. Editar: `unified_tools.py` | G | **Alto** |
| 2.4 | **Citation Validator Subagent** — Subagente Haiku persistente que valida citações durante geração | Novo: `claude_agent/tools/citation_validator_agent.py`. Editar: `langgraph_legal_workflow.py` | M | **Alto** |
| 2.5 | **Multi-pass para docs >500pg** — Chunked processing: split→summarize(Haiku)→merge→generate | Novo: `services/ai/document_chunker.py`. Editar: `langgraph_legal_workflow.py`, `router.py` | G | Médio |
| 2.6 | **LangSmith Integration** — Tracing unificado Claude SDK + LangGraph | Novo: `observability/langsmith_tracer.py`. Editar: `executor.py`, `langgraph_legal_workflow.py` | M | Médio |

### FASE 3: Features Avançadas (6-10 semanas)

Diferenciais competitivos e expansão do ecossistema.

| # | Item | Arquivos | Esforço | Impacto |
|---|------|----------|:-------:|:-------:|
| 3.1 | **Skill Builder (Prompt-to-Skill)** — Wizard conversacional (leigos) + editor YAML/MD (power users). **3 endpoints**: `POST /skills/generate` (diretriz → draft), `POST /skills/validate` (schema + segurança + roteamento TPR/FPR), `POST /skills/publish` (upsert em `LibraryItem(tag="skill")`). **Schema SkillV1**: frontmatter obrigatório (name, triggers[3-12], tools_required, tools_denied, subagent_model, citation_style, output_format, guardrails, examples[2-10]). **Pipeline**: coletar → inferir triggers → gerar draft (LLM) → lint → simular 5 prompts → score qualidade → publicar. Ver Seção 8.6 para detalhes | Backend: `schemas/skills.py` (Pydantic v2), `endpoints/skills.py` (3 rotas), `routes.py` (include). Frontend: `web/src/components/skills/` (SkillWizard, SkillEditor, SkillList), `web/src/app/skills/page.tsx` | G | **Alto** |
| 3.2 | **Dynamic Skill Detection** — Análise de histórico para detectar padrões repetidos e sugerir skills | Novo: `skills/pattern_detector.py`, worker task periódica | G | Médio |
| 3.3 | **MCP Server Standalone** — Microserviço MCP independente para tools jurídicos. **Contratos operacionais** (ver item 4.6): ACL por tenant, rate limiting por tool, cache com TTL, auditoria de chamadas, isolamento de segredos (vault por tenant) | Novo: `apps/mcp-legal-server/` (FastMCP com todos os tools legais), `shared/mcp_contracts.py` | G | Médio |
| 3.4 | **Fan-out de Claude Agents em LangGraph** — N agentes Haiku em paralelo como nós LangGraph | Novo: `langgraph/nodes/parallel_agents_node.py`. Editar: `parallel_research.py` | G | Médio |
| 3.5 | **JusBrasil Integration** — Connector para API/scraping JusBrasil | Novo: `services/jusbrasil_service.py`, novo tool em `sdk_tools.py` | M | **Alto** |

### FASE 4: Operacionalização e Governança (contínuo)

Guardrails de produção para rollout seguro.

| # | Item | Arquivos | Esforço | Impacto |
|---|------|----------|:-------:|:-------:|
| 4.1 | **Feature flags em camadas** — 5 níveis: (1) **Global** (kill switch geral), (2) **Auto-detect** (SDK ativado se `anthropic>=0.50` presente), (3) **Por nó/executor** (flag por executor type: CLAUDE_AGENT, OPENAI_AGENT, etc.), (4) **Limites de segurança** (max tool calls por request, max tokens por delegação), (5) **Analytics** (% de requests roteados, taxa de fallback). Governança: admin panel para toggle; auditoria de quem alterou flags. | `shared/feature_flags.py` (novo), `orchestration/router.py`, admin endpoint | M | **Alto** |
| 4.2 | **SLOs e métricas** — Latência p95/p99, custo por request, taxa de tool approval, taxa de fallback SDK→raw API | `observability/metrics.py` (novo), `executor.py` | M | **Alto** |
| 4.3 | **Circuit breaker MCP** — Se MCP server falhar N vezes consecutivas, desativar temporariamente e usar fallback | `mcp_hub.py`, `shared/tool_handlers.py` | S | Médio |
| 4.4 | **Auditoria exportável** — Log estruturado de todas as tool calls com decisão de permissão, exportável para compliance | `claude_agent/permissions.py`, `observability/audit_log.py` (novo) | M | Médio |
| 4.5 | **Quotas e limites por tenant** — Tokens/requests por período, **budget caps de subagentes** (max tokens delegados por request), **concurrency caps** (max N subagentes simultâneos por tenant), alertas antes de atingir limite | `shared/quotas.py` (novo), `orchestration/router.py` | M | Médio |
| 4.6 | **Contratos operacionais MCP Server** — ACL por tenant (quais tools cada tenant pode acessar), rate limiting por tool, cache de resultados (TTL configurável), auditoria de chamadas, isolamento de segredos (cada tenant tem suas API keys via vault/env separado) | `apps/mcp-legal-server/`, `shared/mcp_contracts.py` (novo) | M | **Alto** |

---

## 5. Mapeamento por Modo de Execução

### Arquitetura real de modos (frontend → backend)

O Iudex tem **4 caminhos de execução** distintos, controlados pelo frontend. Nem todos passam pelo `OrchestrationRouter`:

| Modo UI | Toggle | Frontend entry point | Backend endpoint | Executor | Passa pelo Router? |
|---------|--------|---------------------|-----------------|----------|:---:|
| **⚡ Rápido** (individual) | `mode='individual'` + `chatMode='standard'` | `sendMessage()` | `POST /chat/{id}/messages` → `chat_service.dispatch_turn()` | Chamada **direta** ao modelo (OpenAI/Anthropic/Vertex API) | **NÃO** |
| **⚖️ Comparar** (multi-model) | `chatMode='multi-model'` | `startMultiModelStream()` | `POST /chat/{id}/messages` → `chat_service.dispatch_turn()` com N modelos | N chamadas diretas em paralelo | **NÃO** |
| **👥 Comitê** (multi-agent) | `mode='multi-agent'` | `startAgentGeneration()` → `startLangGraphJob()` | `POST /jobs` → `OrchestrationRouter.route()` | LANGGRAPH / CLAUDE_AGENT / OPENAI_AGENT / GOOGLE_AGENT / PARALLEL | **SIM** |
| **📄 Canvas write** (diff/suggestion) | `mode='multi-agent'` + canvasContext | `startAgentGeneration()` com canvasContext | Legacy endpoint (generateDocument) | Direto com modelo selecionado | **NÃO** |

> **Insight crítico**: O `OrchestrationRouter` só é consultado no modo **Comitê** (multi-agent). No modo **Rápido**, o modelo selecionado é chamado diretamente via `chat_service.dispatch_turn()` — sem LangGraph, sem Agent SDK, sem router. Isso é proposital: modo rápido = resposta direta do modelo.

### Decisão Arquitetural (8ª revisão): Two-Track com contrato explícito

**Diretriz**: manter 2 trilhas, mas eliminar duplicação de lógica.

| Trilha | Objetivo | Contrato |
|--------|----------|----------|
| **Quick (lite)** | Baixa latência, chat interativo | Resposta rápida, limites curtos, sem workflow longo |
| **Executor dedicado (full agentic)** | Casos longos/auditáveis | Policies completas (PermissionManager, routing central, checkpoint/HIL quando aplicável) |

**Ajuste mínimo recomendado**:
1. Definir contrato explícito no backend e UI: `quick = lite`, `executor = full agentic`.
2. Centralizar permissões em um único serviço (`PermissionManager`) para todos os caminhos.
3. Centralizar política de routing (`provider compatibility`, fallback, limites por executor).
4. Expor no UI qual caminho está ativo (`lite` vs `full`).

### Evolução proposta para o modo ⚡ Rápido (sem quebrar o fluxo atual)

| Seleção no modo Rápido | Caminho |
|------------------------|---------|
| **Modelo normal** | Mantém `dispatch_turn()` direto (comportamento atual) |
| **`claude-agent` / `openai-agent` / `google-agent`** | Chamar executor dedicado via router em **perfil quick** |
| **Falha no executor dedicado** | Fallback para loop nativo atual do chat |

**Perfil quick do executor dedicado**:
- `max_iterations` baixo (ex: 4-8)
- timeout curto (ex: 15-30s)
- sem HIL obrigatório
- checkpoint opcional (default OFF no Rápido)

**Pré-requisitos para ativar com segurança**:
1. Unificar permissões (hoje fragmentadas entre loops nativos, MCP e executores).
2. Padronizar eventos SSE entre chat e executores dedicados.
3. Injetar contexto/DB corretamente no caminho do router quando chamado pelo chat rápido.
4. Aplicar regra de provider compatibility no ponto único de routing.

### Cut objetivo de 1 semana (sem refatoração grande)

| Dia | Entrega |
|-----|---------|
| D1 | Feature flag `QUICK_AGENT_BRIDGE_ENABLED` + contrato `lite/full` no metadata SSE |
| D2 | Bridge: `*-agent` no Rápido chama `OrchestrationRouter` com perfil quick |
| D3 | Fallback robusto: erro no executor dedicado retorna ao loop nativo sem quebrar stream |
| D4 | Permission gate único no caminho quick-agent (reuse `PermissionManager`) |
| D5 | UI badge `Lite`/`Full`, métricas e smoke tests end-to-end |

> **Critério de aceite**: modelo normal mantém latência atual no modo Rápido; `*-agent` no modo Rápido passa pelo executor dedicado com fallback transparente em caso de erro.

### Nível 2 — Executors dentro do Comitê (`OrchestrationRouter`)

Quando o frontend envia um job no modo 👥 Comitê, o `OrchestrationRouter` decide entre **5 executors**:

| Executor | Seleção | Base Model (target) | Base Model (atual legacy) | Fluxo |
|----------|---------|--------------------|--------------------------|----|
| **Claude Agent** | `claude-agent` selecionado | `claude-opus-4-6` (Opus 4.6) | `claude-sonnet-4-20250514` via env | `ClaudeAgentExecutor.run()` — loop agentic com tools, Claude Agent SDK |
| **OpenAI Agent** | `openai-agent` selecionado | `gpt-5.2` | `gpt-4o` hardcoded | OpenAI Agents SDK — tools, permissions, checkpoints |
| **Google Agent** | `google-agent` selecionado | `gemini-3-pro-preview` (Pro) | `gemini-3-flash-preview` via env | Google ADK — Vertex AI + tools jurídicas unificadas |
| **LangGraph** | Modelos normais (sem agent) OU `mode="minuta"` | Qualquer | — | 27+ nós: outline→research→debate→audit→finalize. **Checkpoint/pause/resume nativo**: state persistido entre nós, interrupt em HIL (outline approval), resume após feedback do usuário. Vantagem crítica para workflows longos (>10min) |
| **Parallel** | Agent + modelos normais juntos | Agent como primário | — | Agent + Debate em paralelo, LLM Judge merge |

**Registry de modelos** (`config/models.ts`):
- **26+ modelos regulares**: GPT-5.2, GPT-5, Claude 4.5 Opus/Sonnet/Haiku, Gemini 3 Pro/Flash, Grok 4/4.1, Sonar, Llama 4, etc.
- **3 agents**: `claude-agent` (Anthropic SDK), `openai-agent` (OpenAI SDK), `google-agent` (Google ADK)
- Cada agent tem `isAgent: true`, `baseModel`, e `ExecutorType` dedicado no router
- Agents habilitáveis via env: `CLAUDE_AGENT_ENABLED`, `OPENAI_AGENT_ENABLED`, `GOOGLE_AGENT_ENABLED`

**Mapeamento no router** (`router.py:119-123`):
```python
AGENT_TO_EXECUTOR = {
    "claude-agent":  ExecutorType.CLAUDE_AGENT,
    "openai-agent":  ExecutorType.OPENAI_AGENT,
    "google-agent":  ExecutorType.GOOGLE_AGENT,
}
```

### Consequência para o plano

Cada feature precisa mapear para **ambos os níveis**: o modo do frontend (⚡/⚖️/👥/📄) e, dentro do Comitê, o executor escolhido pelo Router:

| Nível | Escopo | Onde aplicar features |
|-------|--------|----------------------|
| **⚡ Rápido** | `chat_service.dispatch_turn()` | Prompt caching, skills injection, tool calling direto |
| **⚖️ Comparar** | `startMultiModelStream()` | N streams independentes, consolidação opcional |
| **👥 Comitê → Claude Agent** | `ClaudeAgentExecutor` (Anthropic SDK) | Skills no system prompt, delegate_subtask, permissions |
| **👥 Comitê → OpenAI Agent** | OpenAI Agents SDK executor | Skills no system prompt, tools jurídicas, checkpoints |
| **👥 Comitê → Google Agent** | Google ADK executor (Vertex AI) | Skills no system prompt, tools Vertex, ADK features |
| **👥 Comitê → LangGraph** | Workflow 27+ nós | Skills no planner, ClaudeAgentNode, CPC compliance node |
| **👥 Comitê → Parallel** | Agent + Debate + Judge | Skills em ambos os braços, validação dupla |
| **📄 Canvas write** | Legacy flow | Mínimo de mudanças |

> **Nota sobre agents**: O plano foca no Claude Agent SDK (Fase 1-3) mas a arquitetura suporta 3 agents. Features como Skills, Permissions e Tools devem ser agnósticas ao provider — implementar para o Claude Agent primeiro e depois adaptar para OpenAI/Google agents usando os mesmos contratos (`SkillMatcher`, `PermissionManager`, `unified_tools`).

### Decisão: Model Registry — Atualização para modelos mais recentes

> **Diretriz**: Usar **todos** os modelos disponíveis no registry de chat. Para os **agents**, usar os modelos **mais atuais** de cada provider.

#### Agents — atualizar `api_model` (backend `model_registry.py`)

| Agent | Atual (LEGACY) | Novo (MAIS ATUAL) | Env var |
|-------|----------------|-------------------|---------|
| `claude-agent` | `claude-sonnet-4-20250514` (Sonnet 4) | `claude-opus-4-6` (Opus 4.6) | `CLAUDE_AGENT_API_MODEL` |
| `openai-agent` | `gpt-4o` (GPT-4o) | `gpt-5.2` | hardcoded → env var `OPENAI_AGENT_API_MODEL` |
| `google-agent` | `gemini-3-flash-preview` (Flash) | `gemini-3-pro-preview` (Pro) | `GOOGLE_AGENT_API_MODEL` |

#### Agents — atualizar `baseModel` (frontend `models.ts`)

| Agent | Atual | Novo |
|-------|-------|------|
| `claude-agent` | `"claude-4.5-opus"` | `"claude-4.6-opus"` (novo ModelId) |
| `openai-agent` | `"gpt-4o"` | `"gpt-5.2"` |
| `google-agent` | `"gemini-3-pro"` | OK (já correto) |

#### Modelos regulares — ADICIONAR ao registry (ambos frontend + backend)

**Anthropic** (novo):
| ID frontend | API ID real | Tier |
|-------------|-------------|------|
| `claude-4.6-opus` | `claude-opus-4-6` | high/high |

**OpenAI** (novos):
| ID frontend | API ID real | Tier |
|-------------|-------------|------|
| `gpt-5.3-codex` | `gpt-5.3-codex` | high/high |
| `gpt-5.2-pro` | `gpt-5.2-pro` | high/high |
| `gpt-5.2-codex` | `gpt-5.2-codex` | high/high |
| `gpt-5.1` | `gpt-5.1` | medium/medium_high |
| `gpt-5.1-codex` | `gpt-5.1-codex` | medium/medium_high |
| `gpt-5.1-codex-mini` | `gpt-5.1-codex-mini` | low/medium |
| `gpt-5-nano` | `gpt-5-nano` | low/low |

> **Nota**: `gpt-5.2-instant` no frontend atual possivelmente deve ser renomeado para `gpt-5.2-codex` (alinhar com nomenclatura oficial OpenAI). Verificar equivalência.

#### Modelos Claude — reclassificar

| ID frontend | API atual | Status |
|-------------|-----------|--------|
| `claude-4.5-opus` | `claude-opus-4-5` | **Legacy** (mover para seção legacy ou manter como opção) |
| `claude-4.5-sonnet` | `claude-sonnet-4-5` | **Atual** (manter) |
| `claude-4.5-haiku` | `claude-haiku-4-5` | **Atual** (manter) |
| `claude-4.6-opus` | `claude-opus-4-6` | **Novo — ADICIONAR** |

#### Subagentes — atualizar referências no plano

O `delegate_subtask` usa `claude-haiku-4-5` (correto — Haiku 4.5 é o modelo barato atual). A referência do agent principal muda:
- Antes: "Opus orquestra" → referia-se a Claude 4.5 Opus
- Agora: "Opus 4.6 orquestra, Haiku 4.5 extrai, Sonnet 4.5 redige"

### Fase 0 — Correções de Integridade

| Item | ⚡ Rápido (`dispatch_turn`) | 👥 Comitê — Claude Agent | 👥 Comitê — LangGraph | 👥 Comitê — Parallel |
|------|---------------------------|-------------------------|----------------------|---------------------|
| **0.1 MCP naming** | Afeta MCP tool calling em `dispatch_turn` (se `IUDEX_MCP_TOOL_CALLING=true`) | Afeta executor quando chama tools via MCP | Afeta nós LangGraph que delegam para MCP via tool_handlers | Ambos os braços afetados |
| **0.2 initialize()** | Startup silencia erro — 1ª chamada MCP lenta | Idem | Idem | Idem |
| **0.3 RISK_TO_PERMISSION** | N/A (Rápido não usa `unified_tools` para permissões — chama modelo direto) | Afeta modo raw API: tools HIGH passam sem aprovação | Afeta nós que usam `unified_tools` | Ambos os braços herdaram política permissiva |
| **0.4 delegate_research** | N/A (Rápido não usa delegate_research) | N/A (solo não usa) | Afeta nós que delegam pesquisa paralela — crash | Braço Debate pode crashar |

### Fase 1 — Quick Wins + Segurança

| Item | ⚡ Rápido (`dispatch_turn`) | 👥 Comitê — Claude Agent | 👥 Comitê — LangGraph | 👥 Comitê — Parallel |
|------|---------------------------|-------------------------|----------------------|---------------------|
| **1.1 Prompt Caching** | Aplicável em `dispatch_turn` para Anthropic models: `cache_control` no system instruction entre turns do mesmo thread | `cache_control` em `_call_claude()` — system + RAG cacheados entre iterações | Em cada nó que chama Claude — contexto do state cacheado entre nós | Braço Agent herda do executor; braço Debate herda dos nós |
| **1.2 Doc Size Router** | N/A (Rápido não gera documentos multi-seção — é chat) | Router ativo para requests do Comitê: <100pg → solo; >500pg → LangGraph | Já orquestrado. Router adiciona: >2000pg → multi-pass | Router decide forçar LangGraph-only para >500pg |
| **1.3 Subagentes** | N/A (Rápido não precisa — é chamada direta) | Tool no SDK: Opus 4.6 chama `delegate_subtask(model="claude-haiku-4-5")` | Nó `claude_agent_subtask_node` | Ambos os braços podem delegar para Haiku 4.5 |
| **1.4 DataJud/CNJ** | Disponível se MCP tool calling ativado em `dispatch_turn` | Novo tool em `sdk_tools.py` | Tool via `unified_tools.py` | Ambos os braços via mesma interface |
| **1.5 ABNT citações** | Pós-processamento de citações na resposta do modelo | `verify_citation` tool expandido | Nó `citation_audit` ABNT completa | Judge aplica ABNT no merge |
| **1.6 Unificação Permissões** | `dispatch_turn` tem tool loops nativos (`run_openai_chat_tool_loop`, `run_anthropic_chat_tool_loop`) e MCP tools — mas **sem** `PermissionManager`. Permissões implícitas via `use_native_tools` flag (`chats.py:3446`) e `mcp_enabled` flag (`chats.py:3480`). Migrar para PM: validar tool calls no dispatch_turn antes de executar | SDK: migrar de `permission_mode="default"` para PM. Raw API: migrar dict local para PM | Nós que usam `unified_tools` passam a consultar PM | Todos unificados: mesma política hierárquica |

### Fase 2 — Core Gaps

| Item | ⚡ Rápido | 👥 Comitê — Agent | 👥 Comitê — LangGraph | 👥 Comitê — Parallel |
|------|----------|-------------------|----------------------|---------------------|
| **2.1 Skills** | `SkillMatcher` injeta skill no system instruction de `dispatch_turn` — modelo recebe instruções especializadas mesmo no chat direto | Injeta skill (`tag="skill"`) no system prompt do executor | Skill define quais nós ativar no grafo | Agent recebe skill no prompt, Debate no state |
| **2.2 Agent como nó LangGraph** | N/A (Rápido chama modelo direto) | N/A (já é o modo solo) | `ClaudeAgentNode` wrapa executor como nó do grafo | Braço Agent já é essencialmente um ClaudeAgentNode |
| **2.3 CPC Compliance** | Pós-processamento: validar CPC na resposta do modelo (best-effort) | Tool `validate_cpc_compliance` chamado pelo executor | Nó dedicado `cpc_compliance_check` após draft | Braço Agent tool + braço Debate debate. Judge pondera |
| **2.4 Citation Validator** | Pós-processamento: verificar citações antes de entregar resposta | Subagente Haiku via `delegate_subtask` | Nó `citation_validator` em paralelo com draft | Validação dupla: inline + audit |
| **2.5 Multi-pass >500pg** | N/A (Rápido é chat, não gera docs longos) | Router redireciona para LangGraph | Sub-grafo `multi_pass_processor` | >500pg → LANGGRAPH-only |
| **2.6 LangSmith** | `@trace` em `dispatch_turn` — span por modelo chamado | `@trace` no executor loop | `@trace` por nó + workflow parent | Trace com 2 branches + judge |

### Fase 3 — Features Avançadas

| Item | ⚡ Rápido | 👥 Comitê — Agent | 👥 Comitê — LangGraph | 👥 Comitê — Parallel |
|------|----------|-------------------|----------------------|---------------------|
| **3.1 Skill Builder UI** | Skills criadas também funcionam no Rápido (injeta no system instruction) | Skills no executor solo | Skills no planner LangGraph | Skills universais |
| **3.2 Dynamic Skill Detection** | Analisa histórico de chats Rápido → sugere skills | Analisa sessões solo | Analisa traces LangGraph | Combina ambos |
| **3.3 MCP Server Standalone** | `dispatch_turn` acessa via MCP se habilitado | Executor acessa direto | Nós acessam via `mcp_tool_call` | Ambos os braços |
| **3.4 Fan-out de Agents** | N/A (chat direto) | N/A (um agent) | `parallel_agents_node` | Sub-fan-out |
| **3.5 JusBrasil** | Tool disponível se MCP tool calling ativado | Tool no SDK | Tool via `unified_tools` | Ambos os braços |

### Fase 4 — Operacionalização

| Item | ⚡ Rápido | 👥 Comitê — Agent | 👥 Comitê — LangGraph | 👥 Comitê — Parallel |
|------|----------|-------------------|----------------------|---------------------|
| **4.1 Canary Rollout** | Feature flags controlam skills/tools disponíveis no chat por tenant | Feature flags por executor | Feature flags por nó do grafo | Flag habilita/desabilita modo |
| **4.2 SLOs/Métricas** | Latência do modelo, custo por turn, TTFT | Latência do loop, custo por iteração | Latência por nó, custo workflow | Max dos 2 braços + judge |
| **4.3 Circuit Breaker MCP** | Se MCP falha em `dispatch_turn` → chat continua sem tools | Executor usa tools locais | Nós degradam para RAG local | Degradam independentemente |
| **4.4 Auditoria** | Log do chat turn com modelo usado e custo | Log de tool calls com decisão | Log de nós com I/O | Log unificado dos braços |
| **4.5 Quotas** | Limite de tokens/turns por período | Limite de iterações/tokens | Limite de nós + custo total | Limite mais restritivo (2x) |

### Regras de Routing por Modo

> **Escopo**: O `OrchestrationRouter` só é consultado no modo **👥 Comitê** (multi-agent). No modo **⚡ Rápido**, o modelo é chamado diretamente por `chat_service.dispatch_turn()` — sem router, sem LangGraph, sem Agent SDK.

#### Estado Atual (`router.py:180-247`) — só modo Comitê

```
OrchestrationRouter.route() — lógica REAL atual:

Input: {selected_models, mode}
Chamado APENAS pelo endpoint /jobs (modo Comitê / multi-agent)

1. Se mode == "minuta":
   → LANGGRAPH (sempre — workflow completo obrigatório)

2. Se algum agent selecionado (in AGENT_MODELS):
   a. Se agent habilitado + sem outros modelos:
      → AGENT_TO_EXECUTOR[agent] (ex: CLAUDE_AGENT)
   b. Se agent habilitado + outros modelos não-agent:
      → PARALLEL (se PARALLEL_EXECUTION_ENABLED, senão só agent)
   c. Se agent desabilitado:
      → LANGGRAPH (fallback com modelos restantes ou gemini-3-flash)

3. Apenas modelos normais (sem agents):
   → LANGGRAPH
```

#### Proposta de Evolução (pós Fase 1-2) — ainda só modo Comitê

```
OrchestrationRouter.route() — lógica PROPOSTA:

Input: {selected_models, mode, document_size, skill_matched}

1. (NOVO) Se document_size > 500pg:
   → LANGGRAPH (multi-pass obrigatório)

2. Se mode == "minuta":
   → LANGGRAPH (mantém lógica atual)

3. (NOVO) Se skill_matched AND skill.prefer_workflow == true:
   → LANGGRAPH (skill define que precisa do workflow completo)

4. Se agent selecionado + habilitado:
   a. Só agent → AGENT_TO_EXECUTOR[agent] (CLAUDE_AGENT/OPENAI_AGENT/GOOGLE_AGENT)
   b. Agent + outros → PARALLEL (mantém lógica atual)

5. (NOVO) Se skill_matched AND skill.prefer_agent == true:
   a. Se all-Anthropic (modelos Claude): → CLAUDE_AGENT
   b. Se all-OpenAI (modelos GPT): → OPENAI_AGENT
   c. Se all-Google (modelos Gemini): → GOOGLE_AGENT
   d. Se mix de providers: → PARALLEL ou LANGGRAPH

6. (NOVO) Regra de provider compatibility:
   a. All-Anthropic (claude-agent + modelos Claude) → CLAUDE_AGENT (modo autônomo SDK nativo)
   b. All-OpenAI (openai-agent + modelos GPT) → OPENAI_AGENT (SDK nativo)
   c. All-Google (google-agent + modelos Gemini) → GOOGLE_AGENT (ADK nativo)
   d. Mix de providers (ex: claude-agent + gemini-3-flash) → PARALLEL ou LANGGRAPH
      (SDKs de agent não suportam tool calling cross-provider nativo)

7. Apenas modelos normais (sem agents, sem skill match):
   → LANGGRAPH (mantém comportamento atual)
```

> **Nota**: Regras 1, 3, 5, 6 são adições propostas. Regras 2, 4, 7 mantêm comportamento atual.
> **Regra 7 NÃO muda o default** — o modo Rápido já é "direto ao modelo" por design do frontend. Não há necessidade de mudar o default do Comitê de LANGGRAPH para CLAUDE_AGENT.
> **Regra 6 (provider compatibility)** — garante que SDKs nativos só processam modelos do próprio provider. Mix cross-provider vai para PARALLEL/LANGGRAPH que são provider-agnostic.
> **Diagrama abaixo**: mostra `CLAUDE_AGENT` como exemplo visual; o mesmo padrão vale para `OPENAI_AGENT` e `GOOGLE_AGENT`.

### Diagrama de Fluxo Dual-Mode

```
                      User Request
                           │
                    ┌──────▼──────┐
                    │  Skill      │
                    │  Matcher    │── skill.md injected
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Orchestration│
                    │ Router       │
                    └──┬───┬───┬──┘
                       │   │   │
         ┌─────────────┘   │   └─────────────┐
         ▼                 ▼                  ▼
  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
  │ CLAUDE_AGENT│  │  LANGGRAPH  │  │   PARALLEL   │
  │    (Solo)   │  │ (Workflow)  │  │  (Agent+Deb) │
  │             │  │             │  │              │
  │ skill in    │  │ skill →     │  │ skill in     │
  │ system      │  │ node        │  │ both arms    │
  │ prompt      │  │ routing     │  │              │
  │             │  │             │  │  ┌────┐┌───┐ │
  │ delegate_   │  │ Claude      │  │  │Agnt││Deb│ │
  │ subtask()   │  │ Agent Node  │  │  └──┬─┘└─┬─┘ │
  │ for cheap   │  │ inside      │  │     └──┬──┘  │
  │ tasks       │  │ graph       │  │     Judge    │
  │             │  │             │  │              │
  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘
         │                │                │
         └────────────────┼────────────────┘
                          ▼
                   ┌─────────────┐
                   │  SSE Stream │
                   │  + LangSmith│
                   │  Traces     │
                   └─────────────┘
```

---

## 6. Arquitetura Alvo (Pós-Implementação)

```
                          ┌─────────────────────┐
                          │   Frontend (Next.js) │
                          │                     │
                          │  Chat + Canvas +     │
                          │  Skill Builder UI +  │
                          │  Workflow Builder    │
                          └──────────┬──────────┘
                                     │ SSE
                          ┌──────────▼──────────┐
                          │   Orchestration      │
                          │   Router             │
                          │                     │
                          │ criteria:            │
                          │ - model selection    │
                          │ - document size      │
                          │ - skill match        │
                          │ - task type          │
                          └──┬──────┬──────┬────┘
                             │      │      │
              ┌──────────────▼┐  ┌──▼──┐  ┌▼──────────────┐
              │ Claude Agent   │  │Lang │  │ Parallel       │
              │ SDK Executor   │  │Graph│  │ Executor       │
              │                │  │     │  │                │
              │ ┌────────────┐ │  │27+  │  │ Agent + Debate │
              │ │ Skills     │ │  │nodes│  │ + LLM Judge    │
              │ │ Injector   │ │  │     │  │                │
              │ └────────────┘ │  │┌───┐│  └────────────────┘
              │ ┌────────────┐ │  ││SDK││
              │ │ Subagent   │ │  ││Node│  ← Claude Agent
              │ │ Delegator  │ │  │└───┘│    como nó LangGraph
              │ │ (Haiku)    │ │  │     │
              │ └────────────┘ │  └─────┘
              └───────┬────────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
    ┌────▼────┐ ┌─────▼─────┐ ┌───▼────┐
    │SDK Tools│ │MCP Server │ │Skills  │
    │(7+3new) │ │(standalone)│ │Registry│
    │         │ │            │ │        │
    │search_* │ │jusbrasil   │ │5 built │
    │verify_* │ │datajud     │ │-in +   │
    │delegate │ │cpc_valid   │ │user    │
    │datajud  │ │vector_srch │ │created │
    └─────────┘ └────────────┘ └────────┘
```

---

## 7. Estimativa de Custo/Benefício

### Economia com Prompt Caching (Fase 1.1)
- Documento de 30 seções: ~30 chamadas Anthropic
- System prompt + RAG context: ~5000 tokens cada
- Sem cache: 30 × 5000 = 150.000 tokens input redundante
- Com cache: 5000 (1ª chamada) + 29 × ~500 (cache hit) = 19.500 tokens
- **Economia: ~87% nos tokens de sistema**

### Economia com Subagentes Haiku (Fase 1.3)
- Metadata extraction com Opus: ~$0.50 (100K tokens)
- Metadata extraction com Haiku: ~$0.01 (50K tokens)
- **Economia: ~98% por delegação simples**

### ROI por Fase

| Fase | Investimento | Retorno |
|------|-------------|---------|
| Fase 0 | 48h dev | Elimina 4 bugs de runtime, MCP funcional, segurança corrigida |
| Fase 1 | 2-3 semanas dev | Redução 40-60% custo API + routing inteligente + permissões unificadas |
| Fase 2 | 4-6 semanas dev | Skills reutilizáveis + compliance automático + observability |
| Fase 3 | 6-10 semanas dev | Skill marketplace + detecção patterns + MCP standalone |
| Fase 4 | Contínuo | Rollout seguro, métricas, quotas, auditoria compliance |

---

## 8. Dependências e Pré-Requisitos

### Fase 0
- Nenhuma dependência externa — apenas correções em código existente
- Testes unitários para cada fix (mock do MCP Hub)

### Fase 1
- `claude-agent-sdk>=0.1.26` (já no requirements.txt)
- `anthropic>=0.50.0` com suporte a `cache_control` (verificar versão). **Atenção**: system prompt usa campo separado `system=` (não messages) — cache_control via content blocks array
- Decisão arquitetural: como o `PermissionManager` se comunica com **ambos** os caminhos (SDK + raw API). Hoje nenhum dos dois usa PM — raw API usa dict local (`executor.py:130`), SDK usa `permission_mode="default"` hardcoded

### Fase 2
- LangSmith API key (criar conta)
- Definição dos 5 skills builtin (conteúdo jurídico com advogado). **Nota**: skills do usuário reutilizam `LibraryItem(type=PROMPT, tag="skill")` — distinto de `tag="agent_template"` (ver Seção 3.2)
- Regras CPC para validate_cpc_compliance (base de conhecimento)

### Fase 3
- FastMCP (`pip install fastmcp`) para MCP Server standalone
- API JusBrasil (verificar disponibilidade e termos)
- Celery/Redis para worker de pattern detection

### Fase 4
- Feature flag service em 5 camadas (ver item 4.1): global, auto-detect, por nó, limites, analytics
- Prometheus/Grafana ou equivalente para métricas e SLOs
- Política de retenção de audit logs definida com compliance
- MCP contracts: vault para segredos por tenant, ACL config por ambiente

---

## 8.5 Políticas Operacionais

### 8.5.1 Perfil de Segurança por Ambiente

O executor de agents tem comportamento diferente dependendo do contexto de deploy:

| Política | Web UI (browser) | Server/API (backend job) |
|----------|-----------------|-------------------------|
| **Bash/Shell** | **DENY** sempre — nenhum agent executa comandos shell via UI | ALLOW com sandbox (cwd restrito, timeout 30s, sem acesso rede) |
| **Filesystem** | **DENY** — sem acesso a FS do servidor | ALLOW com sandbox (read-only em paths permitidos, write apenas em `/tmp/iudex/{tenant}/`) |
| **Network egress** | Allowlist: APIs jurídicas (DataJud, DJEN, JusBrasil) + LLM providers | Idem + endpoints internos |
| **Tool validation** | Validar **antes** de executar: `PermissionManager.check()` mesmo no `dispatch_turn` (corrige R5-1) | Idem, com log de auditoria |
| **Max iterations** | 10 (limit hard para evitar loops infinitos) | 25 (jobs longos como minutas) |
| **Timeout total** | 120s (chat rápido) | 600s (geração de documentos) |

> **Implementação**: `SecurityProfile` enum (`WEB`, `SERVER`) injetado no executor via request context. O `PermissionManager` consulta o perfil antes de cada tool call.

### 8.5.2 Migração "Add, Don't Replace" (Fallback por Nó)

O rollout de cada nova feature usa o padrão **add, don't replace** — nenhum pipeline existente é removido:

```
Request → Router
           ├─ [feature_flag ON]  → Novo caminho (SDK/Agent)
           │    └─ [falha/timeout] → Fallback imediato para caminho legado
           └─ [feature_flag OFF] → Caminho legado (inalterado)
```

**Regras de fallback**:

| Nível | Trigger de fallback | Ação |
|-------|-------------------|------|
| **Por request** | SDK timeout ou erro 5xx | Retry via raw API path (mesmo modelo, sem SDK features) |
| **Por nó LangGraph** | `ClaudeAgentNode` falha | Fallback para nó LangGraph nativo (sem agent loop) |
| **Por executor** | `CLAUDE_AGENT` executor falha N vezes seguidas | Circuit breaker → `LANGGRAPH` como fallback |
| **Global** | Kill switch via feature flag global | Todo tráfego volta para pipeline legado |

> **Métrica de saúde**: Se fallback rate > 5% em 15min, alerta automático + auto-disable da feature flag do nó afetado.

### 8.5.3 Limites Formais de Subagentes

| Limite | Valor | Justificativa |
|--------|-------|---------------|
| **Max profundidade de delegação** | 1 nível (agent → subagent, sem sub-sub) | Evita recursão infinita e explosion de custo |
| **Isolamento de contexto** | Subagente recebe APENAS o `task` string + tools explícitos. NÃO herda conversation history do parent | Segurança (evita leak de dados entre contextos) + economia de tokens |
| **Max subagentes simultâneos** | 3 por request (configurável por tenant via quotas) | Controle de concorrência e custo |
| **Budget cap por delegação** | 10K tokens output por subagente (configurável) | Evita que subagente Haiku gere respostas excessivas |
| **Timeout por subagente** | 30s (Web) / 60s (Server) | Subagente não deve demorar mais que o parent |
| **Modelo permitido para subagente** | Apenas modelos com `cost_tier: "low"` ou `"medium"` **do mesmo provider do parent**. Claude Agent → só Anthropic (Haiku 4.5, Sonnet 4.5). OpenAI Agent → só OpenAI (GPT-5 Mini, GPT-5). Google Agent → só Google (Flash, Pro). **Não misturar providers em subagentes** — cada SDK tem seu próprio formato de tool calling, permissions e streaming | Compatibilidade técnica (SDK-specific) + isolamento de billing por provider |

### 8.5.4 Checkpoint / Pause / Resume (LangGraph)

Workflows longos (minutas >10min) precisam de persistência de estado entre nós. O LangGraph oferece isso nativamente:

| Capacidade | Implementação | Onde atua |
|------------|--------------|-----------|
| **Checkpoint** | `SqliteSaver` ou `PostgresSaver` — state persistido após cada nó | Todos os nós do workflow LangGraph |
| **Interrupt** | `interrupt_before=["outline_approval", "final_review"]` — pausa execução e aguarda input | Nós HIL: outline approval, section review, final approval |
| **Resume** | `graph.invoke(None, config={"thread_id": job_id})` — retoma do último checkpoint | Após feedback do usuário (aprovar/rejeitar/editar outline) |
| **Retry parcial** | Se nó falha, resume do último checkpoint sem reprocessar nós anteriores | Nós de pesquisa (RAG), nós de API externa |
| **Time-travel** | Replay de execução a partir de qualquer checkpoint anterior | Debug, auditoria, rollback de decisão |

**Por executor**:

| Executor | Checkpoint nativo? | Alternativa |
|----------|--------------------|-------------|
| **LangGraph** | **SIM** — `SqliteSaver`/`PostgresSaver` builtin | — |
| **Claude Agent** | NÃO — SDK não persiste estado entre iterações | Implementar: salvar `messages[]` + `tool_results[]` no banco entre iterações do loop. Resume = recarregar e continuar |
| **OpenAI Agent** | Parcial — Agents SDK tem `checkpoints` mas não resume cross-session | Implementar: serializar state para banco, restore via API |
| **Google Agent** | NÃO — ADK não tem checkpoint nativo | Idem Claude Agent |
| **Parallel** | Via LangGraph (braço Debate) + manual (braço Agent) | Combinar ambos |

> **Decisão**: Para workflows que precisam de pause/resume confiável, **preferir LangGraph** como executor (regra de routing). Agent executors são melhores para tarefas autônomas curtas (< 5min) que não precisam de checkpoint intermediário.

### 8.5.5 Citação com Escolha de Estilo

O plano atual é ABNT-centric. Expandir para suportar múltiplos sistemas de citação fim-a-fim, incluindo padrões internacionais:

#### Sistemas Brasileiros

| Estilo | Uso principal | Formato exemplo |
|--------|--------------|-----------------|
| **ABNT NBR 6023** | Petições, pareceres acadêmicos, trabalhos científicos | `SILVA, João. Título. Local: Editora, 2024. p. 15.` |
| **Forense BR** | Citação de jurisprudência, decisões judiciais brasileiras | `STF, RE 123.456, Rel. Min. Fulano, j. 01/01/2024, DJe 15/01/2024` |

#### Sistemas Americanos

| Estilo | Uso principal | Formato exemplo |
|--------|--------------|-----------------|
| **Bluebook** | Padrão dominante em law reviews, cortes federais e estaduais dos EUA | `Smith v. Jones, 500 U.S. 100, 105 (2024).` |
| **APA 7th** | Ciências sociais, psicologia jurídica, interdisciplinar | `Silva, J. (2024). Título do artigo. *Journal*, *12*(3), 15–20.` |
| **Chicago (notes)** | Humanidades, história do direito, livros acadêmicos | `João Silva, *Título* (São Paulo: Editora, 2024), 15.` |
| **ALWD** | Alternativa ao Bluebook em legal writing courses | Similar ao Bluebook com simplificações de formatação |
| **Harvard** | Amplamente usado em universidades (EUA, UK, Austrália, Brasil). Popular em direito comparado e artigos acadêmicos | `Silva, J. (2024) *Título*. São Paulo: Editora, p. 15.` (autor-data, sem footnotes) |

#### Sistemas Europeus

| Estilo | Uso principal | Formato exemplo |
|--------|--------------|-----------------|
| **OSCOLA** | Padrão Oxford — Reino Unido, Commonwealth | `Silva, *Título* (Editora 2024) 15.` (footnotes, sem vírgula antes do ano) |
| **ECLI** | Identificador europeu de jurisprudência (EU/CJEU/ECHR) | `ECLI:EU:C:2024:123` |
| **Vancouver** | Citações médico-legais, perícias, laudos técnicos | `Silva J. Título. Journal. 2024;12(3):15-20.` |

#### Sistemas Simplificados

| Estilo | Uso principal | Formato exemplo |
|--------|--------------|-----------------|
| **Inline** | Referências rápidas em chat, respostas curtas | `(Silva, 2024, p. 15)` |
| **Numérico** | Notas de rodapé numeradas, estilo tribunal | `[1] SILVA, João. Título...` |

**Fluxo**:
1. **UI**: Dropdown `citation_style` no `MinutaSettingsDrawer` (agrupado: BR / Americano / Europeu / Simples)
2. **Prompt**: `SkillMatcher` injeta instrução de estilo no system prompt com regras específicas do sistema escolhido
3. **Subagente validador**: `citation_validator_agent` recebe o estilo e valida conformidade (cada estilo tem suas regras de ordenação, pontuação, itálico)
4. **Post-processing**: `format_reference(style=)` despacha para formatter específico
5. **Fallback**: Se formatter específico não implementado ainda → usa regras genéricas do grupo + warning no output

**Arquivos por estilo**:
```
citations/
├── base.py                    # Interface CitationFormatter
├── abnt_formatter.py          # ABNT NBR 6023 (existente, expandir)
├── abnt_classifier.py         # Classificador ABNT (existente)
├── forense_br_formatter.py    # Jurisprudência brasileira
├── bluebook_formatter.py      # Bluebook (US)
├── apa_formatter.py           # APA 7th
├── chicago_formatter.py       # Chicago notes
├── harvard_formatter.py       # Harvard (autor-data)
├── oscola_formatter.py        # OSCOLA (UK)
├── ecli_formatter.py          # ECLI (EU)
├── vancouver_formatter.py     # Vancouver (médico-legal)
├── inline_formatter.py        # Inline simples
└── numeric_formatter.py       # Notas numeradas
```

> **Rollout**: ABNT (default, Fase 1) → Forense BR + Bluebook + Harvard (Fase 2) → APA + OSCOLA + Chicago (Fase 3) → Vancouver + ECLI + restantes (Fase 4). Total: 12 estilos. Cada formatter é independente — implementar sob demanda conforme clientes solicitam.

### 8.5.6 Adaptive Thinking (Claude Opus 4.6)

**Correção de escopo**: o alvo é **Claude Opus 4.6** (não Opus 4.5).

No Opus 4.6, o comportamento adaptativo é automático **quando** o campo `thinking` é habilitado na API.  
Implementação recomendada:

```python
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=16000,
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},
    messages=[{"role": "user", "content": prompt}],
)
```

#### Política de `effort` por contexto (Iudex)

| Contexto | Effort recomendado | Regra |
|----------|--------------------|-------|
| **Análise jurídica complexa** (mérito, estratégia, peças longas) | `high` ou `max` | Priorizar qualidade e profundidade |
| **Chat rápido com `claude-agent`** | `medium` (default) | Balancear latência/custo |
| **Subtarefas/subagentes** (extração, classificação, parsing) | `low` ou `medium` | Reduzir custo e tempo |

#### Diretrizes operacionais

1. `thinking={"type":"adaptive"}` deve ser ligado explicitamente no caminho Opus 4.6.
2. `effort="max"` é reservado para casos críticos e pode ser controlado por feature flag/tenant.
3. Para modelos sem suporte a adaptive thinking, manter fallback para estratégia legada de reasoning.
4. Em streaming, manter compatibilidade com eventos de thinking e versão resumida para UI.
5. Monitorar custo/tokens por effort no observability para ajuste fino por perfil.

#### Compatibilidade com versão anterior

- **Opus 4.6**: usar adaptive thinking + effort dinâmico.
- **Opus 4.5**: manter modo legado (sem depender de adaptive thinking nativo).

## 8.6 Skill Builder — Prompt-to-Skill (Detalhes Técnicos)

### 8.6.1 Schema SkillV1 (JSON Schema + Pydantic v2)

```
schemas/skills.py → SkillV1(BaseModel)
```

**Campos obrigatórios**:

| Campo | Tipo | Validação |
|-------|------|-----------|
| `name` | `str` | Pattern `^[a-z0-9-]{3,64}$` |
| `description` | `str` | 20-300 chars |
| `version` | `str` | Semver `^\d+\.\d+\.\d+$` |
| `audience` | Enum | `beginner` / `advanced` / `both` |
| `triggers` | `List[str]` | 3-12 itens, unique, 3-80 chars cada |
| `tools_required` | `List[str]` | 1-20 itens, unique |
| `tools_denied` | `List[str]` | Default `["Bash"]` |
| `subagent_model` | `str` | Default `"claude-haiku-4-5"` |
| `prefer_workflow` | `bool` | Não pode ser `true` junto com `prefer_agent` |
| `prefer_agent` | `bool` | Default `true` |
| `citation_style_default` | Enum | 12 estilos: `abnt` / `forense_br` / `bluebook` / `harvard` / `apa` / `chicago` / `oscola` / `ecli` / `vancouver` / `inline` / `numeric` / `alwd` |
| `output_format` | Enum | `chat` / `document` / `checklist` / `json` |
| `instructions` | `str` | Min 200 chars, deve conter seções "instructions" e "output" |
| `guardrails` | `List[str]` | Min 1 item |
| `examples` | `List[{prompt, expected_behavior}]` | 2-10 itens |

**Cross-validations**: `tools_required ∩ tools_denied = ∅`, `!(prefer_workflow && prefer_agent)`

### 8.6.2 Endpoints

| Endpoint | Descrição | Input principal | Output principal |
|----------|-----------|-----------------|------------------|
| `POST /api/v1/skills/generate` | Diretrizes do usuário → draft de skill | `GenerateSkillRequest` (title, objective, user_examples[3-10], negative_examples, audience, tools_allowed) | `GenerateSkillResponse` (draft_id, skill SkillV1, raw_markdown, lint_preview com score 0-100, suggested_tests) |
| `POST /api/v1/skills/validate` | Valida schema, segurança, roteamento | `ValidateSkillRequest` (skill SkillV1, test_prompts {positive[], negative[]}, strict) | `ValidateSkillResponse` (valid, quality_score 0-1, TPR/FPR, security violations, improvements[]) |
| `POST /api/v1/skills/publish` | Publica draft → `LibraryItem(tag="skill")` | `PublishSkillRequest` (draft_id, activate, visibility, if_match_version) | `PublishSkillResponse` (skill_id, status, version, indexed_triggers count) |

### 8.6.3 Pipeline do Construtor

```
1. Coletar         → Diretrizes/prompts do usuário (wizard ou form)
2. Inferir triggers → LLM analisa exemplos + título → sugere 3-12 triggers
3. Gerar draft     → LLM gera frontmatter YAML + instruções estruturadas
4. Lint/Validar    → SkillV1 schema validation + security check (tools_denied)
5. Simular         → 5 prompts (3 positivos, 2 negativos) → TPR/FPR
6. Score           → Qualidade 0-100 (triggers, examples, guardrails, segurança)
7. Publicar        → Upsert LibraryItem(type=PROMPT, tag="skill") + indexar triggers
```

> **Diferença MVP vs Produção**: Step 2 (inferir triggers) no MVP usa substring match; em produção usar embedding similarity via `text-embedding-3-small` ou equivalente. Step 3 no MVP gera instruções template; em produção o LLM recebe os exemplos e gera instruções otimizadas com boas práticas de prompt engineering.

### 8.6.4 Persistência

```
LibraryItem(
    type = LibraryItemType.PROMPT,
    tags = ["skill", "active", "skill_version:1.0.0"],
    name = "petition-analysis",
    description = "--- frontmatter ---\n## Instructions\n...",  # raw markdown completo
    resource_id = "skill:petition-analysis",
    icon = "⚡",
)
```

> **Separação de domínio**: `tag="skill"` vs `tag="agent_template"`. O `SkillMatcher` filtra por `"skill" in tags`. O `template_loader.py` filtra por `"agent_template" in tags`. Nunca misturam.

### 8.6.5 UX — Dois Modos

| Modo | Público | Entrada | Saída |
|------|---------|---------|-------|
| **Wizard** (leigo) | Advogado sem conhecimento técnico | Objetivo em linguagem natural + 3 exemplos de prompts que usaria | Skill pronta, publicada com 1 clique |
| **Editor** (avançado) | Power user / dev | YAML frontmatter + markdown editáveis, diff de versões, teste A/B | Controle total sobre triggers, tools, guardrails |

**Acesso na UI**: `🔖 Bookmark` → `/skill create` (wizard) ou `/skill edit <name>` (editor). Página dedicada `/skills` fora da Ask — sem alterar layout da Ask.

### 8.6.6 Ajustes vs Proposta Original (GPT)

| Aspecto | GPT propôs | Ajuste necessário |
|---------|-----------|-------------------|
| `citation_style` enum | `"abnt" \| "forense"` (2 estilos) | **12 estilos** (ABNT, Forense BR, Bluebook, Harvard, APA, Chicago, OSCOLA, ECLI, Vancouver, Inline, Numérico, ALWD) |
| `DRAFT_CACHE` | Dict em memória | Produção: Redis ou tabela `skill_drafts` com TTL 24h |
| `_build_instructions` | Template estático | Produção: chamada LLM para gerar instruções otimizadas a partir das diretrizes |
| `_extract_triggers` | Substring match | Produção: embedding similarity para matching semântico |
| `_match` no validate | `any(t in low)` | Produção: TF-IDF ou embedding cosine similarity com threshold |

---

## 9. Verificação

### Testes por Fase

**Fase 0 (BLOQUEANTE):**
> Todos os arquivos de teste abaixo **devem ser criados** como parte da implementação.

```bash
# [criar] tests/test_mcp_hub_integration.py
# Verificar que MCP tool_search/tool_call resolvem corretamente
pytest tests/test_mcp_hub_integration.py -v

# Verificar startup sem warnings MCP (não precisa de arquivo novo)
python -c "from app.services.ai.shared.startup import init_ai_services_async; import asyncio; asyncio.run(init_ai_services_async(init_mcp=True))"

# Verificar política de risco (não precisa de arquivo novo)
python -c "
from app.services.ai.shared.unified_tools import RISK_TO_PERMISSION, ToolRiskLevel
from app.services.ai.shared.sse_protocol import ToolApprovalMode
assert RISK_TO_PERMISSION[ToolRiskLevel.MEDIUM] == ToolApprovalMode.ASK
assert RISK_TO_PERMISSION[ToolRiskLevel.HIGH] == ToolApprovalMode.DENY
print('OK: Risk policy correct')
"

# [criar] tests/test_delegate_research.py
# Verificar delegate_research sem TypeError
pytest tests/test_delegate_research.py -v
```

**Fase 1:**
```bash
# [criar] tests/test_prompt_caching.py
pytest tests/test_prompt_caching.py -v

# [criar] tests/test_document_router.py
pytest tests/test_document_router.py -v

# [criar] tests/test_subagent_delegation.py
pytest tests/test_subagent_delegation.py -v

# [criar] tests/test_permission_unification.py
# Verificar que AMBOS os caminhos (SDK + raw API) consultam PermissionManager
pytest tests/test_permission_unification.py -v
```

**Fase 2:**
```bash
# [criar] tests/test_skills_system.py
pytest tests/test_skills_system.py -v

# [criar] tests/test_claude_agent_node.py
pytest tests/test_claude_agent_node.py -v

# Verificar LangSmith traces (não precisa de arquivo novo)
python -c "from langsmith import Client; Client().list_runs(project_name='iudex-legal-ai')"
```

**Fase 4:**
```bash
# [criar] tests/test_feature_flags.py
pytest tests/test_feature_flags.py -v

# [criar] tests/test_mcp_circuit_breaker.py
pytest tests/test_mcp_circuit_breaker.py -v

# [criar] tests/test_user_quotas.py
pytest tests/test_user_quotas.py -v
```

**Teste Manual (todas as fases):**
1. Enviar documento de 50 páginas → deve usar "direct"
2. Enviar documento de 300 páginas → deve usar "rag_enhanced"
3. Enviar documento de 1000 páginas → deve usar "chunked_rag"
4. Digitar "analisar petição" → deve auto-invocar skill `petition-analysis`
5. Verificar LangSmith dashboard → traces com custos por nó
6. Verificar billing → custos menores com Haiku delegations
7. Tool HIGH (ex: bash) → deve ser negado automaticamente
8. MCP server offline → circuit breaker ativa fallback em <5s
9. Usuário basic → não vê skills avançadas (canary rollout)

---

## 10. Plano de UI — Ask Page (Layout-Safe)

> **Princípio**: Nenhum ícone, botão ou elemento de layout novo. Todas as features se encaixam dentro de componentes existentes.
>
> **Nota sobre plano de compactação do ChatInput** (`~/.claude/plans/buzzing-squishing-candy.md`): Existe um plano separado para otimizar o layout do ChatInput (reduzir ~224px → ~142px, mover ContextUsageBar inline, ícones h-8→h-7). Esse plano é de **refinamento visual** (padding, sizing) e **não conflita** com a diretriz acima — não adiciona/remove ícones ou botões, apenas compacta o espaço existente. Pode ser aplicado independentemente, antes ou depois das features deste plano. A diretriz "layout-safe" protege contra **adição de elementos novos**, não contra ajustes de proporção nos existentes.

### 10.1 Inventário Congelado (Baseline)

**Toolbar** (`apps/web/src/app/(dashboard)/ask/page.tsx` — 644 linhas):

```
ESQUERDA:
  [⚡ Zap] Rápido · [👥 Users] Comitê · │ · [👤 User] Normal · [⚖️ Scale] Comparar · AskStreamingStatus

DIREITA:
  [⚖️ Scale] Auditoria · [◧ PanelLeft][⫏ Columns2][▦ LayoutTemplate] · [⛶ Maximize2] ·
  [⚙ Settings2] · [📄 FileText] Novo chat · [✨ Sparkles] Gerar* · [↗ Share2] Share ·
  [⬇ Download] Export · [◨ PanelRight] · [⌃ ChevronUp]
  (* Sparkles só aparece em modo multi-agent)
```

**ChatInput action bar** (`apps/web/src/components/chat/chat-input.tsx` — 2073 linhas):

```
ESQUERDA:
  [⫏ Columns2] · [ModelSelector] · [📄 FileText] Template · [◧ PanelLeftClose/Open] Canvas ·
  │ · [SourcesBadge] · [DeepResearchButton] · [⊞ SlidersHorizontal] Params · │ ·
  [📎 Paperclip] Attach · [🔖 Bookmark] Prompts

DIREITA (ml-auto):
  [ContextUsageBar compact] · [➤ Send]

TEXTAREA: resize-y + [↙ Minimize2] reset (condicional)
```

### 10.2 Features UI por Fase

#### P0/P1 — Encaixe dentro de componentes existentes

| # | Feature | Componente hospedeiro | O que muda internamente | Botão novo? |
|---|---------|----------------------|------------------------|:-:|
| U1 | **MCP health indicators** | `SourcesBadge` tab Conectores (`sources-badge.tsx:1055`) | Adicionar campo `status` ao tipo `McpConnector`, renderizar dot ●/○ ao lado do label. Alimentar via API (circuit breaker Fase 4.3) | NÃO |
| U2 | **Prompt caching savings** | `ContextUsageBar` tooltip (`context-usage-bar.tsx`) | Adicionar linha "💾 Cache: -62K tokens (-74%)" no breakdown do tooltip/popover | NÃO |
| U3 | **Doc size routing feedback** | `AskStreamingStatus` (`ask-streaming-status.tsx`) | Exibir texto de routing: "📄 340pg → RAG Enhanced" como status temporário | NÃO |
| U4 | **Subagent delegation indicator** | `ActivityPanel` dentro de mensagens (`activity-panel.tsx`) | Novo step kind `delegate_subtask` com ícone ⚡ e label "Delegado para Haiku" | NÃO |
| U5 | **Share destravado** | Botão `Share2` existente (`page.tsx:273`) | Adicionar `onClick`: copiar link da conversa para clipboard, toast de confirmação | NÃO |
| U6 | **Export destravado** | Botão `Download` existente (`page.tsx:277`) | Adicionar `onClick`: dropdown DOCX/MD/TXT (reutilizar lógica do export do `ChatInterface`) | NÃO |

#### P2 — Core features sem alterar layout

| # | Feature | Componente hospedeiro | O que muda internamente | Botão novo? |
|---|---------|----------------------|------------------------|:-:|
| U7 | **Skills no SlashMenu** | `SlashCommandMenu` (`slash-command-menu.tsx:329`) | Nova seção "⚡ Skills" com lista de skills disponíveis. Acessível via `/skill` ou clicando 🔖 Bookmark existente | NÃO |
| U8 | **CPC Compliance tab** | `CanvasContainer` Quality tabs (`canvas-container.tsx:981`) | Nova tab "CPC" dentro do grupo Quality: lista de verificações pass/fail/warning com artigo CPC | NÃO |
| U9 | **Citation validation inline** | Editor TipTap dentro do Canvas | Markers/decorations no editor: ✅ verificada, ⚠️ não encontrada — via plugin TipTap | NÃO |
| U10 | **LangSmith trace link** | Footer de `ChatMessage` (`chat-message.tsx`) | Botão discreto "🔍 Trace" na action row existente (Copy, Regenerate, 👍, 👎) | NÃO |

#### P3/P4 — Features avançadas sem alterar layout

| # | Feature | Componente hospedeiro | O que muda internamente | Botão novo? |
|---|---------|----------------------|------------------------|:-:|
| U11 | **Skill Builder** | Nova página `/skills` (fora da Ask page) | Link acessível via SlashMenu: `/skill create` abre nova página | NÃO na Ask |
| U12 | **Skill suggestions** | Toast inline no chat (`ChatInterface`) | Banner discreto: "💡 5 análises similares → Criar skill?" com [Criar][Ignorar] | NÃO |
| U13 | **MCP Server Manager** | `SourcesBadge` tab Conectores | Expandir cards: tools disponíveis, health check, logs recentes | NÃO |
| U14 | **Usage/quotas/economia** | `ContextUsageBar` tooltip/popover | Adicionar seções: "📊 Quota: 47/100", "⚡ Haiku delegations: 3" | NÃO |
| U15 | **Audit trail** | `MinutaSettingsDrawer` (`components/dashboard/minuta-settings-drawer.tsx`) | Nova seção Accordion: log de tool calls com decisão allow/ask/deny, exportar JSON | NÃO |

### 10.3 Correções de Precisão (1ª revisão)

| Erro no plano anterior | Correção |
|---|---|
| "Ask page ~24k linhas" | `ask/page.tsx` = 644 linhas. Complexidade distribuída: `chat-store.ts` (6786), `chat-input.tsx` (2073), `chat-interface.tsx` (984), `sources-badge.tsx` (1119), `minuta-settings-drawer.tsx` (1817) |
| `MinutaSettingsDrawer` em "components/chat" | Caminho correto: `components/dashboard/minuta-settings-drawer.tsx` (import em `page.tsx:6`) |
| "Tool approval precisa de 'lembrar'" | Já existe (`tool-approval-modal.tsx:291-325`): "Apenas desta vez", "Para esta sessão", "Sempre". Não é gap — apenas evoluir UX se necessário |
| `ContextSelector`/`ContextDashboard` listados como Ask page | São da generator page (`/generator`). Não fazem parte da Ask page |
| MCP health "só renderizar status" | `McpConnector` (tipo em `sources-badge.tsx:75`) não tem campo `status`. Precisa: (a) adicionar ao tipo, (b) alimentar via API, (c) renderizar |

---

## 11. Checklist de Preservação de UI/Ícones (Ask Page)

### 11.1 Baseline (não regressão visual)

- [x] Congelar inventário de ícones/botões da Ask toolbar em `apps/web/src/app/(dashboard)/ask/page.tsx`
- [x] Congelar inventário de ícones/botões da ChatInput action bar em `apps/web/src/components/chat/chat-input.tsx`
- [x] Não alterar ordem e variantes dos botões existentes; ajustes de tamanho (`h-* w-*`) somente quando explicitamente previstos no plano de compactação (`~/.claude/plans/buzzing-squishing-candy.md`)
- [x] Não adicionar novo botão visível na toolbar da Ask
- [x] Não adicionar novo botão visível na action bar da ChatInput

### 11.2 Regras de implementação (sem mudar layout)

- [x] `Share` e `Export`: apenas adicionar `onClick` nos botões existentes (`ask/page.tsx:273,277`), sem criar novos
- [x] Skills: integrar via `SlashCommandMenu` (ícone `Bookmark` já existente), sem botão novo
- [x] Uso/quotas/cache: expandir conteúdo do `ContextUsageBar`/tooltip existente, sem novo ícone de toolbar
- [x] Status de roteamento de documento: reutilizar `AskStreamingStatus` (texto/status), sem novo componente fixo
- [x] Subagent activity: mostrar no `ActivityPanel`/eventos de mensagem, sem alterar chrome da página
- [x] Audit trail: colocar dentro de `MinutaSettingsDrawer` existente, sem nova área fixa

### 11.3 Correções de precisão aplicadas (1ª revisão)

- [x] Paths corrigidos: `MinutaSettingsDrawer` está em `components/dashboard`, não `components/chat`
- [x] "Lembrar decisão" no ToolApproval já existe (`tool-approval-modal.tsx:291-325`) — não é gap
- [x] Narrativa corrigida: `ask/page.tsx` = 644 linhas, complexidade em stores/componentes
- [x] `ContextSelector`/`ContextDashboard` removidos da análise (são da generator page)

### 11.4a Correções de precisão técnica (2ª revisão)

| # | Finding | Severidade | Correção aplicada |
|---|---------|:---:|---|
| R2-1 | Raw API não usa `PermissionManager` — usa dict local `DEFAULT_TOOL_PERMISSIONS` (`executor.py:130`). Plano dizia que "raw API usa PM hierárquico". | HIGH | Item 1.6 corrigido: ambos os caminhos (SDK + raw API) ignoram PM e precisam ser migrados |
| R2-2 | `delegate_subtask` usava `async with ClaudeAgentExecutor(...)` mas a classe não é context manager (sem `__aenter__`/`__aexit__`) | HIGH | Exemplo no item 3.1 corrigido: instanciação direta + `async for event in sub.run()` |
| R2-3 | Prompt caching colocava system dentro de `messages[]`. Na API Anthropic, system é campo separado `system=` (`executor.py:630`) | HIGH | Exemplo no item 3.4 corrigido: `kwargs["system"]` como array de content blocks com `cache_control` |
| R2-4 | Routing rules descreviam `len(selected_models) > 1 → PARALLEL` mas lógica real é "agent + não-agent → PARALLEL". Também não existe `mode == "debate"` no router | HIGH | Seção 5 "Regras de Routing" reescrita: estado atual separado de proposta futura |
| R2-5 | `query_datajud` descrito como "não exposto como tool". Na verdade, `consultar_processo_datajud` e `buscar_publicacoes_djen` já existem no Tool Gateway (`tool_registry.py:248-317`) | MEDIUM | Itens 3.5 e 1.4 corrigidos: gap é só no caminho SDK, não no Tool Gateway |
| R2-6 | Skills System proposto como "criar do zero" mas proto-skills existem: `LibraryItem(type=PROMPT, tag="agent_template")` + `template_loader.py` | MEDIUM | Item 3.2 e 2.1 corrigidos: evoluir sistema existente, reutilizar LibraryItem como storage |
| R2-7 | Testes referenciados na Seção 9 não existem (são a criar) | MEDIUM | Adicionado `[criar]` a cada arquivo de teste na Seção 9 |
| R2-8 | Path `langgraph/parallel_research.py` impreciso | LOW | Corrigido para `langgraph/subgraphs/parallel_research.py` |

### 11.4b Correções de precisão técnica (3ª revisão)

| # | Finding | Severidade | Correção aplicada |
|---|---------|:---:|---|
| R3-1 | `delegate_subtask` usava `SSEEventType.CONTENT` (inexistente) e `resolve_tools()` (inexistente). Enum real: `TOKEN`. Método real: `load_unified_tools()` | HIGH | Exemplo reescrito com imports corretos, `SSEEventType.TOKEN`, `load_unified_tools()` |
| R3-2 | Skills e agent templates compartilhavam mesma tag `"agent_template"` sem contrato de domínio distinto | HIGH | Nova tag `"skill"` com schema de frontmatter obrigatório. Tabela de distinção template vs skill adicionada |
| R3-3 | Prompt caching usava `rag_context` e `messages[0]` sem alinhar com assinatura `_call_claude(messages, system_prompt)`. RAG é injetado via `_build_system_prompt()`, não como mensagem | MEDIUM | Exemplo reescrito mostrando 2 blocks no `kwargs["system"]` (base + context), nota sobre separar `_build_system_prompt()` |
| R3-4 | Default routing CLAUDE_AGENT é breaking change (hoje é LANGGRAPH para requests sem agent) | MEDIUM | Resolvido: regra 6 mantém LANGGRAPH como default do Comitê. Modo Rápido já é direto ao modelo por design do frontend |

### 11.4c Correção estrutural (4ª revisão — arquitetura de modos)

| # | Finding | Severidade | Correção aplicada |
|---|---------|:---:|---|
| R4-1 | Plano mapeava 3 modos (Agent Solo / LangGraph / Parallel) mas Iudex tem **4 caminhos de execução**: ⚡ Rápido (`dispatch_turn` direto), ⚖️ Comparar (N modelos paralelos), 👥 Comitê (via Router → 3 executors), 📄 Canvas write (legacy). O `OrchestrationRouter` só atua no modo Comitê. | HIGH | Seção 5 reescrita: tabela com 4 caminhos, "Insight crítico" sobre scope do Router, tabelas de Fase com coluna ⚡ Rápido, regras de routing restritas ao Comitê |

### 11.4d Correções de precisão técnica (5ª revisão)

| # | Finding | Severidade | Correção aplicada |
|---|---------|:---:|---|
| R5-1 | `dispatch_turn` descrito como "sem tools" (linha 411), mas `chats.py` tem tool loops nativos (`run_openai_chat_tool_loop` L4588, `run_anthropic_chat_tool_loop` L5051) e MCP tools (`run_openai_tool_loop` L4634, `run_anthropic_tool_loop` L5095). Flag `use_native_tools` ativada quando modelo é agent-capable (L3446). Flag `mcp_enabled` quando env + request permitem (L3480) | HIGH | Item 1.6 reescrito: dispatch_turn TEM tools (nativos + MCP) mas sem PermissionManager — permissões implícitas via flags |
| R5-2 | Nota antiga na Fase 2 deps (linha 635) dizia `tag="agent_template"` para skills do usuário, contradizendo Seção 3.2 que define `tag="skill"` como tag distinta | HIGH | Corrigido para `tag="skill"` com referência à Seção 3.2 |
| R5-3 | Frontend `AGENT_REGISTRY` mostra `baseModel: "claude-4.5-opus"` e `"gemini-3-pro"` para claude-agent e google-agent, mas backend `model_registry.py` resolve para `claude-sonnet-4-20250514` (L465) e `gemini-3-flash-preview` (L497) via env vars. Apenas openai-agent (gpt-4o) é consistente | MEDIUM | Nota de divergência adicionada ao inventário frontend (Seção 2.2) |

### 11.4 Itens P0/P1 com encaixe seguro

- [x] MCP health: renderizar `status` dos conectores dentro da tab Conectores do `SourcesBadge` (requer adicionar campo ao tipo `McpConnector`)
- [x] Prompt caching savings: incluir métricas no tooltip/popover do `ContextUsageBar`
- [x] Doc size routing feedback: mensagem no stream/status já existente (`AskStreamingStatus`)
- [x] Share/Export destravados: handlers implementados com fallback (clipboard/download)

### 11.5 Critérios de aceite (UI)

- [x] Todos os ícones atuais continuam presentes e no mesmo lugar
- [x] Nenhum botão novo visível foi adicionado na toolbar/chat-input
- [x] Snapshot visual (desktop/mobile) sem diffs estruturais de layout
- [x] Navegação e atalhos existentes (`/`, `@`, anexos, fontes, advanced) inalterados
- [x] Apenas conteúdo interno de popovers/drawers/tabs foi expandido

### 11.6 Referências de código (auditoria)

| Arquivo | O que contém | Linhas |
|---------|-------------|--------|
| `apps/web/src/app/(dashboard)/ask/page.tsx` | Ask page shell, toolbar, layout | 644 |
| `apps/web/src/components/chat/chat-input.tsx` | Input principal, action bar, popovers | 2073 |
| `apps/web/src/components/chat/sources-badge.tsx` | Badge fontes, 4 tabs, MCP conectores | 1119 |
| `apps/web/src/components/chat/context-usage-bar.tsx` | Barra de uso de contexto, tooltip breakdown | 299 |
| `apps/web/src/components/chat/tool-approval-modal.tsx` | Modal aprovação de tools, remember options | 383 |
| `apps/web/src/components/chat/slash-command-menu.tsx` | Menu `/` comandos, prompts, (futuro: skills) | 329 |
| `apps/web/src/components/chat/activity-panel.tsx` | Painel atividade em mensagens | 363 |
| `apps/web/src/components/ask/ask-streaming-status.tsx` | Status streaming no toolbar | 73 |
| `apps/web/src/components/dashboard/minuta-settings-drawer.tsx` | Drawer configurações, 8 seções accordion | 1817 |
| `apps/web/src/components/dashboard/canvas-container.tsx` | Canvas com tabs editor/quality | 981 |
| `apps/web/src/components/chat/chat-message.tsx` | Mensagem individual, action row | 627 |

---

*Documento gerado em 2026-02-05 com base na análise do arquivo "o que significa o neo4j aura agent?.md" e exploração completa do codebase Iudex.*
*Atualizado em 2026-02-05: 5ª revisão — dispatch_turn tools, tag skill vs template, divergência base models agents.*
*Atualizado em 2026-02-05: Model Registry — agents atualizados (Opus 4.6, GPT-5.2, Gemini 3 Pro), modelos novos adicionados ao plano.*
*Atualizado em 2026-02-05: 6ª revisão — segurança por ambiente, fallback "add don't replace", feature flags em camadas, citação multi-estilo, contratos MCP, limites de subagentes.*
*Atualizado em 2026-02-05: 7ª revisão — Skill Builder (Prompt-to-Skill) com schema SkillV1, 3 endpoints, pipeline 7-steps, citation_style expandido para 12 estilos, ajustes vs proposta GPT.*
*Atualizado em 2026-02-05: 8ª revisão — subagentes provider-locked, routing por provider mix (regra 6), checkpoint/pause/resume formalizado por executor.*
*Atualizado em 2026-02-07: 9ª revisão — decisão two-track explícita (`quick = lite`, `executor = full agentic`), proposta de bridge `*-agent` no modo Rápido via executor dedicado (perfil quick), fallback transparente e cut de 1 semana.*
*Atualizado em 2026-02-07: backlog Fase 1 expandido com itens 1.7 (Quick Agent Bridge) e 1.8 (contrato lite/full + fallback + badge UI).*
*Atualizado em 2026-02-07: correção para Claude Opus 4.6 no adaptive thinking (seção 8.5.6) e item 1.9 na Fase 1 para implementação de `thinking={"type":"adaptive"}` com política de effort.*
*Atualizado em 2026-02-05 com Fase 0 (bugfixes), item 1.6 (segurança), Fase 4 (operacionalização) incorporados após code review cruzado Claude×GPT.*
*Atualizado em 2026-02-05 com Seções 10-11 (Plano UI layout-safe + Checklist de preservação) após auditoria de ícones e validação cruzada.*
*Atualizado em 2026-02-05 com correções da 2ª revisão técnica (4 HIGH, 3 MEDIUM, 1 LOW): PermissionManager premissa, delegate_subtask API, prompt caching system field, routing rules estado atual vs proposta, DataJud tools existentes, Skills evolução de LibraryItem, test files [criar], path parallel_research.*
*Atualizado em 2026-02-05 com correções da 3ª revisão técnica (2 HIGH, 2 MEDIUM): SSEEventType.TOKEN + load_unified_tools(), skill tag="skill" com schema distinto, prompt caching alinhado com _call_claude() real, default routing com feature flag.*
*Atualizado em 2026-02-05 com correção estrutural (4ª revisão): 4 caminhos de execução (Rápido/Comparar/Comitê/Canvas), OrchestrationRouter restrito ao Comitê, tabelas de fase com coluna ⚡ Rápido, regra 6 mantém LANGGRAPH como default.*
*Atualizado em 2026-02-05: 5 executors (não 3) — CLAUDE_AGENT + OPENAI_AGENT + GOOGLE_AGENT + LANGGRAPH + PARALLEL. 3 agents no AGENT_REGISTRY com env flags. 26+ modelos regulares. Arquitetura 2 níveis (frontend modes × router executors).*
