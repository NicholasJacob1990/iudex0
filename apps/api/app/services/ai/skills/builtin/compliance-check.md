---
name: compliance-check
description: Validação de conformidade normativa e checklist regulatório.
triggers: ["compliance", "conformidade", "checklist regulatorio"]
tools_required: ["search_legislacao", "search_rag", "verify_citation"]
subagent_model: claude-haiku-4-5
prefer_workflow: true
prefer_agent: false
---

## Instructions
1. Construa checklist de requisitos legais aplicáveis.
2. Marque itens atendidos, pendentes e com evidência insuficiente.
3. Informe risco por item (baixo, médio, alto) e recomendação imediata.
