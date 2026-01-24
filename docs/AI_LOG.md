# AI_LOG.md — Histórico de Sessões Claude Code

> Este arquivo registra as sessões do Claude Code neste projeto.
> Atualize ao final de cada sessão significativa.

---

## Template de Entrada

```markdown
## [DATA] — Objetivo da Sessão

### Contexto
- Motivo/problema que levou à sessão

### Arquivos Alterados
- `caminho/arquivo.ts` — descrição da mudança

### Comandos Executados
- `pnpm test` — resultado
- `pnpm lint` — resultado

### Decisões Tomadas
- Por que escolheu X em vez de Y

### Próximos Passos
- O que ficou pendente

### Feedback do Usuário
- Comentários/correções recebidas
```

---

## 2026-01-24 — Budget Cap para RAG Request

### Contexto
- Implementar controle de custos para operacoes HyDE + multi-query no pipeline RAG
- Evitar gastos excessivos com chamadas LLM durante query expansion

### Arquivos Criados
- `apps/api/app/services/rag/core/budget_tracker.py` — novo modulo para tracking de orcamento por request

### Arquivos Alterados
- `apps/api/app/services/rag/config.py` — adicionadas configuracoes de budget (max_tokens_per_request, max_llm_calls_per_request, warn_at_budget_percent)
- `apps/api/app/services/rag/core/__init__.py` — exporta novos componentes do BudgetTracker
- `apps/api/app/services/rag/core/query_expansion.py` — integrado BudgetTracker nas funcoes expand_async, generate_hypothetical_document, generate_query_variants, rewrite_query e _call_gemini
- `apps/api/app/services/rag/pipeline/rag_pipeline.py` — integrado BudgetTracker no search(), _stage_query_enhancement(), e PipelineTrace

### Comandos Executados
- `python -m py_compile` em todos arquivos alterados — OK
- Testes de import e funcionalidade basica — OK

### Decisoes Tomadas
- Usar estimativa baseada em caracteres para tokens (evitar dependencias pesadas de tokenizers)
- BudgetTracker como dataclass para facilitar serializacao e uso
- Integrar budget tracking opcional (graceful degradation se modulo nao disponivel)
- Adicionar budget_usage ao PipelineTrace para observabilidade completa

### Funcionalidades Implementadas
1. **BudgetTracker class**: Track tokens e LLM calls por request
2. **Budget config**: max_tokens=50000, max_llm_calls=5, warn_at=80%
3. **Integration points**: query expansion, HyDE, multi-query
4. **Observability**: Usage reports no trace output

### Proximos Passos
- Integrar com embedding tracking no vector search
- Adicionar metricas de budget ao dashboard
- Configurar alertas quando budget excedido

---

## 2026-01-23 — Configuração do Sistema de Memória

### Contexto
- Implementar sistema de memória persistente para Claude Code registrar trabalho e melhorar com feedback

### Arquivos Criados
- `CLAUDE.md` — memória principal do projeto
- `.claude/rules/testing.md` — regras de testes
- `.claude/rules/code-style.md` — estilo de código
- `.claude/rules/security.md` — regras de segurança
- `.claude/rules/api.md` — regras da API
- `docs/AI_LOG.md` — este arquivo
- `docs/LESSONS_LEARNED.md` — lições aprendidas

### Comandos Executados
- Nenhum comando de verificação necessário (apenas criação de docs)

### Decisões Tomadas
- Estrutura modular com rules separadas por área
- YAML frontmatter em api.md para aplicar só em apps/api/
- Log e lessons em docs/ para fácil acesso

### Próximos Passos
- Aplicar estrutura nos demais projetos do Cursor
- Criar script de automação

---

## 2026-01-24 — PR2 & PR3: Consolidate Tracing & Unify Pipeline

### Contexto
- Checklist RAG identificou duplicação de tracing e múltiplos pipelines RAG

### PR2: Consolidate Tracing

**Arquivos Alterados:**
- `apps/api/app/services/rag/utils/trace.py` — Adicionados 10 novos event types para compatibilidade
  - QUERY_REWRITE, HYDE_GENERATE, GRAPH_EXPAND, ARGUMENT_CONTEXT, CONTEXT_COMPRESS
  - FALLBACK, RAG_ROUTER_DECISION, PROMPT_FINAL, PARENT_CHILD_EXPAND, GENERIC
- `apps/api/app/services/rag/utils/trace.py` — Adicionado suporte a conversation_id e message_id
- `apps/api/app/services/rag/utils/trace.py` — Adicionada função trace_event_legacy() para compatibilidade
- `apps/api/app/services/rag_trace.py` — Convertido para wrapper que delega ao novo trace.py

**Resultado:**
- Código legado continua funcionando sem mudanças (rag_trace.py é wrapper)
- Novo código pode usar trace.py diretamente com tipos estruturados
- Um único sistema de tracing com múltiplos canais (JSONL, OTel, LangSmith, DB)

