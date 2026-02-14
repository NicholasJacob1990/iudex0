# PLANO: Iudex como Claude Cowork
## Transformacao do Iudex em Plataforma Cowork-Like Multi-Provider

**Data**: 2026-02-11
**Status**: Proposta
**Escopo**: Arquitetura completa para transformar o Iudex numa plataforma com funcionalidades equivalentes ao Claude Cowork, com suporte multi-provider (Claude + OpenAI + Gemini)

---

## 1. Sumario Executivo

### Objetivo
Transformar o Iudex de uma aplicacao juridica com IA numa **plataforma agentica completa** que replica e estende as funcionalidades do Claude Cowork, integrando:
- Sistema de plugins com commands, skills, agents, hooks e conectores
- Orquestracao multi-provider (Claude Agent SDK + OpenAI Agents SDK + Gemini ADK)
- Ecossistema de MCP servers (legal BR, Office, produtividade)
- Marketplace de plugins juridicos

### O que o Iudex JA tem (~80%)
| Componente | Status | Arquivo-chave |
|-----------|--------|---------------|
| Skills engine | Funcional | `services/ai/skills/models.py` |
| Workflow builder (React Flow -> LangGraph) | Funcional | `services/ai/workflow_compiler.py` |
| MCP gateway com ACL | Funcional | `services/ai/mcp_hub.py` |
| Claude Agent SDK | Funcional | `services/ai/claude_agent/executor.py` |
| Playbooks (contract review) | Funcional | `models/playbook.py` |
| RAG 10-stage pipeline | Funcional | `services/rag/pipeline/rag_pipeline.py` |
| Multi-model support | Funcional | `services/ai/model_registry.py` |
| SSE streaming | Funcional | `services/ai/shared/sse_protocol.py` |
| Multi-tenancy | Funcional | `models/organization.py` |
| Audit trail | Funcional | `models/audit_log.py` |
| Tool registry | Funcional | `services/ai/shared/tool_registry.py` |

### O que FALTA (~20%)
| Componente | Prioridade | Complexidade |
|-----------|-----------|-------------|
| Plugin Manager (import/export .plugin) | ALTA | Media |
| Connector abstraction (`~~category`) | ALTA | Baixa |
| Hooks system (event-driven) | ALTA | Media |
| Slash commands system | ALTA | Baixa |
| OpenAI Agents SDK integration | MEDIA | Media |
| Gemini ADK integration | MEDIA | Media |
| MCP servers adicionais | MEDIA | Baixa |
| Plugin marketplace UI | BAIXA | Alta |

---

## 2. Arquitetura Alvo

### 2.1 Visao Geral

```
+========================================================================+
|                        IUDEX COWORK PLATFORM                           |
+========================================================================+
|                                                                        |
|  +-----------------------+    +-----------------------------+          |
|  |    PLUGIN SYSTEM      |    |   MULTI-PROVIDER ENGINE     |          |
|  |  - Plugin Manager     |    |   +-----+  +------+  +---+ |          |
|  |  - Marketplace        |    |   |Claude|  |OpenAI|  |ADK| |          |
|  |  - Lifecycle          |    |   |Agent |  |Agents|  |Gem| |          |
|  |  - .plugin format     |    |   |SDK   |  |SDK   |  |ini| |          |
|  +-----------+-----------+    |   +--+---+  +--+---+  +-+-+ |          |
|              |                |      |         |        |    |          |
|  +-----------v-----------+    +------+---------+--------+----+          |
|  |    COMPONENTS          |          |                                  |
|  |  +--------+ +--------+|    +-----v---------+                        |
|  |  |Commands| |Skills  ||    | ORCHESTRATOR  |                        |
|  |  +--------+ +--------+|    | - Routing     |                        |
|  |  +--------+ +--------+|    | - Handoffs    |                        |
|  |  |Agents  | |Hooks   ||    | - Guardrails  |                        |
|  |  +--------+ +--------+|    | - Parallel    |                        |
|  |  +--------+ +--------+|    +------+--------+                        |
|  |  |Connect.| |MCP     ||           |                                 |
|  |  +--------+ +--------+|    +------v--------+                        |
|  +-----------------------+    | TOOL GATEWAY  |                        |
|                               | - MCP Hub     |                        |
|  +-----------------------+    | - ACL/Rate    |                        |
|  |   EXISTING IUDEX      |    | - Adapters    |                        |
|  |  - Workflows          |    +------+--------+                        |
|  |  - Playbooks          |           |                                 |
|  |  - RAG Pipeline       |    +------v--------+                        |
|  |  - Corpus             |    | MCP SERVERS   |                        |
|  |  - Chat               |    | - Legal BR    |                        |
|  |  - Documents          |    | - Office 365  |                        |
|  |  - Tribunal           |    | - Google WS   |                        |
|  +-----------------------+    | - Notion/Slack|                        |
|                               | - PJe/DataJud |                        |
|                               +---------------+                        |
+========================================================================+
```

