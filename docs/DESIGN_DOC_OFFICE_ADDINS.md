# Design Doc — Add-ins Outlook e Teams para Iudex/Vorbium

> **Versao**: 1.0
> **Data**: 2026-02-10
> **Autor**: Equipe Vorbium
> **Status**: Draft
> **PRD Relacionado**: `PRD_OFFICE_ADDINS.md`

---

## Sumario

1. [Contexto do Repositorio](#1-contexto-do-repositorio)
2. [Stack Tecnologico](#2-stack-tecnologico)
3. [Arquitetura Geral](#3-arquitetura-geral)
4. [ADRs (Architecture Decision Records)](#4-adrs-architecture-decision-records)
5. [Autenticacao e Autorizacao](#5-autenticacao-e-autorizacao)
6. [Microsoft Graph API](#6-microsoft-graph-api)
7. [Outlook Add-in — Componentes](#7-outlook-add-in-componentes)
8. [Teams App — Componentes](#8-teams-app-componentes)
9. [Modelo de Dados](#9-modelo-de-dados)
10. [Endpoints da API](#10-endpoints-da-api)
11. [Seguranca](#11-seguranca)
12. [Observabilidade e Telemetria](#12-observabilidade-e-telemetria)
13. [Deployment e Distribuicao](#13-deployment-e-distribuicao)
14. [Timeline New Outlook](#14-timeline-new-outlook)
15. [Testes e QA](#15-testes-e-qa)
16. [Fases de Implementacao](#16-fases-de-implementacao)

---

## 1. Contexto do Repositorio

### 1.1. Estrutura do Monorepo Iudex

```
iudex/
├── apps/
│   ├── api/                    # FastAPI backend (Python 3.11+)
│   │   ├── app/
│   │   │   ├── api/endpoints/  # 40+ endpoint routers
│   │   │   │   ├── word_addin.py      # Word add-in endpoints (referencia)
│   │   │   │   ├── workflows.py       # Workflow triggers, runs, HIL
│   │   │   │   ├── chats.py           # Chat SSE, multi-LLM
│   │   │   │   └── corpus.py          # Busca semantica, RAG
│   │   │   ├── models/               # SQLAlchemy models
│   │   │   │   ├── workflow.py        # Workflow, WorkflowRun, WorkflowVersion
│   │   │   │   └── user.py           # User, Organization
│   │   │   ├── services/
│   │   │   │   ├── ai/orchestrator.py # Multi-agent orchestrator
│   │   │   │   ├── ai/model_registry.py # Claude, Gemini, GPT registry
│   │   │   │   ├── dms_service.py     # Graph/SharePoint integration
│   │   │   │   └── word_addin_service.py # Word add-in service layer
│   │   │   ├── workers/tasks/
│   │   │   │   └── workflow_tasks.py  # Celery async workflow execution
│   │   │   └── core/
│   │   │       ├── security.py        # JWT, get_current_user
│   │   │       └── config.py          # Settings (env vars)
│   │   └── tests/
│   ├── web/                    # Next.js frontend (React 18)
│   ├── office-addin/           # Word Add-in existente (REFERENCIA)
│   │   ├── manifest.xml        # Manifesto XML classico (Host: Document)
│   │   ├── src/
│   │   │   ├── api/
│   │   │   │   ├── client.ts          # Axios + JWT + refresh queue
│   │   │   │   └── sse-client.ts      # SSE streaming (fetch + ReadableStream)
│   │   │   ├── stores/
│   │   │   │   ├── auth-store.ts      # Zustand + persist (JWT login)
│   │   │   │   ├── chat-store.ts      # Chat state
│   │   │   │   ├── playbook-store.ts  # Playbook runs, redlines
│   │   │   │   └── corpus-store.ts    # Corpus search
│   │   │   ├── office/
│   │   │   │   ├── document-bridge.ts # Office.js Word API bridge
│   │   │   │   └── redline-engine.ts  # OOXML redline insertion
│   │   │   └── components/            # React components (Fluent UI v9)
│   │   ├── package.json               # Vite, React 18, Fluent UI v9
│   │   └── vite.config.ts
│   ├── outlook-addin/         # NOVO — Outlook Add-in
│   └── teams-app/             # NOVO — Teams Bot + Tab
├── packages/
│   └── shared/                # Tipos compartilhados
├── turbo.json
└── package.json               # Turborepo root
```

### 1.2. Padroes Existentes a Reutilizar

| Padrao | Onde Existe | Reutilizar Em |
|--------|-----------|--------------|
| Axios + JWT + refresh queue | `office-addin/src/api/client.ts` | Ambos add-ins |
| SSE streaming client | `office-addin/src/api/sse-client.ts` | Ambos add-ins |
| Zustand stores (auth, chat) | `office-addin/src/stores/` | Ambos add-ins |
| Fluent UI v9 components | `office-addin/src/components/` | Ambos add-ins |
| FastAPI endpoint pattern | `api/endpoints/word_addin.py` | Novos endpoints |
| Pydantic request/response | `api/schemas/word_addin.py` | Novos schemas |
| Celery task pattern | `api/workers/tasks/workflow_tasks.py` | Notificacoes proativas |
| DMS Graph integration | `api/services/dms_service.py` | Graph Mail/Calendar |
| Vite + React + TypeScript | `office-addin/vite.config.ts` | Outlook add-in |

---

## 2. Stack Tecnologico

### 2.1. Outlook Add-in

| Componente | Tecnologia | Versao | Justificativa |
|-----------|-----------|--------|--------------|
| Runtime | Office.js | Mailbox 1.14 (target), 1.5 (min) | Requirement set para NAA + attachments |
| Framework | React | 18.2.x | Mesmo do Word add-in |
| UI Library | Fluent UI v9 | 9.56.x | Design system oficial Microsoft |
| State | Zustand | 4.4.x | Mesmo padrao existente |
| HTTP Client | Axios | 1.6.x | Com refresh queue (padrao existente) |
| SSE | Fetch nativo | N/A | Mesmo padrao de `sse-client.ts` |
| Auth | MSAL.js | >= 3.27.0 | NAA (createNestablePublicClientApplication) |
| Build | Vite | 5.4.x | Mesmo do Word add-in |
| TypeScript | TypeScript | 5.3.x | Strict mode |
| Styling | Tailwind CSS | 3.4.x | Mesmo do Word add-in |
| Manifest | XML | VersionOverrides 1.1 | Host: Mailbox (classico) |

### 2.2. Teams App

| Componente | Tecnologia | Versao | Justificativa |
|-----------|-----------|--------|--------------|
| Bot Runtime | Teams SDK v2 (ou adapter manual) | 2.x (GA JS/C#, Preview Python) | Substitui Bot Framework (descontinuado dez/2025) |
| Bot Hosting | Azure Bot Service | N/A | Endpoint HTTPS para webhooks |
| Tab Framework | React | 18.2.x | Consistencia com demais apps |
| Tab UI | Fluent UI v9 | 9.56.x | Mesmo design system |
| Teams SDK | @microsoft/teams-js | 2.x | SSO, context, deep links |
| Adaptive Cards | adaptivecards-templating | 2.x | Templating engine |
| Auth | MSAL.js + OBO | >= 3.x | SSO Teams + On-Behalf-Of flow |
| Manifest | JSON | Teams app manifest v1.19 | Manifesto unificado Teams Platform |
| Bot Language | Python (FastAPI) | 3.11+ | Integrado ao backend existente |

### 2.3. Backend (Novos Componentes)

| Componente | Tecnologia | Versao | Justificativa |
|-----------|-----------|--------|--------------|
| Outlook endpoints | FastAPI | Existente | Router adicional em `endpoints/` |
| Teams bot endpoint | FastAPI | Existente | Router para webhook do Teams (Activity JSON) |
| Graph SDK | msgraph-sdk-python | 1.x | Tipado, async, auto-retry |
| Webhook receiver | FastAPI | Existente | Endpoint para Graph change notifications |
| Proactive messaging | Teams SDK / Adapter manual | 2.x | Via ConversationReference (padrao Bot Framework mantido) |
| Queue | Celery | Existente | Workflow tasks + notificacoes |
| Cache | Redis | Existente | ConversationReference, tokens Graph |

---

## 3. Arquitetura Geral

### 3.1. Diagrama de Contexto

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Microsoft 365 Tenant                            │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐    │
│  │   Outlook        │  │   Teams          │  │   Word               │    │
│  │   (New/OWA)      │  │   (Desktop/Web)  │  │   (Desktop/Web)      │    │
│  │                   │  │                   │  │                      │    │
│  │  ┌─────────────┐ │  │  ┌─────────────┐ │  │  ┌────────────────┐ │    │
│  │  │ Outlook     │ │  │  │ Teams Bot   │ │  │  │ Word Add-in    │ │    │
│  │  │ Add-in      │ │  │  │ + Tab       │ │  │  │ (existente)    │ │    │
│  │  │ (Task Pane) │ │  │  │             │ │  │  │                │ │    │
│  │  └──────┬──────┘ │  │  └──────┬──────┘ │  │  └───────┬────────┘ │    │
│  └─────────┼────────┘  └─────────┼────────┘  └──────────┼──────────┘    │
│            │                      │                       │               │
│            │ HTTPS                │ HTTPS                 │ HTTPS         │
│            │ + SSE                │ + Bot Framework        │ + SSE         │
└────────────┼──────────────────────┼───────────────────────┼───────────────┘
             │                      │                       │
             ▼                      ▼                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           Iudex API (FastAPI)                           │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ /outlook-    │  │ /teams-bot/  │  │ /word-addin/ │  │ /chats/    │  │
│  │  addin/*     │  │  webhook     │  │  *           │  │ /corpus/   │  │
│  │              │  │  /messages   │  │              │  │ /workflows │  │
│  │ - summarize  │  │              │  │ - analyze    │  │            │  │
│  │ - classify   │  │ Bot Adapter  │  │ - playbook   │  │ Shared     │  │
│  │ - deadlines  │  │ Card Actions │  │ - redline    │  │ Endpoints  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘  │
│         │                  │                  │                │          │
│         ▼                  ▼                  ▼                ▼          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    Service Layer                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │  │
│  │  │ AI          │  │ Workflow    │  │ Corpus      │               │  │
│  │  │ Orchestrator│  │ Engine      │  │ Service     │               │  │
│  │  │ (multi-LLM) │  │ (LangGraph) │  │ (RAG)       │               │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘               │  │
│  │         │                 │                 │                      │  │
│  │         ▼                 ▼                 ▼                      │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────┐  │  │
│  │  │ Claude   │  │ Celery       │  │ Qdrant   │  │ PostgreSQL   │  │  │
│  │  │ Gemini   │  │ Workers      │  │ Pinecone │  │ (SQLAlchemy) │  │  │
│  │  │ GPT      │  │ (Redis)      │  │ Neo4j    │  │              │  │  │
│  │  └──────────┘  └──────────────┘  └──────────┘  └──────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    Microsoft Graph API                             │  │
│  │  Mail.Read │ Calendars.ReadWrite │ User.Read │ ChannelMessage.Read │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2. Fluxo de Dados — Sumarizacao de E-mail

```
User abre e-mail ──► Outlook carrega task pane
                          │
                          ▼
                     Office.js: item.body.getAsync(Html)
                          │
                          ▼
                     POST /outlook-addin/summarize
                     { email_body, email_subject, from, to }
                          │
                          ▼
                     SSE Stream ◄── AI Orchestrator ◄── LLM (Claude/Gemini)
                          │
                          ▼
                     Task Pane renderiza:
                     - Tipo juridico + confianca
                     - Resumo estruturado
                     - Prazos extraidos
                     - Acoes sugeridas
                     - Workflows recomendados
```

### 3.3. Fluxo de Dados — Bot Teams

```
User envia mensagem ──► Teams envia HTTP POST
                              │
                              ▼
                        /teams-bot/webhook
                        Bot Framework Adapter
                              │
                              ▼
                        Classifica intencao:
                        ┌─────┼──────┬────────────┐
                        ▼     ▼      ▼            ▼
                     /pesquisar  /workflow  /status   Chat livre
                        │        │         │          │
                        ▼        ▼         ▼          ▼
                     corpus/   workflow/  workflow/   chats/
                     search    {id}/run   runs/{id}  messages/
                        │        │         │         stream
                        ▼        ▼         ▼          │
                     Adaptive  Adaptive  Adaptive     ▼
                     Card      Card      Card      Text msg
                     (results) (started) (status)  (streamed)
```

### 3.4. Fluxo de Dados — Notificacao Proativa

```
Celery Worker detecta WorkflowRun status change
          │
          ▼
    workflow_tasks.py: on_status_change()
          │
          ▼
    Busca ConversationReference do user no Redis
          │
          ▼
    Bot Framework: ContinueConversationAsync(ref)
          │
          ▼
    Envia Adaptive Card:
    ┌─────────────────────────────┐
    │ Workflow "Due Diligence"    │
    │ Status: Aguardando Aprovacao│
    │                             │
    │ Resumo: Analise de 15       │
    │ clausulas concluida.        │
    │ 3 precisam de revisao.      │
    │                             │
    │ [Aprovar] [Rejeitar] [Ver]  │
    └─────────────────────────────┘
          │
          ▼
    User clica "Aprovar" ──► Card Action callback
          │
          ▼
    POST /workflows/{id}/runs/{runId}/hil
    { action: "approve", node: "review_node" }
          │
          ▼
    Celery resume WorkflowRun
```

---

## 4. ADRs (Architecture Decision Records)

### ADR-001: Manifesto JSON Unificado para Outlook (nao XML)

**Contexto**: O Word add-in existente usa manifesto XML classico com `Host: Document`. Outlook precisa de `Host: Mailbox`. Existem duas opcoes: XML classico separado ou JSON unificado.

**Decisao**: Usar **JSON Unificado** para o Outlook add-in. Manter XML classico para o Word add-in existente (migrar futuramente).

**Justificativa**:
- JSON Unificado ja esta em **producao** para Outlook (GA)
- Schema unico (vs. 7 schemas XML separados) — muito mais simples
- Strings diretas em vez do sistema `resid` + `<Resources>` do XML
- Alinhamento com Teams App model — facilita futura app unica cross-M365
- Suporte a Copilot Agents (anunciado Build 2025)
- Word/Excel/PowerPoint GA para JSON anunciado no Build 2025
- Ferramenta de conversao disponivel: `office-addin-manifest-converter`

**Consequencias**:
- Um manifesto XML (Word, existente) + dois JSON (Outlook + Teams)
- Futuro: migrar Word add-in para JSON unificado e ter app unica
- Possivel manter ambas as versoes simultaneamente durante migracao

**Nota**: O manifesto XML de exemplo na Secao 7.2 serve como referencia de fallback. Para producao, usar o JSON unificado.

### ADR-002: NAA como Autenticacao Primaria (Outlook)

**Contexto**: Outlook add-ins podem usar popup OAuth, SSO via `getAccessToken()`, ou NAA (Nested App Authentication).

**Decisao**: NAA como primario, SSO classico como fallback, popup como ultimo recurso.

**Justificativa**:
- NAA e o modelo recomendado pela Microsoft desde 2024
- Nao requer popup (melhor UX)
- Usa o token do host Office como bootstrap
- Suportado em New Outlook, OWA, e mobile
- Classic Outlook (COM/VSTO) nao suporta NAA — mas esta sendo descontinuado

**Consequencias**: Requer MSAL.js >= 3.27.0. Precisa de fallback para Outlook classic.

### ADR-003: Teams SDK v2 (nao Bot Framework legado)

**Contexto**: Bot Framework SDK foi **descontinuado em dezembro 2025** (suporte encerrado, tickets nao mais atendidos). Microsoft recomenda migracao para Teams SDK v2 ou M365 Agents SDK.

**Decisao**: Usar Teams SDK v2 para o bot Teams, com endpoint webhook integrado ao FastAPI.

**Justificativa**:
- Bot Framework SDK esta descontinuado — nao usar para novos projetos
- Teams SDK v2 reduz boilerplate em 70-90% vs Bot Framework
- Consolida Botbuilder, Graph, Adaptive Cards e Client SDK em biblioteca unica
- Suporte nativo a AI (MCP, A2A) — ideal para integracao multi-agente do Iudex
- Backward-compatible com bots existentes do Bot Framework
- Versao Python ainda em preview — alternativa: endpoint webhook manual no FastAPI que processa Activities diretamente

**Consequencias**:
- Se Python SDK do Teams SDK v2 nao estiver GA, usar adapter manual no FastAPI (recebe Activity JSON, processa, retorna)
- MCP integration permite conectar agentes do Iudex como MCP Servers
- Adaptive Cards rendering e JSON puro (sem SDK de rendering)

### ADR-004: Adaptive Cards para Resultados (nao texto plano)

**Contexto**: Bot pode responder com texto, Hero Cards, ou Adaptive Cards.

**Decisao**: Usar Adaptive Cards para todos os resultados estruturados (pesquisa, workflow, analise).

**Justificativa**:
- Layout rico com botoes, tabelas, badges
- Acoes interativas (aprovar, rejeitar, ver mais)
- Consistencia visual com Microsoft 365
- Schema v1.5 suportado em desktop e web do Teams; **mobile suporta apenas v1.2 completamente**

**Consequencias**: Payload max de 28KB por card. Resultados grandes devem ser paginados. Sempre testar cards em mobile. `wrap: true` obrigatorio em TextBlocks.

### ADR-004b: Proactive Messaging (nao Office 365 Connectors)

**Contexto**: Office 365 Connectors foram **descontinuados em dezembro 2025**. Precisamos de uma alternativa para enviar notificacoes ao Teams.

**Decisao**: Usar Proactive Messaging via ConversationReference (padrao do Bot Service).

**Justificativa**:
- Connectors classicos retornam HTTP 410 (Gone)
- Proactive messaging e o padrao oficial para bots enviarem mensagens sem interacao do usuario
- Funciona com Adaptive Cards (layout rico)
- ConversationReference armazenado em Redis (ADR-007)
- Alternativa: Power Automate Workflows (mais complexo de gerenciar)

**Consequencias**: Precisa de ConversationReference salvo na primeira interacao do usuario com o bot.

### ADR-005: Graph Change Notifications + Delta Query (nao polling)

**Contexto**: Para funcionalidades futuras (monitorar caixa de entrada, sync calendario), precisamos de notificacoes em tempo real do Graph.

**Decisao**: Usar Graph Change Notifications (webhooks) + Delta Query para sincronizacao.

**Justificativa**:
- Polling e ineficiente e consome cota de Graph (10K req/10min)
- Webhooks notificam em near-real-time (< 30s)
- Delta Query permite sync incremental eficiente
- Padrao recomendado pela Microsoft e pela comunidade (Voitanos)

**Consequencias**: Precisa de endpoint HTTPS publico para receber webhooks. Subscriptions expiram (mail: ~3 dias) e precisam ser renovadas. Limite global: Maximo de 1.000 subscriptions ativas por mailbox (todas as apps combinadas).

### ADR-006: Monorepo — Outlook Add-in como App Separado

**Contexto**: O Outlook add-in pode ser um diretorio dentro de `apps/office-addin/` ou um app separado.

**Decisao**: Criar `apps/outlook-addin/` como app separado no monorepo.

**Justificativa**:
- Manifesto diferente (Mailbox vs Document)
- Componentes de UI diferentes (email summary vs document analysis)
- Build independente (deploy pode ser em momentos diferentes)
- Compartilha codigo via `packages/shared/` e imports diretos

**Consequencias**: Alguma duplicacao de boilerplate (vite.config, tailwind.config), compensada pela independencia de deploy.

### ADR-007: ConversationReference em Redis (nao PostgreSQL)

**Contexto**: Para notificacoes proativas, o bot precisa armazenar ConversationReference de cada usuario.

**Decisao**: Armazenar ConversationReference em Redis com TTL.

**Justificativa**:
- Acesso muito frequente (cada notificacao precisa ler)
- Estrutura simples (key: user_id, value: JSON)
- TTL natural (se usuario nao interage por 30 dias, remove)
- Redis ja e usado para cache e Celery broker

**Consequencias**: Perda de dados se Redis reiniciar sem persistencia. Mitigacao: RDB snapshots + re-captura na proxima interacao.

---

## 5. Autenticacao e Autorizacao

### 5.1. Outlook Add-in — NAA (Nested App Authentication)

```
┌──────────────────────────────────────────────────────────┐
│                    Outlook Host                           │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │                    Task Pane                         │ │
│  │                                                     │ │
│  │  1. Check NAA support                               │ │
│  │     Office.context.requirements.isSetSupported(      │ │
│  │       'NestedAppAuth', '1.1')                       │ │
│  │                                                     │ │
│  │  2a. NAA (preferred):                               │ │
│  │      createNestablePublicClientApplication()        │ │
│  │      → acquireTokenSilent({                         │ │
│  │          scopes: ['User.Read', 'Mail.Read'],        │ │
│  │          account: msalInstance.getActiveAccount()    │ │
│  │        })                                           │ │
│  │                                                     │ │
│  │  2b. SSO Fallback:                                  │ │
│  │      OfficeRuntime.auth.getAccessToken()            │ │
│  │      → Exchange for app token (OBO flow)            │ │
│  │                                                     │ │
│  │  2c. Popup Fallback:                                │ │
│  │      msalInstance.loginPopup()                      │ │
│  │                                                     │ │
│  │  3. Send token to Iudex API                         │ │
│  │     POST /auth/microsoft-sso                        │ │
│  │     { microsoft_token, source: 'outlook-addin' }    │ │
│  │                                                     │ │
│  │  4. Receive Iudex JWT                               │ │
│  │     { access_token, refresh_token, user }           │ │
│  │                                                     │ │
│  │  5. Use Iudex JWT for all API calls                 │ │
│  │     (same pattern as Word add-in client.ts)         │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

#### Codigo de Referencia — NAA Setup

```typescript
// apps/outlook-addin/src/auth/msal-config.ts

import {
  createNestablePublicClientApplication,
  type IPublicClientApplication,
} from '@azure/msal-browser';

const MSAL_CONFIG = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID}`,
    supportsNestedAppAuth: true,
    redirectUri: import.meta.env.DEV
      ? 'brk-multihub://localhost'
      : `brk-multihub://${import.meta.env.VITE_ADDIN_DOMAIN}`,
  },
  cache: {
    cacheLocation: 'localStorage', // Alinhado com docs oficiais Microsoft para NAA
    storeAuthStateInCookie: false,
  },
};

const SCOPES = ['User.Read', 'Mail.Read', 'Calendars.ReadWrite'];

let msalInstance: IPublicClientApplication | null = null;

export async function initializeMsal(): Promise<IPublicClientApplication> {
  if (msalInstance) return msalInstance;

  // Check NAA support
  const naaSupported = Office.context.requirements?.isSetSupported(
    'NestedAppAuth', '1.1'
  );

  if (naaSupported) {
    // NAA path (preferred)
    msalInstance = await createNestablePublicClientApplication(MSAL_CONFIG);
  } else {
    // Fallback: standard MSAL (will need popup)
    const { PublicClientApplication } = await import('@azure/msal-browser');
    msalInstance = await PublicClientApplication.createPublicClientApplication({
      ...MSAL_CONFIG,
      auth: {
        ...MSAL_CONFIG.auth,
        redirectUri: window.location.origin,
      },
    });
  }

  return msalInstance;
}

export async function acquireToken(): Promise<string> {
  const msal = await initializeMsal();

  try {
    // Try silent first
    const accounts = msal.getAllAccounts();
    if (accounts.length > 0) {
      const result = await msal.acquireTokenSilent({
        scopes: SCOPES,
        account: accounts[0],
      });
      return result.accessToken;
    }

    // No cached account — try SSO
    const ssoResult = await msal.ssoSilent({ scopes: SCOPES });
    return ssoResult.accessToken;
  } catch {
    // Fallback to popup
    const popupResult = await msal.acquireTokenPopup({ scopes: SCOPES });
    return popupResult.accessToken;
  }
}
```

> **ALERTA CRITICO (Marco 2026)**: O grant "Approved Client App" do Conditional
> Access sera descontinuado em marco 2026. MSAL NAA nao suporta esta politica.
> Tenants que usam esta politica devem migrar para Application Protection Policy
> antes dessa data, caso contrario o NAA retornara erros.
> Ref: https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-conditional-access-grant

#### Metodos MSAL.js Suportados no NAA

| Metodo | Suportado | Nota |
|--------|-----------|------|
| `acquireTokenSilent` | Sim | Metodo principal |
| `acquireTokenPopup` | Sim | Fallback |
| `ssoSilent` | Sim | SSO silencioso |
| `loginPopup` | Sim | Login interativo |
| `loginRedirect` | **Nao** | Lanca excecao no NAA |
| `acquireTokenRedirect` | **Nao** | Lanca excecao no NAA |
| `logout*` | **Nao** | Lanca excecao no NAA |

#### Azure AD App Registration — Configuracao Necessaria

| Campo | Valor |
|-------|-------|
| **Application (client) ID** | UUID gerado pelo Azure |
| **Supported account types** | Accounts in any organizational directory (Multitenant) |
| **SPA Redirect URIs** | `brk-multihub://localhost` (NAA), `https://{domain}/auth/callback` |
| **API Permissions** | `User.Read`, `Mail.Read`, `Mail.ReadBasic`, `Calendars.ReadWrite`, `offline_access` |
| **Expose an API** | `api://{clientId}` com scope `access_as_user` |
| **Authorized client applications** | Office host IDs (ea5a67f6-..., 57fb890c-..., etc.) |

### 5.2. Teams App — SSO + OBO

```
User abre Tab/Bot ──► TeamsJS: authentication.getAuthToken()
                            │
                            ▼
                      Azure AD retorna token
                      (audience: app client ID)
                            │
                            ▼
                      POST /auth/teams-sso
                      { teams_token }
                            │
                            ▼
                      Backend: OBO flow
                      MSAL Python: acquire_token_on_behalf_of()
                      (exchange Teams token for Graph token)
                            │
                            ▼
                      Cria/atualiza usuario no Iudex DB
                      Retorna Iudex JWT
                            │
                            ▼
                      Client usa Iudex JWT para chamadas API
```

#### Codigo de Referencia — Teams SSO

```typescript
// apps/teams-app/src/auth/teams-auth.ts

import { app, authentication } from '@microsoft/teams-js';

export async function getTeamsToken(): Promise<string> {
  await app.initialize();

  const token = await authentication.getAuthToken({
    resources: [import.meta.env.VITE_AZURE_CLIENT_ID],
    silent: true,
  });

  return token;
}

export async function loginWithTeamsSSO(): Promise<AuthResponse> {
  const teamsToken = await getTeamsToken();

  const response = await fetch(`${API_URL}/auth/teams-sso`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ teams_token: teamsToken }),
  });

  return response.json();
}
```

### 5.3. Backend — Novos Endpoints de Auth

```python
# apps/api/app/api/endpoints/auth.py (adicoes)

@router.post("/microsoft-sso")
async def microsoft_sso_login(
    request: MicrosoftSSORequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """
    Autentica usuario via Microsoft token (NAA ou SSO).
    Valida o token com Azure AD, cria/atualiza usuario.
    Retorna JWT do Iudex.
    """
    # 1. Validate Microsoft token
    claims = await validate_microsoft_token(request.microsoft_token)

    # 2. Find or create user
    user = await find_or_create_microsoft_user(
        db=db,
        email=claims['preferred_username'],
        name=claims.get('name', ''),
        oid=claims['oid'],
        tid=claims['tid'],
    )

    # 3. Generate Iudex JWT
    return create_auth_response(user)


@router.post("/teams-sso")
async def teams_sso_login(
    request: TeamsSSoRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """
    Autentica usuario via Teams SSO token.
    Usa OBO flow para obter Graph token se necessario.
    """
    # 1. Validate Teams token
    claims = await validate_microsoft_token(request.teams_token)

    # 2. OBO flow for Graph access
    graph_token = await acquire_obo_token(
        assertion=request.teams_token,
        scopes=['User.Read', 'Mail.Read'],
    )

    # 3. Find or create user
    user = await find_or_create_microsoft_user(
        db=db,
        email=claims['preferred_username'],
        name=claims.get('name', ''),
        oid=claims['oid'],
        tid=claims['tid'],
    )

    # 4. Cache Graph token in Redis
    await cache_graph_token(user.id, graph_token)

    # 5. Generate Iudex JWT
    return create_auth_response(user)
```

---

## 6. Microsoft Graph API

### 6.1. Permissoes Necessarias

| Permissao | Tipo | Uso | Fase |
|-----------|------|-----|------|
| `User.Read` | Delegated | Perfil do usuario | 1 |
| `Mail.Read` | Delegated | Ler e-mails (sumarizacao) | 1 |
| `Mail.ReadBasic` | Delegated | Metadados de e-mail (listagem rapida) | 1 |
| `Calendars.ReadWrite` | Delegated | Criar eventos de prazos | 3 |
| `ChannelMessage.Read.All` | Application | Bot ler mensagens de canal | 2 |
| `ChatMessage.Read.Chat` | RSC | Bot ler mensagens no chat | 2 |
| `User.Read.All` | Application | Lookup de usuarios para notificacoes | 1 |

### 6.2. Throttling — Limites e Estrategias

#### Tabela de Limites

| Escopo | Limite | Janela | Resposta |
|--------|--------|--------|----------|
| Global (tenant) | 130.000 requests | 10 segundos | 429 + Retry-After |
| Por app + tenant | 10.000 requests | 10 minutos | 429 + Retry-After |
| Por mailbox | 10.000 requests | 10 minutos | 429 + Retry-After |
| Batch | 20 requests/batch | N/A | 4 batches concorrentes |

> **Mudanca Set/2025**: A partir de 30/09/2025, o limite per-app/per-user
> per-tenant foi reduzido para **metade** do limite total per-tenant.

#### Throttling States (Graph)

O Graph API opera com 3 estados de throttling:

```
Normal ──► Slow ──► Drop
  │          │        │
  │          │        └─ 429 retornado, requests descartados
  │          └─ Requests enfileirados, latencia aumenta
  └─ Normal processing
```

**Estrategias de mitigacao**:

```python
# apps/api/app/services/graph_client.py

import httpx
from tenacity import retry, wait_exponential, retry_if_exception_type

class GraphClient:
    """Cliente Graph com retry automatico e rate limiting."""

    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
    )
    async def get(self, path: str, params: dict = None) -> dict:
        response = await self.client.get(
            f"{self.base_url}{path}", params=params
        )
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            await asyncio.sleep(retry_after)
            raise httpx.HTTPStatusError(
                "Throttled", request=response.request, response=response
            )
        response.raise_for_status()
        return response.json()

    async def get_paginated(self, path: str, max_pages: int = 10) -> list:
        """Busca paginada com @odata.nextLink."""
        results = []
        url = f"{self.base_url}{path}"
        for _ in range(max_pages):
            data = await self.get(url)
            results.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            url = next_link
        return results
```

### 6.3. Webhooks (Change Notifications)

#### Padrao: Webhook + Delta Query

```
                    Registro
App ──────────────────────────────────► Graph
POST /subscriptions                     │
{                                       │
  changeType: "created,updated",        │
  notificationUrl: "https://...",       │
  resource: "me/messages",              │
  expirationDateTime: "+3 days",        │
  clientState: "secret-value"           │
}                                       │
                                        │
         Notificacao (lightweight)       │
App ◄───────────────────────────────── Graph
POST /webhook/graph-notification
{
  value: [{
    subscriptionId: "...",
    changeType: "created",
    resourceData: {
      id: "message-id"       ◄── Apenas ID, nao conteudo completo
    }
  }]
}
         │
         ▼
    Delta Query para obter detalhes
    GET /me/messages/delta?$deltatoken=...
         │
         ▼
    Processar mudanca (sumarizacao, classificacao)
```

#### Tabela de Expiracao de Subscriptions

| Recurso | Expiracao Maxima | Renovacao |
|---------|-----------------|-----------|
| `messages` (Mail) | 4230 min (~2.94 dias) | Renovar a cada 2 dias |
| `events` (Calendar) | 4230 min (~2.94 dias) | Renovar a cada 2 dias |
| `contacts` | 4230 min (~2.94 dias) | Renovar a cada 2 dias |
| `chatMessage` (Teams) | 60 min | Renovar a cada 50 min |
| `driveItem` (OneDrive) | 42300 min (~29 dias) | Renovar a cada 25 dias |

#### Endpoint de Webhook

```python
# apps/api/app/api/endpoints/graph_webhooks.py

@router.post("/graph-notification")
async def handle_graph_notification(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe change notifications do Microsoft Graph.
    Valida clientState, processa notificacoes.
    """
    # Validation token (subscription setup)
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return PlainTextResponse(validation_token)

    body = await request.json()

    for notification in body.get("value", []):
        # Validate clientState (HMAC)
        if not validate_client_state(notification.get("clientState")):
            continue

        # Dispatch to appropriate handler
        resource = notification.get("resource", "")
        if "messages" in resource:
            await handle_mail_notification(notification, db)
        elif "events" in resource:
            await handle_calendar_notification(notification, db)

    return {"status": "ok"}
```

> **Nota**: Se `expirationDateTime` for mais de 1 hora no futuro, `lifecycleNotificationUrl` e **obrigatorio**.
> Adicionar endpoint `/api/graph/webhook/lifecycle` para receber notificacoes de `subscriptionRemoved`,
> `reauthorizationRequired` e `missed`.

### 6.4. Event Grid vs Event Hubs — Quando Usar

| Criterio | Graph Webhooks | Event Grid | Event Hubs |
|----------|---------------|-----------|-----------|
| **Volume** | < 1000 notif/min | < 10M eventos/seg | Milhoes/seg |
| **Latencia** | < 30s | < 1s | < 1s |
| **Uso ideal** | Notificacoes por usuario | Eventos por tenant | Streaming de alto volume |
| **Para Iudex** | **Fase 1-2** | Fase 3+ | Fase 4+ |
| **Complexidade** | Baixa | Media | Alta |
| **Custo** | Gratis (Graph API) | ~$0.60/M operacoes | ~$11/TU/mes |

**Recomendacao**: Usar Graph Webhooks diretos nas Fases 1-3. Migrar para Event Grid apenas se volume de notificacoes ultrapassar 10.000/minuto por tenant.

---

## 7. Outlook Add-in — Componentes

### 7.1. Estrutura de Diretorio

```
apps/outlook-addin/
├── manifest.xml                 # Host: Mailbox, VersionOverrides 1.1
├── package.json                 # Mesmas deps do Word add-in + MSAL
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── index.html
├── public/
│   └── assets/                  # Icons 16, 32, 80, 128
└── src/
    ├── main.tsx                 # Entry point com Office.onReady
    ├── App.tsx                  # Router principal
    ├── auth/
    │   ├── msal-config.ts       # NAA + fallback MSAL setup
    │   └── auth-provider.tsx    # React context para auth state
    ├── api/
    │   ├── client.ts            # Reutiliza padrao do Word add-in
    │   ├── sse-client.ts        # Reutiliza do Word add-in
    │   └── outlook-api.ts       # Endpoints especificos do Outlook
    ├── office/
    │   ├── mail-bridge.ts       # Bridge para Office.js Mailbox APIs
    │   └── compose-bridge.ts    # Bridge para Compose mode (Fase 3)
    ├── stores/
    │   ├── auth-store.ts        # Zustand (adaptado para MSAL)
    │   ├── email-store.ts       # Estado do e-mail atual
    │   └── summary-store.ts     # Resultado da sumarizacao
    ├── components/
    │   ├── layout/
    │   │   ├── TaskPane.tsx     # Container principal
    │   │   ├── Header.tsx
    │   │   └── TabNavigation.tsx
    │   ├── auth/
    │   │   ├── LoginForm.tsx    # Login com Microsoft
    │   │   └── AuthGuard.tsx
    │   ├── summary/
    │   │   ├── SummaryPanel.tsx # Painel principal de sumarizacao
    │   │   ├── SummaryCard.tsx  # Card de resultado
    │   │   ├── DeadlineList.tsx # Lista de prazos extraidos
    │   │   └── ActionBar.tsx   # Acoes sugeridas
    │   ├── search/
    │   │   ├── CorpusSearch.tsx # Busca no corpus
    │   │   └── ResultCard.tsx
    │   └── workflow/
    │       ├── WorkflowTrigger.tsx # Iniciar workflow
    │       └── WorkflowStatus.tsx  # Status de runs
    └── styles/
        └── globals.css
```

### 7.2. Manifesto XML — Outlook

> **Nota**: ADR-001 decidiu usar JSON Unificado para Outlook. O XML abaixo e
> mantido como referencia/fallback para cenarios onde JSON ainda nao e suportado.
> Para implementacao principal, usar o formato JSON Unificado conforme ADR-001.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp
  xmlns="http://schemas.microsoft.com/office/appforoffice/1.1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:bt="http://schemas.microsoft.com/office/officeappbasictypes/1.0"
  xmlns:mailappor="http://schemas.microsoft.com/office/mailappversionoverrides/1.0"
  xsi:type="MailApp">

  <Id>b2c3d4e5-f6a7-8901-bcde-f12345678901</Id>
  <Version>1.0.0.0</Version>
  <ProviderName>Vorbium</ProviderName>
  <DefaultLocale>pt-BR</DefaultLocale>
  <DisplayName DefaultValue="Vorbium - IA Juridica" />
  <Description DefaultValue="Assistente juridico com IA para analise de e-mails, extracao de prazos e pesquisa no corpus." />
  <IconUrl DefaultValue="https://addin.vorbium.com.br/assets/icon-32.png" />
  <HighResolutionIconUrl DefaultValue="https://addin.vorbium.com.br/assets/icon-128.png" />
  <SupportUrl DefaultValue="https://vorbium.com.br/suporte" />

  <AppDomains>
    <AppDomain>https://addin.vorbium.com.br</AppDomain>
    <AppDomain>https://login.microsoftonline.com</AppDomain>
  </AppDomains>

  <Hosts>
    <Host Name="Mailbox" />
  </Hosts>

  <Requirements>
    <Sets>
      <Set Name="Mailbox" MinVersion="1.5" />
    </Sets>
  </Requirements>

  <FormSettings>
    <Form xsi:type="ItemRead">
      <DesktopSettings>
        <SourceLocation DefaultValue="https://addin.vorbium.com.br/index.html" />
        <RequestedHeight>450</RequestedHeight>
      </DesktopSettings>
    </Form>
  </FormSettings>

  <Permissions>ReadItem</Permissions>

  <Rule xsi:type="RuleCollection" Mode="Or">
    <Rule xsi:type="ItemIs" ItemType="Message" />
  </Rule>

  <VersionOverrides
    xmlns="http://schemas.microsoft.com/office/mailappversionoverrides"
    xsi:type="VersionOverridesV1_0">

    <Requirements>
      <bt:Sets DefaultMinVersion="1.5">
        <bt:Set Name="Mailbox" />
      </bt:Sets>
    </Requirements>

    <Hosts>
      <Host xsi:type="MailHost">
        <DesktopFormFactor>
          <ExtensionPoint xsi:type="MessageReadCommandSurface">
            <OfficeTab id="TabDefault">
              <Group id="VorbiumOutlookGroup">
                <Label resid="GroupLabel" />
                <Control xsi:type="Button" id="AnalyzeButton">
                  <Label resid="AnalyzeButton.Label" />
                  <Supertip>
                    <Title resid="AnalyzeButton.Label" />
                    <Description resid="AnalyzeButton.Tooltip" />
                  </Supertip>
                  <Icon>
                    <bt:Image size="16" resid="Icon.16x16" />
                    <bt:Image size="32" resid="Icon.32x32" />
                    <bt:Image size="80" resid="Icon.80x80" />
                  </Icon>
                  <Action xsi:type="ShowTaskpane">
                    <SourceLocation resid="Taskpane.Url" />
                  </Action>
                </Control>
              </Group>
            </OfficeTab>
          </ExtensionPoint>
        </DesktopFormFactor>

        <MobileFormFactor>
          <ExtensionPoint xsi:type="MobileMessageReadCommandSurface">
            <Group id="VorbiumMobileGroup">
              <Label resid="GroupLabel" />
              <Control xsi:type="MobileButton" id="MobileAnalyzeButton">
                <Label resid="AnalyzeButton.Label" />
                <Icon>
                  <bt:Image size="25" resid="Icon.32x32" />
                  <bt:Image size="32" resid="Icon.32x32" />
                  <bt:Image size="48" resid="Icon.80x80" />
                </Icon>
                <Action xsi:type="ShowTaskpane">
                  <SourceLocation resid="Taskpane.Url" />
                </Action>
              </Control>
            </Group>
          </ExtensionPoint>
        </MobileFormFactor>
      </Host>
    </Hosts>

    <Resources>
      <bt:Images>
        <bt:Image id="Icon.16x16" DefaultValue="https://addin.vorbium.com.br/assets/icon-16.png" />
        <bt:Image id="Icon.32x32" DefaultValue="https://addin.vorbium.com.br/assets/icon-32.png" />
        <bt:Image id="Icon.80x80" DefaultValue="https://addin.vorbium.com.br/assets/icon-80.png" />
      </bt:Images>
      <bt:Urls>
        <bt:Url id="Taskpane.Url" DefaultValue="https://addin.vorbium.com.br/index.html" />
      </bt:Urls>
      <bt:ShortStrings>
        <bt:String id="GroupLabel" DefaultValue="Vorbium" />
        <bt:String id="AnalyzeButton.Label" DefaultValue="Analisar E-mail" />
      </bt:ShortStrings>
      <bt:LongStrings>
        <bt:String id="AnalyzeButton.Tooltip" DefaultValue="Analisar e-mail com IA: sumarizar, classificar e extrair prazos." />
      </bt:LongStrings>
    </Resources>
  </VersionOverrides>
</OfficeApp>
```

### 7.3. Mail Bridge — Office.js APIs

```typescript
// apps/outlook-addin/src/office/mail-bridge.ts

export interface EmailData {
  subject: string;
  from: string;
  to: string[];
  cc: string[];
  dateReceived: string;
  body: string;
  bodyType: 'html' | 'text';
  attachments: AttachmentInfo[];
  conversationId: string;
  internetMessageId: string;
}

export interface AttachmentInfo {
  id: string;
  name: string;
  contentType: string;
  size: number;
  isInline: boolean;
}

/**
 * Extrai dados completos do e-mail atual via Office.js.
 * Usa Mailbox requirement set 1.5+.
 */
export async function getCurrentEmailData(): Promise<EmailData> {
  const item = Office.context.mailbox.item;
  if (!item) throw new Error('Nenhum e-mail selecionado');

  // Get body (HTML preferred)
  const body = await new Promise<string>((resolve, reject) => {
    item.body.getAsync(
      Office.CoercionType.Html,
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve(result.value);
        } else {
          // Fallback to text
          item.body.getAsync(
            Office.CoercionType.Text,
            (textResult) => {
              if (textResult.status === Office.AsyncResultStatus.Succeeded) {
                resolve(textResult.value);
              } else {
                reject(new Error('Falha ao extrair corpo do e-mail'));
              }
            }
          );
        }
      }
    );
  });

  // Get attachments info
  const attachments: AttachmentInfo[] = (item.attachments || []).map((att) => ({
    id: att.id,
    name: att.name,
    contentType: att.contentType,
    size: att.size,
    isInline: att.isInline,
  }));

  return {
    subject: item.subject || '',
    from: item.from?.emailAddress || '',
    to: (item.to || []).map((r) => r.emailAddress),
    cc: (item.cc || []).map((r) => r.emailAddress),
    dateReceived: item.dateTimeCreated?.toISOString() || '',
    body,
    bodyType: 'html',
    attachments,
    conversationId: item.conversationId || '',
    internetMessageId: item.internetMessageId || '',
  };
}
```

> **Nota**: O item ID retornado por Office.js (formato EWS) precisa ser
> convertido para uso com Graph API via `Office.context.mailbox.convertToRestId(itemId, Office.MailboxEnums.RestVersion.v2_0)`.

```typescript
/**
 * Busca conteudo de um anexo especifico.
 * Requer Mailbox 1.8+ para getAttachmentContentAsync.
 */
export async function getAttachmentContent(
  attachmentId: string
): Promise<{ content: string; format: string }> {
  const item = Office.context.mailbox.item;
  if (!item) throw new Error('Nenhum e-mail selecionado');

  return new Promise((resolve, reject) => {
    item.getAttachmentContentAsync(attachmentId, (result) => {
      if (result.status === Office.AsyncResultStatus.Succeeded) {
        resolve({
          content: result.value.content,
          format: result.value.format, // 'base64' | 'url' | 'file'
        });
      } else {
        reject(new Error(`Falha ao obter anexo: ${result.error?.message}`));
      }
    });
  });
}
```

### 7.4. Componente Principal — SummaryPanel

```tsx
// apps/outlook-addin/src/components/summary/SummaryPanel.tsx

import { useEffect, useState } from 'react';
import {
  Card, CardHeader, Badge, Spinner, Text, Divider,
} from '@fluentui/react-components';
import { getCurrentEmailData, type EmailData } from '@/office/mail-bridge';
import { useSSEStream } from '@/hooks/useSSEStream';

interface SummaryResult {
  tipo_juridico: string;
  confianca: number;
  resumo: string;
  partes: string[];
  prazos: Array<{
    data: string;
    descricao: string;
    urgencia: 'alta' | 'media' | 'baixa';
  }>;
  acoes_sugeridas: string[];
  workflows_recomendados: Array<{
    id: string;
    name: string;
    relevance: number;
  }>;
}

export function SummaryPanel() {
  const [emailData, setEmailData] = useState<EmailData | null>(null);
  const [summary, setSummary] = useState<SummaryResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAndSummarize();

    // Listen for item change (pinned pane)
    Office.context.mailbox.addHandlerAsync(
      Office.EventType.ItemChanged,
      () => loadAndSummarize()
    );
  }, []);

  async function loadAndSummarize() {
    setIsLoading(true);
    setError(null);
    setSummary(null);

    try {
      const data = await getCurrentEmailData();
      setEmailData(data);

      // Stream summarization
      await streamSummarize(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido');
    } finally {
      setIsLoading(false);
    }
  }

  async function streamSummarize(data: EmailData) {
    // Uses SSE pattern from sse-client.ts
    const response = await fetch(`${API_URL}/outlook-addin/summarize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAccessToken()}`,
      },
      body: JSON.stringify({
        subject: data.subject,
        from: data.from,
        to: data.to,
        body: data.body,
        body_type: data.bodyType,
        attachments: data.attachments.map(a => a.name),
      }),
    });

    // Parse SSE stream (same pattern as Word add-in)
    // ... (omitted for brevity — see sse-client.ts)
  }

  if (isLoading) return <Spinner label="Analisando e-mail..." />;
  if (error) return <Text style={{ color: 'red' }}>{error}</Text>;
  if (!summary) return null;

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* Classification badge */}
      <div className="flex items-center gap-2">
        <Badge appearance="filled" color="brand">
          {summary.tipo_juridico}
        </Badge>
        <Text size={200}>
          Confianca: {Math.round(summary.confianca * 100)}%
        </Text>
      </div>

      {/* Summary */}
      <Card>
        <CardHeader header={<Text weight="semibold">Resumo</Text>} />
        <Text>{summary.resumo}</Text>
      </Card>

      {/* Deadlines */}
      {summary.prazos.length > 0 && (
        <DeadlineList deadlines={summary.prazos} />
      )}

      {/* Suggested actions */}
      <ActionBar
        actions={summary.acoes_sugeridas}
        workflows={summary.workflows_recomendados}
      />
    </div>
  );
}
```

---

## 8. Teams App — Componentes

### 8.1. Estrutura de Diretorio

```
apps/teams-app/
├── manifest.json               # Teams app manifest v1.19
├── color.png                   # App icon (192x192)
├── outline.png                 # App icon outline (32x32)
├── tab/                        # Tab SPA (React)
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── auth/
│   │   │   └── teams-auth.ts
│   │   ├── api/
│   │   │   ├── client.ts       # Reutiliza padrao
│   │   │   └── sse-client.ts
│   │   ├── stores/
│   │   ├── components/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── WorkflowList.tsx
│   │   │   └── CorpusSearch.tsx
│   │   └── styles/
│   └── index.html
└── bot/                        # Bot logic (Python — integrado ao API)
    └── (endpoints no FastAPI)
```

### 8.1b. Teams SDK v2 — MCP e A2A

O Teams SDK v2 inclui suporte nativo a **Model Context Protocol (MCP)** e **Agent-to-Agent (A2A)** communication, que se alinham com a arquitetura multi-agente do Iudex.

#### MCP Integration (Futuro)

O Iudex pode expor seus agentes como MCP Servers, permitindo que o bot Teams acesse ferramentas de IA via protocolo padrao:

```typescript
// Exemplo: bot Teams conectando ao Iudex como MCP Server
import { App } from '@microsoft/teams.apps';
import { McpClientPlugin } from '@anthropic/mcp-client';

const app = new App();

const prompt = new ChatPrompt({
  instructions: 'Voce e um assistente juridico. Use as ferramentas disponiveis.',
  model: new OpenAIChatModel({ model: 'gpt-5.2' }),
}, [new McpClientPlugin()])
  .usePlugin('mcpClient', { url: 'https://api.vorbium.com.br/mcp' });
```

**Beneficios para o Iudex**:
- Agentes especializados (sumarizacao, pesquisa, analise) acessiveis via MCP
- Workflows multi-agente complexos orquestrados pelo Teams SDK
- Reducao de complexidade de integracao
- Possibilidade de registrar MCP Servers como agent connectors no Teams (Developer Preview)

**Timeline**: Implementar MCP na Fase 3, quando Teams SDK Python estiver GA.

### 8.2. Manifesto JSON — Teams App

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/teams/v1.19/MicrosoftTeams.schema.json",
  "manifestVersion": "1.19",
  "version": "1.0.0",
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "developer": {
    "name": "Vorbium",
    "websiteUrl": "https://vorbium.com.br",
    "privacyUrl": "https://vorbium.com.br/privacidade",
    "termsOfUseUrl": "https://vorbium.com.br/termos"
  },
  "name": {
    "short": "Vorbium",
    "full": "Vorbium - Assistente Juridico com IA"
  },
  "description": {
    "short": "IA juridica para Teams: pesquisa, analise e workflows.",
    "full": "Assistente juridico com inteligencia artificial integrado ao Microsoft Teams. Pesquise jurisprudencia, analise documentos, inicie workflows e receba notificacoes — tudo sem sair do Teams."
  },
  "icons": {
    "color": "color.png",
    "outline": "outline.png"
  },
  "accentColor": "#4F46E5",
  "bots": [
    {
      "botId": "${BOT_APP_ID}",
      "scopes": ["personal", "team", "groupChat"],
      "supportsFiles": false,
      "isNotificationOnly": false,
      "commandLists": [
        {
          "scopes": ["personal", "team", "groupChat"],
          "commands": [
            {
              "title": "pesquisar",
              "description": "Pesquisar no corpus juridico"
            },
            {
              "title": "analisar",
              "description": "Analisar texto com IA juridica"
            },
            {
              "title": "workflow",
              "description": "Iniciar um workflow juridico"
            },
            {
              "title": "status",
              "description": "Ver status de um workflow"
            },
            {
              "title": "ajuda",
              "description": "Ver comandos disponiveis"
            }
          ]
        }
      ]
    }
  ],
  "staticTabs": [
    {
      "entityId": "dashboard",
      "name": "Dashboard",
      "contentUrl": "https://teams.vorbium.com.br/?tab=dashboard",
      "scopes": ["personal"]
    }
  ],
  "configurableTabs": [
    {
      "configurationUrl": "https://teams.vorbium.com.br/config",
      "canUpdateConfiguration": true,
      "scopes": ["team", "groupChat"],
      "context": ["channelTab", "privateChatTab"]
    }
  ],
  "permissions": ["identity", "messageTeamMembers"],
  "validDomains": [
    "teams.vorbium.com.br",
    "api.vorbium.com.br"
  ],
  "webApplicationInfo": {
    "id": "${AZURE_CLIENT_ID}",
    "resource": "api://${AZURE_CLIENT_ID}"
  },
  "authorization": {
    "permissions": {
      "resourceSpecific": [
        {
          "name": "ChatMessage.Read.Chat",
          "type": "Application"
        },
        {
          "name": "TeamSettings.Read.Group",
          "type": "Application"
        },
        {
          "name": "ChannelMessage.Read.Group",
          "type": "Application"
        }
      ]
    }
  }
}
```

### 8.3. Bot Endpoint — FastAPI

> **Nota sobre Bot Framework**: O Bot Framework SDK foi descontinuado em dez/2025.
> O codigo abaixo usa `botbuilder` como adapter (ainda funcional para receber Activities),
> mas deve ser migrado para Teams SDK v2 quando a versao Python atingir GA.
> Alternativa: adapter manual que processa Activity JSON diretamente via FastAPI.

```python
# apps/api/app/api/endpoints/teams_bot.py

"""
Teams Bot endpoint — recebe atividades do Azure Bot Service,
processa comandos e envia respostas (incluindo Adaptive Cards).
Nota: botbuilder usado como adapter; migrar para Teams SDK v2 quando Python GA.
"""

import json
import logging
from typing import Optional

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes
from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.services.teams_bot.bot import IudexBot
from app.services.teams_bot.conversation_store import save_conversation_reference

logger = logging.getLogger(__name__)

router = APIRouter()

# Bot Framework adapter
adapter_settings = BotFrameworkAdapterSettings(
    app_id=settings.TEAMS_BOT_APP_ID,
    app_password=settings.TEAMS_BOT_APP_PASSWORD,
)
adapter = BotFrameworkAdapter(adapter_settings)

# Bot instance
bot = IudexBot()


@router.post("/webhook")
async def teams_webhook(request: Request) -> Response:
    """
    Recebe atividades do Bot Framework (Teams).
    Endpoint registrado no Azure Bot Service.
    """
    body = await request.json()
    activity = Activity().deserialize(body)

    auth_header = request.headers.get("Authorization", "")

    async def call_bot(turn_context: TurnContext):
        # Save conversation reference for proactive messaging
        await save_conversation_reference(turn_context)
        # Process activity
        await bot.on_turn(turn_context)

    try:
        await adapter.process_activity(activity, auth_header, call_bot)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Bot webhook error: {e}")
        return Response(status_code=500)


@router.post("/notify/{user_id}")
async def send_proactive_notification(
    user_id: str,
    notification: dict,
):
    """
    Envia notificacao proativa para um usuario via Teams.
    Chamado internamente pelo Celery worker.
    """
    from app.services.teams_bot.conversation_store import get_conversation_reference
    from app.services.teams_bot.cards import build_notification_card

    ref = await get_conversation_reference(user_id)
    if not ref:
        return {"status": "no_conversation_reference"}

    card = build_notification_card(notification)

    async def send_card(turn_context: TurnContext):
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                attachments=[card],
            )
        )

    await adapter.continue_conversation(
        ref,
        send_card,
        settings.TEAMS_BOT_APP_ID,
    )

    return {"status": "sent"}
```

### 8.4. Bot Logic — Processador de Comandos

```python
# apps/api/app/services/teams_bot/bot.py

"""
IudexBot — Logica principal do bot Teams.
Classifica intencao e despacha para handler apropriado.
"""

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import (
    Activity,
    ActivityTypes,
    Attachment,
    CardAction,
    ActionTypes,
)

from app.services.teams_bot.handlers import (
    handle_search_command,
    handle_analyze_command,
    handle_workflow_command,
    handle_status_command,
    handle_help_command,
    handle_free_chat,
    handle_card_action,
)


class IudexBot(ActivityHandler):
    """Bot Teams do Iudex/Vorbium."""

    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip()

        # Handle Adaptive Card action submissions
        if turn_context.activity.value:
            await handle_card_action(turn_context)
            return

        # Route commands
        if text.startswith("/pesquisar") or text.startswith("pesquisar"):
            query = text.replace("/pesquisar", "").replace("pesquisar", "").strip()
            await handle_search_command(turn_context, query)

        elif text.startswith("/analisar") or text.startswith("analisar"):
            content = text.replace("/analisar", "").replace("analisar", "").strip()
            await handle_analyze_command(turn_context, content)

        elif text.startswith("/workflow") or text.startswith("workflow"):
            name = text.replace("/workflow", "").replace("workflow", "").strip()
            await handle_workflow_command(turn_context, name)

        elif text.startswith("/status") or text.startswith("status"):
            run_id = text.replace("/status", "").replace("status", "").strip()
            await handle_status_command(turn_context, run_id)

        elif text.startswith("/ajuda") or text.startswith("ajuda"):
            await handle_help_command(turn_context)

        else:
            # Free-form chat with LLM
            await handle_free_chat(turn_context, text)

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "Ola! Sou o Vorbium, seu assistente juridico com IA. "
                    "Digite /ajuda para ver os comandos disponiveis."
                )
```

### 8.5. Adaptive Cards — Exemplos

#### Card de Resultado de Pesquisa

```python
# apps/api/app/services/teams_bot/cards.py

def build_search_results_card(query: str, results: list) -> dict:
    """Constroi Adaptive Card com resultados de pesquisa no corpus."""
    items = []
    for i, r in enumerate(results[:5]):
        items.append({
            "type": "Container",
            "items": [
                {
                    "type": "ColumnSet",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "auto",
                            "items": [{
                                "type": "TextBlock",
                                "text": f"#{i+1}",
                                "weight": "Bolder",
                                "color": "Accent",
                            }],
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": r["title"],
                                    "weight": "Bolder",
                                    "wrap": True,
                                },
                                {
                                    "type": "TextBlock",
                                    "text": r["content"][:200] + "...",
                                    "wrap": True,
                                    "size": "Small",
                                },
                                {
                                    "type": "TextBlock",
                                    "text": f"Score: {r['score']:.2f} | Fonte: {r.get('source', 'N/A')}",
                                    "size": "Small",
                                    "isSubtle": True,
                                },
                            ],
                        },
                    ],
                },
            ],
            "separator": True,
        })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Pesquisa: \"{query}\"",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": f"{len(results)} resultados encontrados",
                "size": "Small",
                "isSubtle": True,
            },
            *items,
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Ver todos no Vorbium",
                "url": f"https://app.vorbium.com.br/corpus?q={query}",
            },
        ],
    }
```

#### Card de Notificacao de Workflow (HIL)

```python
def build_hil_notification_card(
    workflow_name: str,
    run_id: str,
    node_name: str,
    summary: str,
) -> dict:
    """Card para Human-in-the-Loop: aprovar/rejeitar."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [{
                            "type": "Image",
                            "url": "https://addin.vorbium.com.br/assets/icon-32.png",
                            "size": "Small",
                        }],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "Aprovacao Necessaria",
                                "weight": "Bolder",
                                "color": "Warning",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Workflow: {workflow_name}",
                                "size": "Small",
                                "isSubtle": True,
                            },
                        ],
                    },
                ],
            },
            {
                "type": "TextBlock",
                "text": f"Etapa: {node_name}",
                "weight": "Bolder",
            },
            {
                "type": "TextBlock",
                "text": summary,
                "wrap": True,
            },
            {
                "type": "Input.Text",
                "id": "comment",
                "placeholder": "Comentario (opcional)",
                "isMultiline": True,
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Aprovar",
                "style": "positive",
                "data": {
                    "action": "hil_approve",
                    "run_id": run_id,
                    "node": node_name,
                },
            },
            {
                "type": "Action.Submit",
                "title": "Rejeitar",
                "style": "destructive",
                "data": {
                    "action": "hil_reject",
                    "run_id": run_id,
                    "node": node_name,
                },
            },
            {
                "type": "Action.OpenUrl",
                "title": "Ver Detalhes",
                "url": f"https://app.vorbium.com.br/workflows/runs/{run_id}",
            },
        ],
    }
```

> **Expiracao de Cards**: Adaptive Cards enviados via Power Automate expiram
> em **30 dias** — acoes nao podem mais ser acionadas apos esse periodo.
> Para cards de HIL (aprovacao de workflow), considerar reenvio automatico
> antes da expiracao.

### 8.6. Proactive Messaging — ConversationReference

```python
# apps/api/app/services/teams_bot/conversation_store.py

"""
Armazena ConversationReference para Proactive Messaging.
Usa Redis para acesso rapido com TTL.
"""

import json
from typing import Optional

from botbuilder.core import TurnContext
from botbuilder.schema import ConversationReference

from app.core.redis_client import redis_client

CONV_REF_PREFIX = "teams:conv_ref:"
CONV_REF_TTL = 60 * 60 * 24 * 30  # 30 days


async def save_conversation_reference(turn_context: TurnContext) -> None:
    """Salva ConversationReference do usuario atual."""
    activity = turn_context.activity
    ref = TurnContext.get_conversation_reference(activity)

    # Key by AAD object ID (from activity.from_property.aad_object_id)
    user_aad_id = activity.from_property.aad_object_id
    if not user_aad_id:
        return

    key = f"{CONV_REF_PREFIX}{user_aad_id}"
    value = json.dumps(ref.serialize())

    await redis_client.setex(key, CONV_REF_TTL, value)


async def get_conversation_reference(
    user_aad_id: str,
) -> Optional[ConversationReference]:
    """Recupera ConversationReference para envio proativo."""
    key = f"{CONV_REF_PREFIX}{user_aad_id}"
    data = await redis_client.get(key)

    if not data:
        return None

    ref_dict = json.loads(data)
    return ConversationReference().deserialize(ref_dict)
```

### 8.7. Integracao com Celery — Notificacoes Proativas

```python
# apps/api/app/workers/tasks/notification_tasks.py

"""
Celery tasks para notificacoes proativas via Teams bot.
"""

from celery import shared_task
from app.services.teams_bot.conversation_store import get_conversation_reference
from app.services.teams_bot.cards import build_hil_notification_card, build_completion_card

import httpx


@shared_task(name="notify_workflow_hil")
def notify_workflow_hil(
    user_aad_id: str,
    workflow_name: str,
    run_id: str,
    node_name: str,
    summary: str,
):
    """Notifica usuario que workflow precisa de aprovacao (HIL)."""
    import asyncio
    asyncio.run(_send_hil_notification(
        user_aad_id, workflow_name, run_id, node_name, summary
    ))


async def _send_hil_notification(
    user_aad_id: str,
    workflow_name: str,
    run_id: str,
    node_name: str,
    summary: str,
):
    """Envia notificacao HIL via endpoint interno do bot."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"http://localhost:8000/api/teams-bot/notify/{user_aad_id}",
            json={
                "type": "hil",
                "workflow_name": workflow_name,
                "run_id": run_id,
                "node_name": node_name,
                "summary": summary,
            },
        )


@shared_task(name="notify_workflow_completed")
def notify_workflow_completed(
    user_aad_id: str,
    workflow_name: str,
    run_id: str,
    summary: str,
):
    """Notifica usuario que workflow completou."""
    import asyncio
    asyncio.run(_send_completion_notification(
        user_aad_id, workflow_name, run_id, summary
    ))
```

---

## 9. Modelo de Dados

### 9.1. Novas Tabelas

```sql
-- Conversation references para proactive messaging (Teams)
-- Nota: armazenado em Redis, nao em PostgreSQL (ADR-007)
-- Mantido aqui para documentacao

-- Microsoft SSO user mapping
CREATE TABLE microsoft_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    microsoft_oid VARCHAR(36) NOT NULL,        -- Azure AD Object ID
    microsoft_tid VARCHAR(36) NOT NULL,        -- Azure AD Tenant ID
    microsoft_email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(microsoft_oid, microsoft_tid)
);

CREATE INDEX ix_microsoft_users_oid ON microsoft_users(microsoft_oid);
CREATE INDEX ix_microsoft_users_user_id ON microsoft_users(user_id);

-- Graph webhook subscriptions
CREATE TABLE graph_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id VARCHAR(255) NOT NULL UNIQUE,  -- Graph subscription ID
    resource VARCHAR(255) NOT NULL,                 -- e.g., "me/messages"
    change_types VARCHAR(100) NOT NULL,             -- e.g., "created,updated"
    expiration_datetime TIMESTAMPTZ NOT NULL,
    client_state VARCHAR(255) NOT NULL,             -- HMAC validation
    notification_url VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    renewed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_graph_subs_user ON graph_subscriptions(user_id);
CREATE INDEX ix_graph_subs_expiry ON graph_subscriptions(expiration_datetime);

-- Email analysis cache (evitar re-processar mesmo e-mail)
CREATE TABLE email_analysis_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    internet_message_id VARCHAR(500) NOT NULL,  -- Unique email identifier
    analysis_type VARCHAR(50) NOT NULL,          -- 'summary', 'classify', 'deadlines'
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE(user_id, internet_message_id, analysis_type)
);

CREATE INDEX ix_email_cache_lookup
    ON email_analysis_cache(user_id, internet_message_id, analysis_type);
CREATE INDEX ix_email_cache_expiry ON email_analysis_cache(expires_at);
```

### 9.2. SQLAlchemy Models

```python
# apps/api/app/models/microsoft_user.py

class MicrosoftUser(Base):
    __tablename__ = "microsoft_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    microsoft_oid: Mapped[str] = mapped_column(String(36), nullable=False)
    microsoft_tid: Mapped[str] = mapped_column(String(36), nullable=False)
    microsoft_email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("microsoft_oid", "microsoft_tid", name="uq_ms_oid_tid"),
    )

    user = relationship("User", backref="microsoft_accounts")
```

### 9.3. Diagrama ER (Novas Entidades)

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│    users     │     │ microsoft_users  │     │ graph_subscriptions │
│              │     │                  │     │                     │
│ id (PK)      │◄───│ user_id (FK)     │     │ id (PK)             │
│ email        │     │ microsoft_oid    │     │ user_id (FK)    ───►│
│ name         │     │ microsoft_tid    │     │ subscription_id     │
│ organization │     │ microsoft_email  │     │ resource            │
│ plan         │     │ display_name     │     │ expiration_datetime │
│ role         │     └──────────────────┘     │ client_state        │
│              │                               └─────────────────────┘
│              │     ┌──────────────────────┐
│              │     │ email_analysis_cache │
│              │◄───│ user_id (FK)         │
│              │     │ internet_message_id  │
│              │     │ analysis_type        │
└──────────────┘     │ result (JSONB)       │
                     │ expires_at           │
                     └──────────────────────┘
```

---

## 10. Endpoints da API

### 10.1. Novos Endpoints — Outlook Add-in

```
POST /api/outlook-addin/summarize          # Sumarizar e-mail (SSE)
POST /api/outlook-addin/classify           # Classificar tipo juridico
POST /api/outlook-addin/extract-deadlines  # Extrair prazos
POST /api/outlook-addin/analyze-attachment # Analisar anexo
POST /api/auth/microsoft-sso              # Login via Microsoft token
```

### 10.2. Novos Endpoints — Teams Bot

```
POST /api/teams-bot/webhook               # Bot Framework webhook
POST /api/teams-bot/notify/{user_id}      # Notificacao proativa (interno)
POST /api/auth/teams-sso                  # Login via Teams SSO
```

### 10.3. Novos Endpoints — Graph Webhooks

```
POST /api/graph/webhook/notification      # Receber change notifications
POST /api/graph/subscriptions             # Criar subscription
DELETE /api/graph/subscriptions/{id}      # Cancelar subscription
POST /api/graph/subscriptions/{id}/renew  # Renovar subscription
```

### 10.4. Endpoints Existentes Reutilizados

```
POST /api/corpus/search                   # Pesquisa semantica (RF-OL-07, RF-TM-04)
POST /api/chats/                          # Criar chat (RF-TM-01)
POST /api/chats/{id}/messages/stream      # Chat com SSE (RF-TM-01)
POST /api/workflows/{id}/run              # Iniciar workflow (RF-OL-08, RF-TM-03)
GET  /api/workflows/runs/{id}             # Status do workflow (RF-TM-05)
POST /api/workflows/{id}/runs/{runId}/hil # Aprovar/rejeitar HIL (UC-05)
POST /api/word-addin/anonymize            # Reutiliza para deteccao LGPD
POST /api/word-addin/playbook/recommend   # Reutiliza para sugestao de workflows
```

### 10.5. Exemplo — Endpoint de Sumarizacao

```python
# apps/api/app/api/endpoints/outlook_addin.py

@router.post("/summarize")
async def summarize_email(
    request: SummarizeEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Sumariza e-mail juridico via SSE.
    Retorna tipo juridico, resumo, partes, prazos, acoes.
    """
    # Check cache
    cached = await get_email_analysis_cache(
        db=db,
        user_id=str(current_user.id),
        message_id=request.internet_message_id,
        analysis_type="summary",
    )
    if cached:
        return JSONResponse(cached)

    # Stream via SSE
    async def generate():
        async for event in outlook_addin_service.summarize_email(
            subject=request.subject,
            from_address=request.from_address,
            to_addresses=request.to_addresses,
            body=request.body,
            body_type=request.body_type,
            user_id=str(current_user.id),
            db=db,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

---

## 11. Seguranca

### 11.1. Content Security Policy (CSP)

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' https://appsforoffice.microsoft.com;
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https:;
  connect-src 'self'
    https://api.vorbium.com.br
    https://graph.microsoft.com
    https://login.microsoftonline.com;
  frame-ancestors 'self'
    https://*.microsoft.com
    https://*.office.com
    https://*.office365.com
    https://*.outlook.com;
  font-src 'self' https://res-1.cdn.office.net;
```

### 11.2. HMAC-SHA256 para Validacao de Webhooks

```python
# apps/api/app/core/webhook_validation.py

import hashlib
import hmac

def validate_client_state(received_state: str, expected_secret: str) -> bool:
    """
    Valida clientState de Graph change notifications.
    Usa HMAC para prevenir webhook spoofing.
    """
    expected_hmac = hmac.new(
        expected_secret.encode('utf-8'),
        msg=b'graph-notification',
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received_state, expected_hmac)


def generate_client_state(secret: str) -> str:
    """Gera clientState para registro de subscription."""
    return hmac.new(
        secret.encode('utf-8'),
        msg=b'graph-notification',
        digestmod=hashlib.sha256,
    ).hexdigest()
```

### 11.3. JWT Validation para Microsoft Tokens

```python
# apps/api/app/core/microsoft_auth.py

import httpx
import jwt
from jwt import PyJWKClient

MICROSOFT_JWKS_URI = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
MICROSOFT_ISSUER_PREFIX = "https://login.microsoftonline.com/"

_jwks_client = None

def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(MICROSOFT_JWKS_URI)
    return _jwks_client


async def validate_microsoft_token(token: str) -> dict:
    """
    Valida JWT da Microsoft seguindo as etapas:
    1. Busca signing keys do JWKS endpoint
    2. Verifica signature
    3. Valida audience (nosso client ID)
    4. Valida issuer (Azure AD)
    5. Valida expiration (exp) e not-before (nbf)
    6. Retorna claims
    """
    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.AZURE_CLIENT_ID,
        options={
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iss": True,
            "verify_aud": True,
        },
        issuer=f"{MICROSOFT_ISSUER_PREFIX}{settings.AZURE_TENANT_ID}/v2.0",
    )

    return claims
```

### 11.4. Rate Limiting por Endpoint

```python
# Limites recomendados para novos endpoints

RATE_LIMITS = {
    "/outlook-addin/summarize": "20/min per user",
    "/outlook-addin/classify": "30/min per user",
    "/outlook-addin/extract-deadlines": "20/min per user",
    "/teams-bot/webhook": "100/min per app",
    "/graph/webhook/notification": "1000/min per app",
    "/auth/microsoft-sso": "10/min per IP",
    "/auth/teams-sso": "10/min per IP",
}
```

### 11.5. Dados Sensiveis — Tratamento LGPD

| Dado | Classificacao | Retencao | Armazenamento |
|------|-------------|---------|--------------|
| Corpo do e-mail | Sensivel | Nao armazenar (processo em memoria) | N/A |
| Resumo gerado | PII potencial | 30 dias (cache) | PostgreSQL (encrypted) |
| ConversationReference | Tecnico | 30 dias (TTL) | Redis |
| Microsoft tokens | Credencial | Session only | MSAL cache (memoria) |
| Iudex JWT | Credencial | Expiracao do token | Client-side (localStorage) |
| Logs de auditoria | Operacional | 90 dias | PostgreSQL |

---

## 12. Observabilidade e Telemetria

### 12.1. Metricas a Coletar

| Metrica | Tipo | Labels | Destino |
|---------|------|--------|---------|
| `outlook_addin.summarize.latency` | Histogram | user_id, status | Application Insights |
| `outlook_addin.summarize.count` | Counter | status, tipo_juridico | Application Insights |
| `teams_bot.message.count` | Counter | command, status | Application Insights |
| `teams_bot.proactive.count` | Counter | type, status | Application Insights |
| `graph.api.latency` | Histogram | endpoint, status | Application Insights |
| `graph.api.throttle.count` | Counter | endpoint | Application Insights |
| `graph.webhook.count` | Counter | resource, change_type | Application Insights |

### 12.2. Logs Estruturados

```python
# Formato de log padrao para novos endpoints
logger.info(
    "outlook_addin.summarize",
    extra={
        "user_id": current_user.id,
        "message_id": request.internet_message_id,
        "email_subject_length": len(request.subject),
        "body_size_bytes": len(request.body),
        "tipo_juridico": result.tipo_juridico,
        "prazos_count": len(result.prazos),
        "latency_ms": elapsed_ms,
    },
)
```

---

## 13. Deployment e Distribuicao

### 13.1. Centralized Deployment — Modos

| Modo | Descricao | Uso |
|------|----------|-----|
| **Fixed** | Add-in instalado para todos, sem opcao de remover | Admin forca instalacao |
| **Available** | Add-in disponivel no catalogo, usuario escolhe instalar | Padrao recomendado |
| **Optional** | Add-in instalado por default, usuario pode remover | Adocao com flexibilidade |

**Recomendacao**: Comecar com **Available**, migrar para **Optional** apos validacao.

### 13.2. Pipeline de Deploy

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────────┐
│ Develop │────►│ Staging  │────►│ Sideload │────►│ Production   │
│         │     │ (deploy) │     │ (test)   │     │ (M365 Admin) │
└─────────┘     └──────────┘     └──────────┘     └──────────────┘

1. Push to feature branch
2. CI builds Outlook + Teams apps
3. Deploy to staging environment
4. Sideload in test tenant
5. Smoke tests + E2E
6. Deploy to production
7. Update manifest in M365 Admin Center
```

### 13.3. Hosting

| Componente | Hosting | URL |
|-----------|---------|-----|
| Outlook Add-in (static) | Vercel / Azure Static Web Apps | `addin.vorbium.com.br` |
| Teams Tab (static) | Vercel / Azure Static Web Apps | `teams.vorbium.com.br` |
| API (FastAPI) | Existente | `api.vorbium.com.br` |
| Bot endpoint | Existente (FastAPI) | `api.vorbium.com.br/api/teams-bot/webhook` |
| Azure Bot Service | Azure | Configurado para `api.vorbium.com.br` |

### 13.4. Variaveis de Ambiente (Novas)

```bash
# Azure AD
AZURE_CLIENT_ID=<uuid>
AZURE_CLIENT_SECRET=<secret>
AZURE_TENANT_ID=<uuid>

# Teams Bot
TEAMS_BOT_APP_ID=<uuid>
TEAMS_BOT_APP_PASSWORD=<secret>

# Graph
GRAPH_WEBHOOK_SECRET=<random-string>
GRAPH_NOTIFICATION_URL=https://api.vorbium.com.br/api/graph/webhook/notification

# Feature flags
OUTLOOK_ADDIN_ENABLED=true
TEAMS_BOT_ENABLED=true
```

---

## 14. Timeline New Outlook

### 14.1. Status da Migracao Microsoft

| Marco | Data | Impacto |
|-------|------|---------|
| New Outlook GA | 2024 | Disponivel para todos os usuarios |
| Classic Outlook opt-out para empresas | **Abril 2026** | Empresas podem adiar migracao |
| Classic Outlook end-of-support | ~2027 (estimado) | COM/VSTO add-ins param de funcionar |

### 14.2. Implicacoes para o Iudex

1. **NAA so funciona no New Outlook** — usuario no Classic precisa de fallback
2. **COM/VSTO add-ins sao incompativeis** com New Outlook — nao construir COM
3. **Web add-ins (Office.js) funcionam em ambos** — nossa escolha correta
4. **Priorizar New Outlook** — enterprise opt-out expira em abril 2026, maioria vai migrar

### 14.3. Estrategia de Compatibilidade

```
New Outlook (Win/Mac) ──► NAA (full features)
        │
Outlook on the Web ──────► NAA (full features)
        │
Outlook Mobile ──────────► NAA (features reduzidas, UI adaptada)
        │
Classic Outlook ─────────► SSO fallback (features basicas)
                           + Banner "Migre para New Outlook"
```

---

## 15. Testes e QA

### 15.1. Estrategia de Testes

| Tipo | Ferramenta | Cobertura |
|------|-----------|----------|
| Unit (Frontend) | Jest + RTL | Components, stores, hooks |
| Unit (Backend) | pytest | Services, models, handlers |
| Integration (API) | pytest + httpx | Endpoints, auth flow |
| E2E (Outlook) | Playwright + Office Sideload | Task pane flows |
| E2E (Teams) | Bot Framework Test | Bot commands, cards |
| E2E (Graph) | Mock Graph + Integration | Webhooks, subscriptions |
| Performance | k6 | API latency, concurrent users |
| Accessibility | axe-core | WCAG 2.1 AA |

### 15.2. Sideloading por Plataforma

| Plataforma | Metodo de Sideload |
|-----------|-------------------|
| **Outlook on the Web** | Settings > Manage Add-ins > Upload manifest XML |
| **New Outlook (Windows)** | `npx office-addin-debugging start manifest.xml` |
| **New Outlook (Mac)** | Copiar manifesto para `~/Library/Containers/com.microsoft.Outlook/Data/Documents/wef` |
| **Classic Outlook** | File > Manage Add-ins > Custom Add-ins |
| **Teams (Desktop/Web)** | Apps > Upload a custom app > Upload manifest.json |
| **Teams (Dev Portal)** | Developer Portal > Import app |

### 15.3. Mock de Office.js

```typescript
// apps/outlook-addin/src/__tests__/mocks/office-mock.ts

/**
 * Mock de Office.js para testes unitarios.
 * Simula Mailbox APIs sem precisar do runtime Office.
 */
const mockMailboxItem = {
  subject: "Notificacao Extrajudicial - Contrato 123/2025",
  from: { emailAddress: "advogado@escritorio.com.br" },
  to: [{ emailAddress: "cliente@empresa.com.br" }],
  cc: [],
  dateTimeCreated: new Date("2026-02-10T10:00:00Z"),
  conversationId: "conv-123",
  internetMessageId: "<msg-123@escritorio.com.br>",
  attachments: [
    {
      id: "att-1",
      name: "notificacao.pdf",
      contentType: "application/pdf",
      size: 245000,
      isInline: false,
    },
  ],
  body: {
    getAsync: jest.fn((type, callback) => {
      callback({
        status: "succeeded",
        value: "<p>Prezado Cliente, segue notificacao...</p>",
      });
    }),
  },
  getAttachmentContentAsync: jest.fn((id, callback) => {
    callback({
      status: "succeeded",
      value: { content: "base64content==", format: "base64" },
    });
  }),
};

(global as any).Office = {
  onReady: jest.fn((callback) => callback({ host: "Outlook" })),
  context: {
    mailbox: {
      item: mockMailboxItem,
      addHandlerAsync: jest.fn(),
    },
    requirements: {
      isSetSupported: jest.fn(() => true),
    },
  },
  CoercionType: { Html: "html", Text: "text" },
  AsyncResultStatus: { Succeeded: "succeeded" },
  EventType: { ItemChanged: "itemChanged" },
};
```

### 15.4. Debugging Tools

| Ferramenta | Plataforma | Uso |
|-----------|-----------|-----|
| F12 DevTools | New Outlook (Windows) | Inspect task pane DOM/JS |
| Safari Web Inspector | Outlook (Mac) | DevTools para add-in |
| Browser DevTools | OWA / Teams Web | Standard browser debug |
| `npx office-addin-debugging start` | Local dev | Sideload + auto-reload |
| Bot Framework Emulator | Local dev | Testar bot sem deploy |
| Adaptive Cards Designer | Web tool | Preview de cards |

---

## 16. Fases de Implementacao

### Fase 1 — MVP (8-10 semanas)

#### Sprint 1-2: Fundacao (2 semanas)
- [ ] Setup `apps/outlook-addin/` (scaffold Vite + React + Fluent UI)
- [ ] Configurar Azure AD App Registration (NAA + SSO)
- [ ] Implementar `msal-config.ts` com NAA + fallback
- [ ] Endpoint `POST /auth/microsoft-sso` no backend
- [ ] Endpoint `POST /auth/teams-sso` no backend
- [ ] Model `MicrosoftUser` + migration
- [ ] Manifesto JSON Unificado do Outlook (Host: Mailbox) — ver ADR-001

#### Sprint 3-4: Outlook Add-in Core (2 semanas)
- [ ] `mail-bridge.ts` — extracao de dados do e-mail
- [ ] Endpoint `POST /outlook-addin/summarize` (SSE)
- [ ] Endpoint `POST /outlook-addin/classify`
- [ ] Endpoint `POST /outlook-addin/extract-deadlines`
- [ ] `SummaryPanel.tsx` — UI de sumarizacao
- [ ] `DeadlineList.tsx` — lista de prazos
- [ ] `ActionBar.tsx` — acoes sugeridas

#### Sprint 5-6: Teams Bot Core (2 semanas)
- [ ] Setup Azure Bot Service
- [ ] Endpoint `POST /teams-bot/webhook`
- [ ] `IudexBot` — handler de mensagens
- [ ] Handler `/pesquisar` com Adaptive Card
- [ ] Handler `/ajuda`
- [ ] Handler de chat livre (LLM)
- [ ] Manifesto JSON do Teams

#### Sprint 7-8: Notificacoes + Polish (2 semanas)
- [ ] `ConversationReference` storage (Redis)
- [ ] Celery task `notify_workflow_hil`
- [ ] Celery task `notify_workflow_completed`
- [ ] HIL Adaptive Card com Aprovar/Rejeitar
- [ ] Card action handler
- [ ] Teams SSO + Tab basica
- [ ] Testes unitarios (min 70% cobertura)

#### Sprint 9-10: QA + Deploy (2 semanas)
- [ ] Sideload testing (Outlook + Teams)
- [ ] E2E tests
- [ ] Security review (CSP, JWT validation, rate limits)
- [ ] Deploy staging
- [ ] Smoke tests em ambiente real
- [ ] Documentacao de admin deployment
- [ ] Deploy producao

### Fase 2 — Expansao (6-8 semanas)
- [ ] Extracao de anexos (Outlook)
- [ ] Pesquisa no corpus (Outlook)
- [ ] Trigger de workflow via e-mail (Outlook)
- [ ] Deteccao LGPD (reutiliza anonymize)
- [ ] Tab dashboard (Teams)
- [ ] RSC permissions (Teams)
- [ ] Streaming bot responses (Teams)
- [ ] Graph webhooks (change notifications)
- [ ] Delta query para sync de e-mails

### Fase 3 — Diferenciacao (6-8 semanas)
- [ ] Calendar integration (criar eventos de prazos)
- [ ] Compose mode (sugestoes ao compor e-mail)
- [ ] Message Extension (Teams)
- [ ] Internacionalizacao (pt-BR + en-US)
- [ ] Event Grid (se volume justificar)
- [ ] Analytics dashboard

---

## Apendice A — Requirement Sets do Outlook

| Requirement Set | Versao | APIs Relevantes |
|----------------|--------|----------------|
| Mailbox 1.1 | 2013 | Read mode basico, subject, from, to |
| Mailbox 1.3 | 2015 | Compose mode, saveAsync |
| Mailbox 1.5 | 2016 | Pinnable task pane, account info |
| Mailbox 1.8 | 2019 | getAttachmentContentAsync, categories |
| Mailbox 1.10 | 2020 | SessionData, notifications |
| Mailbox 1.13 | 2022 | Pinned pane lifecycle, sensitivity labels |
| Mailbox 1.14 | 2023 | NAA support, enhanced permissions |

**Nosso target**: Mailbox 1.14 (NAA), com fallback para 1.5 (minimo funcional).

## Apendice B — Links de Referencia

| Recurso | URL |
|---------|-----|
| Office Add-ins documentation | https://learn.microsoft.com/office/dev/add-ins/ |
| Outlook add-in APIs | https://learn.microsoft.com/office/dev/add-ins/outlook/ |
| NAA documentation | https://learn.microsoft.com/office/dev/add-ins/develop/enable-nested-app-authentication-in-your-add-in |
| Teams app development | https://learn.microsoft.com/microsoftteams/platform/ |
| Bot Framework (Python) | https://learn.microsoft.com/azure/bot-service/ |
| Adaptive Cards | https://adaptivecards.io/ |
| Graph API reference | https://learn.microsoft.com/graph/api/overview |
| Graph change notifications | https://learn.microsoft.com/graph/change-notifications-overview |
| Graph throttling | https://learn.microsoft.com/graph/throttling |
| MSAL.js NAA | https://learn.microsoft.com/entra/msal/js/ |
| Fluent UI v9 | https://react.fluentui.dev/ |
| Teams Toolkit | https://learn.microsoft.com/microsoftteams/platform/toolkit/ |

---

> **Documento vivo** — atualizar conforme decisoes de implementacao sao tomadas.
> **Proximos passos**: Iniciar Sprint 1-2 (Fundacao) conforme descrito na Fase 1.
