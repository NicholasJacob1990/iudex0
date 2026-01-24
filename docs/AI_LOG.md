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

<!-- Novas entradas acima desta linha -->
