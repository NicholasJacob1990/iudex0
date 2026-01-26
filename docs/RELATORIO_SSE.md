# Relatório: Melhores Práticas SSE para Chat com IA vs. Implementação Iudex

> Gerado em: 2026-01-24

## Resumo Executivo

Após pesquisa das melhores práticas atuais (2025-2026) para streaming SSE em aplicações de chat com IA e análise dos arquivos do projeto Iudex, apresento abaixo uma comparação detalhada.

---

## 1. Padrões de Eventos SSE

### Melhores Práticas da Indústria

Segundo a documentação do [AI SDK da Vercel](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) e [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses-streaming):

- **Eventos granulares com padrão start/delta/end:**
  - `text-start`, `text-delta`, `text-end`
  - `reasoning-start`, `reasoning-delta`, `reasoning-end`
  - `tool-input-start`, `tool-input-delta`, `tool-input-available`

- **Tipos de eventos recomendados:**
  - `token/text` - conteúdo incremental
  - `thinking/reasoning` - raciocínio da IA
  - `tool_use/tool_call` - chamadas de ferramentas
  - `error` - erros durante streaming
  - `done/complete` - finalização
  - `meta/status` - metadados e progresso

### Implementação Iudex

**Arquivo:** `apps/api/app/services/chat_service.py`

```python
# Tipos de eventos implementados:
yield {"type": "token", "model": model_id, "delta": str(delta)}
yield {"type": "thinking", "model": model_id, "delta": str(delta)}
yield {"type": "done", "model": model_id, "full_text": full_response}
yield {"type": "error", "model": model_id, "error": str(e)}
yield {"type": "meta", "phase": "answer_start", "t": timestamp}
yield {"type": "step.start", ...}
yield {"type": "step.done", "step_id": ...}
yield {"type": "search_done", ...}
yield {"type": "research_done", ...}
```

### Avaliação

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Eventos de token/texto | ✅ Bem implementado | `type: "token"` com delta |
| Eventos de thinking | ✅ Bem implementado | `type: "thinking"` separado |
| Eventos de erro | ✅ Bem implementado | `type: "error"` com mensagem |
| Evento de conclusão | ✅ Bem implementado | `type: "done"` com full_text |
| Eventos de steps/progress | ✅ Bem implementado | `step.start`, `step.done` |
| Eventos de tool_use | ⚠️ Parcial | Não vi eventos específicos de tool calls |
| Padrão start/delta/end | ⚠️ Parcial | Usa delta, mas sem start/end explícitos |

---

## 2. Estrutura de Payloads JSON

### Melhores Práticas

