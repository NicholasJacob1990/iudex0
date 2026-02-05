# Harvey AI vs Iudex — Relatório Comparativo Completo

> Gerado em 2026-02-02 com base em pesquisa extensiva no site, documentação, help center e blog do Harvey AI.

---

## 1. VAULT (Harvey) vs CORPUS (Iudex)

### 1.1 Armazenamento e Limites

| Recurso | Harvey Vault | Iudex Corpus | Gap |
|---------|-------------|-------------|-----|
| Arquivos por projeto | 100.000 | 10.000 (max_documents) | Harvey 10x maior |
| Storage por projeto | 100 GB | Sem limite definido | Definir limite |
| Tamanho max por arquivo | 100 MB | 10 MB | Harvey 10x maior |
| Formatos suportados | 30+ (PDF, DOCX, XLSX, PPTX, EML, MSG, código) | PDF, DOCX, TXT, XLSX, PPTX | Falta EML/MSG/código |
| Excel: limite de células | 1M células | N/A | Funcionalidade ausente |

### 1.2 Review Tables (Harvey) vs Review Tables (Iudex)

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Tipos de coluna | 7 (verbatim, free response, classification, date, currency, number, custom) | 6 (text, date, currency, number, verbatim, boolean) | Falta: free response, custom |
| Max colunas | 50 | Sem limite definido | OK |
| Workflows one-click | Sim (Merger, SPA, Leases, LPA, Court Opinions) | Nao | Gap P1 |
| Recall dos workflows | 96-99% | N/A | - |
| Verificacao por celula | Summary + source language exata | Sim (results JSON) | Melhorar UX |
| Edicao inline de celulas | Sim | Nao | Gap P2 |
| Export | Excel, Word, CSV com cores | Nao implementado | Gap P1 |
| Query natural language sobre tabela | Sim (Ask over Review) | Nao | Gap P2 |
| Change tracking em celulas | Sim | Nao | Gap P3 |

### 1.3 Organizacao de Arquivos

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Hierarquia de pastas | Sim, com file_paths | Flat (document_ids) | Gap P2 |
| Views | Grid, List, Grouped, Flat | Lista simples | Gap P2 |
| Sorting | Recently viewed, newest, oldest, alphabetical | Por data criacao | Gap P2 |
| Busca server-side | Sim, otimizada | Via API search | OK |
| Tags/metadados | Sim | metadata JSON | OK |
| Deteccao de duplicatas | Sim | Nao | Gap P3 |

### 1.4 Knowledge Bases vs Corpus Projects

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Knowledge Bases separadas | Sim (is_knowledge_base flag) | Sim (is_knowledge_base) | OK - Paridade |
| Escopo (personal/org) | Sim | Sim (ProjectScope enum) | OK - Paridade |
| Compartilhamento | Granular (view/edit/admin) | Sim (CorpusProjectShare) | OK - Paridade |
| Retencao configuravel | Sim | Sim (retention_days) | OK - Paridade |
| Collection name unica | N/A | Sim (collection_name) | OK |
| Contadores (docs/chunks/storage) | Sim | Sim | OK - Paridade |

### 1.5 Integrações DMS

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| iManage | Sim (OAuth, bi-direcional) | Nao | Gap P3 |
| SharePoint | Sim (sync) | Basico (DMS connector) | Gap P3 |
| Google Drive | Sim | Basico (DMS connector) | Gap P3 |
| NetDocuments | Sim | Nao | Gap P3 |

### 1.6 Performance

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Upload 10k arquivos | ~2 min (89% melhoria) | N/A (nao testado) | Otimizar |
| Memoria | 90% reducao (server-side) | Client-side | Gap P2 |
| Prefetching preditivo | Sim | React Query prefetch | Parcial |
| Web workers para upload | Sim | Nao | Gap P2 |

---

## 2. PLAYBOOKS (Harvey) vs PLAYBOOKS (Iudex)

### 2.1 Estrutura de Regras

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Classificacao 3 niveis | Acceptable / Needs Review / Not Acceptable | Sim (acceptable/needs_review/unacceptable) | OK - Paridade |
| Standard Position | Sim | Sim (standard_position) | OK - Paridade |
| Fallback Position | Sim | Sim (fallback_position) | OK - Paridade |
| Guidance/contexto | Sim (por regra) | Parcial | Gap P2 |
| Messaging para clientes | Sim | Nao | Gap P3 |

### 2.2 Criacao de Playbooks

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Criar do zero | Sim | Sim | OK - Paridade |
| Upload de playbook existente | Sim (qualquer formato, AI converte) | Sim (import JSON/Excel) | Parcial |
| Extrair de contratos passados | Sim ("Winning Language") | Nao | Gap P1 |
| AI auto-gera regras | Sim | Nao | Gap P1 |
| Templates pre-construidos | Nao mencionado | Nao | - |

