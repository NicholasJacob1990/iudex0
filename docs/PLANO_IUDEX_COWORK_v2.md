# PLANO v2.2: Iudex como Claude Cowork (Revisão Definitiva)
## Análise Crítica + Plano Otimizado com Inventário Completo

**Data**: 2026-02-11
**Status**: Revisão v2.2 — incorpora INVENTARIO_CHAT_ASSISTENTE_AGENTES.md + BACKEND_DOMAIN_MAP.md
**Contexto**: O Iudex possui ~95%+ da infraestrutura. O gap real é menor do que todas as versões anteriores estimaram.

---

## 1. Evolução do Plano: v1 → v2 → v2.1 → v2.2

| Versão | Erro Principal | Correção |
|--------|---------------|----------|
| v1 | Ignorou SDKs, executors, tool gateway, skills UI existentes | Eliminou Fase 2 inteira (multi-provider) |
| v2 | Disse "Slash commands NÃO EXISTE" e "Marketplace UI NÃO" | v2.1: ambos existem, estender |
| v2.1 | Não leu INVENTARIO nem BACKEND_DOMAIN_MAP | v2.2: corrige 7+ redundâncias adicionais |
| v2.2 | — | Incorpora inventário completo do backend (62 domínios, 400+ endpoints) |

### 1.1 O que v2.1 ERROU (corrigido em v2.2)

| Proposta v2.1 | Realidade (INVENTARIO/DOMAIN_MAP) | Impacto |
|---|---|---|
| Criar `command_service.py` | **JÁ EXISTE** (234 linhas, 9 commands, integrado em `chats.py:1526`) | ESTENDER, não criar |
| Criar `mcp-datajud-server/main.py` | DataJud **COMPLETO**: `djen_service.py` (734 linhas), `DataJudClient`, `ComunicaClient`, watchlist, sync automática, SDK tools | **100% REDUNDANTE** — remover |
| "MCP servers legais NÃO CONECTADOS" | `mcp-legal-server/main.py` existe + SDK tools (`consultar_processo_datajud`, `buscar_publicacoes_djen`) já no Claude agent | PARCIAL — MCP legal server existe |
| SubAgentDefinition "NÃO EXISTE" | `AgentPool` (spawn/cancel/list, max 10/user) + `ParallelAgentsNode` (LangGraph, semaphore, 3 aggregation strategies) | ESTENDER, não criar do zero |
| Commands jurídicos "precisam ser criados" | Endpoints já existem: `/knowledge/jurisprudence/search`, `/knowledge/legislation/search`, `/knowledge/verify-citations`, `/tribunais/processo/...`, `/djen/datajud/search` | Commands = routing para APIs existentes |
| "Marketplace API falta" | 6 endpoints existem: `GET /categories`, `GET/{id}`, `POST/{id}/install`, `POST/{id}/review`, etc. + `app.models.marketplace` | API completa, UI estender |

### 1.2 Inventário COMPLETO do que JÁ EXISTE

#### Backend: Infraestrutura de Agentes
| Componente | Arquivo(s) | Detalhes |
|-----------|-----------|---------|
| Claude Agent SDK | `apps/api/app/services/ai/claude_agent/executor.py` (83KB) | Completo com extended thinking |
| OpenAI Agents SDK | `apps/api/app/services/ai/executors/openai_agent.py` | Handoffs, guardrails |
| Google ADK | `apps/api/app/services/ai/executors/google_agent.py` | Dual: ADK + API |
| Agent Pool | `apps/api/app/services/ai/claude_agent/parallel_agents.py` (289 linhas) | spawn/cancel/list, max 10/user, SSE events |
| Agent Tasks API | `apps/api/app/api/endpoints/agent_tasks.py` | POST /spawn, GET /tasks, DELETE /tasks/{id} |
| Parallel Agents Node | `apps/api/app/services/ai/langgraph/nodes/parallel_agents_node.py` (195 linhas) | Multi-branch, semaphore, concat/best_effort/json |
| Tool Gateway | `apps/api/app/services/ai/tool_gateway/` | registry, policy_engine, 3 adapters |
| Model Router | `apps/api/app/services/ai/model_router.py` | for_agents, for_juridico flags |
| Model Registry | `apps/api/app/services/ai/model_registry.py` | 80+ modelos, 6 providers |

#### Backend: Command Service (EXISTENTE)
| Componente | Arquivo | Detalhes |
|-----------|---------|---------|
| CommandService | `apps/api/app/services/command_service.py` (234 linhas) | `parse_command()` → (response, error) |
| Integração | `apps/api/app/api/endpoints/chats.py:1526` e `:2127` | Intercepta messages antes do LLM |
| Commands atuais | 9 implementados | /list, /use, /templates, /template_id, /template_doc, /template_filters, /template_clear, /clear, /help |

#### Backend: DataJud / DJEN (COMPLETO)
| Componente | Arquivo | Detalhes |
|-----------|---------|---------|
| DataJudClient | `apps/api/app/services/djen_service.py:199-383` | check_updates, search_process via CNJ API |
| ComunicaClient | `apps/api/app/services/djen_service.py:389-603` | DJEN publications, rate limiting |
| DjenService | `apps/api/app/services/djen_service.py:610-724` | Orchestrator: fetch_metadata, check_and_fetch |
| API Endpoints | `apps/api/app/api/endpoints/djen.py` (14 endpoints) | datajud/search, comunica/search, watchlist CRUD |
| Auto-sync | `apps/api/app/services/djen_sync.py` (284 linhas) | Watchlist + workflow triggers |
| SDK Tools | `apps/api/app/services/ai/claude_agent/sdk_tools.py:416-506` | consultar_processo_datajud, buscar_publicacoes_djen |
| Models | `apps/api/app/models/djen.py` | ProcessWatchlist, DjenOabWatchlist, DjenIntimation |
| Schemas | `apps/api/app/schemas/djen.py` (349 linhas) | 9 schemas Pydantic |
| Testes | `tests/test_djen_service.py`, `tests/test_sdk_tools_datajud_djen.py` | 8 test cases |

#### Backend: Knowledge / Jurídico (COMPLETO)
| Componente | Arquivo | Detalhes |
|-----------|---------|---------|
| Legislation Search | `apps/api/app/api/endpoints/knowledge.py` | GET /legislation/search (semântico) |
| Jurisprudence Search | `apps/api/app/api/endpoints/knowledge.py` | GET /jurisprudence/search (court, tema) |
| Web Search | `apps/api/app/api/endpoints/knowledge.py` | GET /web/search (Perplexity→Serper→DDG fallback) |
| Citation Verification | `apps/api/app/api/endpoints/knowledge.py` | POST /verify-citations + POST /shepardize |
| Tribunais | `apps/api/app/api/endpoints/tribunais.py` (13 endpoints) | Credenciais, processo, movimentações, peticionamento |
| MCP Legal Server | `apps/mcp-legal-server/main.py` | FastAPI standalone, /rpc, ACL, rate limiting, cache |

