# Inventário de Chat / Assistente / Agentes (Iudex)

Escopo: levantamento no projeto em `/Users/nicholasjacob/Documents/Aplicativos/Iudex` cobrindo frontend + backend com evidências por arquivo/linha.

## 1) Chat (UI + fluxo principal)

**Frontend (UI e comandos)**
- UI principal do chat e integração com store, canvas, multi‑modelo, aprovação de tools, compactação e checkpoints: `apps/web/src/components/chat/chat-interface.tsx:40`.
- Comandos de barra: detecção de `/` e `@`, menus de comandos e contexto: `apps/web/src/components/chat/chat-input.tsx:165`, `apps/web/src/components/chat/chat-input.tsx:179`, `apps/web/src/components/chat/chat-input.tsx:187`.
- Slash commands (sistema): set‑model, modo multi‑modelo, comandos de canvas, templates, navegação para skills: `apps/web/src/components/chat/slash-command-menu.tsx:25`.
- At‑command para modelos/arquivos/biblioteca/juris/link/áudio, incluindo inserção `@Modelo` ou `@[Item](id:tipo)`: `apps/web/src/components/chat/at-command-menu.tsx:22`, `apps/web/src/components/chat/at-command-menu.tsx:141`.
- Comandos `/canvas`, `/doc`, `/documento`, `/minuta` parseados e normalizados para edição no canvas: `apps/web/src/components/chat/chat-interface.tsx:101`.

**Backend (API do chat)**
- CRUD de chats (sessões), listagem e mensagens: `apps/api/app/api/endpoints/chats.py:1150`, `apps/api/app/api/endpoints/chats.py:1170`, `apps/api/app/api/endpoints/chats.py:1206`, `apps/api/app/api/endpoints/chats.py:1298`, `apps/api/app/api/endpoints/chats.py:1319`.
- Modelo de chat/mensagem (sessão e histórico persistido): `apps/api/app/models/chat.py:20`.

## 2) Streaming

**Frontend**
- SSE para jobs (`/jobs/{id}/stream`) com ingestão de tokens e eventos (canvas, artifacts, tool calls etc.): `apps/web/src/stores/chat-store.ts:389`.
- Streaming de mensagens do chat (`/chats/{id}/messages/stream`) com re‑conexão e Last‑Event‑ID: `apps/web/src/stores/chat-store.ts:4063`.

**Backend**
- Streaming SSE para chat principal: `apps/api/app/api/endpoints/chats.py:1898`.
- Streaming SSE para chat multi‑modelo (`/chat/threads/{id}/messages`): `apps/api/app/api/endpoints/chat.py:1`, `apps/api/app/api/endpoints/chat.py:217`.
- Streaming SSE para jobs e branch de agentes (eventos `token`, `thinking`, `tool_call`, `tool_result`): `apps/api/app/api/endpoints/jobs.py:530`.

## 3) Seleção de modelo / provider

**Frontend**
- Registry de modelos com provider, capacidades, flags para jurídico/agents: `apps/web/src/config/models.ts:1`.
- UI de seleção por provider (OpenAI, Anthropic, Google, xAI, OpenRouter, Perplexity, Internal) e agentes: `apps/web/src/components/chat/model-selector.tsx:33`.
- Slash commands para trocar modelo/mode: `apps/web/src/components/chat/slash-command-menu.tsx:25`.
- At‑command menu para mencionar modelos com `@Modelo`: `apps/web/src/components/chat/at-command-menu.tsx:22`.

**Backend**
- Registry de modelos com provider, capabilities, flags `for_agents`, `for_juridico`, `supports_streaming`: `apps/api/app/services/ai/model_registry.py:21`.
- Validação de modelo no chat streaming: `apps/api/app/api/endpoints/chats.py:2001`.
- Parâmetros multi‑modelo no endpoint de chat paralelo (lista `models` + overrides): `apps/api/app/api/endpoints/chat.py:217`.

## 4) Tools (tool calling + aprovação)

**Frontend**
- Modal de aprovação de tools (nível de risco, preview de input, opções de “lembrar”): `apps/web/src/components/chat/tool-approval-modal.tsx:29`.
- Fluxo de aprovação/negação via `/chats/{id}/tool-approval` e armazenamento de permissões locais: `apps/web/src/stores/chat-store.ts:6931`.

**Backend**
- Endpoint de aprovação de tool com retomada do executor/JobManager: `apps/api/app/api/endpoints/chats.py:7171`.
- Modelo de permissão de tools com escopo (session/project/global) e modos allow/deny/ask: `apps/api/app/models/tool_permission.py:1`.
- Branch de stream de agentes em jobs emitindo eventos `tool_call` e `tool_result`: `apps/api/app/api/endpoints/jobs.py:634`.

## 5) Histórico / sessões

**Backend**
- Entidade Chat (sessão), ChatMessage (histórico) persistidos: `apps/api/app/models/chat.py:20`.
- Listagem/consulta de mensagens por chat (histórico): `apps/api/app/api/endpoints/chats.py:1319`.
- Compactação/summary (modelo de resumos de conversa): `apps/api/app/models/conversation_summary.py:1`.

**Frontend**
- Controle de chat atual, mensagens e ações de compactação: `apps/web/src/stores/chat-store.ts:6903`.

## 6) Assistente (endpoint dedicado)

**Backend**
- Endpoint `/assistant/chat` com streaming SSE e contexto opcional (workflow/document/corpus): `apps/api/app/api/endpoints/assistant.py:1`.
- Streaming do assistente com fallback de provider e envio de citações: `apps/api/app/api/endpoints/assistant.py:152`.

**Frontend (página)**
- Página de marketing/entrada “Assistant”: `apps/web/src/app/assistant/page.tsx:1`.

## 7) Agentes (orquestração e tarefas)

**Frontend**
- Orquestrador de passos (strategist/researcher/drafter/reviewer): `apps/web/src/services/agents/agent-orchestrator.ts:1`.
- Simulação de resposta multi‑agente: `apps/web/src/services/ai-simulation.ts:78`.

**Backend**
- Tarefas de agentes em background (spawn/list/status/cancel): `apps/api/app/api/endpoints/agent_tasks.py:1`.
- Promoção de chat para agente com sessão de contexto e exportação para workflow: `apps/api/app/api/endpoints/context_bridge.py:1`.
- Branch de execução para modelos agentic via OrchestrationRouter no streaming de jobs: `apps/api/app/api/endpoints/jobs.py:530`.

## 8) Multi‑modelo (comparador e consolidação)

**Frontend**
- Toggle de modo multi‑modelo no input e seleção de modelos: `apps/web/src/components/chat/chat-input.tsx:65`.
- Streaming multi‑modelo no store (payload com `models` e parsing de eventos por modelo): `apps/web/src/stores/chat-store.ts:6114`.

**Backend**
- API de chat multi‑modelo com SSE: `apps/api/app/api/endpoints/chat.py:1`.
- Consolidação de respostas multi‑modelo (endpoint citado no header): `apps/api/app/api/endpoints/chat.py:1`.

---

## Cobertura mínima dos requisitos do pedido
- Streaming: seção 2 (frontend + backend).
- Seleção de modelo/provider: seção 3.
- Tools: seção 4.
- Comandos: seção 1 (slash/at) + seção 3 (troca de modelo).
- Histórico: seção 5.
- Sessões: seção 5 + CRUD de chats (seção 1).
- Assistente: seção 6.
- Agentes: seção 7.

