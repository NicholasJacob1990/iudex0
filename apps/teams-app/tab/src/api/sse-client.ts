/**
 * Cliente SSE para streaming de respostas da API Vorbium.
 *
 * Usa fetch nativo + ReadableStream para consumir Server-Sent Events.
 * Mesmo padrao usado pelo apps/office-addin.
 */

import { API_URL, getAccessToken } from './client';

export interface SSEEvent {
  type: 'thinking' | 'content' | 'done' | 'error';
  data: string;
  metadata?: Record<string, unknown>;
}

export interface StreamOptions {
  endpoint: string;
  body: Record<string, unknown>;
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  onDone?: (metadata?: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}

/**
 * Cliente SSE generico para streaming de qualquer endpoint.
 * Envia POST com body JSON e consome stream de eventos SSE.
 */
export async function streamRequest(options: StreamOptions): Promise<void> {
  const {
    endpoint,
    body,
    onThinking,
    onContent,
    onDone,
    onError,
    signal,
  } = options;

  const token = getAccessToken();
  if (!token) {
    onError?.('Nao autenticado');
    return;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Erro desconhecido');
    onError?.(`Erro ${response.status}: ${errorText}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError?.('Stream nao disponivel');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;

        try {
          const event: SSEEvent = JSON.parse(line.slice(6));

          switch (event.type) {
            case 'thinking':
              onThinking?.(event.data);
              break;
            case 'content':
              onContent?.(event.data);
              break;
            case 'done':
              onDone?.(event.metadata);
              return;
            case 'error':
              onError?.(event.data);
              return;
          }
        } catch {
          // Ignore malformed events
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Stream de mensagem em chat (atalho conveniente).
 */
export async function streamChatMessage(options: {
  chatId: string;
  content: string;
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  onDone?: (metadata?: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}): Promise<void> {
  const { chatId, content, ...callbacks } = options;
  return streamRequest({
    endpoint: `/chats/${chatId}/messages/stream`,
    body: { content },
    ...callbacks,
  });
}
