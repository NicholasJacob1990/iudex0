# Plano de Implementação: Claude Agent SDK + Melhorias LangGraph

> **Data**: 2026-01-26
> **Versão**: 1.0
> **Status**: Em Implementação

---

## Sumário Executivo

Este documento detalha o plano de implementação para:

1. **Adicionar Claude Agent SDK** como opção de modelo no Iudex
2. **Melhorar o fluxo LangGraph existente** (sem quebrar)
3. **Implementar execução paralela de agentes**
4. **Adicionar features avançadas**: compactação de contexto, permissões granulares, checkpoints/rewind

---

## 1. Visão Geral da Arquitetura

### 1.1 Estado Atual

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARQUITETURA ATUAL                             │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (Next.js)                                              │
│  └── model-selector.tsx → Seleciona GPT/Claude/Gemini            │
│  └── chat-store.ts → Gerencia estado + SSE                       │
│                                                                  │
│  Backend (FastAPI)                                               │
│  └── langgraph_legal_workflow.py → Orquestração única            │
│  └── agent_clients.py → Clients multi-LLM                        │
│  └── debate_subgraph.py → Debate multi-modelo                    │
│  └── job_manager.py → SSE streaming                              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Arquitetura Proposta

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ARQUITETURA NOVA                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Frontend (Next.js)                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ model-selector.tsx                                                   │    │
│  │ ┌─────────────────────────────┬─────────────────────────────────┐   │    │
│  │ │ Modelos (LangGraph)         │ Agentes (SDK)                   │   │    │
│  │ │ ☑ GPT-5.2                   │ ☐ Claude Agent                  │   │    │
│  │ │ ☑ Claude 4.5 Opus           │   └ Autônomo + Tools            │   │    │
│  │ │ ☑ Gemini 2.0 Flash          │                                 │   │    │
│  │ └─────────────────────────────┴─────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ NOVOS COMPONENTES                                                    │    │
│  │ • context-indicator.tsx      (indicador de contexto %)              │    │
│  │ • tool-approval-modal.tsx    (Ask/Allow/Deny)                       │    │
│  │ • checkpoint-timeline.tsx    (histórico de checkpoints)             │    │
│  │ • agent-tools-panel.tsx      (painel de tools do agent)             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Backend (FastAPI)                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    ORCHESTRATION ROUTER                              │    │
│  │                           │                                          │    │
│  │           ┌───────────────┼───────────────┐                          │    │
│  │           ▼               ▼               ▼                          │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐              │    │
│  │  │ LangGraph   │  │ Claude Agent│  │ Parallel        │              │    │
│  │  │ Workflow    │  │ SDK Executor│  │ Orchestrator    │              │    │
│  │  │ (multi-llm) │  │ (só Claude) │  │ (ambos juntos)  │              │    │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ NOVOS SERVICES                                                       │    │
│  │ • context_manager.py         (compactação de contexto)              │    │
│  │ • tool_permissions.py        (sistema Ask/Allow/Deny)               │    │
│  │ • checkpoint_service.py      (checkpoints + rewind)                 │    │
│  │ • claude_agent_executor.py   (wrapper do Agent SDK)                 │    │
│  │ • parallel_executor.py       (execução paralela)                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Estrutura de Arquivos

### 2.1 Backend - Nova Estrutura

```
apps/api/app/services/ai/
├── orchestration/                      # NOVO: Camada de orquestração
│   ├── __init__.py
│   ├── router.py                       # Decide qual executor usar
│   ├── parallel_executor.py            # Executa múltiplos agentes em paralelo
│   └── event_merger.py                 # Merge SSE de múltiplas fontes
│
├── langgraph/                          # REFATORAR: Isolar LangGraph
│   ├── __init__.py
│   ├── workflow.py                     # langgraph_legal_workflow.py refatorado
│   ├── nodes/                          # Nodes existentes
│   │   ├── __init__.py
│   │   ├── outline.py
│   │   ├── research.py
│   │   ├── debate.py
│   │   └── audit.py
│   ├── subgraphs/
│   │   ├── __init__.py
│   │   ├── debate_subgraph.py          # Existente
│   │   └── parallel_research.py        # NOVO: Research paralelo
│   └── improvements/                   # NOVO: Melhorias
│       ├── __init__.py
│       ├── context_manager.py          # Compactação
│       ├── checkpoint_manager.py       # Rewind avançado
│       └── parallel_nodes.py           # Execução paralela de nodes
│
├── claude_agent/                       # NOVO: Claude Agent SDK
│   ├── __init__.py
│   ├── executor.py                     # Wrapper principal do SDK
│   ├── tools/                          # Tools customizados
│   │   ├── __init__.py
│   │   ├── legal_research.py           # Pesquisa jurídica
│   │   ├── document_editor.py          # Edição de docs
│   │   ├── citation_verifier.py        # Verificar citações
│   │   └── rag_search.py               # Busca no RAG
│   ├── permissions.py                  # Sistema de permissões
│   └── mcp_config.py                   # Config MCP
│
├── shared/                             # NOVO: Compartilhado
│   ├── __init__.py
│   ├── tool_registry.py                # Registry unificado de tools
│   ├── context_protocol.py             # Protocolo de contexto (case bundle)
│   └── sse_protocol.py                 # Eventos SSE padronizados
│
└── [arquivos existentes - NÃO MODIFICAR DIRETAMENTE]
    ├── langgraph_legal_workflow.py     # Será importado pelo novo workflow.py
    ├── agent_clients.py
    ├── model_registry.py               # MODIFICAR: Adicionar claude-agent
    └── ...
```

