# Guia de Planejamento — 5 Gaps Identificados

## Contexto

Após verificação completa da plataforma Iudex (3 níveis: Prompt Skills, Workflow Builder, MCP/Code Skills), foram identificados 5 gaps a serem implementados em paralelo.

---

## Gap 1: Alembic Migration (workflows + workflow_runs)

### Problema
Modelos `Workflow` e `WorkflowRun` existem em `app/models/workflow.py` mas:
- ❌ Não importados em `alembic/env.py` (impede autogenerate)
- ❌ Não importados em `app/core/database.py:init_db()`
- ❌ Nenhuma migration existe em `alembic/versions/`

### Solução
1. **Editar** `alembic/env.py` — adicionar imports de Workflow, WorkflowRun
2. **Editar** `app/core/database.py:init_db()` — adicionar imports
3. **Criar** migration manual `alembic/versions/h8i9j0k1l2m3_add_workflows_tables.py`
   - Tabela `workflows`: id, user_id, organization_id, name, description, graph_json, is_active, is_template, tags, schedule_cron, schedule_enabled, schedule_timezone, last_scheduled_run, created_at, updated_at
   - Tabela `workflow_runs`: id, workflow_id, user_id, status, input_data, output_data, current_node, state_snapshot, logs, error_message, trigger_type, started_at, completed_at, created_at
   - Índices: ix_workflows_user_id, ix_workflows_is_active, ix_workflow_runs_status, ix_workflow_runs_workflow_id

### Arquivos
| Arquivo | Ação |
|---------|------|
| `alembic/env.py` | EDIT — adicionar imports |
| `app/core/database.py` | EDIT — adicionar imports em init_db() |
| `app/models/workflow.py` | EDIT — adicionar campos schedule_* e trigger_type |
| `alembic/versions/h8i9j0k1l2m3_add_workflows_tables.py` | NOVO |

---

## Gap 2: Scheduler/Triggers para Workflows

### Problema
Workflows só executam via `POST /workflows/{id}/run` (manual). Não há:
- ❌ Agendamento cron
- ❌ Triggers por webhook
- ❌ Execução periódica

### Infraestrutura Existente
- ✅ Celery + Redis + Beat já configurados (`app/workers/celery_app.py`)
- ✅ 1 beat_schedule já funciona (`djen-daily-sync`)
- ✅ Webhook endpoint genérico existe (`app/api/endpoints/webhooks.py`)
- ✅ WorkflowRunner com streaming já implementado

### Solução
1. **Editar** `app/models/workflow.py` — adicionar campos: `schedule_cron`, `schedule_enabled`, `schedule_timezone`, `last_scheduled_run`
2. **Criar** `app/workers/tasks/workflow_tasks.py` — Celery task `run_scheduled_workflow`
3. **Criar** `app/services/ai/workflow_scheduler.py` — Classe que carrega schedules do DB e registra no Celery Beat
4. **Editar** `app/api/endpoints/workflows.py` — novos endpoints:
   - `PUT /workflows/{id}/schedule` — configurar cron
   - `POST /workflows/{id}/trigger` — webhook trigger (com secret)
   - `GET /workflows/{id}/schedule` — ver config de agendamento
5. **Editar** `app/workers/celery_app.py` — registrar task e inicialização do scheduler
6. **Frontend**: Componente de agendamento no properties panel do workflow

### Arquivos
| Arquivo | Ação |
|---------|------|
| `app/models/workflow.py` | EDIT — campos schedule_* |
| `app/workers/tasks/workflow_tasks.py` | NOVO — Celery task |
| `app/services/ai/workflow_scheduler.py` | NOVO — Loader de schedules |
| `app/api/endpoints/workflows.py` | EDIT — endpoints schedule/trigger |
| `app/workers/celery_app.py` | EDIT — registrar novo task |
| `apps/web/.../workflow-builder.tsx` | EDIT — UI de agendamento |

---

## Gap 3: UI para MCP Servers do Usuário

### Problema
MCP servers são configurados via env var `IUDEX_MCP_SERVERS` (JSON). Usuários não podem adicionar seus próprios servers pela interface.