### 2.2 Mapeamento Cowork -> Iudex

| Conceito Cowork | Equivalente Iudex | Acao |
|----------------|-------------------|------|
| `plugin.json` manifest | `PluginManifest` model | **Criar** |
| `commands/*.md` | `IudexCommand` + endpoint `/commands` | **Criar** |
| `skills/*/SKILL.md` | `SkillDefinition` (ja existe) | **Estender** |
| `agents/*.md` | `SubAgentDefinition` | **Criar** |
| `hooks/hooks.json` | `HookRegistry` event system | **Criar** |
| `.mcp.json` | `MCPHub` (ja existe) | **Estender** |
| `CONNECTORS.md` / `~~category` | `ConnectorRegistry` abstraction | **Criar** |
| `.plugin` ZIP format | Plugin import/export service | **Criar** |
| Marketplace | `/api/marketplace` (ja existe model) | **Estender** |
| `cowork_settings.json` | Plugin settings per tenant | **Criar** |

---

## 3. Plugin System

### 3.1 Plugin Manifest (SQLAlchemy Model)

**Novo arquivo**: `apps/api/app/models/plugin.py`

```python
class Plugin(Base):
    __tablename__ = "plugins"

    id: str  # UUID
    name: str  # kebab-case, unico
    version: str  # semver
    description: str
    author_name: str
    author_email: Optional[str]
    license: str
    keywords: list  # JSON array

    # Status
    is_installed: bool = False
    is_enabled: bool = False
    scope: str  # "user" | "organization" | "global"

    # Content (stored as JSON blobs)
    manifest_json: dict  # plugin.json completo
    commands_json: list  # lista de commands
    skills_json: list  # lista de skills
    agents_json: list  # lista de agents
    hooks_json: dict  # hooks configuration
    mcp_config_json: dict  # .mcp.json
    connectors_json: list  # connectors mapping

    # Storage
    plugin_archive_ref: Optional[str]  # ref ao .plugin file no storage
    source_url: Optional[str]  # URL do marketplace/git

    # Relations
    user_id: str  # FK - quem instalou
    organization_id: Optional[str]  # FK

    installed_at: datetime
    updated_at: datetime
```

### 3.2 Plugin Manager Service

**Novo arquivo**: `apps/api/app/services/plugin_manager.py`

Responsabilidades:
- `install_plugin(source: str, scope: str)` -- instalar de URL/ZIP/marketplace
- `uninstall_plugin(plugin_id: str)`
- `enable_plugin(plugin_id: str)` / `disable_plugin(plugin_id: str)`
- `import_plugin(file: UploadFile)` -- importar .plugin (ZIP)
- `export_plugin(plugin_id: str) -> bytes` -- exportar como .plugin
- `validate_plugin(manifest: dict) -> ValidationResult`
- `list_plugins(scope: str, enabled_only: bool)`
- `get_plugin_components(plugin_id: str)` -- retorna commands, skills, agents, hooks

### 3.3 Plugin Lifecycle

```
[Marketplace/Upload] -> validate -> install -> enable -> [active]
                                                           |
                                                    disable -> [inactive]
                                                           |
                                                    uninstall -> [removed]
                                                           |
                                                    update -> validate -> [active]
```

### 3.4 Plugin API Endpoints

**Novo arquivo**: `apps/api/app/api/endpoints/plugins.py`

| Metodo | Endpoint | Acao |
|--------|----------|------|
| GET | `/api/plugins` | Listar plugins instalados |
| POST | `/api/plugins/install` | Instalar plugin (URL/marketplace) |
| POST | `/api/plugins/import` | Importar .plugin file |
| GET | `/api/plugins/{id}/export` | Exportar como .plugin |
| PUT | `/api/plugins/{id}/enable` | Habilitar |
| PUT | `/api/plugins/{id}/disable` | Desabilitar |
| DELETE | `/api/plugins/{id}` | Desinstalar |
| POST | `/api/plugins/validate` | Validar manifest |
| GET | `/api/plugins/{id}/commands` | Listar commands do plugin |
| GET | `/api/plugins/{id}/skills` | Listar skills do plugin |

---

## 4. Commands System (Slash Commands)

### 4.1 Command Model

**Novo arquivo**: `apps/api/app/models/command.py`

```python
class Command(Base):
    __tablename__ = "commands"

    id: str
    name: str  # ex: "review-contract"
    plugin_id: Optional[str]  # FK - None = builtin
    description: str  # <60 chars

    # Content
    prompt_template: str  # Markdown com $ARGUMENTS, @path, etc.
    allowed_tools: list  # ["Read", "Grep", "Bash(git:*)"]
    model_override: Optional[str]  # sonnet, opus, haiku, gpt-4, gemini
    argument_hint: Optional[str]

    # Metadata
    scope: str  # user, organization, global
    user_id: str
    organization_id: Optional[str]
    is_active: bool = True
```

### 4.2 Command Executor