### PR3: Unify RAG Pipeline

**Arquivos Criados:**
- `apps/api/app/services/rag/pipeline_adapter.py` — Adapter unificado

**Estratégia:**
- Flag `RAG_USE_NEW_PIPELINE` controla qual pipeline usar (default: legacy)
- Quando features específicas são necessárias (query rewrite com histórico, adaptive routing, argument graph), usa legacy automaticamente
- Quando possível, delega para RAGPipeline novo

**Resultado:**
- API mantém compatibilidade total com build_rag_context()
- Novo código pode usar build_rag_context_unified() com mesmo interface
- Migração gradual: teste com RAG_USE_NEW_PIPELINE=true quando pronto

### Comandos Executados
- `python -c "from app.services.rag.utils.trace import ..."` — OK
- `python -c "from app.services.rag.pipeline_adapter import ..."` — OK

### Próximos Passos
- Testar com RAG_USE_NEW_PIPELINE=true em ambiente de staging
- Gradualmente migrar callers para usar build_rag_context_unified
- Quando validado, tornar novo pipeline o default

---

## 2026-01-24 — Fix TTL Cleanup Field Mismatch (PR1 do checklist RAG)

### Contexto
- Checklist de qualidade RAG identificou que o TTL cleanup não funcionava
- `ttl_cleanup.py` buscava campos inexistentes (`ingested_at`, `created_at`, `timestamp`)
- OpenSearch e Qdrant usam `uploaded_at` como campo de timestamp

### Arquivos Alterados
- `apps/api/app/services/rag/utils/ttl_cleanup.py` — Corrigido para usar `uploaded_at`
  - OpenSearch: mudou query de `should` com 3 campos para `must` com `uploaded_at`
  - Qdrant: mudou `timestamp_fields` de 4 campos incorretos para `["uploaded_at"]`
- `apps/api/tests/test_ttl_cleanup.py` — Criado novo arquivo com 8 testes unitários

### Comandos Executados
- `python -m py_compile app/services/rag/utils/ttl_cleanup.py` — OK
- `pytest tests/test_ttl_cleanup.py -v` — 8 passed

### Decisões Tomadas
- Usar `must` em vez de `should` no OpenSearch (campo é obrigatório, não opcional)
- Teste de código-fonte para validar que o campo correto está sendo usado (evita mocks complexos)

### Impacto
- **Antes**: TTL cleanup nunca deletava dados (buscava campos que não existiam)
- **Depois**: Dados locais mais antigos que TTL (7 dias) serão corretamente removidos

### Próximos Passos (do checklist RAG)
- PR2: Consolidar tracing (`rag_trace.py` → `trace.py`)
- PR3: Unificar pipeline (`build_rag_context()` → `RAGPipeline`)

---

## 2026-01-24 — Simplificação Painel Auditoria + DebateAuditPanel

### Contexto
- Painel de auditoria do Canvas tinha componentes redundantes
- Faltava visibilidade completa dos debates entre agentes no LangGraph

### Arquivos Alterados

**Simplificação do QualityPanel (transcrição):**
- `apps/web/src/components/dashboard/quality-panel.tsx`
  - Removidos botões "Validar Fidelidade", "Só Estrutural", "Gerar Sugestões (IA)"
  - Mantido apenas "Validação Completa" (HIL Unificado)
  - Removidas funções não utilizadas (handleValidate, handleAnalyzeStructure, handleSemanticSuggestions)
  - Removidos states não utilizados (isValidating, isAnalyzing)

**Ajustes nos painéis de Quality Gate e HIL:**
- `apps/web/src/components/dashboard/quality-gate-panel.tsx`
  - Removido defaultValue do accordion (fechado por padrão)
  - Adicionado card "Cobertura refs" com percentual
  - Grid agora tem 4 colunas: Compressão, Cobertura refs, Refs omitidas, Checks

- `apps/api/app/services/ai/quality_gate.py`
  - Adicionado campo `reference_coverage: float` ao dataclass QualityGateResult
  - Retorna coverage no resultado e no gate_results do nó

**Novo componente DebateAuditPanel:**
- `apps/web/src/components/dashboard/debate-audit-panel.tsx` (novo)
  - Mostra drafts completos de cada modelo
  - Exibe divergências detalhadas por seção
  - Lista issues da crítica do comitê
  - Mostra decisões do merge (Judge)
  - Exibe risk flags e claims pendentes
  - Accordion com seções divergentes abertas por padrão

- `apps/web/src/components/dashboard/canvas-container.tsx`
  - Adicionado import e uso do DebateAuditPanel na aba Auditoria

### Comandos Executados
- `npm -w apps/web run type-check` — OK
- `python -c "from app.services.ai.quality_gate import ..."` — OK

### Decisões Tomadas
- HIL Unificado é o mais completo (diff + correção determinística + semântica)
- PreventiveAuditPanel e QualityPanel removidos do Canvas (específicos para transcrição)
- DebateAuditPanel permite auditoria completa dos debates multi-agente