### Infraestrutura Existente
- ✅ `MCPHub` com `list_servers()`, `tool_call()`, `tool_search()`
- ✅ `User.preferences` (JSON field) com endpoints GET/PUT
- ✅ Frontend já tem `mcpToolCalling`, `mcpServerLabels` no Zustand
- ✅ Endpoints MCP: `/mcp/servers`, `/mcp/tools/search`, `/mcp/tools/call`
- ✅ PolicyEngine com rate limiting e audit

### Solução
1. **Editar** `app/services/mcp_hub.py` — carregar servers do user.preferences além de env
2. **Editar** `app/services/mcp_config.py` — função `load_user_mcp_servers(user_id)`
3. **Editar** `app/api/endpoints/mcp.py` — endpoint para gerenciar servers do usuário:
   - `GET /mcp/user-servers` — listar servers do usuário
   - `POST /mcp/user-servers` — adicionar server
   - `PUT /mcp/user-servers/{label}` — editar
   - `DELETE /mcp/user-servers/{label}` — remover
   - `POST /mcp/user-servers/{label}/test` — testar conectividade
4. **Frontend**: Página de configuração MCP em Settings
   - `apps/web/src/components/settings/mcp-servers-config.tsx` — NOVO
   - Formulário: label, URL, allowed_tools, auth type
   - Lista de servers com status (online/offline)
   - Botão "Testar Conexão"

### Segurança
- Validar URL (HTTPS obrigatório em produção)
- Rate limit por server do usuário (max 100 calls/min)
- Whitelist de tools obrigatória
- Tokens armazenados encriptados em preferences

### Arquivos
| Arquivo | Ação |
|---------|------|
| `app/services/mcp_config.py` | EDIT — load_user_mcp_servers() |
| `app/services/mcp_hub.py` | EDIT — merge env + user servers |
| `app/api/endpoints/mcp.py` | EDIT — CRUD user-servers |
| `apps/web/.../settings/mcp-servers-config.tsx` | NOVO |
| `apps/web/.../api-client.ts` | EDIT — métodos MCP |

---

## Gap 4: Sandboxing & Hardening

### Problema
Não há sandboxing explícito para execução de tools/workflows. Embora a postura atual seja segura (sem eval/exec, registry-only tools), falta hardening para produção.

### Postura Atual (Já Implementada)
- ✅ Tool Registry: apenas tools pré-registradas executam
- ✅ PolicyEngine: ALLOW/ASK/DENY por tool
- ✅ Permission Manager: hierarquia session > project > global > system
- ✅ bash/file_write/file_delete → DENY by default
- ✅ Audit logging completo
- ✅ HIL para operações sensíveis
- ✅ Zero eval()/exec() no codebase

### Solução (Hardening Adicional)
1. **Criar** `app/services/ai/sandbox/execution_limits.py` — Limites de execução:
   - Timeout por node de workflow (default 120s)
   - Timeout por workflow completo (default 30min)
   - Max nodes por workflow (50)
   - Max concurrent workflows por user (5)
   - Memory budget por workflow run
2. **Criar** `app/services/ai/sandbox/network_policy.py` — Restrições de rede:
   - URL allowlist para web_search (domínios jurídicos)
   - Block private IPs (SSRF protection)
   - Max response size (10MB)
3. **Editar** `app/services/ai/workflow_compiler.py` — Injetar limites na compilação
4. **Editar** `app/services/ai/workflow_runner.py` — Enforce timeouts
5. **Editar** `app/services/ai/tool_gateway/policy_engine.py` — Adicionar cost tracking

### Arquivos
| Arquivo | Ação |
|---------|------|
| `app/services/ai/sandbox/__init__.py` | NOVO |
| `app/services/ai/sandbox/execution_limits.py` | NOVO |
| `app/services/ai/sandbox/network_policy.py` | NOVO |
| `app/services/ai/workflow_compiler.py` | EDIT — limites |
| `app/services/ai/workflow_runner.py` | EDIT — timeouts |
| `app/services/ai/tool_gateway/policy_engine.py` | EDIT — cost tracking |

---

## Gap 5: Public Marketplace

### Problema
Compartilhamento existe (Share model com PENDING/ACCEPTED) mas não há:
- ❌ Catálogo público de templates/workflows
- ❌ Sistema de rating/review
- ❌ Discovery/busca pública
- ❌ Categorias e tags navegáveis

