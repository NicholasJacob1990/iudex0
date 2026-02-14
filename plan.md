# Plano: Auditoria Unificada de Transcrição

## Contexto

Atualmente existem **3 tabs separadas** de auditoria na página de transcrição:
- **"Correções (HIL)"** — issues acionáveis com apply de correções
- **"Auditoria"** — relatório preventivo (read-only)
- **"Qualidade (Resumo)"** — referências legais ausentes

Isso fragmenta a experiência do usuário e causa sobreposição de dados. O plano unifica tudo em **uma única aba "Auditoria"** ao final do pipeline, com:
- Correções estruturais aplicadas **automaticamente** (sem HIL)
- Correções de conteúdo apresentadas via **HIL com diffs**
- Nota de fidelidade (formatted vs raw) visível
- Relatório consolidado

---

## Arquitetura Proposta

### Fluxo Simplificado

```
Transcrição (Whisper)
    → Formatação (LLM)
    → Auditoria Preventiva (VomoMLX)
    → Análise Estrutural
    → False Positive Filtering
    ──────────────────────────────────
    AUTO-APPLY: Correções estruturais  ← SEM HIL (duplicatas, numeração, headings com confidence ≥ 0.90)
    ──────────────────────────────────
    → Resultado com estrutural já corrigido
    → Uma única aba "Auditoria" com:
       ├─ Nota de fidelidade (score 0-10)
       ├─ Resumo de módulos (preventiva, estrutural, qualidade)
       ├─ Issues de CONTEÚDO pendentes ← COM HIL (omissões, distorções, alucinações)
       ├─ Log de correções estruturais auto-aplicadas (colapsável)
       └─ Diff viewer para cada issue de conteúdo
```

---

## Etapas de Implementação

### Fase 1 — Backend: Auto-apply estrutural no pipeline

**Arquivos:** `transcription_service.py`, `audit_pipeline.py`, `quality_service.py`

1. **No `transcription_service.py`**, após a auditoria preventiva + análise estrutural:
   - Separar issues em `structural` (fix_type=structural, confidence ≥ 0.90) e `content` (o resto)
   - Chamar `quality_service.apply_unified_hil_fixes()` **automaticamente** para as estruturais
   - O `formatted_text` retornado ao frontend já terá correções estruturais aplicadas
   - Salvar log das correções auto-aplicadas em `auto_applied_structural` no result

2. **Novo campo no payload de resposta** do job:
   ```python
   {
     "formatted_text": "...",  # já com estrutural corrigido
     "audit": {
       "score": 9.07,
       "status": "ok|warning|error",
       "auto_applied": [
         {"id": "dup_001", "type": "duplicate_paragraph", "description": "...", "applied": true}
       ],
       "pending_hil": [
         {"id": "omit_001", "type": "omission", "severity": "high", ...patch, ...evidence}
       ],
       "modules": [...],
       "false_positives_removed": 3
     }
   }
   ```

3. **Threshold de auto-apply estrutural:**
   - `confidence ≥ 0.90` + `fix_type == "structural"` → auto-apply
   - `confidence 0.50–0.89` + `fix_type == "structural"` → vai para HIL (caso raro)
   - `fix_type == "content"` → sempre HIL (independente de confidence)

### Fase 2 — Backend: Endpoint unificado de auditoria

**Arquivo:** `audit_unified.py` (já existe, refatorar)

1. **`POST /api/audit-unified/audit`** — retorna auditoria consolidada:
   - Input: `job_id` (carrega tudo do job) ou `raw_content` + `formatted_content`
   - Output: score, auto_applied[], pending_hil[], modules[], markdown_report
   - Deduplicação por fingerprint
   - Classificação automática structural vs content

2. **`POST /api/audit-unified/apply-hil`** — aplica correções HIL aprovadas:
   - Input: `job_id`, `approved_issues[]`, `content`, `raw_content`, `model_selection`
   - Output: `content` corrigido, contagem de aplicações, erros
   - Somente issues de **conteúdo** (estruturais já foram auto-aplicadas)
   - Fallback: se content vier vazio, retorna original

