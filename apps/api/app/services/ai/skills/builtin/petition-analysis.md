---
name: petition-analysis
description: Analisa petições jurídicas, estrutura e pedidos principais.
triggers: ["analisar petição", "analise de peticao", "revisar petição"]
tools_required: ["search_rag", "search_jurisprudencia", "verify_citation"]
subagent_model: claude-haiku-4-5
prefer_workflow: false
prefer_agent: true
---

## Instructions
1. Extraia o pedido principal e os fundamentos jurídicos.
2. Liste inconsistências fáticas e lacunas probatórias.
3. Proponha melhorias objetivas de redação e estratégia.