### Estrutura Final Aba Auditoria (Canvas)
```
1. Cabeçalho Compliance + Risk Badge
2. QualityGatePanel (compressão, cobertura, refs omitidas)
3. HilChecklistPanel (10 fatores de risco)
4. Relatório de Conformidade (Markdown)
5. Tabela de Citações
6. DebateAuditPanel (drafts, divergências, críticas, merge)
7. HilHistoryPanel (histórico de interações humanas)
8. AuditIssuesPanel (se houver issues)
```

---

## 2026-01-24 — Histórico de Interações HIL

### Contexto
- Interações HIL (Human-in-the-Loop) não estavam sendo registradas para auditoria
- Faltava histórico de aprovações, edições e instruções dadas ao agente

### Arquivos Alterados

**Backend:**
- `apps/api/app/services/ai/langgraph_legal_workflow.py`
  - Adicionado campo `hil_history: List[Dict[str, Any]]` ao DocumentState

- `apps/api/app/api/endpoints/jobs.py`
  - Endpoint `/resume` agora captura conteúdo original antes de resumir
  - Cria entrada de histórico com: id, timestamp, checkpoint, user, decisão, conteúdo antes/depois, instruções, proposta
  - Inclui `hil_history` no resume_payload para persistir no state
  - Evento `hil_response` agora inclui `hil_entry` completo
  - Evento `done` agora inclui `hil_history`, `processed_sections`, `has_any_divergence`, `divergence_summary`

**Frontend:**
- `apps/web/src/components/dashboard/hil-history-panel.tsx` (novo)
  - Exibe histórico de todas as interações HIL
  - Cards com: checkpoint, timestamp, usuário, decisão
  - Mostra instruções dadas ao agente
  - Mostra proposta do usuário (quando rejeita)
  - Diff visual entre conteúdo original e editado
  - Ordenado por timestamp (mais recente primeiro)

- `apps/web/src/components/dashboard/canvas-container.tsx`
  - Adicionado import e uso do HilHistoryPanel na aba Auditoria

### Estrutura de uma entrada HIL
```json
{
  "id": "uuid",
  "timestamp": "2026-01-24T10:30:00Z",
  "checkpoint": "section",
  "section_title": "Dos Fatos",
  "user_id": "user_123",
  "user_email": "user@example.com",
  "decision": "edited",
  "approved": true,
  "original_content": "...",
  "edited_content": "...",
  "instructions": "...",
  "proposal": "...",
  "iteration": 1
}
```

### Comandos Executados
- `npm -w apps/web run type-check` — OK
- `python -m py_compile app/api/endpoints/jobs.py` — OK

---

## 2026-01-24 — CaseState Enxuto e Auditável

### Contexto
- Codebase precisava de um estado mínimo (CaseState) auditável
- LangGraph DocumentState tinha 90% dos campos necessários mas não era persistido
- Faltavam: tasks[], partes, cnj_number normalizado

### Arquivos Criados
- `apps/api/app/models/workflow_state.py` — Persiste DocumentState do LangGraph
  - sources[], citations_map (retrieval)
  - drafts_history, hil_history (versões)
  - routing_decisions, alert_decisions, citation_decisions, audit_decisions, quality_decisions (decisions_log)
  - Método `from_document_state()` para converter do LangGraph

- `apps/api/app/models/case_task.py` — Tarefas derivadas com prazos
  - Campos: deadline, priority, status, task_type
  - Sources: manual, djen, workflow, ai_suggested
  - Métodos: `from_djen_intimation()`, `from_workflow_suggestion()`

- `apps/api/alembic/versions/d3a4f8c9e2b1_add_workflow_state_case_tasks.py` — Migração

### Arquivos Alterados
- `apps/api/app/models/case.py`
  - Adicionado `cnj_number` (normalizado no padrão CNJ)
  - Adicionado `classe` (classe processual)
  - Adicionado `assunto` (assunto principal)
  - Adicionado `partes` (JSONB com autor, réu, terceiros, advogados)
  - Métodos: `normalize_cnj()`, `add_parte()`, `get_partes_resumo()`

- `apps/api/app/models/__init__.py`
  - Adicionados exports dos novos modelos

- `apps/api/app/api/endpoints/jobs.py`
  - Import de `WorkflowState` e `AsyncSessionLocal`
  - Função `persist_workflow_state()` para persistência em background
  - Chamada via `asyncio.create_task()` no evento "done"

### Estrutura Final do CaseState

```
Case (DB)
├── cnj_number (normalizado)
├── partes (JSONB: autor, réu, terceiros)
├── classe, assunto, tribunal
└── tasks[] → CaseTask

WorkflowState (DB) — Persistido após workflow
├── sources[] (documentos recuperados)
├── retrieval_queries[]
├── citations_map
├── drafts_history[]
├── hil_history[]
├── processed_sections[]
└── decisions (routing, alerts, citations, audit, quality)
```