**Novo arquivo**: `apps/api/app/services/command_executor.py`

Responsabilidades:
- Parse `$ARGUMENTS`, `$1`, `$2`, `@path`
- Resolver `~~category` via ConnectorRegistry
- Executar inline bash (`` !`cmd` ``)
- Injetar `${PLUGIN_ROOT}` paths
- Rotear para provider correto (Claude/OpenAI/Gemini)
- Streaming response via SSE

### 4.3 Frontend Integration

**Editar**: `apps/web/src/components/chat/chat-input.tsx`

- Autocomplete de `/` commands no input do chat
- Mostrar lista de commands disponiveis com descricoes
- Parse de argumentos apos o command name
- Renderizar help inline ao digitar `/help`

---

## 5. Hooks System (Event-Driven)

### 5.1 Hook Events

| Evento | Quando Dispara | Payload |
|--------|---------------|---------|
| `PreToolUse` | Antes de executar tool | tool_name, arguments, agent |
| `PostToolUse` | Apos tool executar | tool_name, result, duration |
| `PostToolUseFailure` | Apos falha de tool | tool_name, error |
| `PreModelCall` | Antes de chamar LLM | model, messages, tools |
| `PostModelCall` | Apos resposta do LLM | model, response, tokens |
| `SessionStart` | Inicio de sessao de chat | user, session_id |
| `SessionEnd` | Fim de sessao | user, session_id, summary |
| `WorkflowNodeStart` | Inicio de node no workflow | workflow_id, node_id |
| `WorkflowNodeEnd` | Fim de node | workflow_id, node_id, output |
| `DocumentIngested` | Documento ingerido no RAG | document_id, chunks |
| `PlaybookApplied` | Playbook aplicado a contrato | playbook_id, document_id |
| `CommandExecuted` | Slash command executado | command_name, arguments |

### 5.2 Hook Types

```python
class HookType(str, Enum):
    COMMAND = "command"   # Executa script/comando
    PROMPT = "prompt"     # Avalia com LLM
    FUNCTION = "function" # Chama funcao Python
    WEBHOOK = "webhook"   # POST para URL externa
```

### 5.3 Hook Registry

**Novo arquivo**: `apps/api/app/services/hook_registry.py`

```python
class HookRegistry:
    """Registro central de hooks com suporte a plugins."""

    async def register(event: str, hook: HookDefinition, plugin_id: Optional[str])
    async def unregister(hook_id: str)
    async def emit(event: str, payload: dict) -> list[HookResult]
    async def get_hooks(event: str, matcher: Optional[str]) -> list[HookDefinition]
```

### 5.4 Integracao com Tool Gateway

**Editar**: `apps/api/app/services/ai/shared/tool_handlers.py`

Adicionar emit de hooks antes/depois de cada tool execution:
```python
# Antes
results = await hook_registry.emit("PreToolUse", {"tool": name, "args": args})
if any(r.decision == "block" for r in results):
    return blocked_response(results)

# Executar tool
result = await tool.execute(args)

# Depois
await hook_registry.emit("PostToolUse", {"tool": name, "result": result})
```

---

## 6. Connector Abstraction (`~~category`)

### 6.1 Connector Registry

**Novo arquivo**: `apps/api/app/services/connector_registry.py`

```python
# Categorias padrao
CONNECTOR_CATEGORIES = {
    "chat": ["slack", "teams", "discord"],
    "email": ["outlook", "gmail"],
    "calendar": ["outlook_calendar", "google_calendar"],
    "cloud_storage": ["onedrive", "google_drive", "box", "s3"],
    "knowledge_base": ["notion", "confluence"],
    "project_tracker": ["linear", "jira", "asana"],
    "office_suite": ["microsoft_365", "google_workspace"],
    "data_warehouse": ["postgresql", "opensearch", "neo4j"],
    "crm": ["salesforce", "hubspot"],
    "legal_research": ["pje", "brlaw", "datajud"],
    "legal_documents": ["iudex_corpus", "iudex_rag"],
}

class ConnectorRegistry:
    """Resolve ~~category para MCP server concreto."""

    async def resolve(category: str, tenant_id: str) -> MCPServerConfig
    async def set_mapping(category: str, mcp_server: str, tenant_id: str)
    async def get_mappings(tenant_id: str) -> dict[str, str]
```

### 6.2 Configuracao por Tenant

Cada organizacao configura seus conectores:
```json
{
    "organization_id": "org_123",
    "connectors": {
        "chat": "slack",
        "email": "outlook",
        "calendar": "google_calendar",
        "cloud_storage": "onedrive",
        "legal_research": "pje"
    }
}
```

### 6.3 Resolucao em Prompts

Quando um command/skill contem `~~chat`, o CommandExecutor:
1. Consulta ConnectorRegistry para o tenant
2. Resolve `~~chat` -> `slack`
3. Busca MCP server `slack` no MCPHub
4. Substitui no prompt com instrucoes especificas do MCP

