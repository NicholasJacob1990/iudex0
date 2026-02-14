# PRD — Add-ins Outlook e Teams para Iudex/Vorbium

> **Versao**: 1.0
> **Data**: 2026-02-10
> **Autor**: Equipe Vorbium
> **Status**: Draft

---

## Sumario

1. [Visao do Produto](#1-visao-do-produto)
2. [Personas e Usuarios-Alvo](#2-personas-e-usuarios-alvo)
3. [Problemas e Oportunidades](#3-problemas-e-oportunidades)
4. [Casos de Uso Principais](#4-casos-de-uso-principais)
5. [Requisitos Funcionais (RF)](#5-requisitos-funcionais-rf)
6. [Requisitos Nao-Funcionais (RNF)](#6-requisitos-nao-funcionais-rnf)
7. [Comandos e Interacoes](#7-comandos-e-interacoes)
8. [Matching e Classificacao Inteligente](#8-matching-e-classificacao-inteligente)
9. [Limites e Restricoes de Plataforma](#9-limites-e-restricoes-de-plataforma)
10. [Dependencias Externas](#10-dependencias-externas)
11. [Priorizacao MoSCoW](#11-priorizacao-moscow)
12. [Metricas de Sucesso](#12-metricas-de-sucesso)
13. [Riscos e Mitigacoes](#13-riscos-e-mitigacoes)
14. [Fases de Entrega](#14-fases-de-entrega)

---

## 1. Visao do Produto

### 1.1. Contexto

O Iudex (marca comercial: Vorbium) e uma plataforma juridica com IA multi-agente que ja possui:

- **Web App** (Next.js) — interface principal com chat, RAG, workflows LangGraph, playbooks
- **Word Add-in** (`apps/office-addin/`) — task pane React para analise de contratos, redlines OOXML, chat, corpus, traducao e anonimizacao
- **API** (FastAPI) — 40+ endpoints com streaming SSE, multi-LLM (Claude, Gemini, GPT), orquestrador multi-agente
- **Workflows** — Visual builder (React Flow) com execucao LangGraph, Human-in-the-Loop (HIL), agendamento cron, webhooks
- **DMS Integration** — Google Drive e SharePoint/OneDrive via MS Graph (ja implementado em `dms_service.py`)

### 1.2. Oportunidade

Advogados e equipes juridicas passam 60-70% do tempo de trabalho em e-mail (Outlook) e comunicacao de equipe (Teams). Integrar o Iudex diretamente nesses ambientes elimina a troca de contexto e permite:

- **No Outlook**: Triagem inteligente de e-mails juridicos, sumarizacao, extracao de prazos, trigger de workflows, pesquisa no corpus direto do e-mail
- **No Teams**: Bot conversacional para consultas juridicas, cards com resultados de analise, notificacoes proativas de workflow, pesquisa de jurisprudencia sem sair do chat

### 1.3. Visao Estrategica

> Ser a plataforma juridica que acompanha o advogado em todos os seus pontos de trabalho digital — Word, Outlook, Teams e Web — com inteligencia contextual unificada.

---

## 2. Personas e Usuarios-Alvo

### P1: Advogado Associado

- **Perfil**: 3-8 anos de experiencia, gerencia carteira de contratos e e-mails de clientes
- **Dor principal**: Gasta 2h+ por dia classificando e-mails, identificando urgencias, buscando precedentes
- **Expectativa**: Ver imediatamente o tipo juridico do e-mail, prazos extraidos, e acoes sugeridas

### P2: Socio/Gestor de Equipe

- **Perfil**: Toma decisoes, delega tarefas, precisa de visibilidade sobre o pipeline
- **Dor principal**: Dificuldade de acompanhar status de workflows e revisoes em andamento
- **Expectativa**: Receber notificacoes no Teams quando workflows completam, HIL precisa de aprovacao, ou prazos se aproximam

### P3: Paralegal/Estagiario

- **Perfil**: Executa pesquisas, organiza documentos, prepara minutas
- **Dor principal**: Muitas ferramentas diferentes, copiar/colar entre sistemas
- **Expectativa**: Pesquisar corpus e jurisprudencia direto do Teams, receber analises simplificadas

### P4: Administrador de TI

- **Perfil**: Responsavel por seguranca, compliance e deployment
- **Dor principal**: Controlar acesso, garantir LGPD, gerenciar apps no Microsoft 365
- **Expectativa**: Deploy centralizado, logs de auditoria, controle granular de permissoes

---

## 3. Problemas e Oportunidades

| # | Problema | Impacto | Oportunidade |
|---|---------|---------|-------------|
| 1 | Troca de contexto constante entre email e plataforma | -30% produtividade | Add-in Outlook com analise in-situ |
| 2 | E-mails juridicos nao classificados/priorizados | Prazos perdidos, risco de responsabilidade | Classificacao automatica + extracao de prazos |
| 3 | Equipe nao recebe notificacoes de workflows | Atrasos em aprovacoes HIL | Bot Teams com notificacoes proativas |
| 4 | Pesquisa de jurisprudencia exige abrir plataforma | Interrupcao do fluxo de trabalho | Comando `/pesquisar` no Teams |
| 5 | Resultados de analise isolados no web app | Dificuldade de compartilhar com equipe | Adaptive Cards no Teams |
| 6 | Nenhuma integracao com calendario/prazos | Prazos gerenciados manualmente | Graph Calendar integration |

---

## 4. Casos de Uso Principais

### UC-01: Sumarizacao de E-mail Juridico (Outlook)

**Ator**: Advogado Associado
**Trigger**: Abre e-mail no Outlook, clica no botao "Vorbium" na ribbon
**Fluxo**:
1. Add-in extrai corpo do e-mail + anexos via Office.js (`item.body.getAsync`)
2. Envia para API `/outlook-addin/summarize`
3. API processa com LLM, retorna sumarizacao estruturada
4. Task pane exibe: tipo juridico, partes, prazos, resumo, acoes sugeridas
5. Usuario pode acionar workflow diretamente do painel

### UC-02: Trigger de Workflow via E-mail (Outlook)

**Ator**: Advogado Associado
**Trigger**: No painel do Outlook, seleciona "Iniciar Workflow"
**Fluxo**:
1. Lista workflows disponiveis (filtrados por tipo de documento detectado)
2. Usuario seleciona workflow e preenche inputs (pre-populados com dados do e-mail)
3. API cria WorkflowRun via `/workflows/{id}/run`
4. Progresso exibido no task pane com SSE
5. Resultado final exibido como Adaptive Card no painel

### UC-03: Pesquisa de Corpus via E-mail (Outlook)

**Ator**: Advogado Associado
**Trigger**: Seleciona trecho do e-mail, clica "Pesquisar no Corpus"
**Fluxo**:
1. Add-in extrai texto selecionado
2. Envia para API `/corpus/search`
3. Resultados exibidos no task pane com score de relevancia
4. Usuario pode clicar para ver documento completo no web app

### UC-04: Bot Juridico no Teams (Teams)

**Ator**: Qualquer membro da equipe
**Trigger**: Menciona @Vorbium no chat ou envia mensagem no 1:1 com o bot
**Fluxo**:
1. Bot recebe mensagem via Bot Framework
2. Classifica intencao (consulta, pesquisa, comando, status)
3. Processa com LLM do Iudex (mesma API de chat)
4. Retorna resposta como Adaptive Card ou texto formatado
5. Suporta contexto multi-turno

### UC-05: Notificacao Proativa de Workflow (Teams)

**Ator**: Socio/Gestor
**Trigger**: Workflow atinge estado HIL (paused_hil) ou completa
**Fluxo**:
1. Worker Celery detecta mudanca de status no WorkflowRun
2. Envia notificacao via Proactive Messaging do Bot Framework
3. Teams exibe Adaptive Card com status, resumo, e botao de acao
4. Usuario pode aprovar/rejeitar HIL diretamente no card
5. Resposta enviada de volta para API, workflow resume

### UC-06: Tab de Dashboard no Teams (Teams)

**Ator**: Socio/Gestor
**Trigger**: Abre a aba "Vorbium" no canal do Teams
**Fluxo**:
1. Tab carrega SPA React (mesma base do web app, adaptada)
2. Exibe dashboard: workflows recentes, analises pendentes, metricas
3. Permite iniciar workflows, ver historico, acessar corpus
4. Autenticacao SSO via Teams SDK

### UC-07: Extracao de Prazos de E-mail (Outlook)

**Ator**: Advogado Associado
**Trigger**: Painel do Outlook exibe prazos extraidos automaticamente
**Fluxo**:
1. Add-in envia corpo do e-mail para API `/outlook-addin/extract-deadlines`
2. LLM extrai datas, prazos, obrigacoes com nivel de urgencia
3. Task pane exibe timeline de prazos
4. Botao "Adicionar ao Calendario" cria evento via Graph Calendar API
5. Botao "Criar Tarefa" cria tarefa no Planner/To Do

---

## 5. Requisitos Funcionais (RF)

### 5.1. Outlook Add-in

| ID | Requisito | Prioridade | Descricao |
|----|----------|-----------|----------|
| RF-OL-01 | Autenticacao NAA/SSO | Must | Nested App Authentication com MSAL.js >= 3.27.0, fallback para popup/redirect |
| RF-OL-02 | Extracao de corpo do e-mail | Must | `item.body.getAsync(Office.CoercionType.Html)` para HTML, fallback para texto |
| RF-OL-03 | Extracao de anexos | Should | `item.getAttachmentContentAsync()` com suporte a inline e regular |
| RF-OL-04 | Sumarizacao inteligente | Must | Sumarizacao estruturada com tipo juridico, partes, resumo, acoes |
| RF-OL-05 | Classificacao de tipo juridico | Must | Classificar e-mail em categorias (contratual, litigioso, regulatorio, etc.) |
| RF-OL-06 | Extracao de prazos | Must | Extrair datas, prazos processuais, obrigacoes contratuais com urgencia |
| RF-OL-07 | Pesquisa no corpus | Should | Busca semantica no corpus a partir de texto selecionado |
| RF-OL-08 | Trigger de workflow | Should | Iniciar workflow com dados pre-populados do e-mail |
| RF-OL-09 | Streaming SSE | Must | Respostas de IA via SSE (mesmo padrao do Word add-in: `sse-client.ts`) |
| RF-OL-10 | Integracao com Calendar | Could | Criar eventos no calendario via Graph Calendar API |
| RF-OL-11 | Compose mode | Could | Sugestoes de texto ao compor e-mail juridico |
| RF-OL-12 | Deteccao de dados sensiveis | Should | Alertar sobre dados sensiveis (LGPD) antes de encaminhar e-mails |

#### RF-OL-01 Detalhamento: NAA (Nested App Authentication)

NAA e o modelo de autenticacao recomendado pela Microsoft para add-ins Office desde 2024. Diferente do popup OAuth2, NAA usa o token do host Office como bootstrap:

- **MSAL.js >= 3.27.0** com `createNestablePublicClientApplication()`
- **Broker URI**: `brk-multihub://localhost` (registrado no Azure AD como SPA redirect)
- **Scopes padrao**: `User.Read`, `Mail.Read`, `Calendars.ReadWrite`
- **Fallback**: Verificar `Office.context.requirements.isSetSupported('NestedAppAuth', '1.1')`. Se false, usar `OfficeRuntime.auth.getAccessToken()` (SSO classico) ou popup MSAL
- **Plataformas suportadas**: New Outlook (Windows/Mac), Outlook na Web, Outlook mobile (iOS/Android)
- **Nao suportado**: Outlook classic (COM) — deve exibir mensagem de incompatibilidade

### 5.2. Teams Add-in

| ID | Requisito | Prioridade | Descricao |
|----|----------|-----------|----------|
| RF-TM-01 | Bot conversacional | Must | Bot com NLU via LLM, contexto multi-turno, Adaptive Cards |
| RF-TM-02 | Autenticacao SSO Teams | Must | TeamsJS SDK v2 + `authentication.getAuthToken()` com OBO flow |
| RF-TM-03 | Tab de dashboard | Should | Tab estatica/configuravel com SPA React para dashboard |
| RF-TM-04 | Pesquisa de corpus via comando | Must | `/pesquisar [query]` retorna Adaptive Cards com resultados |
| RF-TM-05 | Notificacoes proativas | Must | Notificar usuario quando workflow completa ou HIL precisa de input |
| RF-TM-06 | Message Extension | Could | Buscar corpus/jurisprudencia inline ao compor mensagem |
| RF-TM-07 | Adaptive Cards interativos | Must | Cards com botoes de acao para aprovar/rejeitar HIL, ver detalhes |

> **Nota mobile**: Teams mobile suporta apenas Adaptive Cards **v1.2**. Cards criticos (HIL, notificacoes) devem usar apenas features v1.2 para garantir compatibilidade. Ver risco R13.

| RF-TM-08 | RSC (Resource-Specific Consent) | Should | Permissoes granulares por canal/equipe sem admin global |
| RF-TM-09 | Streaming de respostas | Should | Bot envia respostas parciais via `streamingActivity()` (SDK >= 4.22) |
| RF-TM-10 | Internacionalizacao | Could | Suporte pt-BR e en-US baseado no locale do Teams |

### 5.3. Compartilhados (Ambos Add-ins)

| ID | Requisito | Prioridade | Descricao |
|----|----------|-----------|----------|
| RF-SH-01 | Reutilizar API existente | Must | Mesmos endpoints do Iudex — sem duplicar logica |
| RF-SH-02 | Reutilizar SSE client | Must | Mesmo padrao de `sse-client.ts` do Word add-in |
| RF-SH-03 | Estado persistente | Should | Zustand + persist (mesmo padrao de `auth-store.ts`) |
| RF-SH-04 | Auditoria/logging | Must | Registrar acoes do usuario para compliance (LGPD) |
| RF-SH-05 | Multi-tenant | Must | Suportar organizacoes diferentes com isolamento de dados |

---

## 6. Requisitos Nao-Funcionais (RNF)

| ID | Categoria | Requisito | Meta | Medida |
|----|----------|----------|------|--------|
| RNF-01 | Performance | Tempo de carga do task pane | < 2s | Lighthouse FCP |
| RNF-02 | Performance | Tempo de resposta sumarizacao | < 5s (first token via SSE) | P95 latency |
| RNF-03 | Performance | Tempo de carga da Tab Teams | < 3s | Lighthouse FCP |
| RNF-04 | Disponibilidade | Uptime do bot Teams | 99.5% | Azure Monitor |
| RNF-05 | Seguranca | Dados em transito | TLS 1.2+ | Certificado |
| RNF-06 | Seguranca | Tokens armazenados | Somente em memoria (MSAL cache) | Code review |
| RNF-07 | Seguranca | CSP headers | Restritivo (script-src 'self') | Manifest + headers |
| RNF-08 | Compatibilidade | Outlook platforms | New Outlook (Win/Mac), OWA, Mobile | E2E tests |
| RNF-09 | Compatibilidade | Teams platforms | Desktop, Web, Mobile | E2E tests |
| RNF-10 | Acessibilidade | WCAG 2.1 AA | Conformidade | axe-core |
| RNF-11 | Escalabilidade | Usuarios simultaneos | 1000+ task panes concorrentes | Load test |
| RNF-12 | Observabilidade | Telemetria | Logs estruturados, metricas de uso | Application Insights |
| RNF-13 | Compliance | LGPD/GDPR | Dados pessoais minimizados, consentimento | Checklist legal |

---

## 7. Comandos e Interacoes

### 7.1. Outlook — Acoes no Task Pane

| Acao | Input | Output | Endpoint |
|------|-------|--------|----------|
| Sumarizar | Corpo do e-mail (auto) | Card com resumo estruturado | `POST /outlook-addin/summarize` |
| Classificar | Corpo do e-mail (auto) | Tipo juridico + confianca | `POST /outlook-addin/classify` |
| Extrair prazos | Corpo do e-mail (auto) | Lista de prazos com urgencia | `POST /outlook-addin/extract-deadlines` |
| Pesquisar corpus | Texto selecionado | Resultados rankeados | `POST /corpus/search` |
| Iniciar workflow | Dados do e-mail + selecao | WorkflowRun ID + SSE | `POST /workflows/{id}/run` |
| Detectar sensiveis | Corpo do e-mail (auto) | Entidades LGPD detectadas | `POST /word-addin/anonymize` (reutiliza) |

### 7.2. Teams — Comandos do Bot

| Comando | Descricao | Exemplo | Modo |
|---------|----------|---------|------|
| `/pesquisar [query]` | Busca no corpus juridico | `/pesquisar prescricao trabalhista` | Slash command |
| `/analisar` | Analisa texto colado na mensagem | `/analisar [texto do contrato]` | Slash command |
| `/workflow [nome]` | Inicia workflow por nome | `/workflow due-diligence` | Slash command |
| `/status [id]` | Status de um workflow run | `/status abc-123` | Slash command |
| `/ajuda` | Lista comandos disponiveis | `/ajuda` | Slash command |
| Mensagem livre | Chat juridico com IA | "Qual o prazo para recurso ordinario?" | Conversacional |
| `dry-run [workflow]` | Simula workflow sem executar | `dry-run revisao-contratual` | Conversacional |
| `suggest` | Sugere proximo passo | "Recebi intimacao, suggest" | Conversacional |

### 7.3. Teams — Adaptive Cards (Acoes)

| Card | Acoes Disponiveis | Callback |
|------|------------------|----------|
| Resultado de Pesquisa | "Ver detalhes", "Abrir no Vorbium" | Deep link para web app |
| Notificacao de Workflow | "Aprovar", "Rejeitar", "Ver detalhes" | `POST /workflows/{id}/runs/{runId}/hil` |
| Resultado de Analise | "Copiar resumo", "Iniciar revisao" | Trigger de novo workflow |
| Status de Prazo | "Adicionar ao calendario", "Delegar" | Graph Calendar API |

---

## 8. Matching e Classificacao Inteligente

### 8.1. Classificacao de E-mail

O sistema classifica e-mails em categorias juridicas usando o mesmo pipeline LLM do Iudex:

| Categoria | Exemplos | Acoes Sugeridas |
|-----------|---------|----------------|
| **Contratual** | Envio de minutas, negociacao de clausulas | Analisar com playbook, iniciar revisao |
| **Litigioso** | Intimacoes, citacoes, decisoes judiciais | Extrair prazos, criar tarefa |
| **Regulatorio** | Consultas de compliance, normas | Pesquisar corpus regulatorio |
| **Societario** | Atas, procuracoes, alteracoes contratuais | Iniciar workflow societario |
| **Trabalhista** | Reclamatoria, acordos, rescisoes | Calcular valores, pesquisar jurisprudencia |
| **Administrativo** | Agendamentos, cobrancas, informes | Classificar e arquivar |

### 8.2. Matching de Workflows

Baseado na classificacao do e-mail, o sistema sugere workflows relevantes:

1. **Deteccao de tipo de documento** — Reutiliza `playbook/recommend` (ja existe em `client.ts`)
2. **Score de relevancia** — Baseado em embeddings do titulo/descricao do workflow vs. conteudo do e-mail
3. **Historico do usuario** — Workflows mais usados pelo usuario aparecem primeiro
4. **Filtro por organizacao** — Workflows publicados + pessoais

### 8.3. RSC Permissions (Teams)

Para funcionar em canais/equipes sem exigir admin global:

| Permission | Scope | Uso |
|-----------|-------|-----|
| `TeamSettings.Read.Group` | Team | Ler configuracoes do time |
| `ChannelMessage.Read.Group` | Channel | Ler mensagens do canal (para context) |
| `ChatMessage.Read.Chat` | Chat | Ler mensagens em chat 1:1 |
| `TeamMember.Read.Group` | Team | Listar membros para notificacoes |

---

## 9. Limites e Restricoes de Plataforma

### 9.1. Outlook Add-in — Limites Reais

| Limite | Valor | Impacto | Mitigacao |
|--------|-------|---------|----------|
| `body.getAsync()` tamanho | 500K chars (web/mobile), ~1 MB (desktop) | E-mails muito grandes podem truncar | Paginar ou extrair primeiros 50KB |
| Concurrent async calls | 3 simultaneas (web/mobile), mais no desktop | Multiplas operacoes em paralelo | Queue com max concurrency |
| Task pane largura | 320px minimo, ~350px recomendado | UI deve ser compacta | Design mobile-first |
| Manifest XML max hosts | 1 por manifesto (Document, Mailbox) | Precisa manifesto separado do Word | Manifesto dedicado para Mailbox |
| NAA support | Apenas New Outlook + OWA | Classic Outlook (COM) nao suporta | Fallback graceful + mensagem |
| Attachment download | 1 por vez, max ~10 MB via EWS | Anexos grandes precisam de Graph | Usar Graph API para anexos > 5MB |
| Requirement Sets necessarios | Mailbox 1.5+ (minimo), 1.14 (recomendado) | Funcionalidades variam por versao | Feature detection com `isSetSupported()` |
| Pinned task pane | Apenas Mailbox 1.13+ | Manter aberto entre e-mails | Detectar e adaptar UX |
| CPU single core | 90% threshold (alerta apos 3 violacoes/5s) | Add-in desabilitado se exceder | Processamento pesado no backend, nao no client |
| Memoria | 50% do total disponivel no documento/mailbox | Add-in terminado se exceder | Lazy load, code splitting, tree shaking |
| Crashes por sessao | 4 crashes = desabilitado | Add-in para de funcionar | Error boundaries, tratamento robusto de erros |
| Unresponsiveness | 5 segundos = restart | Perda de estado | Operacoes async, nunca bloquear main thread |
| Custom Properties | 2.500 caracteres | Pouco espaco para metadata | Armazenar dados no backend, nao localmente |
| Session Data | 50.000 chars (1.15), ~2.6 MB (preview) | Cache local limitado | Usar para estado de sessao, nao dados grandes |

### 9.2. Teams App — Limites Reais

| Limite | Valor | Impacto | Mitigacao |
|--------|-------|---------|----------|
| Adaptive Card tamanho | 28 KB max payload | Cards complexos podem exceder | Paginar resultados, lazy load |
| Adaptive Card schema | v1.5 (Teams suporta ate 1.5) | Features de 1.6+ nao renderizam | Testar com schema 1.5 |
| Bot message rate | 1 msg/seg por conversa, 30/seg global | Burst de notificacoes limitado | Queue com rate limiter |
| Proactive message | Requer ConversationReference | Precisa armazenar referencia na 1a interacao | Salvar no DB na primeira mensagem |
| Tab iframe | 2048 chars na URL | Parametros de query limitados | Usar postMessage para dados |
| App manifest v1.19 | Manifesto unificado (JSON) | Formato diferente do Word (XML) | Seguir schema Teams Platform |
| RSC permissions | Requer Teams admin consent | Pode bloquear adocao | Funcionar sem RSC com features reduzidas |
| Streaming responses | SDK >= 4.22 via `sendActivity` chunks | Versoes antigas nao suportam | Feature detection |

### 9.3. Microsoft Graph API — Limites

| Limite | Valor | Contexto |
|--------|-------|---------|
| Throttle global | 130.000 req/10 seg (tenant) | Limite por tenant no Microsoft 365 |
| Throttle por app | 10.000 req/10 min (app + tenant) | Limite especifico por app registrado |
| Throttle por mailbox | 10.000 req/10 min | Limite por caixa de correio |
| Delta query | Suportado para messages, events, contacts | Eficiente para sync incremental |
| Webhook max subscriptions | 10.000 por app | Suficiente para uso enterprise |
| Webhook expiracao (mail) | 4230 min (~3 dias) | Precisa renovar periodicamente |
| Webhook expiracao (events) | 4230 min (~3 dias) | Mesma janela que mail |
| Webhook notification size | 4 KB | Notificacao com `resourceData` limitada |
| Batch requests | 20 requests por batch | Agrupar chamadas Graph |
| Subscriptions por mailbox | 1.000 (todas as apps) | Limite global Graph API |
| lifecycleNotificationUrl | Obrigatorio se expiration > 1h | Subscriptions Graph API |

---

## 10. Dependencias Externas

| Dependencia | Versao Minima | Uso | Risco |
|------------|--------------|-----|-------|
| **Azure AD App Registration** | N/A | OAuth2 + NAA + SSO | Requer admin consent para permissoes Graph |
| **Microsoft Graph API** | v1.0 | Mail, Calendar, Presence, Users | Rate limiting, breaking changes |
| **MSAL.js** | 3.27.0+ | NAA para Outlook add-in | Versao minima para createNestablePublicClientApplication |
| **Office.js** | Mailbox 1.5+ | APIs do Outlook | Requirement sets variam por plataforma |
| **TeamsJS SDK** | 2.x | SSO, contexto Teams, deep links | v1 deprecated, v2 tem breaking changes |
| **Teams SDK v2** | 2.x (GA JS/C#, Preview Python) | Bot conversacional Teams — substitui Bot Framework (descontinuado dez/2025) | Python em preview; alternativa: adapter manual no FastAPI |
| **Adaptive Cards SDK** | 1.5 | Cards interativos no Teams | Schema 1.5 e o maximo suportado pelo Teams |
| **Azure Bot Service** | N/A | Hosting do bot endpoint | Custo mensal, SLA 99.9% |
| **Iudex API** (FastAPI) | Existente | Todos os endpoints de IA, corpus, workflows | Deve suportar carga adicional |
| **Redis** | Existente | Cache, rate limiting, session | Ja usado pelo Iudex |
| **Celery** | Existente | Workers para workflows async | Ja usado pelo Iudex |

---

## 11. Priorizacao MoSCoW

### Must Have (Fase 1)

- [x] RF-OL-01: Autenticacao NAA/SSO
- [x] RF-OL-02: Extracao de corpo do e-mail
- [x] RF-OL-04: Sumarizacao inteligente
- [x] RF-OL-05: Classificacao de tipo juridico
- [x] RF-OL-06: Extracao de prazos
- [x] RF-OL-09: Streaming SSE
- [x] RF-TM-01: Bot conversacional
- [x] RF-TM-02: Autenticacao SSO Teams
- [x] RF-TM-04: Pesquisa de corpus via comando
- [x] RF-TM-05: Notificacoes proativas
- [x] RF-TM-07: Adaptive Cards interativos
- [x] RF-SH-01: Reutilizar API existente
- [x] RF-SH-02: Reutilizar SSE client
- [x] RF-SH-04: Auditoria/logging
- [x] RF-SH-05: Multi-tenant

### Should Have (Fase 2)

- [ ] RF-OL-03: Extracao de anexos
- [ ] RF-OL-07: Pesquisa no corpus
- [ ] RF-OL-08: Trigger de workflow
- [ ] RF-OL-12: Deteccao de dados sensiveis
- [ ] RF-TM-03: Tab de dashboard
- [ ] RF-TM-08: RSC permissions
- [ ] RF-TM-09: Streaming de respostas
- [ ] RF-SH-03: Estado persistente

### Could Have (Fase 3)

- [ ] RF-OL-10: Integracao com Calendar
- [ ] RF-OL-11: Compose mode
- [ ] RF-TM-06: Message Extension
- [ ] RF-TM-10: Internacionalizacao

### Won't Have (Neste ciclo)

- Integracao com Planner/To-Do (avaliar Fase 4)
- Add-in para PowerPoint (sem caso de uso juridico claro)
- Copilot Plugin (aguardar estabilizacao da plataforma)

---

## 12. Metricas de Sucesso

### 12.1. Adocao

| Metrica | Meta (3 meses) | Meta (6 meses) |
|---------|----------------|----------------|
| Instalacoes Outlook add-in | 50 | 200 |
| Instalacoes Teams app | 50 | 200 |
| DAU (daily active users) | 20% dos instalados | 30% dos instalados |
| Comandos/dia no Teams bot | 100 | 500 |
| Sumarizacoes/dia no Outlook | 200 | 1000 |

### 12.2. Engajamento

| Metrica | Meta |
|---------|------|
| Tempo medio no task pane (Outlook) | > 2 min por sessao |
| Workflows iniciados via Outlook/Teams | > 20% do total |
| Taxa de aprovacao HIL via Teams card | > 80% (vs. web app) |
| Pesquisas de corpus via Teams | > 15% do total |

### 12.3. Qualidade

| Metrica | Meta |
|---------|------|
| Acuracia de classificacao de e-mail | > 90% |
| Acuracia de extracao de prazos | > 95% |
| Satisfacao do usuario (NPS) | > 40 |
| Taxa de erro do bot | < 5% |
| Tempo de resposta (P95) | < 3s para first token |

---

## 13. Riscos e Mitigacoes

| # | Risco | Probabilidade | Impacto | Mitigacao |
|---|-------|--------------|---------|----------|
| R1 | Admin nao aprova permissoes Graph | Media | Alto | Funcionar com permissoes minimas, documentar beneficios para admin |
| R2 | Classic Outlook sem suporte NAA | Alta | Medio | Fallback SSO classico + mensagem de migrar para New Outlook |
| R3 | Rate limiting do Graph em tenant grande | Media | Alto | Cache agressivo, delta queries, batch requests |
| R4 | Adaptive Card muito complexo > 28KB | Baixa | Medio | Paginar resultados, lazy-load detalhes |
| R5 | Bot Framework breaking changes | Baixa | Medio | Pin de versoes, testes automatizados |
| R6 | Latencia da API em picos | Media | Alto | Auto-scaling, cache Redis, queue Celery |
| R7 | Dados sensiveis em logs do bot | Media | Alto | Sanitizacao de logs, politica de retencao |
| R8 | New Outlook timeline (enterprise opt-out abril 2026) | Alta | Alto | Priorizar New Outlook, mas manter fallback basico |
| R9 | Concorrencia com Microsoft Copilot | Media | Medio | Focar em features juridicas especializadas (playbooks, corpus) |
| R10 | Office 365 Connectors descontinuados (dez/2025) | Confirmado | Baixo | Usar Proactive Messaging via ConversationReference |
| R11 | Bot Framework SDK descontinuado (dez/2025) | Confirmado | Medio | Usar Teams SDK v2 (Python em preview) ou adapter manual no FastAPI |
| R12 | Deprecacao Conditional Access | Alta | O grant "Approved Client App" do Conditional Access sera descontinuado em marco 2026. MSAL NAA nao suporta esta politica. Tenants que usam devem migrar para Application Protection Policy antes dessa data. | Documentar requisito de migracao; testar com Application Protection Policy |
| R13 | Adaptive Cards v1.2 no mobile | Media | Teams mobile suporta apenas Adaptive Cards v1.2 (desktop/web suportam v1.5). Cards com features v1.3+ podem nao renderizar corretamente no mobile. | Testar todos os cards em mobile; usar v1.2 features para cards criticos |

---

## 14. Fases de Entrega

### Fase 1 — MVP (8-10 semanas)

**Outlook Add-in:**
- Task pane React (mesma stack do Word add-in)
- Autenticacao NAA com fallback
- Sumarizacao de e-mail com SSE
- Classificacao de tipo juridico
- Extracao de prazos
- Manifesto JSON Unificado para host Mailbox (ver ADR-001 no Design Doc)

**Teams App:**
- Bot conversacional com LLM
- SSO via TeamsJS SDK v2
- Comando `/pesquisar` com Adaptive Cards
- Notificacoes proativas de workflow (HIL + completion)
- Manifesto JSON unificado

**Backend:**
- Endpoints `/outlook-addin/*` (3-4 novos)
- Webhook handler para notificacoes proativas
- ConversationReference storage

### Fase 2 — Expansao (6-8 semanas)

**Outlook Add-in:**
- Extracao e analise de anexos
- Pesquisa no corpus
- Trigger de workflow via e-mail
- Deteccao de dados sensiveis (LGPD)

**Teams App:**
- Tab de dashboard
- RSC permissions
- Streaming de respostas do bot
- Estado persistente (Zustand)

### Fase 3 — Diferenciacao (6-8 semanas)

**Outlook Add-in:**
- Integracao com Calendar (criar eventos de prazos)
- Compose mode (sugestoes ao compor)

**Teams App:**
- Message Extension (busca inline)
- Internacionalizacao completa

### Fase 4 — Futuro (TBD)

- Copilot Plugin (quando plataforma estabilizar)
- Integracao Planner/To-Do
- Analytics avancado de uso por equipe
- Marketplace Microsoft AppSource

---

> **Proximos passos**: Ver `DESIGN_DOC_OFFICE_ADDINS.md` para detalhes de implementacao tecnica.
