/**
 * Funcoes de API especificas para o Outlook Add-in.
 *
 * Endpoints de sumarizacao (SSE), classificacao e extracao de prazos.
 */

import { streamSSE } from './sse-client';
import type {
  EmailSummarizeRequest,
  ClassifyResult,
  DeadlineResult,
} from './client';
import { api } from './client';

export interface EmailData {
  subject: string;
  body: string;
  sender: string;
  recipients: string[];
  date: string;
  conversationId?: string;
  internetMessageId?: string;
  attachments?: Array<{
    name: string;
    contentType: string;
    size?: number;
  }>;
}

export interface SummarizeCallbacks {
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  onDone?: (metadata?: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
}

/**
 * Sumariza um e-mail via SSE streaming.
 * O backend retorna eventos progressivos com o resumo sendo gerado.
 */
export async function summarizeEmail(
  data: EmailData,
  callbacks: SummarizeCallbacks
): Promise<void> {
  return streamSSE({
    url: '/outlook-addin/summarize',
    body: {
      subject: data.subject,
      body: data.body,
      sender: data.sender,
      recipients: data.recipients,
      date: data.date,
      attachments: data.attachments?.map((a) => ({
        name: a.name,
        contentType: a.contentType,
      })),
    },
    ...callbacks,
  });
}

/**
 * Classifica o tipo juridico de um e-mail.
 */
export async function classifyEmail(
  data: EmailData
): Promise<ClassifyResult> {
  const request: EmailSummarizeRequest = {
    subject: data.subject,
    body: data.body,
    sender: data.sender,
    recipients: data.recipients,
    date: data.date,
    attachments: data.attachments?.map((a) => ({
      name: a.name,
      contentType: a.contentType,
    })),
  };
  const { data: result } = await api.post<ClassifyResult>(
    '/outlook-addin/classify',
    request
  );
  return result;
}

/**
 * Extrai prazos de um e-mail.
 */
export async function extractDeadlines(
  data: EmailData
): Promise<DeadlineResult[]> {
  const request: EmailSummarizeRequest = {
    subject: data.subject,
    body: data.body,
    sender: data.sender,
    recipients: data.recipients,
    date: data.date,
    attachments: data.attachments?.map((a) => ({
      name: a.name,
      contentType: a.contentType,
    })),
  };
  const { data: result } = await api.post<DeadlineResult[]>(
    '/outlook-addin/deadlines',
    request
  );
  return result;
}