### Comandos Executados
- `python -m py_compile ...` — OK para todos os arquivos

### Próximos Passos
- ~~Rodar migração: `alembic upgrade head`~~ ✅
- ~~Criar endpoints REST para consultar WorkflowState e CaseTasks~~ ✅
- Integrar criação automática de tasks a partir do DJEN

### Endpoints REST Criados (v5.7)

**WorkflowState:**
- `GET /audit/workflow-states` — Lista estados de workflow do usuário
- `GET /audit/workflow-states/{id}` — Detalhes completos (auditoria)
- `GET /audit/workflow-states/by-job/{job_id}` — Busca por job
- `GET /audit/workflow-states/{id}/sources` — Fontes recuperadas
- `GET /audit/workflow-states/{id}/decisions` — Decisões do workflow
- `GET /audit/workflow-states/{id}/hil-history` — Histórico HIL

**CaseTasks:**
- `GET /audit/tasks` — Lista tarefas (filtros: case, status, priority, overdue)
- `GET /audit/tasks/{id}` — Detalhes da tarefa
- `POST /audit/tasks` — Criar tarefa manual
- `PATCH /audit/tasks/{id}` — Atualizar tarefa
- `DELETE /audit/tasks/{id}` — Deletar tarefa

**Summary:**
- `GET /audit/summary` — Resumo para dashboard

---

## 2026-01-24 — Auditoria Detalhada no GeneratorWizard

### Contexto
- A página de geração de peças (`/cases/[id]` aba Generation) usava `GeneratorWizard`
- Este componente não tinha os novos painéis de auditoria criados para o CanvasContainer
- Usuário pediu para preservar a UI existente e incorporar o painel completo de auditoria

### Arquivos Alterados
- `apps/web/src/components/dashboard/generator-wizard.tsx`
  - Adicionados imports: QualityGatePanel, HilChecklistPanel, DebateAuditPanel, HilHistoryPanel
  - Adicionada seção expandível "Auditoria Detalhada" após os painéis existentes (JobQualityPanel, etc.)
  - Accordion colapsável com todos os 4 painéis de auditoria

### Estrutura Adicionada
```tsx
<Accordion type="single" collapsible>
    <AccordionItem value="audit-details">
        <AccordionTrigger>
            Auditoria Detalhada [Badge: Compliance & HIL]
        </AccordionTrigger>
        <AccordionContent>
            1. QualityGatePanel (compressão, cobertura, refs omitidas)
            2. HilChecklistPanel (10 fatores de risco)
            3. DebateAuditPanel (drafts, divergências, críticas, merge)
            4. HilHistoryPanel (histórico de interações humanas)
        </AccordionContent>
    </AccordionItem>
</Accordion>
```

### Comandos Executados
- `npm -w apps/web run type-check` — OK

### Decisões Tomadas
- Seção expandível preserva UI limpa por padrão
- Accordion colapsável não atrapalha fluxo de geração
- Mesmos painéis do CanvasContainer para consistência

---

## 2026-01-24 — B2 Citer/Verifier Node (Gate Pré-Debate)

### Contexto
- Análise comparativa entre arquitetura proposta (Times A/B) e fluxo LangGraph atual
- Identificado gap: verificação de rastreabilidade afirmação→fonte era parcial (policy [n], retry need_juris)
- Implementado B2 Citer/Verifier como gate obrigatório entre pesquisa e debate

### Arquivos Criados
- `apps/api/app/services/ai/citer_verifier.py` — Nó B2 completo com:
  - Extração de afirmações jurídicas via LLM
  - Mapeamento para fontes RAG e citations_map
  - Tags [VERIFICAR] em claims sem fonte
  - Decisão de force_hil (coverage < 60%) e block_debate (coverage < 30%)

### Arquivos Alterados
- `apps/api/app/services/ai/langgraph_legal_workflow.py`:
  - Adicionado import do citer_verifier_node
  - Adicionados campos ao DocumentState: citer_verifier_result, verified_context, citer_verifier_force_hil, citer_verifier_coverage, citer_verifier_critical_gaps, citer_min_coverage
  - Registrado nó no workflow
  - Alterada edge: fact_check → citer_verifier → debate (com router condicional)
  - Atualizado docstring do módulo

### Fluxo Atualizado
```
fact_check → citer_verifier → [coverage >= 0.3] → debate
                            → [coverage < 0.3] → divergence_hil (skip debate)
```

### Comandos Executados
- `python -m py_compile apps/api/app/services/ai/citer_verifier.py` — OK
- `python -c "from app.services.ai.langgraph_legal_workflow import legal_workflow_app"` — OK

### Decisões Tomadas
- Arquivo separado (citer_verifier.py) para modularidade
- Coverage mínimo padrão de 60% (configurável via citer_min_coverage)
- Block debate se coverage < 30% (muito baixo para gerar conteúdo confiável)
- Router condicional permite skip do debate em casos críticos