---

## 7. Multi-Provider Agent Orchestration

### 7.1 Arquitetura Unificada

**Novo arquivo**: `apps/api/app/services/ai/orchestrator/unified_orchestrator.py`

```python
class UnifiedOrchestrator:
    """Orquestrador que abstrai Claude, OpenAI e Gemini SDKs."""

    providers = {
        "claude": ClaudeAgentProvider,
        "openai": OpenAIAgentProvider,
        "gemini": GeminiAgentProvider,
    }

    async def execute(
        self,
        agent_config: AgentConfig,
        input: str,
        tools: list[ToolDefinition],
        provider: str = "claude",  # ou "openai", "gemini", "auto"
        stream: bool = True,
    ) -> AsyncGenerator[SSEEvent, None]:
        provider_instance = self.providers[provider]
        async for event in provider_instance.execute(agent_config, input, tools):
            yield self._normalize_event(event)
```

### 7.2 Claude Agent Provider (ja existe, adaptar)

**Editar**: `apps/api/app/services/ai/claude_agent/executor.py`

- Extrair interface `AgentProvider`
- Manter agentic loop existente
- Adicionar suporte a SubAgentDefinition dos plugins

### 7.3 OpenAI Agent Provider (novo)

**Novo arquivo**: `apps/api/app/services/ai/openai_agent/provider.py`

```python
class OpenAIAgentProvider(AgentProvider):
    """Provider usando OpenAI Agents SDK."""

    async def execute(self, config, input, tools):
        from agents import Agent, Runner

        agent = Agent(
            name=config.name,
            instructions=config.instructions,
            model=config.model or "gpt-4.1",
            tools=self._convert_tools(tools),
            handoffs=self._build_handoffs(config),
            input_guardrails=self._build_guardrails(config),
        )

        result = Runner.run_streamed(agent, input)
        async for event in result.stream_events():
            yield self._to_sse(event)
```

Recursos do OpenAI SDK a aproveitar:
- **Handoffs** nativos para routing entre areas do direito
- **Guardrails** para validacao LGPD de dados sensiveis
- **Structured output** (Pydantic) para pareceres tipados
- **Tracing** integrado com Langfuse/Datadog
- **Sessions** para persistencia de historico

### 7.4 Gemini Agent Provider (novo)

**Novo arquivo**: `apps/api/app/services/ai/gemini_agent/provider.py`

```python
class GeminiAgentProvider(AgentProvider):
    """Provider usando Google ADK."""

    async def execute(self, config, input, tools):
        from google.adk.agents import Agent
        from google.adk.runners import Runner

        agent = Agent(
            name=config.name,
            model=config.model or "gemini-2.5-pro",
            instruction=config.instructions,
            tools=self._convert_tools(tools),
            sub_agents=self._build_sub_agents(config),
            before_model_callback=self._guardrail_callback(config),
        )

        runner = Runner(agent=agent, ...)
        async for event in runner.run_async(...):
            yield self._to_sse(event)
```

Recursos do Gemini ADK a aproveitar:
- **SequentialAgent / ParallelAgent / LoopAgent** para workflows complexos
- **Callbacks** (before/after model/tool) como guardrails
- **State management** com prefixos (user:, app:, temp:)
- **MCPToolset** nativo para conectar MCP servers
- **A2A Protocol** para comunicacao inter-agentes
- **1M tokens** de contexto para documentos extensos

### 7.5 Provider Selection Strategy

```python
class ProviderRouter:
    """Decide qual provider usar baseado no contexto."""

    ROUTING_RULES = {
        # Tarefas que precisam de raciocinio juridico profundo
        "legal_analysis": "claude",      # Claude Opus - melhor raciocinio
        "contract_review": "claude",
        "legal_drafting": "claude",

        # Tarefas de routing/triagem
        "triage": "openai",              # Handoffs nativos
        "multi_agent_routing": "openai",

        # Pesquisa paralela
        "parallel_research": "gemini",    # ParallelAgent nativo
        "document_processing": "gemini",  # 1M token context

        # Tarefas simples/rapidas
        "quick_chat": "gemini_flash",     # Custo-beneficio
        "data_extraction": "gemini_flash",

        # Fallback
        "default": "claude",
    }
```

---

## 8. MCP Integration Strategy

### 8.1 MCP Servers a Integrar

#### Prioridade CRITICA (Fase 1)
| Server | Uso | Configuracao |
|--------|-----|-------------|
| **PJe MCP** | Consulta processual | `chapirousIA/pje-mcp-server` via stdio |
| **BRLaw MCP** | Jurisprudencia STF/STJ/TST | `pdmtt/brlaw_mcp_server` via stdio |
| **DataJud wrapper** | Metadados CNJ | **Criar** wrapper MCP sobre API REST |

