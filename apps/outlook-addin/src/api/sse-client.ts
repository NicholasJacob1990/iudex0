/**
 * Cliente SSE generico para streaming de respostas da API Vorbium.
 *
 * Usa fetch nativo + ReadableStream para consumir Server-Sent Events.
 * Adaptado do apps/office-addin para uso generico no Outlook Add-in.
 */

import { API_URL, getAccessToken } from './client';

export interface SSEEvent {
  type: 'thinking' | 'content' | 'done' | 'error';
  data: string;
  metadata?: Record<string, unknown>;
}

/**
 * Funcao generica para consumir streams SSE.
 * Reutilizavel para summarize, classify, e outros endpoints de streaming.
 */
export async function streamSSE(options: {
  url: string;
  body: Record<string, unknown>;
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  onDone?: (metadata?: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}): Promise<void> {
  const { url, body, onThinking, onContent, onDone, onError, signal } = options;

  const token = getAccessToken();
  if (!token) {
    onError?.('Nao autenticado');
    return;
  }

  const fullUrl = url.startsWith('http') ? url : `${API_URL}${url}`;

  const response = await fetch(fullUrl, {
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
          // Ignora eventos malformados
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Stream de mensagem para chat (compatibilidade com Word add-in).
 */
export interface StreamMessageOptions {
  chatId: string;
  content: string;
  attachments?: string[];
  model?: string;
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  onDone?: (metadata?: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}

export async function streamMessage(options: StreamMessageOptions): Promise<void> {
  const { chatId, content, attachments, model, ...callbacks } = options;

  const body: Record<string, unknown> = { content };
  if (attachments?.length) body.attachments = attachments;
  if (model) body.model_id = model;

  return streamSSE({
    url: `/chats/${chatId}/messages/stream`,
    body,
    ...callbacks,
  });
}
