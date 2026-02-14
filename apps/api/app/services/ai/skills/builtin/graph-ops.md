---
name: graph-ops
description: Consultas ao grafo/GDS via ask_graph (sem poluir UI) com seleção de operação por intenção e guardrails de custo.
triggers: ["grafo", "neo4j", "gds", "centralidade", "comunidades", "similaridade"]
tools_required: ["ask_graph"]
prefer_workflow: false
prefer_agent: true
---

## Instructions
Você está em modo de análise do grafo jurídico. Use **apenas operações tipadas** via `ask_graph`.

### Regras
- Nunca invente IDs. Para qualquer entidade, comece com `ask_graph(operation="search")` e peça confirmação se houver ambiguidade.
- Prefira operações básicas (search/neighbors/path/count) antes de rodar GDS quando possível.
- Evite rodar mais de 1 algoritmo GDS pesado por turno sem o usuário pedir explicitamente.
- Se o contexto indicar **MODO GRAFO (UI)**, não realize escrita no grafo (`link_entities`, `recompute_co_menciona`); oriente o usuário a usar `/link`.

### Seleção rápida (intenção -> operation)
- Vizinhos/relacionados: `neighbors` (ou `related_entities` se o usuário pedir relações reais do grafo)
- Caminho/como conecta/cadeia: `path` (ou `audit_graph_chain` quando o usuário pedir auditoria/evidências)
- Comunidades/clusters: `leiden` (preferir) ou `community_detection`
- Centralidade:
  - “mais citados/conectados”: `degree_centrality` ou `discover_hubs`
  - “ponte/intermediários”: `betweenness_centrality` e/ou `bridges`/`articulation_points`
- Similaridade:
  - lista de similares: `node_similarity` (ou `knn`)
  - score entre 2 nós: `adamic_adar`

