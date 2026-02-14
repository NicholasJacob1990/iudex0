/**
 * Mock do Office.js para testes unitarios.
 *
 * Conforme Design Doc Section 15.3.
 * Simula Office.context.mailbox.item para testes do mail-bridge.
 */

interface MockEmailAddressDetails {
  displayName: string;
  emailAddress: string;
}

interface MockAttachmentDetails {
  id: string;
  name: string;
  contentType: string;
  size: number;
  isInline: boolean;
}

interface MockAsyncResult<T> {
  status: 'succeeded' | 'failed';
  value: T;
  error?: { message: string };
}

interface MockMailboxItem {
  subject: string;
  from: MockEmailAddressDetails;
  to: MockEmailAddressDetails[];
  cc: MockEmailAddressDetails[];
  dateTimeCreated: Date;
  conversationId: string;
  internetMessageId: string;
  attachments: MockAttachmentDetails[];
  body: {
    getAsync: (
      coercionType: unknown,
      callback: (result: MockAsyncResult<string>) => void
    ) => void;
  };
  getAttachmentContentAsync: (
    attachmentId: string,
    callback: (
      result: MockAsyncResult<{ content: string; format: string }>
    ) => void
  ) => void;
}

const mockItem: MockMailboxItem = {
  subject: 'RE: Contrato de Prestacao de Servicos - Prazo 15/03/2025',
  from: {
    displayName: 'Dr. Carlos Silva',
    emailAddress: 'carlos.silva@escritorio.com.br',
  },
  to: [
    {
      displayName: 'Dra. Ana Oliveira',
      emailAddress: 'ana.oliveira@empresa.com.br',
    },
  ],
  cc: [
    {
      displayName: 'Secretaria Juridica',
      emailAddress: 'juridico@empresa.com.br',
    },
  ],
  dateTimeCreated: new Date('2025-02-10T14:30:00Z'),
  conversationId: 'AAQkAGQ0MjBj-mock-conversation-id',
  internetMessageId: '<mock-message-id@escritorio.com.br>',
  attachments: [
    {
      id: 'AAMkAGQ0-attachment-1',
      name: 'Contrato_v3.pdf',
      contentType: 'application/pdf',
      size: 245760,
      isInline: false,
    },
    {
      id: 'AAMkAGQ0-attachment-2',
      name: 'Procuracao.pdf',
      contentType: 'application/pdf',
      size: 102400,
      isInline: false,
    },
  ],
  body: {
    getAsync: (
      _coercionType: unknown,
      callback: (result: MockAsyncResult<string>) => void
    ) => {
      callback({
        status: 'succeeded',
        value: `Prezada Dra. Ana,

Segue em anexo a versao revisada do contrato de prestacao de servicos.

Principais alteracoes:
1. Clausula 5.2 - Ajuste no prazo de pagamento (30 para 45 dias)
2. Clausula 8.1 - Inclusao de clausula de confidencialidade
3. Clausula 12.3 - Revisao da multa por rescisao

IMPORTANTE: O prazo para assinatura e 15/03/2025.
Favor revisar e retornar ate 10/03/2025.

Atenciosamente,
Dr. Carlos Silva
OAB/SP 123.456`,
      });
    },
  },
  getAttachmentContentAsync: (
    _attachmentId: string,
    callback: (
      result: MockAsyncResult<{ content: string; format: string }>
    ) => void
  ) => {
    callback({
      status: 'succeeded',
      value: {
        content: 'base64-encoded-content-mock',
        format: 'base64',
      },
    });
  },
};

const mockMailbox = {
  item: mockItem,
  addHandlerAsync: (
    _eventType: unknown,
    _handler: () => void,
    callback?: (result: MockAsyncResult<void>) => void
  ) => {
    callback?.({
      status: 'succeeded',
      value: undefined,
    });
  },
  removeHandlerAsync: (
    _eventType: unknown,
    callback?: (result: MockAsyncResult<void>) => void
  ) => {
    callback?.({
      status: 'succeeded',
      value: undefined,
    });
  },
};

const mockOffice = {
  onReady: (callback: (info: { host: string }) => void) => {
    callback({ host: 'Outlook' });
  },
  context: {
    mailbox: mockMailbox,
  },
  HostType: {
    Outlook: 'Outlook',
    Word: 'Word',
    Excel: 'Excel',
  },
  CoercionType: {
    Text: 'Text',
    Html: 'Html',
  },
  AsyncResultStatus: {
    Succeeded: 'succeeded',
    Failed: 'failed',
  },
  EventType: {
    ItemChanged: 'ItemChanged',
  },
};

// Injeta o mock no escopo global
(globalThis as Record<string, unknown>).Office = mockOffice;

export { mockOffice, mockItem, mockMailbox };