### 2.2 Backend - Novos Models

```
apps/api/app/models/
├── [existentes]
├── tool_permission.py                  # NOVO
├── conversation_summary.py             # NOVO
└── checkpoint.py                       # NOVO (extende WorkflowState)
```

### 2.3 Frontend - Novos Componentes

```
apps/web/src/
├── components/chat/
│   ├── [existentes]
│   ├── context-indicator.tsx           # NOVO
│   ├── tool-approval-modal.tsx         # NOVO
│   ├── checkpoint-timeline.tsx         # NOVO
│   └── agent-tools-panel.tsx           # NOVO
├── stores/
│   └── chat-store.ts                   # MODIFICAR: Adicionar estados
└── config/
    └── models.ts                       # MODIFICAR: Adicionar claude-agent
```

---

## 3. Schemas do Banco de Dados

### 3.1 ToolPermission

```sql
CREATE TABLE tool_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    pattern VARCHAR(500),                    -- Glob pattern para input
    mode VARCHAR(10) NOT NULL CHECK (mode IN ('allow', 'deny', 'ask')),
    scope VARCHAR(10) NOT NULL CHECK (scope IN ('session', 'project', 'global')),
    session_id UUID REFERENCES workflow_states(id),
    project_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_permission UNIQUE (user_id, tool_name, pattern, scope)
);

CREATE INDEX idx_tool_permissions_user ON tool_permissions(user_id);
CREATE INDEX idx_tool_permissions_session ON tool_permissions(session_id);
```

### 3.2 ConversationSummary

```sql
CREATE TABLE conversation_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    from_message_id UUID NOT NULL REFERENCES chat_messages(id),
    to_message_id UUID NOT NULL REFERENCES chat_messages(id),
    summary_text TEXT NOT NULL,
    tokens_original INTEGER NOT NULL,
    tokens_compressed INTEGER NOT NULL,
    compression_ratio FLOAT GENERATED ALWAYS AS (
        CASE WHEN tokens_original > 0
        THEN tokens_compressed::float / tokens_original
        ELSE 0 END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_summaries_chat ON conversation_summaries(chat_id);
```

### 3.3 Checkpoint (Extende WorkflowState)

```sql
CREATE TABLE checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES workflow_states(id) ON DELETE CASCADE,
    turn_id UUID REFERENCES chat_messages(id),
    snapshot_type VARCHAR(20) NOT NULL CHECK (snapshot_type IN ('auto', 'manual', 'hil')),
    description VARCHAR(500),
    state_snapshot JSONB NOT NULL,           -- LangGraph state serializado
    files_snapshot_uri VARCHAR(1000),        -- S3/local path para arquivos
    is_restorable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_checkpoints_job ON checkpoints(job_id);
CREATE INDEX idx_checkpoints_created ON checkpoints(created_at DESC);
```

---

## 4. Fases de Implementação

### FASE 1: Fundação (Prioridade Alta)

| Task | Descrição | Arquivos | Dependências |
|------|-----------|----------|--------------|
| 1.1 | Criar estrutura de diretórios | orchestration/, claude_agent/, shared/, langgraph/ | - |
| 1.2 | Implementar SSE Protocol unificado | shared/sse_protocol.py | - |
| 1.3 | Criar models de banco | models/tool_permission.py, conversation_summary.py, checkpoint.py | - |
| 1.4 | Criar migrations Alembic | alembic/versions/ | 1.3 |
| 1.5 | Implementar ContextManager | langgraph/improvements/context_manager.py | 1.2 |