#### Prioridade ALTA (Fase 2)
| Server | Uso | Configuracao |
|--------|-----|-------------|
| **Google Workspace** | Docs, Sheets, Calendar, Gmail | `taylorwilsdon/google_workspace_mcp` |
| **Microsoft 365** | Outlook, Word, Excel, Teams | `Softeria/ms-365-mcp-server` |
| **Notion** | Knowledge base | `makenotion/notion-mcp-server` |
| **Slack** | Comunicacao | `modelcontextprotocol/server-slack` |
| **PostgreSQL** | Database queries | `crystaldba/postgres-mcp` |

#### Prioridade MEDIA (Fase 3)
| Server | Uso | Configuracao |
|--------|-----|-------------|
| **Neo4j** | Knowledge graph | `neo4j/mcp` |
| **Elasticsearch** | Full-text search | `elastic/mcp-server-elasticsearch` |
| **Tavily** | Web research | `tavily-ai/tavily-mcp` |
| **Memory** | Contexto persistente | `modelcontextprotocol/server-memory` |
| **Sequential Thinking** | Raciocinio complexo | `modelcontextprotocol/server-sequential-thinking` |
| **Email (IMAP/SMTP)** | Comunicacao direta | `ai-zerolab/mcp-email-server` |
| **Cerebra Legal** | Raciocinio juridico | `yoda-digital/mcp-cerebra-legal-server` |

### 8.2 Extensao do MCPHub

**Editar**: `apps/api/app/services/ai/mcp_hub.py`

Adicionar:
- `register_from_plugin(plugin_id, mcp_config)` -- registrar MCPs de plugins
- `get_servers_by_category(category)` -- para resolver `~~category`
- `health_check_all()` -- verificar saude de todos os servers
- Suporte a tipo `stdio` (spawn de processos)
- Suporte a tipo `sse` (conexoes SSE persistentes)

### 8.3 DataJud MCP Server (criar)

**Novo app**: `apps/mcp-datajud-server/`

Wrapper MCP sobre a API publica do DataJud (CNJ):
- `datajud_search(tribunal, query)` -- buscar processos
- `datajud_get_process(numero_cnj)` -- detalhes do processo
- `datajud_get_movements(numero_cnj)` -- movimentacoes
- Auth via chave publica DPJ

---

## 9. Skills System Enhancement

### 9.1 Estender SkillDefinition

**Editar**: `apps/api/app/services/ai/skills/models.py`

Adicionar campos para compatibilidade com SKILL.md format:

```python
@dataclass(frozen=True)
class SkillDefinition:
    # Existentes
    name: str
    description: str
    triggers: list[str]
    tools_required: list[str]
    instructions: str
    source: str
    subagent_model: Optional[str] = None
    prefer_workflow: bool = False
    prefer_agent: bool = True

    # Novos (Cowork-compatible)
    plugin_id: Optional[str] = None
    version: Optional[str] = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    allowed_tools: Optional[list[str]] = None
    context: Optional[str] = None  # "fork" para subagent isolado
    agent_type: Optional[str] = None  # "Explore", "Plan", etc.
    references: Optional[list[str]] = None  # paths para docs adicionais
    provider_preference: Optional[str] = None  # "claude", "openai", "gemini"
```

### 9.2 Progressive Disclosure

Implementar 3 niveis de carregamento:
1. **Metadata** (~100 palavras) -- sempre em contexto (name + description)
2. **Instructions** (<3000 palavras) -- carregado quando skill e ativado
3. **References** (ilimitado) -- carregado sob demanda quando agente precisa

### 9.3 Skill Loader de Plugins

**Editar**: `apps/api/app/services/ai/skills/loader.py`

Adicionar `load_plugin_skills(plugin_id)` que:
1. Le skills_json do Plugin model
2. Converte para SkillDefinition
3. Registra no SkillRegistry com namespace `plugin_name:skill_name`

---

## 10. SubAgent System

### 10.1 SubAgent Definition

**Novo arquivo**: `apps/api/app/models/subagent.py`

```python
class SubAgentDefinition(Base):
    __tablename__ = "subagent_definitions"

    id: str
    name: str  # kebab-case
    plugin_id: Optional[str]
    description: str  # quando o orquestrador deve delegar

    # Configuration
    system_prompt: str  # instructions markdown
    model: Optional[str]  # override de modelo
    provider: Optional[str]  # claude, openai, gemini
    allowed_tools: list  # ferramentas permitidas
    disallowed_tools: list  # ferramentas bloqueadas
    max_turns: int = 50

    # Skills pre-loaded
    skills: list  # skill names to preload

    # MCP servers
    mcp_servers: list  # MCP server names disponiveis

    # UI hints
    color: Optional[str]  # blue, cyan, green, yellow, magenta, red
    icon: Optional[str]

    # Metadata
    scope: str  # user, organization, global
    user_id: str
    organization_id: Optional[str]
    is_active: bool = True
```

### 10.2 Agent Router

**Novo arquivo**: `apps/api/app/services/ai/orchestrator/agent_router.py`