### Próximos Passos
- Testes unitários para citer_verifier_node
- UI para exibir resultado da verificação (coverage, claims verificados/não verificados)
- Considerar Time A (Monitoramento) como próximo gap a implementar

---

## 2026-01-24 — Documentacao Completa do RAG Pipeline

### Contexto
- Solicitacao de criar pacote de documentacao abrangente para o sistema RAG
- Consolidar informacoes dispersas em codigo e arquivos existentes

### Arquivos Criados
- `docs/rag/ARCHITECTURE.md` — Arquitetura do pipeline de 10 estagios
  - Diagrama Mermaid do fluxo completo
  - Descricao detalhada de cada estagio (Query Enhancement, Lexical, Vector, Merge, CRAG, Rerank, Expand, Compress, Graph, Trace)
  - Modelo de seguranca multi-tenant
  - Feature flags e otimizacoes

- `docs/rag/CONFIG.md` — Referencia completa de configuracao
  - Todas as 60+ variaveis de ambiente documentadas
  - Agrupadas por categoria (Feature Flags, CRAG, Query Expansion, Reranking, Compression, Storage, Tracing)
  - Valores padrao, ranges validos e exemplos

- `docs/rag/API.md` — Documentacao da API REST
  - 5 endpoints: search, ingest/local, ingest/global, delete, stats
  - Request/response schemas com exemplos
  - Codigos de erro e rate limiting
  - Exemplos em Python, JavaScript e cURL

### Arquivos Lidos para Extracao de Informacao
- `apps/api/app/services/rag/config.py` — Todas as configuracoes
- `apps/api/app/services/rag/pipeline/rag_pipeline.py` — Logica do pipeline
- `apps/api/app/api/endpoints/rag.py` — Endpoints da API
- `rag.md` — Material de referencia (livro RAG)

### Comandos Executados
- `mkdir -p docs/rag` — Criar diretorio

### Decisoes Tomadas
- Documentacao em Portugues (idioma do projeto)
- Mermaid para diagramas (suportado pelo GitHub)
- Organizacao em 3 arquivos separados por publico (arquitetura, ops/config, devs/API)
- Incluir referencias a papers originais (RAG, CRAG, HyDE, RRF)

### Proximos Passos
- Criar testes de validacao da documentacao (links, exemplos)
- Adicionar documentacao de GraphRAG quando Neo4j for expandido
- Criar guia de troubleshooting

---

## 2026-01-24 — Consolidacao RAG: Remocao de Shims e Extracao de Utilitarios

### Contexto
- Codigo RAG tinha duplicacao de funcoes utilitarias (env_bool, env_int, env_float)
- Shims `rag_context.py` e `rag_module.py` delegavam para implementacoes reais
- Arquivos importavam dos shims em vez de importar diretamente

### Arquivos Criados
- `apps/api/app/services/rag/utils/env_helpers.py` — Funcoes utilitarias extraidas
  - `env_bool()` — Parse de boolean de variavel de ambiente
  - `env_int()` — Parse de int de variavel de ambiente
  - `env_float()` — Parse de float de variavel de ambiente

### Arquivos Alterados

**Fase 1: Atualizacao de imports para usar implementacoes reais:**
- `apps/api/app/api/endpoints/chats.py`
  - `from app.services.rag.pipeline_adapter import build_rag_context_unified as build_rag_context`
- `apps/api/app/services/chat_service.py`
  - `from app.services.rag.pipeline_adapter import build_rag_context_unified as build_rag_context`
- `apps/api/app/services/ai/langgraph_legal_workflow.py`
  - `from app.services.rag_module_old import create_rag_manager, get_scoped_knowledge_graph`
- `apps/api/app/services/document_generator.py`
  - `from app.services.rag_module_old import RAGManager, create_rag_manager`
- `apps/api/app/api/endpoints/admin_rag.py`
  - `from app.services.rag_module_old import create_rag_manager`
- `apps/api/app/api/endpoints/advanced.py`
  - `from app.services.rag_module_old import RAGManager`
- `apps/api/app/services/ai/orchestrator.py`
  - `from app.services.rag_module_old import create_rag_manager`
- `apps/api/app/services/rag/pipeline/rag_pipeline.py`
  - `from app.services.rag_module_old import get_scoped_knowledge_graph`

**Fase 2: Extracao de utilitarios duplicados:**
- `apps/api/app/services/rag_context_legacy.py`
  - Removidas funcoes locais `_env_bool`, `_env_int`, `_env_float`
  - Importa de `app.services.rag.utils.env_helpers`
- `apps/api/app/services/rag/pipeline_adapter.py`
  - Removidas funcoes locais `_env_bool`, `_env_int`, `_env_float`
  - Importa de `app.services.rag.utils.env_helpers`
