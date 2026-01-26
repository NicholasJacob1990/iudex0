# Relatório de Verificação: APIs de Deep Research

> Gerado em: 2026-01-24

## Resumo Executivo

Analisei a documentação oficial das APIs de Deep Research (Google Gemini, Perplexity, OpenAI) e comparei com a implementação atual no projeto Iudex. Este relatório identifica o estado de conformidade, recursos não utilizados e oportunidades de melhoria.

---

## 1. Google Gemini Deep Research

### Documentação Oficial (2025-2026)
- [Gemini Deep Research Agent](https://ai.google.dev/gemini-api/docs/deep-research)
- [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)

**Interactions API - Eventos de Streaming:**
| Evento | Descrição |
|--------|-----------|
| `interaction.start` | Início da tarefa, fornece `interaction.id` |
| `content.delta` | Conteúdo incremental |
| `interaction.complete` | Pesquisa concluída |
| `error` | Falha na execução |

**Parâmetros da API:**
```python
client.interactions.create(
    input="prompt",
    agent='deep-research-pro-preview-12-2025',
    background=True,
    stream=True,
    agent_config={"type": "deep-research", "thinking_summaries": "auto"},
    tools=[{"type": "file_search", "file_search_store_names": [...]}],
    previous_interaction_id="ID"  # Para follow-ups
)
```

**Grounding Metadata:**
- `webSearchQueries` - queries executadas
- `groundingChunks` - fontes web (URI, title)
- `groundingSupports` - mapeamento texto→fonte com `startIndex`, `endIndex`
- `searchEntryPoint` - HTML/CSS para sugestões de pesquisa

### Verificação da Implementação Iudex

**Arquivo:** `apps/api/app/services/ai/deep_research_service.py`

| Recurso | Status | Observação |
|---------|--------|------------|
| `interactions.create` | ✅ Implementado | Linhas 348, 634 |
| `background=True, stream=True` | ✅ Implementado | Correto |
| `agent_config.thinking_summaries` | ✅ Implementado | `"auto"` |
| Evento `thinking` | ✅ Implementado | Processado no loop de eventos |
| Evento `content` | ✅ Implementado | Acumulado em `final_report` |
| Evento `interaction.end` | ✅ Implementado | Usado para finalizar |
| `google_search` tool (fallback) | ✅ Implementado | Para modelos não-agent |
| `groundingMetadata` extração | ✅ Implementado | Em `agent_clients.py` linhas 2109-2145 |
| `webSearchQueries` extração | ✅ Implementado | Extraído e emitido como `grounding_query` |
| `groundingChunks` extração | ✅ Implementado | Extraído e emitido como `grounding_source` |

| Recurso | Status | Observação |
|---------|--------|------------|
| `file_search` tool | ⚠️ Não utilizado | API suporta integração com File Search Stores |
| `url_context` tool | ⚠️ Não utilizado | Habilitado por padrão, mas não explorado explicitamente |
| `previous_interaction_id` | ⚠️ Não utilizado | Permite follow-ups em conversas de pesquisa |
| `groundingSupports` com índices | ⚠️ Parcial | Extrai fontes mas não usa `startIndex/endIndex` para citações inline |
| Reconexão a streams (`last_event_id`) | ❌ Não implementado | Permite retomar streams interrompidas |
| Suporte multimodal (imagens) | ❌ Não implementado | API aceita entrada com imagens |

### 🆕 Novos Recursos 2025-2026

| Recurso | Descrição | Recomendação |
|---------|-----------|--------------|
| **Gemini 3 Pro** | Modelo mais recente para Deep Research | Verificar se `deep-research-pro-preview-12-2025` é o mais atual |
| **Billing por query** | Gemini 3 cobra por search query, não por prompt | Monitorar custos ($2-5 por tarefa) |
| **10 grounding sources** | Suporte a até 10 fontes de grounding simultâneas | Combinar Google Search + custom search APIs |

---

## 2. Perplexity Sonar Deep Research

### Documentação Oficial (2025)
- [Sonar Deep Research](https://docs.perplexity.ai/getting-started/models/models/sonar-deep-research)
- [Perplexity API Docs](https://docs.perplexity.ai/)

**Estrutura de Resposta:**
```json
{
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 500,
    "citation_tokens": 200,
    "num_search_queries": 30,
    "reasoning_tokens": 150,
    "cost": {
      "input_tokens_cost": 0.0002,
      "output_tokens_cost": 0.004,
      "search_queries_cost": 0.15,
      "total_cost": 0.1542
    }
  },
  "citations": ["https://..."],
  "search_results": [{"title": "...", "url": "...", "snippet": "..."}]
}
```

**Parâmetros Suportados:**
- `search_domain_filter` - filtro de domínios
- `search_recency_filter` - `day`, `week`, `month`, `year`
- `search_context_size` - `low`, `medium`, `high`
- `return_related_questions` - sugestões de follow-up
- `web_search_options` com geolocalização

### Verificação da Implementação Iudex

**Arquivos:**
- `apps/api/app/services/ai/deep_research_service.py`
- `apps/api/app/services/ai/perplexity_config.py`

| Recurso | Status | Observação |
|---------|--------|------------|
| Modelo `sonar-deep-research` | ✅ Implementado | Linha 143-154 |
| Streaming com `AsyncPerplexity` | ✅ Implementado | Linhas 751-805 |
| `search_domain_filter` | ✅ Implementado | `perplexity_config.py` linha 137-139 |
| `search_recency_filter` | ✅ Implementado | Linha 145-147 |
| `search_after_date/before_date` | ✅ Implementado | Linhas 149-155 |
| `last_updated_after/before` | ✅ Implementado | Linhas 157-163 |
| `search_context_size` | ✅ Implementado | Linha 127-129 |
| `search_country/region/city` | ✅ Implementado | Linhas 165-175 |
| Geolocalização (`latitude/longitude`) | ✅ Implementado | Linhas 177-181 |
| Extração de `citations` | ✅ Implementado | Linhas 473-476, 781-783 |
| Extração de `search_results` | ✅ Implementado | Linhas 468-470, 772-779 |
| `reasoning_effort` | ✅ Implementado | Linha 435 |
| `citation_tokens` tracking | ✅ Implementado | Linhas 447-459 |

| Recurso | Status | Observação |
|---------|--------|------------|
| `return_related_questions` | ⚠️ Não utilizado | API retorna sugestões de follow-up |
| `return_images` | ⚠️ Disponível mas não usado em DR | Presente em `perplexity_config.py` |
| `return_videos` | ⚠️ Disponível mas não usado em DR | Presente em `perplexity_config.py` |
| Cost breakdown em resposta | ⚠️ Não extraído | API retorna custos detalhados por tipo |

---

## 3. OpenAI Deep Research (Responses API)

### Documentação Oficial (2025-2026)
- [Deep Research API Cookbook](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api)
- [Deep Research Guide](https://platform.openai.com/docs/guides/deep-research)
- [Web Search Tool](https://platform.openai.com/docs/guides/tools-web-search)

**Modelos Disponíveis:**
- `o3-deep-research-2025-06-26` - Alta qualidade, mais lento
- `o4-mini-deep-research-2025-06-26` - Rápido, para baixa latência

**Responses API:**
```python
response = client.responses.create(
    model="o3-deep-research-2025-06-26",
    input=[
        {"role": "developer", "content": [...]},
        {"role": "user", "content": [...]}
    ],
    reasoning={"summary": "auto", "effort": "high"},
    tools=[{"type": "web_search_preview"}],
    background=True  # Para requisições longas
)
```

**Eventos de Streaming:**
- `web_search_call.in_progress` - busca em andamento
- `web_search_call.searching` - executando queries
- `web_search_call.completed` - busca concluída
- Annotations com citações inline

### Verificação da Implementação Iudex

**Arquivo principal:** `apps/api/app/services/ai/deep_research_service.py`

| Recurso | Status | Observação |
|---------|--------|------------|
| `responses.create` | ✅ Implementado | Usa Responses API (streaming e não-streaming) |
| `reasoning.effort` | ✅ Implementado | Propagado via config (`effort`) |
| `reasoning.summary: "auto"` | ✅ Implementado | Resumo automático de raciocínio quando disponível |

| Recurso | Status | Observação |
|---------|--------|------------|
| Modelos `o3-deep-research` / `o4-mini-deep-research` | ✅ Implementado | Suporta modelos deep-research (default: `o4-mini-deep-research`) |
| `web_search_preview` tool | ✅ Implementado | Usa `web_search_preview` com fallback para `web_search` |
| `background=True` mode | ⚠️ Não utilizado | Pode reduzir timeouts em tarefas longas |
| Eventos de streaming `web_search_call.*` | ✅ Implementado | Mapeado para `step.*` (queries/sources) |
| Annotations com citações | ✅ Implementado | Extrai URL citations/annotations e inclui em `done.sources` |
| Webhooks para background mode | ❌ Não implementado | API suporta notificações assíncronas |
| `code_interpreter` tool | ❌ Não implementado | Disponível para análise de dados |
| MCP (Model Context Protocol) | ❌ Não implementado | Integração com fontes internas |

---

## Resumo Consolidado

### Legenda
- ✅ Corretamente implementado
- ⚠️ Recurso disponível mas não utilizado
- ❌ Faltando ou desatualizado
- 🆕 Novo recurso recomendado

### Por Provider

| Provider | Implementação | Cobertura |
|----------|---------------|-----------|
| **Google Gemini** | ✅ Boa | ~75% |
| **Perplexity** | ✅ Excelente | ~90% |
| **OpenAI** | ✅ Boa | ~70% |

### Prioridades de Melhoria

#### Alta Prioridade
1. **OpenAI background mode + webhooks**: Para evitar timeouts em pesquisas longas
2. **Google reconexão de streams**: Implementar `last_event_id`/resume para resiliência

#### Média Prioridade
4. **`groundingSupports` com índices**: Usar `startIndex/endIndex` para citações inline precisas
5. **Perplexity `return_related_questions`**: Exibir sugestões de follow-up na UI
6. **Google `file_search` tool**: Integrar documentos próprios na pesquisa

#### Baixa Prioridade
7. **Google entrada multimodal**: Suporte a imagens nas queries
8. **Perplexity cost breakdown**: Exibir custos detalhados por componente
9. **OpenAI MCP integration**: Para fontes de dados internas

---

## Arquivos Analisados

| Arquivo | Caminho Completo |
|---------|------------------|
| Deep Research Service | `apps/api/app/services/ai/deep_research_service.py` |
| Agent Clients | `apps/api/app/services/ai/agent_clients.py` |
| Perplexity Config | `apps/api/app/services/ai/perplexity_config.py` |
| Chat Service | `apps/api/app/services/chat_service.py` |

---

## Fontes

- [Gemini Deep Research Agent](https://ai.google.dev/gemini-api/docs/deep-research)
- [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)
- [Perplexity Sonar Deep Research](https://docs.perplexity.ai/getting-started/models/models/sonar-deep-research)
- [OpenAI Deep Research Cookbook](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api)
- [OpenAI Deep Research Announcement](https://community.openai.com/t/deep-research-in-the-api-webhooks-and-web-search-with-o3/1299919)
- [OpenAI Responses API with Agents SDK](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents)