Responsabilidades:
- Analisar user prompt
- Match com SubAgentDefinitions registradas (description + examples)
- Decidir se delega ou processa diretamente
- Para OpenAI: usar handoffs nativos
- Para Gemini: usar sub_agents nativos
- Para Claude: usar Task tool com subagent_type

---

## 11. Frontend Changes

### 11.1 Plugin Manager UI

**Nova pagina**: `apps/web/src/app/(dashboard)/plugins/page.tsx`

- Lista de plugins instalados (cards com status enabled/disabled)
- Botao "Install Plugin" (URL ou upload .plugin)
- Botao "Browse Marketplace"
- Panel de detalhes: commands, skills, agents, hooks de cada plugin
- Toggle enable/disable
- Configuracao de conectores por organizacao

### 11.2 Commands Autocomplete

**Editar**: `apps/web/src/components/chat/chat-input.tsx`

- Ao digitar `/`, mostrar dropdown de commands disponiveis
- Filtrar por digitacao
- Mostrar description e argument_hint
- Tab para autocompletar
- Agrupar por plugin

### 11.3 Agent Picker

**Editar**: `apps/web/src/components/chat/chat-interface.tsx`

- Selector de provider (Claude/OpenAI/Gemini/Auto)
- Selector de modelo especifico
- Indicador visual do provider ativo (cor do avatar)
- Badge com nome do subagent quando delegado

### 11.4 Connector Settings

**Nova pagina**: `apps/web/src/app/(dashboard)/settings/connectors/page.tsx`

- Grid de categorias (`~~chat`, `~~email`, etc.)
- Dropdown para selecionar MCP server de cada categoria
- Status de conexao (connected/disconnected)
- Botao "Test Connection"

### 11.5 Hooks Dashboard

**Nova pagina**: `apps/web/src/app/(dashboard)/settings/hooks/page.tsx`

- Lista de hooks registrados por evento
- Formulario para criar hook (type, matcher, command/prompt)
- Logs de execucao de hooks
- Toggle enable/disable por hook

---

## 12. Built-in Legal Plugin (iudex-legal-br)

### 12.1 Commands

| Command | Descricao | Provider |
|---------|-----------|---------|
| `/revisar-contrato` | Revisao contra playbook BR | Claude |
| `/triagem-nda` | Pre-triagem de NDAs | Gemini Flash |
| `/analisar-peticao` | Analise de peticao | Claude |
| `/pesquisar-jurisprudencia` | Busca STF/STJ/TST | Gemini (paralelo) |
| `/calcular-prazo` | Calculo de prazo processual | Qualquer |
| `/briefing-diario` | Resumo do dia (prazos, audiencias) | Gemini Flash |
| `/redigir-parecer` | Gerar parecer juridico | Claude |
| `/consultar-processo` | Consultar PJe/DataJud | Qualquer |
| `/verificar-citacoes` | Validar citacoes legais | Claude |
| `/compliance-lgpd` | Verificar compliance LGPD | Claude |

### 12.2 Skills

| Skill | Triggers | Provider Recomendado |
|-------|----------|---------------------|
| `analise-contrato-br` | "analisar contrato", "revisar clausulas" | Claude |
| `pesquisa-juridica` | "pesquisar legislacao", "buscar jurisprudencia" | Gemini (parallel) |
| `peticionamento` | "redigir peticao", "elaborar recurso" | Claude |
| `compliance-lgpd` | "verificar LGPD", "dados pessoais" | Claude |
| `calculo-trabalhista` | "calcular verbas", "rescisao" | OpenAI (structured) |
| `triagem-processual` | "classificar caso", "tipo de acao" | OpenAI (handoffs) |

### 12.3 Agents

| Agent | Descricao | Model | Tools |
|-------|-----------|-------|-------|
| `analista-civel` | Direito Civil, contratos, obrigacoes | Claude Opus | RAG, PJe, BRLaw |
| `analista-penal` | Direito Penal | Claude Opus | RAG, BRLaw |
| `analista-trabalhista` | Direito do Trabalho, CLT | Claude Opus | RAG, BRLaw |
| `pesquisador-legal` | Pesquisa paralela multi-fonte | Gemini Flash | BRLaw, DataJud, Web |
| `redator-juridico` | Redacao de pecas processuais | Claude Opus | RAG, Templates |
| `revisor-qualidade` | Revisao de qualidade e citacoes | Claude Sonnet | Citation Verifier |

### 12.4 Hooks

```json
{
  "PreToolUse": [
    {
      "matcher": "pje_.*|datajud_.*",
      "hooks": [{
        "type": "function",
        "function": "audit_legal_tool_access",
        "description": "Audita todo acesso a dados processuais"
      }]
    }
  ],
  "PostModelCall": [
    {
      "matcher": "*",
      "hooks": [{
        "type": "function",
        "function": "verify_legal_citations",
        "description": "Verifica citacoes legais na resposta"
      }]
    }
  ],
  "DocumentIngested": [
    {
      "matcher": "contrato|peticao|sentenca",
      "hooks": [{
        "type": "function",
        "function": "auto_classify_legal_document",
        "description": "Classifica automaticamente documentos juridicos"
      }]
    }
  ]
}
```