Segundo [Speakeasy OpenAPI](https://www.speakeasy.com/openapi/content/server-sent-events) e [OpenAI](https://platform.openai.com/docs/api-reference/responses-streaming):

```json
// OpenAI Responses API
{"type":"response.output_text.delta","delta":"Hello"}
{"type":"response.reasoning.delta","delta":"Thinking..."}

// AI SDK Vercel
{"type":"text-delta","textDelta":"Hello","textBlockId":"block_123"}
{"type":"reasoning-delta","reasoningDelta":"...","reasoningBlockId":"..."}
```

### Implementação Iudex

```python
# chat_service.py
{"type": "token", "model": model_id, "delta": str(delta)}
{"type": "thinking", "model": model_id, "delta": str(delta)}
{"type": "done", "model": model_id, "full_text": full_response, "thinking": full_thinking}
```

### Avaliação

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Estrutura consistente | ✅ Bem implementado | Todos eventos têm `type` e dados relevantes |
| Identificador de modelo | ✅ Excelente | Inclui `model` em cada evento |
| Serialização JSON | ✅ Bem implementado | `json.dumps()` correto |
| IDs únicos para blocos | ⚠️ Faltando | Não há `blockId` ou `textBlockId` para rastreamento |
| Metadados de timing | ✅ Parcial | Tem `t` em alguns eventos (meta) |

---

## 3. Backpressure e Flow Control

### Melhores Práticas

Segundo [Medium - SSE Comprehensive Guide](https://medium.com/@moali314/server-sent-events-a-comprehensive-guide-e4b15d147576):

- **Buffering adaptativo** no servidor
- **Rate limiting** para eventos de alta frequência
- **Event batching** para reduzir overhead
- SSE não suporta backpressure nativo do cliente - usar TCP flow control

### Implementação Iudex

```python
# chat_service.py
yield {"type": "token", "model": model_id, "delta": str(delta)}
await asyncio.sleep(0)  # Yield para event loop
```

### Avaliação

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Async/await correto | ✅ Bem implementado | Usa `async for` e `await asyncio.sleep(0)` |
| Event batching | ⚠️ Parcial | Chunks de 64 chars em alguns lugares |
| Rate limiting | ❌ Faltando | Sem rate limiting explícito |
| Buffer management | ⚠️ Implícito | Depende do FastAPI/Starlette |

---

## 4. Reconnection Patterns

### Melhores Práticas

Segundo [SSE specification](https://html.spec.whatwg.org/multipage/server-sent-events.html) e [Procedure Tech Blog](https://procedure.tech/blogs/the-streaming-backbone-of-llms-why-server-sent-events-(sse)-still-wins-in-2025):

- **Last-Event-ID:** Enviar ID em cada evento para reconexão
- **retry:** Definir intervalo de retry no servidor
- **Heartbeats:** Enviar comentários SSE a cada poucos segundos

### Implementação Iudex

**Backend (single-chat: `apps/api/app/api/endpoints/chats.py`):**
- Emite `retry: 2000` (no primeiro evento) e `id:` incremental por evento.
- Emite `request_id` no evento `meta` inicial (usado como token de replay).
- Suporta **resume**: reenviar `stream_request_id` no body + `Last-Event-ID` no header para retomar eventos.

**Backend (multi-chat: `apps/api/app/api/endpoints/chat.py`):**
- Emite `retry: 2000` e `id:` incremental por evento.
- (Ainda) não implementa replay/resume com `Last-Event-ID` (stream é “live-only”).

**Frontend (`apps/web/src/stores/chat-store.ts`):**
- Parseia `id:` e `retry:` do stream.
- Em caso de queda, tenta **1 reconexão** com `Last-Event-ID` + `stream_request_id` (maxReconnects=1).

### Avaliação

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Keepalive/heartbeat | ✅ Implementado | Função `sse_keepalive()` existe |
| Last-Event-ID | ✅ Implementado (single-chat) / ⚠️ Parcial (multi-chat) | Single-chat suporta replay via `stream_request_id` + `Last-Event-ID`; multi-chat ainda não |
| retry: header | ✅ Implementado | Servidor envia `retry:` no stream |
| Reconnection logic | ⚠️ Parcial | Frontend tenta 1 reconexão; pode evoluir para backoff e múltiplas tentativas |
| Event ID tracking | ✅ Implementado | `id:` incremental + dedupe por `Last-Event-ID` no cliente |

---

## 5. Error Handling

### Melhores Práticas

Segundo [Apidog Blog](https://apidog.com/blog/stream-llm-responses-using-sse/) e [OpenRouter Docs](https://openrouter.ai/docs/api/reference/errors-and-debugging):

- Enviar eventos de erro específicos no stream
- Não fechar conexão abruptamente
- Incluir códigos de erro e mensagens úteis
- Emitir `error` event antes de fechar

### Implementação Iudex

**Backend:**
```python
yield {"type": "error", "model": model_id, "error": str(e)}
yield {"type": "research_error", "message": str(exc)}
```

**Frontend:**
```typescript
eventSource.onerror = (e) => {
    const hasReviewOpen = !!get()?.reviewData;
    if (!hasReviewOpen) {
        console.error('SSE Error', e);
    }
    closeLangGraphStream();
    set({ isAgentRunning: false });
};
```

### Avaliação

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Eventos de erro in-stream | ✅ Bem implementado | Vários tipos de erro emitidos |
| Error codes | ⚠️ Parcial | Apenas mensagens, sem códigos |
| Graceful degradation | ⚠️ Parcial | Frontend fecha conexão em erro |
| Recovery options | ❌ Faltando | Sem sugestões de retry ao usuário |
| Error categorization | ⚠️ Parcial | Tipos diferentes (error, research_error) |

---

## 6. Multi-Provider Abstraction

### Melhores Práticas

Segundo [Vercel AI SDK](https://blog.logrocket.com/unified-ai-interfaces-vercel-sdk/) e [OpenRouter](https://skywork.ai/blog/openrouter-review-2025-unified-ai-model-api-pricing-privacy/):

- Interface unificada para todos os providers
- Normalização de response formats
- Fallback automático entre providers
- Abstração de streaming behaviors

### Implementação Iudex

**Arquivo:** `apps/api/app/services/ai/agent_clients.py`

```python
async def stream_openai_async(client, prompt, model, ...):
    async for chunk in stream:
        yield ('thinking', choice.delta.reasoning_content)
        yield ('text', delta)

async def stream_anthropic_async(client, prompt, model, ...):
    async for event in stream:
        yield ('thinking', thinking_text)
        yield ('text', text)

async def stream_vertex_gemini_async(client, prompt, model, ...):
    async for chunk in stream_obj:
        yield ("thinking", text)
        yield ("text", text)
        yield ("grounding_query", query)
        yield ("grounding_source", src)
```

### Avaliação

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Interface normalizada | ✅ Excelente | Todos retornam tuples (type, content) |
| Suporte multi-provider | ✅ Excelente | OpenAI, Claude, Gemini, Perplexity |
| Abstração de thinking | ✅ Bem implementado | Normalizado em todos os providers |
| Provider-specific features | ✅ Bem implementado | Grounding do Gemini preservado |
| Fallback logic | ⚠️ Parcial | Fallback em alguns casos, mas não sistemático |
| Error normalization | ⚠️ Parcial | Erros não totalmente normalizados |

---

## 7. Recursos Adicionais Encontrados

### Headers SSE Corretos

**Implementação Iudex:**
```python
return StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
    }
)
```

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Content-Type | ✅ Correto | `text/event-stream` |
| Cache-Control | ✅ Correto | `no-cache, no-transform` |
| Connection | ✅ Correto | `keep-alive` |
| X-Accel-Buffering | ⚠️ Faltando | Recomendado para Nginx: `X-Accel-Buffering: no` |

### Named Events (jobs.py)

```python
def sse_event(data: dict, event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

| Aspecto | Status | Comentário |
|---------|--------|------------|
| Named events | ✅ Implementado | Usa `event:` field em jobs.py |
| Event filtering | ✅ Implementado | Frontend escuta eventos específicos |

---

## Resumo Consolidado

### ✅ O que já está bem implementado

1. **Tipos de eventos variados** - token, thinking, done, error, meta, step.*
2. **Estrutura JSON consistente** - Sempre com `type` e dados relevantes
3. **Identificador de modelo** - Inclui `model` em cada evento (excelente para multi-model)
4. **Keepalive implementado** - Função `sse_keepalive()` para prevenir timeouts
5. **Multi-provider abstraction** - Interface normalizada para OpenAI, Claude, Gemini
6. **Named events** - Uso de `event:` field em jobs.py
7. **Headers SSE corretos** - Cache-Control, Connection adequados
8. **Async streaming** - Uso correto de async generators
9. **Eventos de progresso** - step.start, step.done, search_done, etc.
10. **Separação thinking/text** - Raciocínio separado do conteúdo

### ⚠️ O que pode melhorar

1. **Resume no multi-chat** - Suportar replay por `Last-Event-ID` também em `/multi-chat/*`
2. **Padrão start/delta/end completo** - Implementar text-start/text-end
3. **Error codes estruturados** - Além de mensagens, incluir códigos
4. **Rate limiting** - Controle de taxa para eventos de alta frequência
5. **Reconnection no frontend** - Evoluir para backoff e mais tentativas (hoje maxReconnects=1)
6. **X-Accel-Buffering header** - Para proxies Nginx (já está presente em streams principais; garantir em todos)
7. **Block IDs** - IDs únicos para cada bloco de texto/thinking
8. **Fallback sistemático** - Mecanismo de fallback entre providers mais robusto
9. **Tool call events** - Eventos específicos para chamadas de ferramentas
10. **Timing metadata** - Incluir timestamps consistentes em todos os eventos

### ❌ O que está faltando

1. **Resume no multi-chat** - Sem capacidade de retomar do último evento em `/multi-chat/*`
2. **Automatic reconnection robusta** - Backoff + múltiplas tentativas (hoje limitado)
3. **Event versioning** - Sem versionamento de schema de eventos
4. **Backpressure signaling** - Sem mecanismo para sinalizar cliente lento
5. **Compression** - Eventos não são comprimidos (SSE é text-only)
6. **Rate limit headers** - Não informa limites de rate ao cliente

---

## Recomendações Prioritárias

### Alta Prioridade

1. **Levar resume para multi-chat** (`/multi-chat/threads/{id}/messages`):
- Cache/replay server-side (mesma ideia do `ChatStreamSession` do single-chat).
- Aceitar `Last-Event-ID` e reentregar eventos a partir do último id.

2. **Reconnection com backoff no frontend**:
- Aumentar `maxReconnects` e aplicar backoff progressivo usando o `retry:` do servidor como base.

3. **Eventos de tool calls**:
- Emitir eventos dedicados (ex.: `tool_call.start/delta/done`) para tornar a UI mais previsível.

```typescript
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

eventSource.onerror = (e) => {
    if (reconnectAttempts < maxReconnectAttempts) {
        setTimeout(() => {
            reconnectAttempts++;
            attachLangGraphStream(jobId, persistChatId, set, get);
        }, Math.min(1000 * Math.pow(2, reconnectAttempts), 30000));
    }
};
```

### Média Prioridade

4. **Adicionar X-Accel-Buffering:**
```python
headers={
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # Nginx
}
```

5. **Padronizar error codes:**
```python
yield {
    "type": "error",
    "code": "PROVIDER_UNAVAILABLE",
    "message": "Claude API unavailable",
    "recoverable": True
}
```

---

## Fontes

- [SSE's Glorious Comeback: Why 2025 is the Year of Server-Sent Events](https://portalzine.de/sses-glorious-comeback-why-2025-is-the-year-of-server-sent-events/)
- [The Streaming Backbone of LLMs: Why SSE Still Wins in 2025](https://procedure.tech/blogs/the-streaming-backbone-of-llms-why-server-sent-events-(sse)-still-wins-in-2025)
- [AI SDK UI: Stream Protocols](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)
- [OpenAI Streaming Events](https://platform.openai.com/docs/api-reference/responses-streaming)
- [How to build unified AI interfaces using the Vercel AI SDK](https://blog.logrocket.com/unified-ai-interfaces-vercel-sdk/)
- [OpenRouter Review 2025: Unified AI Model API](https://skywork.ai/blog/openrouter-review-2025-unified-ai-model-api-pricing-privacy/)
- [Server-Sent Events: A Comprehensive Guide](https://medium.com/@moali314/server-sent-events-a-comprehensive-guide-e4b15d147576)
- [How to Stream LLM Responses Using SSE](https://apidog.com/blog/stream-llm-responses-using-sse/)
- [Server Sent Events in OpenAPI best practices](https://www.speakeasy.com/openapi/content/server-sent-events)
- [The Complete Guide to Streaming LLM Responses](https://dev.to/hobbada/the-complete-guide-to-streaming-llm-responses-in-web-applications-from-sse-to-real-time-ui-3534)