### FASE 2: Claude Agent SDK (Prioridade Alta)

| Task | Descrição | Arquivos | Dependências |
|------|-----------|----------|--------------|
| 2.1 | Implementar ClaudeAgentExecutor | claude_agent/executor.py | 1.2 |
| 2.2 | Criar tools jurídicos | claude_agent/tools/*.py | 2.1 |
| 2.3 | Implementar PermissionManager | claude_agent/permissions.py | 1.3 |
| 2.4 | Adicionar claude-agent no registry | model_registry.py | 2.1 |
| 2.5 | Integrar com job_manager | jobs.py, job_manager.py | 2.1, 2.3 |

### FASE 3: Melhorias LangGraph (Prioridade Média)

| Task | Descrição | Arquivos | Dependências |
|------|-----------|----------|--------------|
| 3.1 | Refatorar workflow para nova estrutura | langgraph/workflow.py | 1.1 |
| 3.2 | Implementar parallel_research subgraph | langgraph/subgraphs/parallel_research.py | 3.1 |
| 3.3 | Adicionar ParallelNodeExecutor | langgraph/improvements/parallel_nodes.py | 3.1 |
| 3.4 | Integrar ContextManager no workflow | langgraph/workflow.py | 1.5, 3.1 |
| 3.5 | Implementar CheckpointManager | langgraph/improvements/checkpoint_manager.py | 1.3 |

### FASE 4: Orquestração Paralela (Prioridade Média)

| Task | Descrição | Arquivos | Dependências |
|------|-----------|----------|--------------|
| 4.1 | Implementar OrchestrationRouter | orchestration/router.py | 2.1, 3.1 |
| 4.2 | Implementar ParallelExecutor | orchestration/parallel_executor.py | 4.1 |
| 4.3 | Criar EventMerger | orchestration/event_merger.py | 1.2 |
| 4.4 | Integrar com endpoints | api/endpoints/jobs.py | 4.1, 4.2 |

### FASE 5: Frontend (Prioridade Média)

| Task | Descrição | Arquivos | Dependências |
|------|-----------|----------|--------------|
| 5.1 | Atualizar model-selector | components/chat/model-selector.tsx | 2.4 |
| 5.2 | Criar tool-approval-modal | components/chat/tool-approval-modal.tsx | 2.3 |
| 5.3 | Criar context-indicator | components/chat/context-indicator.tsx | 1.5 |
| 5.4 | Criar checkpoint-timeline | components/chat/checkpoint-timeline.tsx | 3.5 |
| 5.5 | Atualizar chat-store | stores/chat-store.ts | 5.1-5.4 |

---

## 5. Especificações Técnicas

### 5.1 SSE Events Novos

```typescript
// Eventos existentes mantidos
type ExistingEvents =
  | 'token'           // Streaming de texto
  | 'outline'         // Estrutura do documento
  | 'hil_required'    // Human-in-the-loop
  | 'audit_done'      // Resultado de auditoria
  | 'thinking'        // Extended thinking
  | 'done'            // Conclusão

// Novos eventos
type NewEvents =
  | 'agent_iteration'         // Iteração do agent loop
  | 'tool_call'               // Agent chamou uma tool
  | 'tool_result'             // Resultado da tool
  | 'tool_approval_required'  // Precisa aprovação para tool
  | 'context_warning'         // Contexto chegando no limite
  | 'compaction_done'         // Compactação realizada
  | 'checkpoint_created'      // Checkpoint criado
  | 'parallel_start'          // Início de execução paralela
  | 'parallel_complete'       // Fim de execução paralela
  | 'node_start'              // Node LangGraph iniciou
  | 'node_complete'           // Node LangGraph completou
```

### 5.2 ModelConfig para Claude Agent

```python
# Em model_registry.py
ModelConfig(
    id="claude-agent",
    provider="anthropic",
    family="claude",
    label="Claude Agent",
    context_window=200_000,
    latency_tier="medium",
    cost_tier="high",
    capabilities=["chat", "code", "agents", "tools", "autonomous"],
    for_agents=True,
    for_juridico=True,
    thinking_category="native",
    max_output_tokens=16384,

    # Campos novos para agents
    is_agent=True,
    base_model="claude-4.5-opus",
    tools_enabled=[
        "search_jurisprudencia",
        "search_legislacao",
        "search_rag",
        "search_templates",
        "read_document",
        "edit_document",
        "create_section",
        "verify_citation",
        "find_citation_source"
    ],
    default_permission_mode="ask"
)
```

### 5.3 Fluxo de Decisão do Router

```python
def determine_executor(selected_models: List[str], mode: str) -> ExecutorType:
    """
    Regras de decisão:

    1. Se só "claude-agent" selecionado:
       → CLAUDE_AGENT (Agent SDK autônomo)

    2. Se "claude-agent" + outros modelos:
       → PARALLEL (Agent executa + outros validam)

    3. Se só modelos normais (GPT, Claude, Gemini):
       → LANGGRAPH (workflow existente)

    4. Se mode == "minuta" e qualquer seleção:
       → LANGGRAPH (workflow de minuta)
    """

    has_claude_agent = "claude-agent" in selected_models
    has_other_models = any(m != "claude-agent" for m in selected_models)

    if mode == "minuta":
        return ExecutorType.LANGGRAPH

    if has_claude_agent and not has_other_models:
        return ExecutorType.CLAUDE_AGENT

    if has_claude_agent and has_other_models:
        return ExecutorType.PARALLEL

    return ExecutorType.LANGGRAPH
```

### 5.4 Sistema de Permissões

```python
# Hierarquia de precedência (mais específico primeiro)
PERMISSION_HIERARCHY = [
    "session",   # Regras da sessão atual
    "project",   # Regras do projeto/caso
    "global",    # Regras globais do usuário
    "system"     # Defaults do sistema
]

# Defaults do sistema
SYSTEM_DEFAULTS = {
    # Leitura: permitido automaticamente
    "search_jurisprudencia": "allow",
    "search_legislacao": "allow",
    "search_rag": "allow",
    "search_templates": "allow",
    "read_document": "allow",
    "verify_citation": "allow",
    "find_citation_source": "allow",

    # Escrita: pedir aprovação
    "edit_document": "ask",
    "create_section": "ask",

    # Alto risco: negar por padrão
    "bash": "deny",
    "file_write": "deny",
    "file_delete": "deny",
}
```

---

## 6. Comportamento na UI

### 6.1 Seleção de Modelos

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Seleção                              │ Comportamento                    │
├─────────────────────────────────────────────────────────────────────────┤
│ ☑ GPT + ☑ Claude + ☑ Gemini          │ LangGraph debate (existente)     │
├─────────────────────────────────────────────────────────────────────────┤
│ ☑ Claude Agent (só)                  │ Agent SDK autônomo com tools     │
├─────────────────────────────────────────────────────────────────────────┤
│ ☑ Claude Agent + ☑ GPT + ☑ Gemini    │ PARALELO:                        │
│                                      │ → Agent faz research + draft     │
│                                      │ → GPT/Gemini validam/debatem     │
│                                      │ → Merge com resolução de conflitos│
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 UI do Claude Agent

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Chat com Claude Agent                                     [Contexto: 45%]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ 👤 User: Pesquise jurisprudência sobre dano moral em relações de        │
│    consumo e elabore os fundamentos jurídicos.                          │
│                                                                          │
│ 🤖 Claude Agent:                                                         │
│    ┌──────────────────────────────────────────────────────────────┐     │
│    │ 🔧 Tool: search_jurisprudencia                                │     │
│    │ Query: "dano moral relação consumo CDC"                       │     │
│    │ Status: ✅ Executado (5 resultados)                           │     │
│    └──────────────────────────────────────────────────────────────┘     │
│                                                                          │
│    ┌──────────────────────────────────────────────────────────────┐     │
│    │ 🔧 Tool: search_legislacao                                    │     │
│    │ Query: "CDC art 6 direitos básicos consumidor"                │     │
│    │ Status: ✅ Executado                                          │     │
│    └──────────────────────────────────────────────────────────────┘     │
│                                                                          │
│    ┌──────────────────────────────────────────────────────────────┐     │
│    │ 🔧 Tool: edit_document                                        │     │
│    │ Section: "II - DOS FUNDAMENTOS JURÍDICOS"                     │     │
│    │ Status: ⏳ Aguardando aprovação                               │     │
│    │                                                               │     │
│    │ [👁 Preview] [✅ Aprovar] [❌ Negar] [⚙️ Sempre permitir]      │     │
│    └──────────────────────────────────────────────────────────────┘     │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│ Checkpoints: [1] Início → [2] Após research → [3] Atual                 │
│              [🔙 Rewind para checkpoint anterior]                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Testes

### 7.1 Testes Unitários

```
tests/
├── unit/
│   ├── test_context_manager.py
│   ├── test_permission_manager.py
│   ├── test_claude_agent_executor.py
│   ├── test_parallel_executor.py
│   └── test_orchestration_router.py
```

### 7.2 Testes de Integração

```
tests/
├── integration/
│   ├── test_claude_agent_flow.py
│   ├── test_parallel_execution.py
│   ├── test_langgraph_improvements.py
│   └── test_checkpoint_restore.py
```

### 7.3 Testes E2E

```
tests/
├── e2e/
│   ├── test_model_selector_agent.py
│   ├── test_tool_approval_flow.py
│   └── test_rewind_functionality.py
```

---

## 8. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Quebrar workflow LangGraph existente | Média | Alto | Refatoração gradual, testes extensivos |
| Latência alta na execução paralela | Média | Médio | Timeouts, fallback para sequencial |
| Custos elevados com Agent SDK | Alta | Médio | Rate limiting, budgets por sessão |
| Conflitos de merge em execução paralela | Média | Médio | Juiz (LLM) para resolver conflitos |
| Permissões muito restritivas | Baixa | Baixo | Defaults balanceados, fácil ajuste |

---

## 9. Métricas de Sucesso

- [ ] Claude Agent disponível no seletor de modelos
- [ ] Execução paralela funcional (agent + debate)
- [ ] Compactação de contexto ativa (threshold 70%)
- [ ] Sistema de permissões funcionando (Ask/Allow/Deny)
- [ ] Checkpoints com rewind funcional
- [ ] Testes com cobertura > 80%
- [ ] Zero regressões no workflow existente

---

## 10. Cronograma

```
Semana 1: FASE 1 (Fundação)
├── Dia 1-2: Estrutura de diretórios + SSE Protocol
├── Dia 3-4: Models + Migrations
└── Dia 5: Context Manager

Semana 2: FASE 2 (Claude Agent SDK)
├── Dia 1-2: Executor + Tools
├── Dia 3: Permissions
├── Dia 4: Registry + Integração
└── Dia 5: Testes

Semana 3: FASE 3 (LangGraph Improvements)
├── Dia 1-2: Refatoração workflow
├── Dia 3: Parallel research
├── Dia 4: Parallel nodes
└── Dia 5: Checkpoint manager

Semana 4: FASE 4-5 (Orquestração + Frontend)
├── Dia 1-2: Router + Parallel executor
├── Dia 3-4: Frontend components
└── Dia 5: Testes E2E + Deploy
```

---

## Apêndice A: Comandos de Setup

```bash
# Criar estrutura de diretórios
mkdir -p apps/api/app/services/ai/{orchestration,langgraph/{nodes,subgraphs,improvements},claude_agent/tools,shared}

# Criar migrations
cd apps/api && alembic revision --autogenerate -m "add_agent_tables"

# Instalar dependências
pip install anthropic[agent]  # Se disponível, ou anthropic>=0.40.0

# Rodar testes
pytest tests/unit/ -v
pytest tests/integration/ -v
```

---

## Apêndice B: Variáveis de Ambiente

```env
# Adicionar ao .env
CLAUDE_AGENT_ENABLED=true
CLAUDE_AGENT_DEFAULT_MODEL=claude-4.5-opus
CLAUDE_AGENT_MAX_ITERATIONS=50
CLAUDE_AGENT_PERMISSION_MODE=ask
CONTEXT_COMPACTION_THRESHOLD=0.7
PARALLEL_EXECUTION_ENABLED=true
PARALLEL_EXECUTION_TIMEOUT=300
```

---

## Apêndice C: Ajustes Críticos (Revisão 26/01/2026)

Ajustes identificados para evitar surpresas durante implementação:

### C.1 Dependência "Claude Agent SDK"

**Problema**: `pip install anthropic[agent]` pode não existir ou variar.

**Solução**:
```python
# requirements.txt
anthropic>=0.40.0  # Versão mínima com tool use
# OU se existir agent extra:
# anthropic[agent]>=0.40.0

# Fallback no código:
try:
    from anthropic.agent import Agent  # Se existir
except ImportError:
    # Usar implementação manual com tool use
    from app.services.ai.claude_agent.executor import ClaudeAgentExecutor as Agent
```

### C.2 SSE Unificado - Contrato de Eventos

**Problema**: EventMerger precisa ordenar/deduplicar eventos de múltiplas fontes.

**Solução**: Definir contrato mínimo:
```python
@dataclass
class SSEEvent:
    type: str
    data: Dict[str, Any]
    # Campos obrigatórios para merge
    event_id: str = field(default_factory=lambda: str(uuid4()))
    source: str = "unknown"  # "agent" | "langgraph" | "parallel"
    sequence: int = 0
    job_id: str = ""
    timestamp: float = field(default_factory=time.time)
```

### C.3 Tool Permissions - NULL em Pattern

**Problema**: `UNIQUE(..., pattern, ...)` permite múltiplos NULL em pattern.

**Solução**:
```sql
-- Usar COALESCE no índice
CREATE UNIQUE INDEX idx_unique_permission
ON tool_permissions(user_id, tool_name, COALESCE(pattern, '*'), scope);

-- OU índice parcial
CREATE UNIQUE INDEX idx_default_permission
ON tool_permissions(user_id, tool_name, scope)
WHERE pattern IS NULL;
```

### C.4 Checkpoints - Política de Retenção

**Problema**: `state_snapshot JSONB` pode crescer rápido.

**Solução**:
```python
# config.py
CHECKPOINT_RETENTION_DAYS = 7
CHECKPOINT_MAX_PER_JOB = 20
CHECKPOINT_MAX_SIZE_MB = 10

# Política de cleanup (cron job)
async def cleanup_old_checkpoints():
    await db.execute("""
        DELETE FROM checkpoints
        WHERE created_at < NOW() - INTERVAL '{} days'
        AND snapshot_type = 'auto'
    """.format(CHECKPOINT_RETENTION_DAYS))

# files_snapshot_uri: usar S3 com lifecycle policy
# Segurança: encriptar state_snapshot se contiver PII
```

### C.5 Paralelismo - Estratégia de Merge

**Problema**: Merge precisa limites de custo/tempo e plano de cancelamento.

**Solução**:
```python
# parallel_executor.py
PARALLEL_TIMEOUT_SECONDS = 300
PARALLEL_MAX_COST_USD = 5.0

async def execute_parallel(...):
    try:
        agent_task = asyncio.create_task(self._run_agent(...))
        debate_task = asyncio.create_task(self._run_debate(...))

        # Timeout por ramo
        done, pending = await asyncio.wait(
            [agent_task, debate_task],
            timeout=PARALLEL_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_EXCEPTION
        )

        # Cancelar pendentes se um falhar
        for task in pending:
            task.cancel()

    except asyncio.TimeoutError:
        # Fallback: usar só o que completou
        ...
```

### C.6 Feature Flags - Zero Regressões

**Problema**: Garantir que funcionalidade existente não quebre.

**Solução**: Aplicar flags desde o início no router:
```python
# orchestration/router.py
from app.core.config import settings

def determine_executor(selected_models, mode):
    # Feature flags
    if not settings.CLAUDE_AGENT_ENABLED and "claude-agent" in selected_models:
        selected_models = [m for m in selected_models if m != "claude-agent"]
        # Log warning

    if not settings.PARALLEL_EXECUTION_ENABLED:
        # Forçar sequencial
        return ExecutorType.LANGGRAPH

    # ... resto da lógica
```

### C.7 UX - Router Precedence

**Problema**: `mode == minuta` força LANGGRAPH, mas usuário pode não saber.

**Solução**: Feedback visual no frontend:
```typescript
// model-selector.tsx
{mode === 'minuta' && selectedAgents.includes('claude-agent') && (
  <Alert variant="warning">
    Modo Minuta usa o workflow completo (LangGraph).
    O Claude Agent será usado para research, mas o debate
    multi-modelo continuará ativo.
  </Alert>
)}
```

### C.8 Evitar Refatoração por Movimentação

**Problema**: Mover arquivos existentes pode quebrar imports.

**Solução**: Estratégia incremental:
```python
# 1. Manter arquivos existentes no lugar
# apps/api/app/services/ai/langgraph_legal_workflow.py (NÃO MOVER)

# 2. Criar novos módulos que IMPORTAM dos existentes
# apps/api/app/services/ai/langgraph/workflow.py
from ..langgraph_legal_workflow import (
    create_legal_workflow,
    LegalWorkflowState,
    # ... re-export tudo
)

# Adicionar novas funcionalidades aqui
class EnhancedLegalWorkflow(LegalWorkflowBase):
    ...

# 3. Migrar imports gradualmente por etapas
```

---

*Documento gerado em 2026-01-26. Atualizar conforme progresso da implementação.*
*Revisão com ajustes críticos: 2026-01-26*