### 12.5 Connectors

```markdown
| Category | Placeholder | Default | Alternativas |
|----------|------------|---------|-------------|
| Legal Research | ~~legal_research | iudex_rag | brlaw, pje, datajud |
| Cloud Storage | ~~cloud_storage | onedrive | google_drive, s3 |
| Chat | ~~chat | slack | teams |
| Calendar | ~~calendar | google_calendar | outlook_calendar |
| Email | ~~email | outlook | gmail |
| Knowledge Base | ~~knowledge_base | notion | confluence |
```

---

## 13. Fases de Implementacao

### Fase 1: Foundation (2-3 semanas)
**Objetivo**: Plugin system basico + Commands + Hooks

1. Criar model `Plugin` + migration
2. Criar `PluginManager` service
3. Criar model `Command` + migration
4. Criar `CommandExecutor` service
5. Criar `HookRegistry` service
6. Criar endpoints `/api/plugins/*` e `/api/commands/*`
7. Integrar hooks no tool gateway existente
8. Frontend: autocomplete de `/commands` no chat input

**Arquivos novos**:
- `apps/api/app/models/plugin.py`
- `apps/api/app/models/command.py`
- `apps/api/app/services/plugin_manager.py`
- `apps/api/app/services/command_executor.py`
- `apps/api/app/services/hook_registry.py`
- `apps/api/app/api/endpoints/plugins.py`
- `apps/api/app/api/endpoints/commands.py`

**Arquivos editados**:
- `apps/api/app/api/routes.py` (registrar novos routers)
- `apps/api/app/services/ai/shared/tool_handlers.py` (hooks integration)
- `apps/web/src/components/chat/chat-input.tsx` (command autocomplete)

### Fase 2: Multi-Provider (2-3 semanas)
**Objetivo**: OpenAI + Gemini providers + Orchestrator

1. Criar interface `AgentProvider` base
2. Adaptar `ClaudeAgentExecutor` como `ClaudeAgentProvider`
3. Criar `OpenAIAgentProvider` com Agents SDK
4. Criar `GeminiAgentProvider` com ADK
5. Criar `UnifiedOrchestrator`
6. Criar `ProviderRouter` (auto-selection)
7. Frontend: provider selector + model picker

**Arquivos novos**:
- `apps/api/app/services/ai/orchestrator/unified_orchestrator.py`
- `apps/api/app/services/ai/orchestrator/agent_router.py`
- `apps/api/app/services/ai/orchestrator/provider_router.py`
- `apps/api/app/services/ai/openai_agent/provider.py`
- `apps/api/app/services/ai/gemini_agent/provider.py`

**Dependencias**:
- `pip install openai-agents` (OpenAI Agents SDK)
- `pip install google-adk` (Gemini ADK)

### Fase 3: MCP Expansion (1-2 semanas)
**Objetivo**: Integrar MCP servers prioritarios

1. Configurar PJe MCP server (stdio)
2. Configurar BRLaw MCP server (stdio)
3. Criar DataJud MCP wrapper
4. Configurar Google Workspace MCP
5. Configurar MS 365 MCP (se aplicavel)
6. Criar `ConnectorRegistry`
7. Frontend: connector settings page

**Arquivos novos**:
- `apps/mcp-datajud-server/` (novo app)
- `apps/api/app/services/connector_registry.py`
- `apps/web/src/app/(dashboard)/settings/connectors/page.tsx`

### Fase 4: Legal Plugin (1-2 semanas)
**Objetivo**: Plugin iudex-legal-br completo

1. Criar 10 commands legais
2. Criar 6 skills especializadas
3. Criar 6 subagent definitions
4. Configurar hooks de auditoria
5. Configurar connectors mapping
6. Empacotar como .plugin
7. Testar end-to-end

### Fase 5: Plugin Marketplace UI (2 semanas)
**Objetivo**: Interface completa de gerenciamento

1. Plugin manager page (install/enable/disable)
2. Marketplace browser (search, filter, install)
3. Plugin builder wizard
4. Hooks dashboard
5. Connector settings
6. Agent picker no chat
7. Subagent management

### Fase 6: Polish & Production (1-2 semanas)
**Objetivo**: Estabilidade e deploy

1. Testes E2E para plugin lifecycle
2. Testes de integracao multi-provider
3. Rate limiting por provider
4. Error handling e fallbacks
5. Documentacao de API
6. Performance tuning
7. Security audit (plugin sandboxing)

---

## 14. Estimativa de Novos Arquivos