3. **Remover/deprecar endpoints redundantes:**
   - `/api/transcription/apply-revisions` → redirecionar para unified
   - Manter backward compatibility temporária com wrapper

### Fase 3 — Frontend: Aba única "Auditoria"

**Arquivo novo:** `apps/web/src/components/transcription/unified-audit-tab.tsx`

#### Layout da aba:

```
┌─────────────────────────────────────────────────┐
│ 🛡️ Nota de Fidelidade: 9.07/10    Status: ✅ OK │
│ [████████████████████░░] 90.7%                   │
│ Módulos: Preventiva ✅ | Estrutural ✅ | Ref ⚠️   │
├─────────────────────────────────────────────────┤
│                                                   │
│ ── Correções Automáticas (3 aplicadas) ──── [v]  │
│ │ ✅ Duplicata removida: §14 "Ônus da Prova"    │
│ │ ✅ Numeração corrigida: H2 16→17               │
│ │ ✅ Heading renomeado: "Conclusão" → "Pedidos"  │
│ └────────────────────────────────────────────── │
│                                                   │
│ ── Pendentes: Revisão Humana (2 issues) ───────  │
│                                                   │
│ ☐ [ALTA] Omissão: Lei 14.133/2021                │
│   │ RAW: "conforme a lei quatorze mil..."         │
│   │ Formatado: (ausente)                          │
│   │ ┌─ Diff ──────────────────────────┐          │
│   │ │ - (nenhuma referência)           │          │
│   │ │ + Art. 5º da Lei 14.133/2021     │          │
│   │ └─────────────────────────────────┘          │
│   │ Confiança: 87%  |  Fonte: Preventiva         │
│                                                   │
│ ☐ [MÉDIA] Distorção: Tema 1070                    │
│   │ RAW: "tema mil e setenta"                     │
│   │ Formatado: "Tema 1.070 do STF"               │
│   │ ┌─ Diff ──────────────────────────┐          │
│   │ │ - Tema 1.070 do STF              │          │
│   │ │ + Tema 1.070/STF (RE 123.456)    │          │
│   │ └─────────────────────────────────┘          │
│   │ Confiança: 72%  |  Fonte: Preventiva         │
│                                                   │
│ [Selecionar tudo] [Auto-aplicar seguros]          │
│           [ 🤖 Aplicar 2 Correções ]              │
├─────────────────────────────────────────────────┤
│ 📋 Relatório Completo                     [v]    │
│   (markdown colapsável do relatório preventivo)   │
└─────────────────────────────────────────────────┘
```

#### Componentes internos:

1. **`AuditScoreHeader`** — nota, status, módulos (reutiliza `audit-health-bar.tsx` refatorado)
2. **`AutoAppliedSection`** — lista colapsável de correções automáticas (read-only, verde)
3. **`HilIssuesList`** — lista de issues pendentes com:
   - Checkbox de seleção
   - Severidade + tipo colorido
   - Evidência RAW vs Formatado lado a lado
   - **DiffPreview inline** (reutiliza lógica do `diff` library existente)
   - Badge de confiança
   - Botão expandir/colapsar
4. **`AuditReportAccordion`** — markdown do relatório preventivo completo (colapsável)

### Fase 4 — Frontend: Integração na página de transcrição

**Arquivo:** `apps/web/src/app/(dashboard)/transcription/page.tsx`

1. **Remover tabs separadas:**
   - Remove tab "Correções (HIL)" (`value="hil"`)
   - Remove tab "Auditoria" (`value="preventive"`)
   - Remove tab "Qualidade (Resumo)" (`value="quality"`)

2. **Adicionar tab única:**
   ```tsx
   <TabsTrigger value="audit">
     Auditoria {pendingHilCount > 0 && <Badge>{pendingHilCount}</Badge>}
   </TabsTrigger>
   ```

3. **Simplificar estado:**
   - Consolidar `auditIssues`, `preventiveAudit`, `auditSummary` em um único objeto `auditState`
   - Derivar `autoApplied` e `pendingHil` do `auditState`

