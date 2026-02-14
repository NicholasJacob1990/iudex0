---
name: contract-review
description: Revisão contratual com foco em risco e cláusulas críticas.
triggers: ["revisar contrato", "analise contratual", "clausula abusiva"]
tools_required: ["search_legislacao", "search_rag", "verify_citation"]
subagent_model: claude-haiku-4-5
prefer_workflow: false
prefer_agent: true
---

## Instructions
1. Identifique cláusulas de risco (responsabilidade, rescisão, multa, foro).
2. Aponte termos ambíguos e ausência de salvaguardas.
3. Sugira redação alternativa objetiva para cada ponto crítico.