- `apps/api/app/services/rag/pipeline/rag_pipeline.py`
  - Removidas funcoes locais `_env_bool`, `_env_int`
  - Importa de `app.services.rag.utils.env_helpers`
- `apps/api/app/services/rag/utils/__init__.py`
  - Adicionados exports de `env_bool`, `env_int`, `env_float`

**Atualizacao de documentacao dos shims:**
- `apps/api/app/services/rag_context.py` — Marcado como DEPRECATED com imports preferidos
- `apps/api/app/services/rag_module.py` — Marcado como DEPRECATED com imports preferidos

### Comandos Executados
- `python -c "from app.services.rag.utils.env_helpers import ..."` — OK
- `python -c "from app.services.rag.pipeline_adapter import ..."` — OK
- `python -c "from app.services.rag_context import ..."` — OK (shim ainda funciona)
- `python -c "from app.services.rag_module import ..."` — OK (shim ainda funciona)
- `python -c "import app.api.endpoints.chats; ..."` — OK (todos modulos modificados)

### Decisoes Tomadas
- Shims mantidos para compatibilidade (marcados como deprecated)
- Imports diretos usam `rag_module_old` e `rag.pipeline_adapter`
- Funcoes utilitarias centralizadas em `rag/utils/env_helpers.py`
- Alias `_env_bool` mantido nos arquivos para minimizar mudancas internas

### Resultado
- **Antes**: 3 copias de `_env_bool`, `_env_int`, `_env_float`
- **Depois**: 1 implementacao em `env_helpers.py`, importada por 3 arquivos
- Shims continuam funcionando para codigo legado
- Novo codigo deve importar diretamente das implementacoes reais

---

## 2026-01-24 — Preload Strategy para Reranker e Embeddings

### Contexto
- Cold start latency no reranker model impactava primeira requisicao RAG
- Necessidade de eliminar latencia inicial carregando modelos no startup

### Arquivos Alterados
- `apps/api/app/services/rag/core/reranker.py`
  - Adicionado metodo `preload()` que carrega modelo e executa warmup inference
  - Adicionado metodo `is_preloaded()` para verificar status
  - Warmup usa query e documento juridico real em portugues

- `apps/api/app/services/rag/core/embeddings.py`
  - Adicionada lista `COMMON_LEGAL_QUERIES` com 31 queries juridicas comuns
  - Adicionada funcao `preload_embeddings_cache()` para pre-carregar embeddings
  - Adicionada funcao `is_embeddings_service_ready()` para verificar status

- `apps/api/app/main.py`
  - Adicionada funcao async `_preload_rag_models()` no lifespan
  - Preload executado em thread pool para nao bloquear event loop
  - Configuravel via `RAG_PRELOAD_RERANKER=true` e `RAG_PRELOAD_EMBEDDINGS=true`

### Variaveis de Ambiente
```bash
# Habilitar preload do reranker (cross-encoder model)
RAG_PRELOAD_RERANKER=true

# Habilitar preload de embeddings de queries juridicas comuns
RAG_PRELOAD_EMBEDDINGS=true
```

### Comandos Executados
- `python -m py_compile app/main.py app/services/rag/core/reranker.py app/services/rag/core/embeddings.py` — OK

### Decisoes Tomadas
- Preload via run_in_executor para nao bloquear startup
- Configuracao opt-in via env vars (padrao false)
- Queries de warmup em portugues juridico para otimizar cache hit rate
- Log de tempo de carga para monitoramento

### Impacto
- **Antes**: Primeira query RAG tinha latencia adicional de 2-5s para carregar modelo
- **Depois**: Modelos carregados no startup, primeira query sem cold start

---

## 2026-01-24 — CI/CD Integration para RAG Evaluation Automatizada

### Contexto
- Necessidade de automatizar avaliacao de qualidade do sistema RAG
- Workflow CI/CD para validar thresholds de metricas em PRs e pushes
- Execucao semanal completa com metricas LLM

### Arquivos Criados
- `.github/workflows/rag-eval.yml` — Workflow principal com:
  - Triggers: push/PR em paths RAG, schedule semanal (Monday 6am UTC), workflow_dispatch manual
  - Job `evaluate`: metricas basicas (context_precision, context_recall)
  - Job `weekly-full-eval`: metricas completas incluindo LLM (faithfulness, answer_relevancy)
  - Thresholds: context_precision >= 0.70, context_recall >= 0.65
  - Comentario automatico em PRs com resultados
  - Upload de artefatos (30 dias para PRs, 90 dias para weekly)

- `evals/benchmarks/v1.0_legal_domain.jsonl` — Dataset de benchmark juridico
  - 12 queries cobrindo Lei, Jurisprudencia, Doutrina
  - Topicos: licitacao, sumulas STJ, prisao preventiva, contratos admin, prescricao, dano moral coletivo, habeas corpus, desconsideracao PJ, dolo/culpa, modulacao STF, principios admin, reserva do possivel