#### Backend: APIs de Domínio (62 domínios, 400+ endpoints)
| Domínio | Endpoints | Relevância para Plugins |
|---------|-----------|------------------------|
| Marketplace | 6 | install, review, categories — backend completo |
| MCP | 12 | servers, tools/search, tools/call, user-servers CRUD, gateway |
| Skills | 3 | generate, validate, publish |
| Workflows | 38 | run, test, schedule, trigger, permissions |
| Playbooks | 22 | analyze, import, export, generate |
| Documents | 22 | upload, OCR, summary, transcribe, audit |
| Corpus | 26 | ingest, search, collections, admin |
| Graph | 19+8+6 | entities, ask, risk, Neo4j |
| Audit | 19+2 | tool-calls, export, tasks |
| DMS | 12 | providers, connect, import (Google Drive, OneDrive, etc.) |

#### Frontend
| Componente | Arquivo(s) | Detalhes |
|-----------|-----------|---------|
| Slash Command Menu | `slash-command-menu.tsx` (347 linhas) | 15 SystemCommands, search, keyboard nav |
| At Command Menu | `at-command-menu.tsx` (252 linhas) | 13 AI models, files, library, juris |
| Chat Input | `chat-input.tsx` (577 linhas) | / e @ triggers, 6 quick actions |
| Chat Interface | `chat-interface.tsx` | Canvas, multi-model, tool approval, checkpoints |
| Tool Approval Modal | `tool-approval-modal.tsx` | Risk levels, preview, "lembrar" |
| Skills Page | `skills/page.tsx` | Wizard + editor modes |
| Marketplace Page | `marketplace/page.tsx` (204 linhas) | Search, filter, install grid |
| Model Selector | `model-selector.tsx` | 6 providers, agents toggle |
| Agent Orchestrator | `services/agents/agent-orchestrator.ts` | strategist/researcher/drafter/reviewer |

### 1.3 Gap REAL Atualizado (v2.2)

| Componente | Status | Ação v2.2 |
|-----------|--------|-----------|
| **Plugin model/lifecycle** | ❌ NÃO EXISTE | Criar model + service |
| **Plugin manifest format** | ❌ NÃO EXISTE | Criar schema JSON |
| **Command model (DB-backed, plugin-aware)** | ⚠️ PARCIAL | `CommandService` existe com 9 commands hardcoded. Adicionar model DB + `source` field |
| **HookRegistry** | ❌ NÃO EXISTE | Criar (4 eventos iniciais) |
| **ConnectorRegistry** | ❌ NÃO EXISTE | Criar (~~category resolver) |
| **Observability persistence** | ⚠️ PARCIAL | Audit log in-memory → persistir em DB |
| **Slash commands plugin-aware** | ⚠️ PARCIAL | Menu tem 15 SystemCommands + CommandService tem 9. Mesclar + carregar da API |
| **Marketplace plugin category** | ⚠️ PARCIAL | API (6 endpoints) + UI existem. Adicionar tipo "plugin" |

### 1.4 O que foi REMOVIDO do plano (vs v2.1)

| Item Removido | Motivo |
|---|---|
| `apps/mcp-datajud-server/main.py` | DataJud completo via `djen_service.py` + SDK tools |
| "Criar command_service.py" | JÁ EXISTE (234 linhas) |
| SubAgentDefinition como conceito novo | AgentPool + ParallelAgentsNode já cobrem spawn/execute/cancel |
| "Conectar MCP servers legais ao MCPHub" | `mcp-legal-server` + `sdk_tools.py` já existem |
| Commands que "precisam prompts novos" | Commands podem rotear para endpoints existentes (knowledge, tribunais, djen) |

### 1.5 Decisões de Paridade com Cowork