4. **Fluxo de dados:**
   ```
   Job carregado → payload.audit contém tudo
                     ├─ score, status
                     ├─ auto_applied[] (já aplicadas)
                     └─ pending_hil[] (para HIL)

   Usuário seleciona issues → clica "Aplicar"
                     ↓
   POST /api/audit-unified/apply-hil
                     ↓
   Conteúdo atualizado + issues removidas da lista
   ```

### Fase 5 — Diff Viewer aprimorado

**Arquivo:** Refatorar `audit-issues-panel.tsx` → extrair `DiffViewer` reutilizável

1. **Dois modos de visualização por issue:**
   - **Inline diff** — old (vermelho) / new (verde) lado a lado no card
   - **Expandido** — modal com contexto completo (5 linhas antes/depois)

2. **Para issues de conteúdo:**
   - Mostrar evidência RAW (com highlight do trecho relevante)
   - Mostrar trecho formatado atual
   - Mostrar sugestão de correção como diff
   - Veredito da validação (Confirmado / Falso Positivo Possível)

3. **Para correções auto-aplicadas (log):**
   - Mostrar o que foi corrigido (tipo + descrição breve)
   - Expandível para ver diff completo do que foi feito

### Fase 6 — Testes

1. **Backend tests:**
   - `test_auto_apply_structural.py` — verifica que estruturais são auto-aplicadas
   - `test_unified_audit_endpoint.py` — verifica endpoint consolidado
   - `test_content_hil_only.py` — verifica que conteúdo nunca é auto-aplicado

2. **Frontend tests (se aplicável):**
   - Renderização da aba unificada
   - Seleção e aplicação de HIL
   - Estado de "desatualizado" após aplicação

---

## Regras de Negócio Consolidadas

| Tipo | Auto-apply? | HIL? | Threshold |
|------|-------------|------|-----------|
| Duplicata (seção/parágrafo) | ✅ Sim | Não | confidence ≥ 0.90 |
| Numeração de headings | ✅ Sim | Não | confidence ≥ 0.90 |
| Heading rename (semântico) | ✅ Sim* | Fallback HIL | confidence ≥ 0.90, senão HIL |
| Omissão de conteúdo | ❌ Não | ✅ Sempre | Qualquer |
| Distorção de conteúdo | ❌ Não | ✅ Sempre | Qualquer |
| Alucinação | ❌ Não | ✅ Sempre | Qualquer |
| Referência legal ausente | ❌ Não | ✅ Sempre | Qualquer |
| Autoria (fontes) | ❌ Não | ✅ Sempre | Qualquer |

## Ordem de Implementação

1. **Fase 1** (Backend auto-apply) — base para tudo
2. **Fase 2** (Endpoint unificado) — API limpa para o frontend
3. **Fase 3** (Componente frontend) — UI da aba unificada
4. **Fase 4** (Integração na página) — remove tabs antigas, conecta nova
5. **Fase 5** (Diff viewer) — melhoria visual
6. **Fase 6** (Testes) — validação completa

## Arquivos Principais a Modificar

### Backend
- `apps/api/app/services/transcription_service.py` — auto-apply + payload consolidado
- `apps/api/app/services/audit_pipeline.py` — classificação structural vs content
- `apps/api/app/services/quality_service.py` — threshold de auto-apply
- `apps/api/app/api/endpoints/audit_unified.py` — endpoints refatorados
- `apps/api/app/schemas/audit_unified.py` — schemas atualizados

### Frontend
- **Novo:** `apps/web/src/components/transcription/unified-audit-tab.tsx`
- **Novo:** `apps/web/src/components/transcription/diff-viewer.tsx` (extraído)
- `apps/web/src/app/(dashboard)/transcription/page.tsx` — tabs simplificadas
- `apps/web/src/lib/unified-audit.ts` — tipos atualizados
- `apps/web/src/lib/api-client.ts` — endpoints atualizados

### Testes
- **Novo:** `apps/api/tests/test_auto_apply_structural.py`
- **Novo:** `apps/api/tests/test_unified_audit_endpoint.py`