- `evals/scripts/run_eval.sh` — Script para execucao local
  - Opcoes: --dataset, --top-k, --with-llm, --persist-db, --min-precision, --min-recall
  - Timestamp automatico no output
  - Geracao de report se eval_report.py existir

- `evals/results/.gitkeep` — Placeholder para diretorio de resultados

### Arquivos Alterados
- `eval_rag.py` — Adicionado alias `--output` para `--out` (compatibilidade CI)
- `.gitignore` — Adicionadas regras para ignorar resultados de avaliacao (exceto .gitkeep)

### Arquivos Removidos
- `.github/workflows/rag_eval.yml` — Removido (substituido pelo novo rag-eval.yml mais completo)

### Comandos Executados
- `mkdir -p evals/benchmarks evals/scripts evals/results` — OK
- `chmod +x evals/scripts/run_eval.sh` — OK

### Decisoes Tomadas
- Workflow dispatch manual para flexibilidade em testes
- Schedule semanal com metricas LLM (mais caro, mas completo)
- Thresholds conservadores inicialmente (70%/65%) para permitir baseline
- Comentario em PR usa GitHub Script para melhor formatacao
- Artefatos de weekly com 90 dias para analise de tendencias

### Proximos Passos
- Adicionar mais queries ao benchmark conforme casos de uso reais
- Configurar secrets no GitHub (OPENAI_API_KEY, GOOGLE_API_KEY)
- Ajustar thresholds apos baseline estabelecido
- Integrar com dashboard de observabilidade

---

## 2026-01-24 — Legal Domain RAG Evaluation Metrics

### Contexto
- Necessidade de metricas de avaliacao especificas para dominio juridico brasileiro
- Metricas RAGAS padrao nao capturam nuances legais (citacoes, vigencia temporal, jurisdicao)
- Implementacao de avaliador complementar ao RAGAS existente

### Arquivos Criados
- `apps/api/app/services/ai/rag_evaluator.py` — Modulo completo com:
  - `LegalEvalResult` dataclass para resultados de avaliacao
  - `extract_legal_claims()` — Extrai afirmacoes juridicas do texto
  - `count_cited_claims()` — Conta claims com citacoes
  - `evaluate_citation_coverage()` — % de claims com fonte atribuida
  - `extract_cited_laws()` — Extrai referencias legais (Lei, Decreto, MP, LC, etc.)
  - `is_law_current()` — Verifica se lei ainda esta em vigor (database de leis revogadas)
  - `evaluate_temporal_validity()` — % de leis citadas ainda vigentes
  - `evaluate_jurisdiction_match()` — Verifica se jurisdicao esta correta
  - `extract_legal_entities()` — Extrai entidades por tipo (laws, articles, sumulas, decisions)
  - `evaluate_entity_accuracy()` — Precision/recall de entidades extraidas
  - `evaluate_legal_answer()` — Executa todas as avaliacoes em uma resposta
  - `add_legal_metrics_to_ragas()` — Integra metricas legais aos resultados RAGAS
  - `evaluate_legal_batch()` — Avalia batch de amostras

### Padroes Regex Implementados
- Leis: Lei, LC, Decreto, Decreto-Lei, MP, Resolucao, IN, Portaria
- Codigos: CF, CPC, CPP, CTN, CDC, CLT, ECA
- Artigos: Art. X, Art. X, caput, Art. X, I, Art. X, § 1º
- Sumulas: Sumula X TST/STF/STJ, Sumula Vinculante X, OJ X SDI
- Decisoes: RE, REsp, ADI, HC, MS + numeros CNJ

### Database de Leis Revogadas
- Lei 8.666/93 — parcialmente revogada (Lei 14.133/2021)
- Lei 10.520/2002 — revogada (Lei 14.133/2021)
- MP 927/2020 — perdeu eficacia (nao convertida)
- MP 936/2020 — convertida (Lei 14.020/2020)
- Decreto-Lei 200/67 — parcialmente vigente

### Metricas Implementadas
1. **Citation Coverage** (0-1): % de claims juridicos com citacao
2. **Temporal Validity** (0-1): % de leis citadas em vigor
3. **Jurisdiction Match** (bool): Jurisdicao correta (federal, estadual, municipal, trabalhista)
4. **Entity Precision** (0-1): Entidades corretas / entidades encontradas
5. **Entity Recall** (0-1): Entidades encontradas / entidades esperadas
6. **Legal Score** (0-1): Media ponderada (25% cit + 20% temp + 15% jur + 20% prec + 20% rec)

### Comandos Executados
- `python -m py_compile apps/api/app/services/ai/rag_evaluator.py` — OK
- Testes unitarios inline — 10/10 passaram

### Integracao com eval_rag.py
- Funcao `add_legal_metrics_to_ragas()` adiciona metricas legais ao payload existente
- Pode ser chamada apos `ragas.evaluate()` para enriquecer resultados
- Adiciona campos `legal_*` ao summary e `legal_metrics` a cada sample