| Feature | Decisão v2.2 |
|---------|-------------|
| VM sandbox | Web app, não desktop |
| `.plugin` ZIP | Necessário para paridade com Cowork (upload/export e compat com plugins existentes) |
| GitHub marketplace | Não obrigatório no MVP, mas compatível via sync/import de marketplaces externos |
| LSP servers | Não é IDE |
| bubblewrap/seccomp | ACL do tool_gateway resolve |
| agents/*.md como arquivos | AgentPool + ParallelAgentsNode já fazem spawn dinâmico |

### 1.6 Riscos

| Risco | Severidade | Mitigação |
|-------|-----------|-----------|
| Feature creep | ALTA | MVP: 10 commands (routing), 4 hooks, 1 plugin built-in |
| Plugin sem ecossistema | ALTA | `iudex-legal-br` como dogfood |
| Complexidade | ALTA | 334 services, 400+ endpoints — cada novo arquivo deve justificar-se |
| Quebrar CommandService existente | MÉDIA | Manter backward-compat: hardcoded commands continuam funcionando |

---

## 2. Escopo e Princípios

### 2.1 Princípio

**Não** "transformar Iudex em Cowork". **Sim**: adicionar plugin model + hook system ao sistema já robusto. O resto é wiring.

### 2.2 Escopo (evolução)

```
Plano v1:   ~25 arquivos novos, 6 fases, 10-14 semanas
Plano v2:   ~12 arquivos novos, 3 fases, 4-6 semanas
Plano v2.1: ~12 arquivos novos, 3 fases, 4-6 semanas (reordenado)
Plano v2.2: ~9 arquivos novos, 2 fases, 3-4 semanas (inventário completo)
```

### 2.3 Fases

```
v2.2:
─────
Fase 1 (sem 1-2): Plugin Foundation + Commands (extend) + Hooks
Fase 2 (sem 3-4): Connectors + Observability + Plugin Ecosystem + Marketplace
```

**Fase 2 anterior (MCP Legal) foi eliminada** — DataJud, Tribunais, Knowledge, MCP Legal Server já estão todos implementados.

---

## 3. Fase 1: Plugin Foundation + Commands + Hooks (sem 1-2)

### 3.1 Plugin Model (Foundation)

**Novo arquivo**: `apps/api/app/models/plugin.py`

```python
class Plugin(Base):
    __tablename__ = "plugins"

    id: str  # UUID
    name: str  # kebab-case, único
    version: str  # semver
    description: str
    author: Optional[str]

    # Status
    is_enabled: bool = True
    scope: str  # "user", "organization", "global"

    # Components referenciados via source = "plugin:{id}"
    # Commands, Skills, Hooks linkam por plugin_id

    # MCP config (se o plugin traz MCPs adicionais)
    mcp_servers: Optional[dict]  # {name: MCPServerConfig}
    connectors: Optional[dict]  # {category: server_name}

    # Metadata
    user_id: str
    organization_id: Optional[str]
    installed_at: datetime
```

**Plugin Manifest Format** (JSON):

```json
{
    "name": "iudex-legal-br",
    "version": "1.0.0",
    "description": "Plugin jurídico para direito brasileiro",
    "author": "Iudex Team",

    "commands": [
        {
            "name": "pesquisar-jurisprudencia",
            "description": "Pesquisa jurisprudência em tribunais",
            "route_to": "/api/knowledge/jurisprudence/search",
            "prompt_template": "Pesquise jurisprudência sobre: $ARGUMENTS",
            "allowed_tools": ["search_jurisprudencia", "brlaw_search"]
        }
    ],

    "skills": [
        {
            "name": "analise-contrato-br",
            "markdown": "---\nname: analise-contrato-br\n..."
        }
    ],

    "hooks": [
        {
            "event": "PreToolUse",
            "matcher": "pje_.*|datajud_.*",
            "type": "function",
            "handler": "audit_legal_access"
        }
    ],

    "connectors": {
        "legal_research": "brlaw",
        "legal_process": "pje"
    }
}
```

### 3.2 Command Model (DB-backed, extend existente)

**Diferença crítica vs v2.1**: O `CommandService` já existe e intercepta messages no `chats.py`. A estratégia é:
1. Criar model `Command` no DB para commands dinâmicos (de plugins e usuários)
2. ESTENDER `CommandService.parse_command()` para consultar o DB além dos hardcoded
3. Manter backward-compat: os 9 commands hardcoded continuam funcionando

**Novo arquivo**: `apps/api/app/models/command.py`

```python
class Command(Base):
    __tablename__ = "commands"

    id: str  # UUID
    name: str  # "pesquisar-jurisprudencia" (sem /)
    description: str  # <80 chars

    # Execution — dois modos
    prompt_template: Optional[str]  # Modo 1: Prompt com $ARGUMENTS → LLM
    route_to: Optional[str]  # Modo 2: Rotear para endpoint existente

    model_override: Optional[str]
    provider_override: Optional[str]
    allowed_tools: Optional[list]

    # Metadata
    source: str  # "builtin", "user", "plugin:{id}"
    plugin_id: Optional[str]  # FK para Plugin
    user_id: str
    organization_id: Optional[str]
    scope: str  # "personal", "organization", "global"
    is_active: bool = True
    skill_id: Optional[str]  # FK para LibraryItem
```

**Editar** (NÃO criar): `apps/api/app/services/command_service.py`

```python
class CommandService:
    # Manter parse_command() existente para os 9 hardcoded

    async def parse_command(self, text, db, user_id, chat_context):
        """Existente: processa /list, /use, /templates, etc."""
        # ... código existente ...

        # NOVO: se não é comando hardcoded, buscar no DB
        if text.startswith("/"):
            cmd_name = text.split()[0][1:]  # remove /
            arguments = text[len(cmd_name)+2:].strip()
            db_cmd = await self._get_db_command(cmd_name, db, user_id)
            if db_cmd:
                return await self._execute_db_command(db_cmd, arguments, chat_context)

        return None, None  # não é comando

    async def _execute_db_command(self, cmd, arguments, context):
        """Executa command DB-backed."""
        if cmd.route_to:
            # Modo routing: chamar endpoint interno
            return await self._route_to_endpoint(cmd.route_to, arguments)
        else:
            # Modo prompt: substituir $ARGUMENTS e enviar ao LLM
            prompt = cmd.prompt_template.replace("$ARGUMENTS", arguments)
            prompt = await connector_registry.resolve_all(prompt, context.get("org_id"))
            return prompt, None  # retorna prompt para o LLM processar
```

**Guardrails obrigatórios para `route_to` (MVP):**
1. Allowlist explícita de endpoints internos permitidos por command.
2. Método HTTP fixo por command (`GET` ou `POST`) e validação de payload/schema.
3. Reuso do contexto de autenticação/autorização do usuário (sem bypass de RBAC).
4. Timeout por chamada e circuit breaker para evitar encadeamentos lentos.
5. Logs de auditoria (`command_name`, `route_to`, `status`, `duration_ms`).

**Novo endpoint**: `apps/api/app/api/endpoints/commands.py`

| Método | Endpoint | Ação |
|--------|----------|------|
| GET | `/api/commands` | Listar commands (para autocomplete) |
| POST | `/api/commands` | Criar command |
| PUT | `/api/commands/{id}` | Atualizar |
| DELETE | `/api/commands/{id}` | Deletar |

Nota: execução é via `chats.py` (intercepta no fluxo existente), não precisa de endpoint `/execute`.

#### Frontend: ESTENDER slash-command-menu

**Editar**: `apps/web/src/components/chat/slash-command-menu.tsx`

1. Buscar commands DB-backed via GET `/api/commands` ao abrir
2. Mesclar com 15 SystemCommands existentes
3. Nova categoria "Jurídico" / por plugin name
4. Commands DB-backed executam via message normal (CommandService intercepta)

#### Commands Built-in (10 jurídicos — routing para APIs existentes)

| Command | Modo | Roteia Para / Prompt |
|---------|------|---------------------|
| `/pesquisar-jurisprudencia` | route | `GET /api/knowledge/jurisprudence/search?query=$ARGUMENTS` |
| `/pesquisar-legislacao` | route | `GET /api/knowledge/legislation/search?query=$ARGUMENTS` |
| `/consultar-processo` | route | `GET /api/djen/datajud/search` com npu=$ARGUMENTS |
| `/verificar-citacoes` | route | `POST /api/knowledge/verify-citations` |
| `/shepardize` | route | `POST /api/knowledge/shepardize` |
| `/revisar-contrato` | prompt | "Revise o contrato contra o playbook ativo: $ARGUMENTS" |
| `/analisar-peticao` | prompt | "Analise a petição: $ARGUMENTS" |
| `/briefing` | prompt | "Gere briefing jurídico sobre: $ARGUMENTS" |
| `/redigir-parecer` | prompt | "Redija parecer jurídico sobre: $ARGUMENTS" |
| `/compliance-lgpd` | prompt | "Verifique compliance LGPD: $ARGUMENTS" |

### 3.3 Hooks System (Mínimo Viável)

4 eventos iniciais:

| Evento | Quando | Uso |
|--------|--------|-----|
| `PreToolUse` | Antes de MCP tool | Audit, bloqueio |
| `PostToolUse` | Após MCP tool | Logging, cache |
| `PreModelCall` | Antes de LLM | Guardrail input |
| `PostModelCall` | Após LLM | Verificação output |

**Novo arquivo**: `apps/api/app/services/hook_registry.py`

```python
class HookType(str, Enum):
    FUNCTION = "function"
    WEBHOOK = "webhook"

class HookDefinition:
    id: str
    event: str
    matcher: Optional[str]  # regex
    hook_type: HookType
    handler: str
    priority: int = 0
    enabled: bool = True
    source: str  # "builtin", "plugin:{id}"

class HookResult:
    decision: str  # "allow", "block", "modify"
    reason: Optional[str]
    modified_data: Optional[dict]

class HookRegistry:
    _hooks: dict[str, list[HookDefinition]] = {}

    def register(self, hook: HookDefinition):
        self._hooks.setdefault(hook.event, []).append(hook)
        self._hooks[hook.event].sort(key=lambda h: h.priority)

    async def emit(self, event: str, payload: dict) -> list[HookResult]:
        results = []
        for hook in self._hooks.get(event, []):
            if hook.matcher and not re.match(hook.matcher, payload.get("tool", "")):
                continue
            if not hook.enabled:
                continue
            result = await self._execute_hook(hook, payload)
            results.append(result)
            if result.decision == "block":
                break
        return results
```

**Integração** — editar 2 arquivos:

1. `apps/api/app/services/ai/shared/tool_handlers.py` — PreToolUse/PostToolUse
2. `apps/api/app/services/ai/executors/base.py` — PreModelCall/PostModelCall

**Hooks built-in (5)**:

```python
# 1. Audit de acesso a tools jurídicas
@builtin_hook("PreToolUse", matcher="pje_.*|datajud_.*|brlaw_.*|consultar_processo.*|buscar_publicacoes.*")
async def audit_legal_tool_access(payload):
    await audit_log.record("legal_tool_access", payload)
    return HookResult(decision="allow")

# 2. PII masking em respostas
@builtin_hook("PostModelCall")
async def check_pii_in_response(payload):
    if contains_cpf_or_sensitive(payload["response"]):
        return HookResult(decision="modify", modified_data={"response": mask_pii(payload["response"])})
    return HookResult(decision="allow")

# 3. Rate limiting
@builtin_hook("PreToolUse", matcher="deep_research|web_search")
async def rate_limit_expensive_tools(payload):
    if await is_rate_limited(payload["user_id"], payload["tool"]):
        return HookResult(decision="block", reason="Rate limit exceeded")
    return HookResult(decision="allow")

# 4. Persist tool audit → DB
@builtin_hook("PostToolUse", priority=999)
async def persist_tool_audit(payload):
    await db.execute(AuditLog.insert().values(
        event_type="tool_use", tool_name=payload["tool"],
        duration_ms=payload.get("duration_ms"), user_id=payload.get("user_id")
    ))
    return HookResult(decision="allow")

# 5. Persist model audit → DB
@builtin_hook("PostModelCall", priority=999)
async def persist_model_audit(payload):
    await db.execute(AuditLog.insert().values(
        event_type="model_call", provider=payload.get("provider"),
        token_count=payload.get("tokens"), user_id=payload.get("user_id")
    ))
    return HookResult(decision="allow")
```

---

## 4. Fase 2: Connectors + Observability + Plugin Ecosystem + Marketplace (sem 3-4)

### 4.1 Connector Registry

**Novo arquivo**: `apps/api/app/services/connector_registry.py`

```python
DEFAULT_CONNECTORS = {
    "legal_research": "iudex_rag",
    "legal_process": "pje",
    "jurisprudence": "brlaw",
    "office_suite": "google_workspace",
    "cloud_storage": "google_drive",
    "chat": "slack",
}

class ConnectorRegistry:
    async def resolve(self, category: str, org_id: str) -> str:
        org_config = await get_org_connector_config(org_id)
        return org_config.get(category, DEFAULT_CONNECTORS.get(category, category))

    async def resolve_all(self, text: str, org_id: str) -> str:
        for match in re.findall(r"~~(\w+)", text):
            server = await self.resolve(match, org_id)
            text = text.replace(f"~~{match}", server)
        return text
```

### 4.2 Observability Persistence

**Editar**: `apps/api/app/models/audit_log.py` — adicionar campos:

```python
event_type: Optional[str]      # "tool_use", "model_call", "hook_decision"
tool_name: Optional[str]
provider: Optional[str]
duration_ms: Optional[int]
token_count: Optional[int]
hook_decision: Optional[str]
hook_source: Optional[str]
```

Persistência via hooks #4 e #5 acima (seção 3.3).

### 4.3 Plugin Service

**Novo arquivo**: `apps/api/app/services/plugin_service.py`

```python
class PluginService:
    async def install(self, manifest: PluginManifest, scope: str) -> Plugin:
        plugin = Plugin(name=manifest.name, version=manifest.version, ...)

        for cmd in manifest.commands:
            await command_service.create_db_command(cmd, source=f"plugin:{plugin.id}")

        for skill in manifest.skills:
            await skill_service.publish_from_plugin(skill, plugin.id)

        for hook in manifest.hooks:
            hook_registry.register(HookDefinition(..., source=f"plugin:{plugin.id}"))

        return plugin

    async def enable(self, plugin_id: str): ...
    async def disable(self, plugin_id: str): ...
    async def uninstall(self, plugin_id: str): ...

    async def export_cowork_compat(self, plugin_id: str) -> bytes:
        """Exporta no formato .plugin ZIP compatível com Cowork."""

    async def import_cowork_compat(self, plugin_file: bytes) -> Plugin:
        """Importa plugin Cowork (.plugin ZIP)."""
```

**Novo endpoint**: `apps/api/app/api/endpoints/plugins.py`

| Método | Endpoint | Ação |
|--------|----------|------|
| GET | `/api/plugins` | Listar plugins instalados |
| POST | `/api/plugins/install` | Instalar plugin (manifest JSON ou .plugin ZIP) |
| POST | `/api/plugins/import-batch` | Importar lote de plugins (diretório/local marketplace) |
| GET | `/api/plugins/marketplaces` | Listar marketplaces configurados |
| POST | `/api/plugins/marketplaces/sync` | Sincronizar catálogo de marketplace |
| PUT | `/api/plugins/{id}/toggle` | Enable/disable |
| DELETE | `/api/plugins/{id}` | Desinstalar |
| GET | `/api/plugins/{id}/export` | Exportar como .plugin |

### 4.4 Seed inicial + Importação em lote (paridade Cowork)

Instalar automaticamente `iudex-legal-br`:
- 10 commands (da tabela 3.2 — 5 routing + 5 prompt)
- 5 hooks built-in (seção 3.3)
- Connector mappings default
- Vincula skills existentes da library

Adicionar importação em lote dos plugins de exemplo (estilo Cowork):
- Origem padrão configurável via `PLUGIN_IMPORT_ROOT`
- Exemplo local: `/Users/nicholasjacob/Library/Application Support/Claude/local-agent-mode-sessions/3d43c458-1aed-4cfd-872c-2ab09a7d9f12/dfd08182-6851-4208-987d-a76af950d101/cowork_plugins`
- Ler `known_marketplaces.json`, catálogo de `marketplaces/*/.claude-plugin/marketplace.json` e `plugin.json`
- Importar plugins por allowlist (default: `data`, `finance`, `legal`, `productivity`, `cowork-plugin-management`)
- Execução idempotente (não reinstalar mesma versão/hash)
- Modo `dry_run` e relatório final de sucesso/falha por plugin

### 4.5 Frontend: ESTENDER Marketplace

**Editar**: `apps/web/src/app/(dashboard)/marketplace/page.tsx`

1. Adicionar "Plugins" às categorias (Minutas, Workflows, Prompts, Cláusulas, Agentes, Pareceres, **Plugins**)
2. Cards de plugin: commands count, hooks count
3. Usar `POST /api/marketplace/{id}/install` existente (adaptar para plugins)
4. Toggle enable/disable para plugins instalados
5. Ações no menu de plugins (paridade Cowork): `Navegar por plugins`, `Fazer upload de plugin`, `Importar plugins de exemplo`
6. Tela de conectores por plugin com estado `instalado/desconectado` e botão `Instalar`

**Editar**: `apps/web/src/app/(dashboard)/skills/page.tsx`

- Badge "Plugin: {name}" em skills de plugins
- Filtro: "Minhas Skills" | "Plugins" | "Todas"

---

## 5. Resumo Comparativo: v1 → v2 → v2.1 → v2.2

| Aspecto | v1 | v2 | v2.1 | v2.2 |
|---------|----|----|------|------|
| Arquivos novos | ~25 | ~12 | ~12 | **~9** |
| Fases | 6 | 3 | 3 | **2** |
| Estimativa | 10-14 sem | 4-6 sem | 4-6 sem | **3-4 sem** |
| Multi-provider | Criar | JÁ EXISTE | JÁ EXISTE | JÁ EXISTE |
| CommandService | Criar | Criar | Criar | **ESTENDER existente** |
| DataJud MCP | Criar wrapper | Criar wrapper | Criar wrapper | **JÁ EXISTE completo** |
| MCP Legal | Criar | Configurar | Configurar | **JÁ EXISTE** |
| Agent spawn | Não mencionado | Não mencionado | SubAgentDefinition | **AgentPool JÁ EXISTE** |
| Slash commands | Criar | Criar | ESTENDER | **ESTENDER** |
| Marketplace | Criar | Criar | ESTENDER | **ESTENDER (API+UI)** |
| Knowledge API | Não mencionado | Não mencionado | Não mencionado | **JÁ EXISTE (5 endpoints)** |
| Tribunais API | Não mencionado | Não mencionado | Não mencionado | **JÁ EXISTE (13 endpoints)** |

---

## 6. Arquivos a Criar/Editar

### Novos (~9 arquivos)

```
Backend:
├── apps/api/app/models/command.py               # Command model (DB)
├── apps/api/app/models/plugin.py                # Plugin model
├── apps/api/app/schemas/commands.py             # Request/response
├── apps/api/app/schemas/plugins.py              # Request/response + PluginManifest
├── apps/api/app/api/endpoints/commands.py       # CRUD /api/commands
├── apps/api/app/api/endpoints/plugins.py        # /api/plugins/*
├── apps/api/app/services/plugin_service.py      # Plugin lifecycle
├── apps/api/app/services/connector_registry.py  # Resolver ~~category
├── apps/api/app/services/hook_registry.py       # Hook system
```

### Editar (~9 arquivos)

```
Backend:
├── apps/api/app/services/command_service.py              # Adicionar DB lookup + route_to
├── apps/api/app/api/routes.py                             # Registrar novos routers
├── apps/api/app/services/ai/shared/tool_handlers.py      # Hook integration (tools)
├── apps/api/app/services/ai/executors/base.py             # Hook integration (models)
├── apps/api/app/models/audit_log.py                       # Campos observabilidade

