# Neo4j Aura Agent no Iudex — Matriz de Fit + POC recomendada

Data: 2026-02-04

Este documento parte do estado atual do Iudex:

- RAG pipeline com *Graph Enrich* (Stage 9) e backend Neo4j via `Neo4jMVPService`/Cypher.
  - Referência: `apps/api/app/services/rag/pipeline/rag_pipeline.py:2869`
  - Referência: `apps/api/app/services/rag/core/neo4j_mvp.py:2119`
- Workflow LangGraph com roteamento por seção e flags `use_hyde`/`use_graph`.
  - Referência: `apps/api/app/services/ai/langgraph_legal_workflow.py:653`
- Página `/graph` (Next.js) baseada em `@neo4j-nvl/react`, consumindo endpoints `/graph/*`.
  - Referência: `apps/web/src/app/(dashboard)/graph/GraphPageClient.tsx:145`
  - Referência: `apps/api/app/api/endpoints/graph.py:35`

O objetivo aqui é responder: “Aura Agent substitui ou complementa?” e definir uma POC com baixo risco.

---

## 0) Escopos de corpus na página `/graph` (Global × Privado × Local)

No Iudex, a página `/graph` consulta o grafo Neo4j com **trimming** por escopo:

- **Privado (tenant)**: conteúdo do seu usuário/organização (o “seu” corpus). Sempre disponível.
- **Global**: corpus compartilhado (público/curado). A UI controla via toggle **“Incluir corpus global”**.
- **Local**: conteúdo **do caso/material selecionado** (ex.: documentos/caso específico). Por segurança, o backend **não inclui `scope=local` por padrão** para evitar misturar “local de todos os casos”. O `local` só entra quando o usuário ativa **“Filtrar grafo por materiais”** e seleciona **Docs/Casos**.

Esse comportamento é importante para avaliar o Aura Agent: qualquer substituição/complemento precisa manter o mesmo trimming (tenant/global/local) e auditoria.

---

## 1) Matriz “Substitui vs Complementa”

Legenda:
- **Substitui**: faz sentido mover a responsabilidade para Aura Agent (com desativação do caminho atual).
- **Complementa**: usar Aura Agent como *tool* extra (exploração, aceleração, protótipo) sem trocar o core.
- **Não encaixa (agora)**: por requisitos (write-path, trimming, auditoria, custo previsível).

| Componente do Iudex | Hoje (como funciona) | Aura Agent encaixa? | Ganho potencial | Riscos / o que você perde | Recomendação prática |
|---|---|---:|---|---|---|
| **Stage 9: Graph Enrich (RAG pipeline)** | Contexto do grafo como etapa do pipeline (preferindo Neo4jMVP quando disponível). | **Complementa** | Prototipar novas queries/contextos sem deploy do backend. | Governança/auditoria (caixa-preta), custo/latência cloud, e principalmente **trimming multi-tenant** precisa ser garantido. | Manter o Stage 9 no backend. Aura Agent só entra como “consulta auxiliar” e **read-only**. |
| **Graph-first no LangGraph** | Se `use_graph`/`neo4j_only`, tenta paths/contexto antes da busca híbrida. | **Complementa** | Criar um “Graph Analyst Tool” para perguntas ad-hoc (Text2Cypher) quando o roteador detectar que é “pergunta de grafo”. | Determinismo (Text2Cypher), risco de prompt-injection, necessidade de logs. | Integrar como *tool* com **limites e allowlist** (ver POC). |
| **Endpoints /graph/path** | `shortestPath` com trimming por tenant/escopo (via Cypher) no backend. | **Substitui (parcial)** | Deploy rápido de variações de path queries e explicações. | Se a UI chamar Aura direto: RBAC/logs ficam mais difíceis; e query precisa manter `tenant_id`/sigilo. | Substituir só se existir **proxy backend** mantendo RBAC + auditoria. Caso contrário, manter no backend. |
| **/graph/semantic-neighbors** | Co-ocorrência em chunks + amostras de contexto, com trimming por tenant/escopo. | **Substitui (parcial)** | Acelera iteração e tuning de heurísticas/queries. | Mesmo risco de RBAC/logs e consistência com “sigilo”. | Bom candidato de POC **read-only**. Preferir proxy. |
| **/graph/export** (visualização NVL) | Exporta nós/arestas e mistura entidades + Facts (opcional), com filtros por materiais. | **Não encaixa (agora)** | Aura Agent pode expor queries, mas a montagem do payload e heurísticas de UI estão no Iudex. | Você perde controle fino de shape/dedup/tuning do payload. | Mantenha no backend. Use Aura para **consultas auxiliares** que alimentam export (se necessário). |
| **Ingestão KG** (`/graph/add-from-rag`, facts, memória) | Write-path de entidades/facts/consulta/memória (Neo4j). | **Não encaixa (agora)** | — | Aura Agent tende a ser mais “consulta” do que “ETL/ingest” (além de riscos de permissão). | Não migrar. Mantenha ingestão no backend. |
| **CogRAG / Memória Cognitiva** | Persistência em Neo4j via Cypher controlado pelo app (com IDs/tenant). | **Não encaixa (agora)** | — | Segurança + consistência transacional + PII. | Não migrar. |
| **Observabilidade / Audit / HIL** | Você controla logs/eventos do pipeline e decisões. | **Complementa** | Pode acelerar exploração, mas só se conseguir log estruturado. | Você pode “perder” rastreabilidade se não encapsular. | Se usar Aura Agent, **encapsular via proxy** que loga request/response. |

