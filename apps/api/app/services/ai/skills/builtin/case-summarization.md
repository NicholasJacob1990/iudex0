---
name: case-summarization
description: Sumarização executiva de autos e histórico processual.
triggers: ["resumir processo", "sumario dos autos", "resumo do caso"]
tools_required: ["search_rag", "ask_graph", "verify_citation"]
subagent_model: claude-haiku-4-5
prefer_workflow: false
prefer_agent: true
---

## Instructions
1. Monte linha do tempo dos fatos processuais relevantes.
2. Sintetize pedidos, decisões e próximos marcos.
3. Finalize com riscos e pontos de atenção para estratégia.