### Proximos Passos
- Integrar chamada ao rag_evaluator no eval_rag.py principal
- Adicionar queries com expected_entities ao benchmark
- Criar dashboard de metricas legais
- Expandir database de leis revogadas

---

## 2026-01-24 — Testes Unitarios RAG Pipeline Core

### Contexto
- Componentes core do RAG pipeline (CRAG gate, query expansion, reranker) sem cobertura de testes
- Necessidade de testes que nao dependam de conexoes reais (OpenSearch, Qdrant)
- Uso de mocks para simular comportamentos

### Arquivos Criados

**Estrutura de testes:**
- `apps/api/tests/rag/__init__.py` — Pacote de testes RAG
- `apps/api/tests/rag/fixtures.py` — Fixtures e mocks compartilhados
  - Mock OpenSearch client responses
  - Mock Qdrant client responses
  - Mock embedding responses
  - Sample legal documents (legislacao, jurisprudencia)
  - Sample queries with expected results
  - Helper functions para assertions

**Testes CRAG Gate (66 testes):**
- `apps/api/tests/rag/test_crag_gate.py`
  - TestCRAGConfig: default values, overrides, from_rag_config
  - TestEvidenceLevel: classification properties, confidence scores
  - TestCRAGEvaluation: serialization, reason property
  - TestCRAGGateClassification: STRONG/MODERATE/LOW/INSUFFICIENT evidence
  - TestCRAGGateDecisions: pass/fail thresholds
  - TestCRAGGateRecommendedActions: strategies por evidence level
  - TestRetryStrategyBuilder: strategies for each evidence level
  - TestCRAGOrchestrator: evaluate, should_retry, get_retry_parameters
  - TestCRAGAuditTrail: create, add_action, finalize, serialization
  - TestCRAGIntegration: search_with_correction, dedupe
  - TestConvenienceFunctions: evaluate_crag_gate, get_retry_strategy
  - TestEdgeCases: single result, negative scores, missing fields

**Testes Query Expansion (65 testes):**
- `apps/api/tests/rag/test_query_expansion.py`
  - TestQueryExpansionConfig: default values, from_rag_config
  - TestTTLCache: get/set, expiration, eviction, stats
  - TestRRFScore: score calculation, rank ordering
  - TestMergeResultsRRF: dedup, fusion boost, top_k
  - TestMergeLexicalVectorRRF: hybrid results, weighted fusion
  - TestLegalAbbreviationExpansion: STF, STJ, CPC, CLT, CF expansion
  - TestQueryExpansionService: cache, heuristic variants
  - TestQueryExpansionServiceWithMockedLLM: HyDE, multi-query, advanced search
  - TestSingletonFactory: get_instance, reset
  - TestEdgeCases: unicode, special characters, LLM failure

**Testes Reranker (53 testes):**
- `apps/api/tests/rag/test_reranker.py`
  - TestRerankerConfig: default values, from_rag_config
  - TestRerankerResult: creation, bool, len, iter
  - TestPortugueseLegalDomainBoost: art, sumula, tribunals, CNJ, lei patterns
  - TestCrossEncoderRerankerCore: empty results, score preservation
  - TestBatchProcessing: multiple queries, top_k
  - TestTextTruncation: short, long, word boundary, empty
  - TestLazyLoading: model not loaded on init, loaded on use
  - TestFallbackBehavior: fallback model, original order
  - TestScoreNormalization: negative scores, min_score filter
  - TestConvenienceFunctions: rerank, rerank_with_metadata
  - TestSingletonPattern: get_instance, reset, cache
  - TestEdgeCases: missing text, empty text, different field names
  - TestLegalDomainIntegration: boost affects ranking

### Comandos Executados
- `pytest tests/rag/test_crag_gate.py -v -o "addopts="` — 66 passed
- `pytest tests/rag/test_query_expansion.py -v -o "addopts="` — 65 passed
- `pytest tests/rag/test_reranker.py -v -o "addopts="` — 53 passed
- `pytest tests/rag/ -v -o "addopts="` — 299 passed total

### Decisoes Tomadas
- Fixtures em arquivo separado para reutilizacao
- Mocks de CrossEncoder, OpenSearch, Qdrant para evitar dependencias externas
- Testes de edge cases para robustez
- Documentacao brasileira nos samples (legislacao, jurisprudencia)
- Patterns de domain boost para portugues juridico

### Cobertura de Testes
- **CRAG Gate**: evidence classification, gate decisions, retry strategies, audit trail
- **Query Expansion**: TTL cache, RRF fusion, legal abbreviations, HyDE, multi-query
- **Reranker**: legal domain boost, batch processing, lazy loading, fallback behavior

### Proximos Passos
- Integrar testes ao CI/CD pipeline
- Adicionar testes de integracao com mocks de storage services
- Expandir cobertura para graph enrichment e compression modules

---

<!-- Novas entradas acima desta linha -->