### 2.3 Execucao de Playbooks

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Revisao automatica | Sim (analisa cada clausula) | Sim (via LangGraph) | OK - Paridade |
| Redlines sugeridos | Sim (um clique ou batch) | Sim (suggested_changes) | OK - Paridade |
| Comment bubbles | Sim (auto-gerados) | Nao | Gap P2 |
| Mark as Reviewed | Sim | Nao | Gap P2 |
| Filtro por tipo de flag | Sim | Nao | Gap P2 |
| Deteccao de TODAS mudancas | Sim (alem das regras do playbook) | Nao | Gap P2 |

### 2.4 Integracoes

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Word Add-In | Sim (nativo) | Em desenvolvimento | Em progresso |
| Execucao web | Via Word | Sim (web app) | OK |
| Export Excel | Sim (.xlsx com cores) | Sim (export implementado) | OK - Paridade |
| Compartilhamento externo | Sim (Shared Spaces, Guest Accounts) | Sim (guest accounts) | OK - Paridade |

### 2.5 Versao e Permissoes

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Version history | Sim (quem editou, quando) | Parcial (updated_at) | Gap P2 |
| Controle de acesso | Granular (view/edit/admin) | Sim (permission enforcement) | OK - Paridade |
| Audit trail | Sim | Nao | Gap P3 |
| Perspectiva de parte | Sim (qual lado voce representa) | Nao | Gap P3 |

### 2.6 Performance

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Velocidade | 5x mais rapido (2025) | N/A | - |
| Sugestoes geradas | 4.5x mais sugestoes | N/A | - |
| Reducao de tempo | 60% (Talanx case) | N/A | - |
| 95%+ redlines automaticos | Sim (Harvey interno) | N/A | - |

---

## 3. WORKFLOWS (Harvey) vs Iudex

### 3.1 Workflow Builder

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Builder visual no-code | Sim (4 tipos de blocos) | Nao | Gap P3 |
| Linguagem natural para workflow | Sim | Nao | Gap P3 |
| Prompt chaining | Sim (steps backend invisiveis) | Nao | Gap P3 |
| Branching condicional | Sim | Nao | Gap P3 |
| @-mentions em prompts | Sim | Nao | Gap P3 |
| Optional steps | Sim | Nao | Gap P3 |
| Workflows criados | 19.000+ | 0 | - |

> **Nota**: O Workflow Builder do Harvey e uma funcionalidade completamente separada que nao temos equivalente. Considerar para roadmap futuro.

---

## 4. UI/UX COMPARATIVO

### 4.1 Design System

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Tokens semanticos | Sim (role-based: foreground-base) | Tailwind utility classes | Diferente abordagem |
| Componentes | Shadcn + custom | Shadcn/ui | OK - Similar |
| Dark mode | Em preparacao (tokens ready) | Sim (darkMode: class) | OK |
| Cursor AI rules | Sim (auto-use novos tokens) | Nao | Considerar |
| Linter rules para tokens | Sim | Nao | Considerar |

### 4.2 Navegacao

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Sidebar global | Sim (5 areas principais) | Sim | OK - Paridade |
| Global search (Cmd+K) | Sim | Sim (Command Palette) | OK - Paridade |
| Homepage personalizada | Sim (sugestoes, recent work) | Dashboard basico | Gap P2 |
| Busca cross-feature | Sim (vaults, threads, workflows) | Parcial | Gap P2 |

### 4.3 Mobile

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| App iOS nativo | Sim (iOS 18.2+) | Nao | Gap P3 |
| App Android nativo | Sim | Nao | Gap P3 |
| Voice input | Sim | Nao | Gap P3 |
| Scan & Upload | Sim (camera) | Nao | Gap P3 |

### 4.4 Colaboracao

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Shared Spaces | Sim (firmas + clientes) | Guest accounts | Parcial |
| Guest Accounts | Sim (sem precisar ser cliente) | Sim (implementado) | OK - Paridade |
| Permissions granulares | view/comment/run/edit | view/edit/admin | OK - Similar |
| Audit Logs API | Sim (usuario, timestamp, IP, acao) | Nao | Gap P3 |

---

## 5. API COMPARATIVA

### 5.1 Harvey API vs Iudex API

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| Vault/Corpus CRUD | Sim (REST) | Sim (REST) | OK - Paridade |
| Upload com file_paths | Sim | Sim | OK - Paridade |
| Rate limiting | 10 req/min (Vault) | Sim (configuravel) | OK - Paridade |
| Paginacao | page/per_page | Sim | OK - Paridade |
| Auth | Bearer JWT | Bearer JWT | OK - Paridade |
| Audit Logs endpoint | Sim | Nao | Gap P3 |

---

