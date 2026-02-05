/**
 * Cliente SSE para streaming de respostas da API Vorbium.
 *
 * Usa fetch nativo + ReadableStream para consumir Server-Sent Events.
 * Mesmo padrão usado pelo apps/web.
 */

import { API_URL, getAccessToken } from './client';

export interface SSEEvent {
  type: 'thinking' | 'content' | 'done' | 'error' | 'deepresearch_step';
  data: string;
  metadata?: Record<string, unknown>;
}

export interface StreamMessageOptions {
  chatId: string;
  content: string;
  attachments?: string[];
  model?: string;
  playbook_id?: string;
  web_search?: boolean;
  rag_enabled?: boolean;
  reasoning_level?: string;
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  onDone?: (metadata?: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}

/**
 * Envia uma mensagem para o chat com streaming SSE.
 * Chama callbacks conforme eventos chegam.
 */
export async function streamMessage(options: StreamMessageOptions): Promise<void> {
  const {
    chatId,
    content,
    attachments,
    model,
    playbook_id,
    web_search,
    rag_enabled,
    reasoning_level,
    onThinking,
    onContent,
    onDone,
    onError,
    signal,
  } = options;

  const token = getAccessToken();
  if (!token) {
    onError?.('Não autenticado');
    return;
  }

  const body: Record<string, unknown> = { content };
  if (attachments?.length) body.attachments = attachments;
  if (model) body.model_id = model;
  if (playbook_id) body.playbook_id = playbook_id;
  if (web_search !== undefined) body.web_search = web_search;
  if (rag_enabled !== undefined) body.rag_enabled = rag_enabled;
  if (reasoning_level) body.reasoning_level = reasoning_level;

  const response = await fetch(
    `${API_URL}/chats/${chatId}/messages/stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      signal,
    }
  );

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Erro desconhecido');
    onError?.(`Erro ${response.status}: ${errorText}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError?.('Stream não disponível');
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
 * Stream de edição de conteúdo inline (para drafting).
 */
export async function streamEditContent(options: {
  content: string;
  instruction: string;
  model?: string;
  context?: string;
  onContent?: (text: string) => void;
  onDone?: (result: { original: string; edited: string }) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}): Promise<void> {
  const { content, instruction, model, context, onContent, onDone, onError, signal } =
    options;

  const token = getAccessToken();
  if (!token) {
    onError?.('Não autenticado');
    return;
  }

  const body: Record<string, unknown> = { content, instruction };
  if (model) body.model = model;
  if (context) body.context = context;

  const response = await fetch(`${API_URL}/word-addin/edit-content`, {
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
    onError?.('Stream não disponível');
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
          const event = JSON.parse(line.slice(6));
          switch (event.type) {
            case 'content':
              onContent?.(event.data);
              break;
            case 'done':
              onDone?.({ original: content, edited: event.data });
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
 * Stream de tradução de conteúdo.
 */
export async function streamTranslateContent(options: {
  content: string;
  source_lang?: string;
  target_lang?: string;
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  onDone?: (result: string) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}): Promise<void> {
  const {
    content,
    source_lang = 'pt',
    target_lang = 'en',
    onThinking,
    onContent,
    onDone,
    onError,
    signal,
  } = options;

  const token = getAccessToken();
  if (!token) {
    onError?.('Não autenticado');
    return;
  }

  const response = await fetch(`${API_URL}/word-addin/translate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ content, source_lang, target_lang }),
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Erro desconhecido');
    onError?.(`Erro ${response.status}: ${errorText}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError?.('Stream não disponível');
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
          const event = JSON.parse(line.slice(6));
          switch (event.type) {
            case 'thinking':
              onThinking?.(event.data);
              break;
            case 'content':
              onContent?.(event.data);
              break;
            case 'done':
              onDone?.(event.data);
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