Frontend:
├── apps/web/src/components/chat/slash-command-menu.tsx    # Carregar commands da API
├── apps/web/src/app/(dashboard)/marketplace/page.tsx      # Categoria "Plugins"
├── apps/web/src/app/(dashboard)/skills/page.tsx           # Badge/filtro por plugin
```

### Alembic Migration (1 arquivo)

```
├── apps/api/alembic/versions/xxx_add_commands_plugins.py  # Tabelas + colunas audit_log
```

---

## 7. Ordem de Implementação

### Semana 1-2: Plugin Foundation + Commands + Hooks

1. Migration: tabelas `commands`, `plugins` + colunas `audit_log`
2. Model: `Plugin` + `Command`
3. Schema: `PluginManifest`, `CreateCommandRequest`
4. ESTENDER: `CommandService` — DB lookup + route_to mode
5. Endpoint: CRUD `/api/commands`
6. Service: `HookRegistry` (register, emit)
7. Integração: hooks em tool_handlers + executors
8. 5 hooks built-in (audit, PII, rate limit, persist tool, persist model)
9. Frontend: ESTENDER `slash-command-menu.tsx`
10. Seed: 10 commands built-in (5 routing + 5 prompt)

### Semana 3-4: Connectors + Plugin Ecosystem + Marketplace

1. Service/config: `ConnectorRegistry` (~~category resolver)
2. Service: `PluginService` (install, enable, disable, export, import)
3. Endpoint: `/api/plugins/*`
4. Built-in: plugin `iudex-legal-br`
5. Frontend: ESTENDER `marketplace/page.tsx` com "Plugins"
6. Frontend: ESTENDER `skills/page.tsx` com badge/filtro
7. Import/export Cowork-compatible (`.plugin`)
8. Importação em lote de plugins de exemplo (local marketplace)
9. Testes E2E

---

## 8. O que NÃO fazer

| Não Fazer | Por que |
|-----------|---------|
| Criar executors/providers | 3 existem |
| Criar tool_gateway | Existe com adapters |
| Recriar skills system | Wizard + editor + validation existem |
| Criar DataJud MCP wrapper | `djen_service.py` (734 linhas) + SDK tools existem |
| Criar MCP legal server | `apps/mcp-legal-server/main.py` existe |
| Criar nova página de plugins | Marketplace existe |
| Criar novo autocomplete de / | `slash-command-menu.tsx` existe |
| Criar novo command_service.py | Existe (234 linhas), estender |
| Criar SubAgentDefinition | AgentPool + ParallelAgentsNode existem |
| Criar Knowledge endpoints | 5 endpoints existem (legislação, jurisprudência, web, citations, shepardize) |
| Criar Tribunais endpoints | 13 endpoints existem |
| Importar todos os plugins sem curadoria | Fazer allowlist + validação + dry-run para reduzir risco operacional |
| 14 eventos de hook | 4 bastam |
| A2A Protocol | Premature optimization |

---

## 9. Métricas de Sucesso

| Métrica | Meta Fase 1 | Meta Final |
|---------|-------------|-----------|
| Commands disponíveis | 10 built-in + 9 hardcoded | 25+ |
| Commands executados/dia | > 10 | > 50 |
| Hooks registrados | 5 built-in | 10+ |
| Plugins instalados | 1 (legal-br) | 5+ |
| Tempo de `/command` (routing) | < 1s | < 500ms |
| Tempo de `/command` (prompt) | < 5s | < 3s |
| Tool events persistidos/dia | > 100 | > 1000 |

---

## Apêndice A: Infraestrutura Existente Completa

| Componente | Arquivo | Usado Para |
|-----------|---------|-----------|
| Claude Agent SDK | `apps/api/app/services/ai/claude_agent/executor.py` | Provider principal |
| OpenAI Agents SDK | `apps/api/app/services/ai/executors/openai_agent.py` | Handoffs/guardrails |
| Google ADK | `apps/api/app/services/ai/executors/google_agent.py` | Parallel/Loop agents |
| Agent Pool | `apps/api/app/services/ai/claude_agent/parallel_agents.py` | Spawn/cancel agents |
| Agent Tasks API | `apps/api/app/api/endpoints/agent_tasks.py` | POST /spawn, GET /tasks |
| Parallel Agents Node | `apps/api/app/services/ai/langgraph/nodes/parallel_agents_node.py` | Multi-branch LangGraph |
| Tool Gateway | `apps/api/app/services/ai/tool_gateway/` | MCP ↔ providers |
| 3 Adapters | `apps/api/app/services/ai/tool_gateway/adapters/claude,openai,gemini_adapter.py` | Tool format conversion |
| MCPHub | `apps/api/app/services/mcp_hub.py` | Registro MCP servers |
| MCP Legal Server | `apps/mcp-legal-server/main.py` | RPC, ACL, rate limiting |
| Model Router | `apps/api/app/services/ai/model_router.py` | Auto-seleção provider |
| Model Registry | `apps/api/app/services/ai/model_registry.py` | 80+ modelos, 6 providers |
| CommandService | `apps/api/app/services/command_service.py` | 9 slash commands |
| Skills Engine | `skills/skill_builder.py` | Semantic matching |
| Skills UI | `/skills/page.tsx` | Wizard + editor |
| Skills API | `apps/api/app/api/endpoints/skills.py` | Generate, validate, publish |
| Slash Commands | `apps/web/src/components/chat/slash-command-menu.tsx` | 15 SystemCommands |
| At Commands | `apps/web/src/components/chat/at-command-menu.tsx` | @mentions |
| Chat Input | `apps/web/src/components/chat/chat-input.tsx` | / e @ triggers |
| Tool Approval | `apps/web/src/components/chat/tool-approval-modal.tsx` | Risk levels + permissions |
| Marketplace | `apps/web/src/app/(dashboard)/marketplace/page.tsx` + `apps/api/app/api/endpoints/marketplace.py` | Search/filter/install + reviews |
| DataJud | `apps/api/app/services/djen_service.py` (734 linhas) | DataJudClient + ComunicaClient |
| DataJud SDK Tools | `apps/api/app/services/ai/claude_agent/sdk_tools.py:416-506` | consultar_processo_datajud, buscar_publicacoes_djen |
| DataJud Sync | `apps/api/app/services/djen_sync.py` (284 linhas) | Auto-sync watchlist + workflow triggers |
| DataJud API | `apps/api/app/api/endpoints/djen.py` (14 endpoints) | CRUD + search + sync |
| Knowledge API | `apps/api/app/api/endpoints/knowledge.py` (5 endpoints) | Legislação, jurisprudência, web, citations, shepardize |
| Tribunais API | `apps/api/app/api/endpoints/tribunais.py` (13 endpoints) | Credenciais, processos, peticionamento |
| DMS | `apps/api/app/api/endpoints/dms.py` (12 endpoints) | Google Drive, OneDrive, etc. |
| Workflows | `apps/api/app/api/endpoints/workflows.py` (38 endpoints) | Run, test, schedule, trigger |
| Playbooks | `apps/api/app/api/endpoints/playbooks.py` (22 endpoints) | Analyze, import, export |
| Graph | `apps/api/app/api/endpoints/graph*.py` (33 endpoints) | Neo4j entities, ask, risk |
| Audit | `apps/api/app/api/endpoints/audit*.py` (21 endpoints) | Tool calls, export, tasks |
| SSE Protocol | `apps/api/app/services/ai/shared/sse_protocol.py` | Streaming unificado |
| RAG Pipeline | `apps/api/app/services/rag/pipeline/` | Pesquisa em documentos |
| Playbook Model | `apps/api/app/models/playbook.py` | Contract review rules |

## Apêndice B: Cotejo Iudex vs Cowork (10 Domínios) — Atualizado v2.2

| Domínio | Iudex | Cowork | Gap Real |
|---------|-------|--------|----------|
| **Commands** | CommandService (9 hardcoded) + SlashCommandMenu (15 SystemCommands) | Plugin-registered dynamic | Adicionar DB model + API |
| **Plugins** | Conceito não existe | Core da arquitetura | Criar model + lifecycle |
| **Skills** | Completo (wizard, editor, validation, publishing, quality score) | SKILL.md files | **Iudex superior** |
| **Hooks** | Não existe | hooks.json (14 eventos) | Criar 4 eventos MVP |
| **Connectors** | Não existe | ~~category abstraction | Criar config simples |
| **MCP** | MCPHub + MCP Legal Server + tool_gateway + 3 adapters + user-servers CRUD | .mcp.json per-plugin | **Iudex superior** |
| **SubAgents** | AgentPool (spawn/cancel) + ParallelAgentsNode (LangGraph) | agents/*.md | **Iudex superior** (dinâmico vs estático) |
| **Observability** | In-memory audit + 21 audit endpoints | Não mencionado | Persistência em DB |
| **Multi-Provider** | 3 SDKs + tool gateway + adapters + router + 80+ modelos | Claude only | **Iudex superior** |
| **Domain** | 400+ endpoints, 62 domínios, DataJud/DJEN, Knowledge, Tribunais, RAG, Playbooks, Graph, DMS | Genérico | **Iudex superior** |
| **Marketplace** | 6 API endpoints + UI (search/filter/install/reviews) | GitHub-based | **Iudex superior** |
| **Tool Approval** | Modal + PermissionModel (session/project/global scopes) | Não mencionado | **Iudex superior** |

---

## Apêndice C: Adendo de Lifecycle — Plugin ↔ Skills ↔ MCP (v2.2.1)

**Data**: 2026-02-11
**Origem**: Debate Claude vs Codex/GPT — análise crítica dos gaps não endereçados no plano v2.2
**Status**: Complemento obrigatório antes da implementação

### C.1 Problema

O plano v2.2 propõe integração skills↔plugins como cosmética (badge + filtro na UI). Porém o sistema de Skills **já possui** infraestrutura de `source`, precedência e versionamento que precisa ser estendida — não apenas decorada. Sem lifecycle explícito, disable/uninstall/update de plugins deixará o sistema em estado inconsistente.

**Infraestrutura existente relevante:**

| Componente | Arquivo | O que já faz |
|-----------|---------|-------------|
| `SkillDefinition.source` | `services/ai/skills/models.py` | Rastreia origem: `"builtin:*"`, `"library:*"`, `"inline"`, `"draft:*"` |
| `SkillRegistry.__init__` | `services/ai/skills/registry.py` | Dedup por nome, precedência User > Builtin |
| `SkillRegistry.build()` | `services/ai/skills/registry.py` | Carrega builtin + user, merge com user first |
| `LibraryItem.tags` | `models/library.py` | Tags: `"skill"`, `"skill_version:N"`, `"visibility:*"`, `"state:*"` |
| `MCPHub.with_user_servers()` | `services/mcp_hub.py:507-526` | Merge de servidores user sobre builtin+env, retorna novo hub |
| `load_user_skills()` | `services/ai/skills/loader.py` | Query LibraryItem WHERE type=PROMPT AND "skill" in tags |

### C.2 Regra de Precedência (OBRIGATÓRIO)

```
User (library:*) > Fork (fork:plugin:*) > Plugin (plugin:*) > Builtin (builtin:*)
```

Quando nomes colidem, a skill de maior precedência vence. Fork é uma cópia pessoal que o usuário editou a partir de uma skill de plugin.

### C.3 Lifecycle: Plugin ↔ Skills

#### C.3.1 Instalar plugin

```python
# Em PluginService.install():
for skill_def in manifest.skills:
    item = LibraryItem(
        id=uuid4(),
        user_id=installer_user_id,
        type=LibraryItemType.PROMPT,
        name=skill_def["name"],
        description=skill_def["markdown"],       # Markdown completo da skill
        tags=[
            "skill",
            f"plugin:{plugin.id}",                # NOVO: identifica origem
            f"plugin_name:{plugin.name}",         # Para display na UI
            f"skill_version:1",
            f"visibility:{plugin.scope}",
            f"state:active",
            "schema:skill.v1",
        ],
        resource_id=f"plugin-skill-{plugin.id}-{skill_def['name']}",
        token_count=0,
    )
    db.add(item)
```

#### C.3.2 Desabilitar plugin

Skills do plugin ficam `state:inactive` — não aparecem no SkillRegistry, mas não são deletadas.

```python
# Em PluginService.disable():
items = await db.execute(
    select(LibraryItem).where(
        LibraryItem.tags.contains([f"plugin:{plugin_id}"]),
        LibraryItem.type == LibraryItemType.PROMPT,
    )
)
for item in items.scalars():
    tags = [t for t in item.tags if not t.startswith("state:")]
    tags.append("state:inactive")
    item.tags = tags
```

#### C.3.3 Habilitar plugin

Reverso: skills voltam a `state:active`.

```python
# Em PluginService.enable():
# Mesmo pattern, mas tags.append("state:active")
```

#### C.3.4 Desinstalar plugin

Skills do plugin são **deletadas**, EXCETO forks do usuário (que sobrevivem).

```python
# Em PluginService.uninstall():
items = await db.execute(
    select(LibraryItem).where(
        LibraryItem.tags.contains([f"plugin:{plugin_id}"]),
        LibraryItem.type == LibraryItemType.PROMPT,
    )
)
for item in items.scalars():
    is_fork = any(t.startswith("fork:") for t in item.tags)
    if is_fork:
        # Manter fork, remover referência ao plugin
        item.tags = [t for t in item.tags
                     if not t.startswith("plugin:") and not t.startswith("plugin_name:")]
        item.tags.append("source:orphaned_fork")
    else:
        await db.delete(item)
```

#### C.3.5 Usuário edita skill de plugin (Fork)

Quando o usuário edita uma skill com tag `plugin:*`, criar cópia pessoal:

```python
# Em endpoint PUT /skills/{id} ou POST /skills/publish (quando draft_id aponta para skill de plugin):
original = await db.get(LibraryItem, skill_id)
is_plugin_skill = any(t.startswith("plugin:") for t in (original.tags or []))

if is_plugin_skill:
    # Criar fork — nova LibraryItem, source diferente
    fork = LibraryItem(
        id=uuid4(),
        user_id=current_user.id,
        type=LibraryItemType.PROMPT,
        name=original.name,                      # Mesmo nome — vence por precedência
        description=new_markdown,                 # Versão editada
        tags=[
            "skill",
            f"fork:plugin:{plugin_id}",           # Marca como fork
            f"skill_version:1",
            "visibility:personal",
            "state:active",
            "schema:skill.v1",
        ],
        resource_id=f"fork-{original.resource_id}",
        token_count=0,
    )
    db.add(fork)
    # NÃO modifica o original do plugin
```

#### C.3.6 Atualizar plugin

Quando plugin é atualizado (nova versão), atualizar skills não-forkadas; forkadas mantêm versão do usuário.

```python
# Em PluginService.update():
for skill_def in new_manifest.skills:
    existing = await _find_plugin_skill(db, plugin_id, skill_def["name"])
    if existing:
        is_fork = any(t.startswith("fork:") for t in (existing.tags or []))
        if is_fork:
            continue  # Respeitar versão do usuário
        # Atualizar skill do plugin
        existing.description = skill_def["markdown"]
        version = _extract_version(existing.tags) + 1
        existing.tags = [t for t in existing.tags if not t.startswith("skill_version:")]
        existing.tags.append(f"skill_version:{version}")
    else:
        # Nova skill adicionada pelo plugin — criar
        await _create_plugin_skill(db, plugin_id, skill_def)
```

### C.4 Estender SkillRegistry

**Editar**: `apps/api/app/services/ai/skills/registry.py`

```python
class SkillRegistry:
    """Unified registry for builtin + plugin + user-defined skills."""

    def __init__(self, skills: List[SkillDefinition]):
        dedup: dict[str, SkillDefinition] = {}
        for skill in skills:
            existing = dedup.get(skill.name)
            if existing and self._priority(existing) >= self._priority(skill):
                continue
            dedup[skill.name] = skill
        self._skills = list(dedup.values())

    @staticmethod
    def _priority(skill: SkillDefinition) -> int:
        """User > Fork > Plugin > Builtin."""
        src = skill.source
        if src.startswith("library:"):
            return 40
        if src.startswith("fork:"):
            return 30
        if src.startswith("plugin:"):
            return 20
        if src.startswith("builtin:"):
            return 10
        return 0

    @classmethod
    async def build(
        cls,
        *,
        user_id: str,
        db: AsyncSession,
        include_builtin: bool = True,
        plugin_ids: Optional[List[str]] = None,
    ) -> "SkillRegistry":
        builtin = load_builtin_skills() if include_builtin else []
        user = await load_user_skills(user_id, db)
        plugin = await load_plugin_skills(user_id, db, plugin_ids) if plugin_ids else []
        # Order: user first (highest priority), then plugin, then builtin
        return cls([*user, *plugin, *builtin])
```

**Editar**: `apps/api/app/services/ai/skills/loader.py` — adicionar:

```python
async def load_plugin_skills(
    user_id: str, db: AsyncSession, plugin_ids: Optional[List[str]] = None
) -> List[SkillDefinition]:
    """Load active skills from enabled plugins."""
    stmt = (
        select(LibraryItem)
        .where(
            LibraryItem.type == LibraryItemType.PROMPT,
        )
        .order_by(LibraryItem.created_at)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    skills: List[SkillDefinition] = []
    for item in items:
        tags = item.tags or []
        if "skill" not in tags:
            continue
        # Filtrar: só skills de plugins habilitados e state:active
        plugin_tag = next((t for t in tags if t.startswith("plugin:") and not t.startswith("plugin_name:")), None)
        if not plugin_tag:
            continue
        if "state:inactive" in tags:
            continue
        pid = plugin_tag.split(":", 1)[1]
        if plugin_ids and pid not in plugin_ids:
            continue

        is_fork = any(t.startswith("fork:") for t in tags)
        source = f"fork:plugin:{pid}" if is_fork else f"plugin:{pid}"

        if not item.description:
            continue
        parsed = parse_skill_markdown(item.description, source=source)
        if parsed:
            skills.append(parsed)
    return skills
```

### C.5 Lifecycle: Plugin ↔ MCP Servers

**Problema**: O `Plugin` model tem `mcp_servers: Optional[dict]`, mas o plano não define como esses servers se integram ao `MCPHub`.

**Solução**: Estender o padrão `MCPHub.with_user_servers()` (linhas 507-526):

```python
# Adicionar em MCPHub:
def with_plugin_servers(self, plugins: List["Plugin"]) -> "MCPHub":
    """Return a new hub instance that includes MCP servers from enabled plugins."""
    from app.services.mcp_config import MCPServerConfig

    plugin_servers: List[MCPServerConfig] = []
    for plugin in plugins:
        if not plugin.is_enabled or not plugin.mcp_servers:
            continue
        for name, config in plugin.mcp_servers.items():
            label = f"plugin:{plugin.id}:{name}"  # Namespace por plugin
            plugin_servers.append(MCPServerConfig(
                label=label,
                url=config.get("url", ""),
                allowed_tools=config.get("allowed_tools"),
                auth=config.get("auth"),
            ))

    if not plugin_servers:
        return self

    merged = MCPHub.__new__(MCPHub)
    merged._servers = {**self._servers}
    for s in plugin_servers:
        merged._servers[s.label] = s
    merged._builtin_handlers = dict(getattr(self, "_builtin_handlers", {}))
    merged._tools_cache = {}
    merged._lock = asyncio.Lock()
    merged._circuit_state = dict(getattr(self, "_circuit_state", {}))
    merged._clock = getattr(self, "_clock", time.monotonic)
    merged._circuit_failures = getattr(self, "_circuit_failures", 3)
    merged._circuit_cooldown_seconds = getattr(self, "_circuit_cooldown_seconds", 30)
    merged._contracts = getattr(self, "_contracts", get_mcp_contracts())
    return merged
```

**Uso no chat flow** (em `chats.py` ou executor):

```python
hub = get_mcp_hub()
hub = hub.with_user_servers(user.preferences)
hub = hub.with_plugin_servers(user_enabled_plugins)  # NOVO
```

**Credenciais**: Tokens de MCP servers de plugins são armazenados no campo `Plugin.mcp_servers` (JSON encriptado). O `PluginService.install()` deve validar URLs (HTTPS) e mascarar tokens no response.

### C.6 Lifecycle: Plugin ↔ Commands

Mesmo padrão das Skills:

| Ação | Commands |
|------|----------|
| Install | Criar registros `Command` com `source="plugin:{id}"` |
| Disable | Setar `Command.is_active = False` WHERE plugin_id |
| Enable | Setar `Command.is_active = True` WHERE plugin_id |
| Uninstall | Deletar Commands WHERE plugin_id (sem fork para commands) |
| Update | Atualizar Commands WHERE plugin_id AND não editados pelo usuário |

### C.7 Lifecycle: Plugin ↔ Hooks

| Ação | Hooks |
|------|-------|
| Install | `hook_registry.register()` com `source="plugin:{id}"` |
| Disable | `hook_registry.disable_by_source(f"plugin:{id}")` |
| Enable | `hook_registry.enable_by_source(f"plugin:{id}")` |
| Uninstall | `hook_registry.unregister_by_source(f"plugin:{id}")` |

**Sandboxing de hooks de plugins (MVP)**:
- Timeout: 5s por hook execution (hardcoded, não configurável por plugin)
- Sem acesso a DB direto — hooks de plugins são `type: "webhook"` only
- Rate limit: max 100 hook executions/minuto por plugin

### C.8 Matriz de Lifecycle Completa

| Ação Plugin | Skills | Commands | Hooks | MCP Servers |
|-------------|--------|----------|-------|-------------|
| **Install** | Criar LibraryItems com tag `plugin:{id}` | Criar Commands com `source="plugin:{id}"` | `register()` com source | Adicionar ao MCPHub via `with_plugin_servers()` |
| **Disable** | `state:inactive` em tags | `is_active = False` | `disable_by_source()` | `with_plugin_servers()` filtra `is_enabled` |
| **Enable** | `state:active` em tags | `is_active = True` | `enable_by_source()` | Servers voltam ao merge |
| **Uninstall** | Deletar (exceto forks) | Deletar | `unregister_by_source()` | Removidos do merge |
| **Update** | Atualizar não-forkadas | Atualizar | Re-register | Atualizar configs |
| **User Fork** | Nova LibraryItem `fork:plugin:*` | N/A (commands sem fork) | N/A | N/A |

### C.9 Frontend: Além de Badge + Filtro

**Skills page** (`skills/page.tsx`):

1. **Badge**: `"Plugin: {name}"` em skills com tag `plugin:*` (já no plano)
2. **Badge**: `"Fork"` em skills com tag `fork:plugin:*`
3. **Read-only indicator**: Skills de plugin sem fork mostram aviso "Esta skill pertence ao plugin X. Editar criará uma cópia pessoal."
4. **Botão "Restaurar original"**: Em forks, permite deletar o fork e voltar à versão do plugin
5. **Filtro**: `"Minhas Skills"` | `"Plugins"` | `"Forks"` | `"Todas"` (já no plano, estendido)

**Marketplace page** (`marketplace/page.tsx`):

6. **Plugin detail**: Mostrar lista de skills/commands/hooks incluídos antes de instalar
7. **Estado de skills**: Indicar quais skills do plugin foram forkadas pelo usuário

### C.10 Impacto no Escopo

| Item | Plano v2.2 | Adendo v2.2.1 |
|------|-----------|---------------|
| Arquivos novos | ~9 | **~12** (+3) |
| `plugin_skill_lifecycle.py` | Não previsto | **Novo** (~120 linhas): fork, sync, state transitions |
| Migration extra | Não previsto | **Novo**: índice em tags para queries `plugin:*` |
| `tests/test_plugin_lifecycle.py` | Não previsto | **Novo**: 12+ test cases para matriz C.8 |
| Editar `registry.py` | Não previsto | **Sim**: precedência 4 níveis + `load_plugin_skills()` |
| Editar `loader.py` | Não previsto | **Sim**: `load_plugin_skills()` |
| Editar `mcp_hub.py` | Não previsto | **Sim**: `with_plugin_servers()` |
| Estimativa total | 3-4 semanas | **4-5 semanas** (+1 semana para lifecycle + testes) |

### C.11 Ordem de Implementação (Atualizada)

Inserir entre items 7 e 8 da Semana 1-2 (Seção 7):

```
7.  Integração: hooks em tool_handlers + executors
7a. NOVO: Estender SkillRegistry com precedência 4 níveis (User>Fork>Plugin>Builtin)
7b. NOVO: Adicionar load_plugin_skills() em loader.py
7c. NOVO: Adicionar with_plugin_servers() em MCPHub
8.  5 hooks built-in
```

Inserir na Semana 3-4:

```
2.  Service: PluginService (install, enable, disable, export, import)
2a. NOVO: Plugin lifecycle para skills (fork, state transitions, update sync)
2b. NOVO: Plugin lifecycle para commands (activate/deactivate)
2c. NOVO: Plugin lifecycle para hooks (register/unregister by source)
2d. NOVO: Plugin lifecycle para MCP servers (merge/remove)
3.  Endpoint: /api/plugins/*
3a. NOVO: Testes E2E para matriz de lifecycle (C.8)
```