## 6. SEGURANCA

| Recurso | Harvey | Iudex | Gap |
|---------|--------|-------|-----|
| SOC2 Type II | Sim | Nao | Futuro |
| ISO 27001 | Sim | Nao | Futuro |
| GDPR/LGPD | Sim (GDPR) | Parcial (LGPD) | Adequar |
| SAML SSO | Sim | Nao (JWT simples) | Gap P2 |
| IP allow-listing | Sim | Nao | Gap P3 |
| Encryption at rest | Sim | Sim (Fernet) | OK |
| Data isolation | Logica por firma | Por organizacao | OK - Similar |
| In-region storage | Sim (EU, US, AU) | Single region | Gap P3 |

---

## 7. PRIORIDADES DE IMPLEMENTACAO

### P0 - Ja Implementado (Paridade)
- [x] Knowledge Bases com flag is_knowledge_base
- [x] Compartilhamento com permissoes (view/edit/admin)
- [x] Review Tables com 6 tipos de coluna
- [x] Classificacao 3 niveis (acceptable/needs_review/unacceptable)
- [x] Standard + Fallback positions
- [x] Export de playbooks (JSON/Excel)
- [x] Guest accounts
- [x] Rate limiting
- [x] Retencao configuravel
- [x] Corpus ↔ Chat integracao
- [x] Playbook ↔ Minuta integracao
- [x] Prefetching com React Query
- [x] PPTX/XLSX text extraction
- [x] Verbatim + Source Provenance

### P1 - Alta Prioridade (Gaps criticos para competitividade)
- [ ] **Review Table Export** com Excel/CSV e cores de status
- [ ] **Workflows one-click** para tipos comuns de contratos brasileiros
- [ ] **Extrair playbook de contratos passados** ("Winning Language")
- [ ] **AI auto-geracao de regras** a partir de upload de playbook

### P2 - Media Prioridade (Melhorias significativas de UX)
- [ ] Edicao inline de celulas em Review Tables
- [ ] Query natural language sobre Review Tables
- [ ] Hierarquia de pastas no Corpus
- [ ] Views multiplas (Grid/List/Grouped)
- [ ] Homepage personalizada com sugestoes
- [ ] Comment bubbles auto-gerados em Playbooks
- [ ] Mark as Reviewed em Playbooks
- [ ] Filtro por tipo de flag
- [ ] Version history detalhado
- [ ] SAML SSO
- [ ] Server-side processing para grandes volumes

### P3 - Baixa Prioridade (Diferenciais futuros)
- [ ] Workflow Builder visual (no-code)
- [ ] Integracoes DMS profundas (iManage, NetDocuments)
- [ ] Mobile apps nativos (iOS/Android)
- [ ] Voice input
- [ ] Audit Logs API
- [ ] Perspectiva de parte em playbooks
- [ ] Messaging para clientes
- [ ] Change tracking em celulas
- [ ] Deteccao de duplicatas
- [ ] IP allow-listing
- [ ] In-region storage

---

## 8. METRICAS DE REFERENCIA (Harvey)

| Metrica | Valor |
|---------|-------|
| Usuarios | 100.000+ profissionais juridicos |
| Clientes | 1.000+ firmas |
| Queries diarias | 200K+ |
| Arquivos processados | 1.3M+ |
| Adocao mensal | 92% |
| Horas economizadas/mes | 20+ por profissional |
| ARR | ~$100M (estimativa) |
| Pricing | ~$1.000-1.200/usuario/mes |
| Features lancadas (2025) | 120+ |

---

## 9. CONCLUSAO

### Onde Iudex tem Paridade
O Iudex ja implementa os fundamentos competitivos: knowledge bases, review tables, playbooks com classificacao 3 niveis, compartilhamento granular, guest accounts, e integracao corpus↔chat. A arquitetura esta solida.

### Onde Harvey se Destaca
1. **Escala**: 100k docs vs 10k, workflows one-click com 96-99% recall
2. **UX Polish**: Edicao inline, query em linguagem natural sobre tabelas, views multiplas
3. **Ecossistema**: Word Add-In maduro, mobile apps, DMS integrations profundas
4. **Workflow Builder**: Funcionalidade unica de automacao visual sem equivalente no Iudex
5. **Performance**: Upload otimizado com web workers, server-side processing

### Proximos Passos Recomendados
Focar nos itens P1 para atingir competitividade funcional, especialmente:
1. Export de Review Tables com formatacao
2. Workflows pre-construidos para contratos brasileiros (diferencial local)
3. Geracao automatica de playbooks a partir de contratos existentes

O diferencial do Iudex deve ser a **especializacao no mercado juridico brasileiro** (LGPD, tipos de contratos locais, integracao com PJe, legislacao brasileira), algo que Harvey nao oferece.