**Resumo executivo**:
- Aura Agent é mais valioso como **camada de exploração + prototipagem + endpoints read-only**.
- O “core” do Iudex (RAG pipeline, ingestão, HIL/audit, trimming) **não deve sair** do backend.

---

## 2) Candidatos ideais de POC (baixo risco, alto sinal)

Foque em endpoints read-only com alto uso e bem definidos:

1) **`GET /graph/path`** (caminho entre conceitos)
   - Referência: `apps/api/app/api/endpoints/graph.py:898`
   - Sucesso da POC = conseguir a mesma qualidade de caminho + mesmas restrições de acesso.

2) **`GET /graph/semantic-neighbors/{entity_id}`** (vizinhos semânticos por co-ocorrência)
   - Referência: `apps/api/app/api/endpoints/graph.py:1084`
   - Sucesso da POC = latência/qualidade aceitável + mesmos filtros de escopo/sigilo.

3) **`POST /graph/lexical-search`** (busca por entidades no grafo)
   - Referência: `apps/api/app/api/endpoints/graph.py:1281`
   - Sucesso da POC = “encontra o que o usuário procura” com baixa fricção.

Evite na POC:
- `POST /graph/add-from-rag` e qualquer write-path.
- `GET /graph/export` (shape de payload é acoplado à UI).

---

## 3) Desenho de integração recomendado (para não perder governança)

**Não** exponha Aura Agent diretamente ao browser.

Preferência: **Backend proxy “AuraAgentGateway”** no Iudex:

- Frontend → chama `apps/api` (como hoje)
- `apps/api` → chama Aura Agent (REST) com credenciais server-side
- `apps/api` → aplica:
  - RBAC / tenant context (quem é o usuário, o que pode ver)
  - **allowlist** de queries/ações (especialmente se tiver Text2Cypher)
  - logs/auditoria (request_id, usuário, latência, custo estimado)

Isso preserva seu modelo de segurança e evita “shadow APIs”.

---

## 4) POC de 1–2 semanas (checklist objetivo)

### Semana 1 — “Read-only parity”

- [ ] Provisionar AuraDB de teste (somente dados públicos / anonimizados).
- [ ] Replicar schema mínimo necessário (Entity/Chunk/Document e relacionamentos relevantes).
- [ ] Implementar 2 endpoints via Aura Agent (templates):
  - [ ] path
  - [ ] semantic-neighbors
- [ ] Criar 1 endpoint proxy no `apps/api` para cada um (mesma interface do Iudex).
- [ ] Criar harness de comparação:
  - [ ] Dado `(source_id,target_id)`, comparar se “encontra caminho” e se o caminho é plausível.
  - [ ] Dado `entity_id`, comparar top vizinhos (sobreposição e coerência).

### Semana 2 — “Text2Cypher com guardrails” (opcional)

- [ ] Implementar uma *tool* “Ask the Graph” (Text2Cypher) **com allowlist**:
  - apenas `MATCH/RETURN`, sem `CREATE/MERGE/DELETE`
  - limitar labels/relTypes acessáveis
  - limitar `LIMIT`, `max_hops`, tempo máximo
- [ ] Adicionar logs completos: input do usuário, cypher gerado, parâmetros, contagem de nós retornados.

---

## 5) Métricas de decisão (go/no-go)

Qualidade:
- Taxa de sucesso (HTTP 2xx) por endpoint
- “Paridade funcional”: mesma semântica de trimming/sigilo/escopo
- Overlap qualitativo (amostras revisadas por humano): caminhos e vizinhos fazem sentido?

Performance:
- p50 / p95 latência (comparar com backend atual)
- Throughput sob carga (ex.: 20 rps para path/neighbor)

Custo:
- custo por 1k requests por endpoint
- custo marginal de spikes (se houver)

Operação:
- tempo para iterar uma nova query (do “quero X” até “rodando na UI”)
- facilidade de debugar incidentes (logs suficientes?)

Se **qualidade e RBAC** não forem equivalentes, a recomendação é manter Aura Agent apenas como “explore tool” interna.