### Infraestrutura Existente
- ✅ Share model com resource_type, permission, status
- ✅ LibraryItem com is_shared, tags
- ✅ Workflow com is_template, tags
- ✅ Templates legais pré-definidos
- ✅ Endpoints de compartilhamento (share/accept/reject/revoke)

### Solução
1. **Criar** `app/models/marketplace.py` — Novos modelos:
   - `MarketplaceItem`: resource_type, resource_id, publisher_id, title, description, category, tags, is_published, download_count, avg_rating
   - `MarketplaceReview`: item_id, user_id, rating (1-5), comment
2. **Criar** `app/api/endpoints/marketplace.py` — Endpoints:
   - `GET /marketplace` — Catálogo público (filtro por category, tags, search)
   - `GET /marketplace/{id}` — Detalhe do item
   - `POST /marketplace` — Publicar (owner only)
   - `PUT /marketplace/{id}` — Editar publicação
   - `DELETE /marketplace/{id}` — Retirar do marketplace
   - `POST /marketplace/{id}/install` — Instalar/clonar para minha conta
   - `POST /marketplace/{id}/review` — Avaliar
   - `GET /marketplace/{id}/reviews` — Listar avaliações
   - `GET /marketplace/categories` — Categorias disponíveis
3. **Criar** migration para tabelas marketplace
4. **Frontend**: Página de marketplace
   - `apps/web/src/app/(dashboard)/marketplace/page.tsx`
   - `apps/web/src/components/marketplace/marketplace-catalog.tsx`
   - `apps/web/src/components/marketplace/marketplace-item-card.tsx`
   - `apps/web/src/components/marketplace/publish-dialog.tsx`

### Categorias Sugeridas
- Minutas (petições, contratos, pareceres)
- Workflows (fluxos de automação)
- Prompts (instruções para IA)
- Cláusulas (biblioteca de cláusulas)
- Agents (templates de agente)

### Arquivos
| Arquivo | Ação |
|---------|------|
| `app/models/marketplace.py` | NOVO |
| `app/schemas/marketplace.py` | NOVO |
| `app/api/endpoints/marketplace.py` | NOVO |
| `app/api/routes.py` | EDIT — registrar router |
| `alembic/versions/...marketplace.py` | NOVO |
| `apps/web/.../marketplace/page.tsx` | NOVO |
| `apps/web/.../marketplace/marketplace-catalog.tsx` | NOVO |
| `apps/web/.../marketplace/marketplace-item-card.tsx` | NOVO |
| `apps/web/.../marketplace/publish-dialog.tsx` | NOVO |
| `apps/web/.../api-client.ts` | EDIT — métodos marketplace |
| `apps/web/.../sidebar-pro.tsx` | EDIT — link Marketplace |

---

## Ordem de Execução (Paralelo)

Todos os 5 gaps são **independentes** e podem ser implementados em paralelo:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Gap 1          │  │  Gap 2          │  │  Gap 3          │  │  Gap 4          │  │  Gap 5          │
│  Migration      │  │  Scheduler      │  │  User MCP UI    │  │  Sandboxing     │  │  Marketplace    │
│  Alembic        │  │  Celery Beat    │  │  Config page    │  │  Hardening      │  │  Catalog        │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │                    │                    │
         └────────────────────┴────────────────────┴────────────────────┴────────────────────┘
                                                   │
                                            ┌──────┴──────┐
                                            │  Integração │
                                            │  Final      │
                                            └─────────────┘
```

### Dependência única
- Gap 2 (Scheduler) precisa dos campos do Gap 1 (Migration), mas o agente do Gap 2 pode criar os campos no model e o Gap 1 gera a migration que os inclui.

---

## Métricas de Sucesso

| Gap | Critério de Conclusão |
|-----|----------------------|
| 1. Migration | `alembic upgrade head` passa sem erro |
| 2. Scheduler | Workflow com cron executa automaticamente |
| 3. User MCP | Usuário adiciona MCP server pela UI e usa tools |
| 4. Sandboxing | Workflow com timeout é cancelado; SSRF blocked |
| 5. Marketplace | Publicar template → outro user instala → rating funciona |