### Backend (Python)
```
apps/api/app/
├── models/
│   ├── plugin.py                    # NOVO
│   ├── command.py                   # NOVO
│   └── subagent.py                  # NOVO
├── services/
│   ├── plugin_manager.py            # NOVO
│   ├── command_executor.py          # NOVO
│   ├── hook_registry.py             # NOVO
│   ├── connector_registry.py        # NOVO
│   └── ai/
│       ├── orchestrator/
│       │   ├── unified_orchestrator.py  # NOVO
│       │   ├── agent_router.py          # NOVO
│       │   └── provider_router.py       # NOVO
│       ├── openai_agent/
│       │   └── provider.py              # NOVO
│       └── gemini_agent/
│           └── provider.py              # NOVO
├── api/endpoints/
│   ├── plugins.py                   # NOVO
│   └── commands.py                  # NOVO
└── schemas/
    ├── plugin.py                    # NOVO
    └── command.py                   # NOVO

apps/mcp-datajud-server/             # NOVO app
├── main.py
├── datajud_client.py
└── requirements.txt
```

### Frontend (TypeScript/React)
```
apps/web/src/
├── app/(dashboard)/
│   ├── plugins/page.tsx             # NOVO
│   └── settings/
│       ├── connectors/page.tsx      # NOVO
│       └── hooks/page.tsx           # NOVO
├── components/
│   ├── plugins/
│   │   ├── plugin-card.tsx          # NOVO
│   │   ├── plugin-manager.tsx       # NOVO
│   │   └── marketplace-browser.tsx  # NOVO
│   ├── commands/
│   │   └── command-autocomplete.tsx # NOVO
│   └── settings/
│       ├── connector-grid.tsx       # NOVO
│       └── hooks-dashboard.tsx      # NOVO
└── stores/
    └── plugin-store.ts              # NOVO
```

---

## 15. Riscos e Mitigacoes

| Risco | Impacto | Mitigacao |
|-------|---------|----------|
| Complexidade multi-provider | Alto | Comecar com Claude, adicionar providers incrementalmente |
| Performance de MCP stdio | Medio | Connection pooling, cache de resultados |
| Sandboxing de plugins | Alto | Validacao rigorosa de manifest, allowlist de tools |
| LGPD em dados processuais | Alto | Hooks de auditoria, mascaramento de PII |
| Custo de API multi-provider | Medio | ProviderRouter otimiza custo vs qualidade |
| Conflito de plugins | Medio | Namespace isolation, priority ordering |
| Latencia de MCP chain | Medio | Parallel MCP calls, timeout configs |

---

## 16. Metricas de Sucesso

| Metrica | Meta |
|---------|------|
| Plugins instalados por tenant | > 3 |
| Commands executados/dia | > 50 |
| Providers utilizados | >= 2 |
| MCP servers conectados | >= 5 |
| Tempo medio de command execution | < 10s |
| Taxa de sucesso de hooks | > 99% |
| Cobertura de testes E2E | > 80% |

---

## Apendice A: Comparativo de SDKs

| Feature | Claude Agent SDK | OpenAI Agents SDK | Gemini ADK |
|---------|-----------------|-------------------|-----------|
| Handoffs nativos | - | Sim | Via sub_agents |
| Guardrails nativos | - | Sim (in/out/tool) | Via callbacks |
| Workflow agents | - | - | Seq/Par/Loop |
| MCP nativo | Core | Suporte | MCPToolset |
| A2A Protocol | - | - | Sim |
| Tracing | Basico | 20+ integracoes | Built-in |
| Sessions | Manual | SQLite/SQLAlchemy | InMemory/DB/Vertex |
| Streaming | Sim | Sim | Sim |
| Structured output | tool_use | Pydantic | JSON Schema |
| Context window | 200K (Opus) | 128K (GPT-4.1) | 1M (Pro) |
| Melhor para | Raciocinio | Orquestracao | Pipelines |

## Apendice B: MCP Servers Prioritarios

| Server | Repositorio | Tipo | Relevancia |
|--------|------------|------|-----------|
| PJe | chapirousIA/pje-mcp-server | stdio | CRITICA |
| BRLaw | pdmtt/brlaw_mcp_server | stdio | CRITICA |
| DataJud | Criar wrapper | http | CRITICA |
| Google Workspace | taylorwilsdon/google_workspace_mcp | stdio | ALTA |
| MS 365 | Softeria/ms-365-mcp-server | stdio | ALTA |
| Notion | makenotion/notion-mcp-server | stdio | ALTA |
| Slack | modelcontextprotocol/server-slack | stdio | ALTA |
| PostgreSQL | crystaldba/postgres-mcp | stdio | ALTA |
| Neo4j | neo4j/mcp | stdio | MEDIA |
| Elasticsearch | elastic/mcp-server-elasticsearch | stdio | MEDIA |
| Tavily | tavily-ai/tavily-mcp | stdio | MEDIA |
| Memory | modelcontextprotocol/server-memory | stdio | MEDIA |
| Cerebra Legal | yoda-digital/mcp-cerebra-legal-server | stdio | MEDIA |
| Email | ai-zerolab/mcp-email-server | stdio | MEDIA |
