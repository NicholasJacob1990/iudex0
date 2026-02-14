/**
 * Custom hook para consumir streams SSE em componentes React.
 *
 * Abstrai o ciclo de vida do streaming: start, cancel, cleanup.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { streamSSE } from '@/api/sse-client';

interface UseSSEStreamOptions {
  url: string;
}

interface SSEStreamState {
  isStreaming: boolean;
  content: string;
  thinking: string;
  error: string | null;
  metadata: Record<string, unknown> | undefined;
}

interface UseSSEStreamReturn extends SSEStreamState {
  start: (body: Record<string, unknown>) => Promise<void>;
  cancel: () => void;
  clear: () => void;
}

export function useSSEStream({ url }: UseSSEStreamOptions): UseSSEStreamReturn {
  const [state, setState] = useState<SSEStreamState>({
    isStreaming: false,
    content: '',
    thinking: '',
    error: null,
    metadata: undefined,
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup ao desmontar
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const start = useCallback(
    async (body: Record<string, unknown>) => {
      // Cancela stream anterior
      abortControllerRef.current?.abort();

      const controller = new AbortController();
      abortControllerRef.current = controller;

      setState({
        isStreaming: true,
        content: '',
        thinking: '',
        error: null,
        metadata: undefined,
      });

      try {
        await streamSSE({
          url,
          body,
          onThinking: (text) => {
            setState((prev) => ({
              ...prev,
              thinking: prev.thinking + text,
            }));
          },
          onContent: (text) => {
            setState((prev) => ({
              ...prev,
              content: prev.content + text,
            }));
          },
          onDone: (metadata) => {
            setState((prev) => ({
              ...prev,
              isStreaming: false,
              metadata,
            }));
          },
          onError: (error) => {
            setState((prev) => ({
              ...prev,
              isStreaming: false,
              error,
            }));
          },
          signal: controller.signal,
        });
      } catch (err: unknown) {
        if ((err as Error).name === 'AbortError') return;
        const message =
          err instanceof Error ? err.message : 'Erro no streaming';
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: message,
        }));
      }
    },
    [url]
  );

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
    setState((prev) => ({
      ...prev,
      isStreaming: false,
    }));
  }, []);

  const clear = useCallback(() => {
    abortControllerRef.current?.abort();
    setState({
      isStreaming: false,
      content: '',
      thinking: '',
      error: null,
      metadata: undefined,
    });
  }, []);

  return {
    ...state,
    start,
    cancel,
    clear,
  };
}
