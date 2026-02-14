/**
 * Zustand store para resultados de sumarizacao de e-mail.
 *
 * Gerencia streaming SSE, resultado final e estado de loading.
 */

import { create } from 'zustand';
import { summarizeEmail } from '@/api/outlook-api';
import type { EmailData } from '@/office/mail-bridge';
import type { ClassifyResult, DeadlineResult } from '@/api/client';

export interface SummaryResult {
  classificacao: ClassifyResult | null;
  resumo: string;
  prazos: DeadlineResult[];
  acoes_sugeridas: string[];
  workflows_recomendados: string[];
}

interface SummaryState {
  summary: SummaryResult | null;
  isStreaming: boolean;
  streamingContent: string;
  thinkingContent: string;
  error: string | null;
  abortController: AbortController | null;
  summarize: (emailData: EmailData) => Promise<void>;
  cancel: () => void;
  clear: () => void;
}

export const useSummaryStore = create<SummaryState>()((set, get) => ({
  summary: null,
  isStreaming: false,
  streamingContent: '',
  thinkingContent: '',
  error: null,
  abortController: null,

  summarize: async (emailData: EmailData) => {
    // Cancela stream anterior se existir
    get().cancel();

    const controller = new AbortController();
    set({
      isStreaming: true,
      streamingContent: '',
      thinkingContent: '',
      error: null,
      summary: null,
      abortController: controller,
    });

    try {
      await summarizeEmail(
        {
          subject: emailData.subject,
          body: emailData.body,
          sender: emailData.senderEmail || emailData.sender,
          recipients: emailData.recipients,
          date: emailData.date,
          conversationId: emailData.conversationId,
          internetMessageId: emailData.internetMessageId,
          attachments: emailData.attachments?.map((a) => ({
            name: a.name,
            contentType: a.contentType,
            size: a.size,
          })),
        },
        {
          onThinking: (text: string) => {
            set((state) => ({
              thinkingContent: state.thinkingContent + text,
            }));
          },
          onContent: (text: string) => {
            set((state) => ({
              streamingContent: state.streamingContent + text,
            }));
          },
          onDone: (metadata?: Record<string, unknown>) => {
            const finalContent = get().streamingContent;

            // Tenta parsear metadata como resultado estruturado
            const result: SummaryResult = {
              classificacao: (metadata?.classificacao as ClassifyResult) || null,
              resumo: finalContent,
              prazos: (metadata?.prazos as DeadlineResult[]) || [],
              acoes_sugeridas: (metadata?.acoes_sugeridas as string[]) || [],
              workflows_recomendados:
                (metadata?.workflows_recomendados as string[]) || [],
            };

            set({
              summary: result,
              isStreaming: false,
              abortController: null,
            });
          },
          onError: (error: string) => {
            set({
              error,
              isStreaming: false,
              abortController: null,
            });
          },
          signal: controller.signal,
        }
      );
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return;
      const message =
        err instanceof Error ? err.message : 'Erro ao sumarizar e-mail';
      set({
        error: message,
        isStreaming: false,
        abortController: null,
      });
    }
  },

  cancel: () => {
    const controller = get().abortController;
    if (controller) {
      controller.abort();
      set({ isStreaming: false, abortController: null });
    }
  },

  clear: () =>
    set({
      summary: null,
      isStreaming: false,
      streamingContent: '',
      thinkingContent: '',
      error: null,
      abortController: null,
    }),
}));
