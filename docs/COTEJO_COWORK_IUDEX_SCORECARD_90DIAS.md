# Cotejo Cowork x Iudex: Scorecard e Roadmap 90 Dias

Data de referência: 2026-02-11
Escopo: comparação funcional entre capacidades do Claude Cowork e o estado atual do Iudex.

## 1) Scorecard (0-5)

| Capability Cowork | Iudex (0-5) | Status | Evidência principal |
|---|---:|---|---|
| Chat + SSE + sessões + histórico | 5 | Forte | `apps/web/src/stores/chat-store.ts`, `apps/api/app/api/endpoints/chats.py` |
| Multi-model/provider selection | 4 | Forte | `apps/web/src/components/chat/model-selector.tsx`, `apps/api/app/services/ai/model_registry.py` |
| Skills engine | 5 | Forte | `apps/api/app/services/ai/skills/models.py`, `apps/api/app/services/ai/skills/loader.py` |
| Slash commands | 3 | Parcial | `apps/web/src/components/chat/slash-command-menu.tsx`, `apps/api/app/services/command_service.py` |
| Plugin manifest/lifecycle | 1 | Gap | Planejado em `docs/PLANO_IUDEX_COWORK.md` |
| Plugin import/export `.plugin` | 1 | Gap | Planejado em `docs/PLANO_IUDEX_COWORK.md` |
| Marketplace de plugins | 2 | Parcial | `apps/api/app/api/endpoints/marketplace.py`, `apps/web/src/app/(dashboard)/marketplace/page.tsx` |
| Connectors `~~category` | 2 | Parcial | MCP existe; resolução por categoria planejada |
| MCP integration | 4 | Forte | `apps/api/app/api/endpoints/mcp.py`, `apps/api/app/services/mcp_hub.py` |
| Hooks event-driven nativos | 2 | Parcial | Webhooks existem; HookRegistry planejado |
| Subagentes formais por plugin | 2 | Parcial | Base de agentes existe; modelo plugin-first pendente |
| Observabilidade/tracing/audit persistente | 3 | Parcial | Audit log persistente + partes in-memory |
| Segurança/RBAC/multi-tenant | 5 | Forte | `apps/api/app/core/security.py`, `apps/api/app/models/organization.py` |
| Vertical jurídico (PJe/DJEN/DataJud/playbooks) | 5 | Diferencial | `apps/api/app/api/endpoints/djen.py`, `apps/api/app/api/endpoints/tribunais.py`, `apps/api/app/api/endpoints/playbooks.py` |

## 2) Diagnóstico objetivo

- Paridade alta no núcleo de produto (chat, skills, multi-model, jurídico).
- Gap principal para convergir com Cowork: plataforma de plugins completa (manifest/lifecycle/import-export/marketplace plugin-first/hooks/connectors por categoria).
- Iudex já supera Cowork no domínio jurídico verticalizado (PJe, DJEN, DataJud, playbooks e fluxos forenses).

## 3) Roadmap 30/60/90

## Fase 1 (0-30 dias) — Foundation Plugin-Core
Período: 2026-02-11 a 2026-03-13

Entregas:
1. `PluginManifest` + migrations (plugin_id, scope, status, source, version).
2. `PluginManager` (install/enable/disable/uninstall/list).
3. `CommandRegistry` plugin-aware (escopo user/org/global).
4. Endpoints mínimos `/api/plugins` e `/api/plugins/{id}/commands`.

Definition of Done:
1. Instalar 1 plugin de teste e executar 3 commands com sucesso.
2. Habilitar/desabilitar plugin sem reinício da API.
3. Gerar audit log de install/enable/disable/uninstall.

## Fase 2 (31-60 dias) — Connectors + Hooks + Marketplace Base
Período: 2026-03-14 a 2026-04-12

Entregas:
1. `ConnectorRegistry` com resolução `~~category` por tenant.
2. `HookRegistry` com eventos: `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`.
3. Marketplace plugin-first: listagem, instalação e atualização de versão.
4. UI mínima de gestão de plugins e conectores.

Definition of Done:
1. 5 categorias de connector funcionando (`chat`, `email`, `cloud_storage`, `knowledge_base`, `legal_research`).
2. 3 hooks ativos com comportamento de allow/block validado.
3. Instalação de 2 plugins via UI em 1 clique.

## Fase 3 (61-90 dias) — Hardening + Subagentes + Operação
Período: 2026-04-13 a 2026-05-12

Entregas:
1. Subagentes por plugin (`agents/*.md` ou equivalente Iudex).
2. Import/export `.plugin` com validação de schema.
3. Observabilidade persistente (tool audit, traces, métricas de execução/custo/latência).
4. Testes E2E de lifecycle de plugin + commands + hooks + connectors.

Definition of Done:
1. 1 plugin completo em produção interna (commands + skills + connectors + subagente).
2. Round-trip export/import sem perda de metadados.
3. Dashboards operacionais com métricas reais e alertas básicos.

## 4) KPIs de aceite (até 2026-05-12)

| KPI | Meta |
|---|---:|
| Plugins instalados por tenant | >= 3 |
| Commands executados/dia | >= 50 |
| Connectors configurados/tenant | >= 5 |
| Sucesso de execução de plugin commands | >= 95% |
| Tempo médio command -> resposta | < 10s |
| Cobertura E2E (plugin lifecycle + commands) | >= 80% |
| Taxa de falha por hook | < 1% |
| Custo médio por execução multi-provider | tendência estável/decrescente |

## 5) Backlog técnico por sprint (sugestão)

Sprint 1:
1. Modelagem PluginManifest + migrations.
2. Serviço PluginManager + endpoints de base.
3. Testes de contrato API para lifecycle.

Sprint 2:
1. CommandRegistry plugin-aware.
2. Integração com chat input (`/` autocomplete por escopo).
3. Auditoria de eventos de command execution.

Sprint 3:
1. ConnectorRegistry e mapeamentos por tenant.
2. Resolução `~~category` em runtime.
3. UI de conectores por organização.

Sprint 4:
1. HookRegistry com eventos principais.
2. Policies de allow/block para tools.
3. Testes E2E com cenários de bloqueio.

Sprint 5:
1. Marketplace plugin-first (backend + UI).
2. Install/update flows com versionamento.
3. Curadoria inicial de plugins (legal/data/productivity).

Sprint 6:
1. Subagentes por plugin.
2. Import/export `.plugin`.
3. Hardening de observabilidade, métricas e alertas.

## 6) Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| Complexidade de runtime plugin + hooks | Alto | Entregar incremental por feature-flag |
| Regressão no chat core | Alto | Suite E2E obrigatória por release |
| Custos de multi-provider | Médio | Router de custo/qualidade e budgets por tenant |
| Segurança de plugins | Alto | Allowlist de tools + validação de manifest + isolamento de escopo |
| Latência de cadeia MCP | Médio | Timeout por tool + retries controlados + cache |

## 7) Referências de apoio

- Mapa backend: `docs/BACKEND_DOMAIN_MAP.md`
- Plano alvo: `docs/PLANO_IUDEX_COWORK.md`
- Chat/agentes inventário: `INVENTARIO_CHAT_ASSISTENTE_AGENTES.md`
- Artefatos Cowork locais: `/Users/nicholasjacob/Library/Application Support/Claude/local-agent-mode-sessions/3d43c458-1aed-4cfd-872c-2ab09a7d9f12/dfd08182-6851-4208-987d-a76af950d101/cowork_plugins`
