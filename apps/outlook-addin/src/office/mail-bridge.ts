/**
 * Ponte entre o Outlook Add-in e a API Office.js Mailbox.
 *
 * Extrai dados do e-mail atual usando Office.context.mailbox.item.
 * Conforme Design Doc Section 7.3.
 */

export interface AttachmentInfo {
  id: string;
  name: string;
  contentType: string;
  size: number;
  isInline: boolean;
}

export interface EmailData {
  subject: string;
  body: string;
  sender: string;
  senderEmail: string;
  recipients: string[];
  ccRecipients: string[];
  date: string;
  conversationId: string;
  internetMessageId: string;
  attachments: AttachmentInfo[];
}

/**
 * Obtem dados do e-mail atualmente aberto no Outlook.
 * Usa Office.context.mailbox.item para acessar propriedades do e-mail.
 */
export async function getCurrentEmailData(): Promise<EmailData> {
  return new Promise((resolve, reject) => {
    const item = Office.context.mailbox.item;

    if (!item) {
      reject(new Error('Nenhum e-mail selecionado'));
      return;
    }

    // Obtem o corpo do e-mail em texto plano
    item.body.getAsync(
      Office.CoercionType.Text,
      (bodyResult: Office.AsyncResult<string>) => {
        if (bodyResult.status === Office.AsyncResultStatus.Failed) {
          reject(new Error(`Erro ao obter corpo do e-mail: ${bodyResult.error?.message}`));
          return;
        }

        const body = bodyResult.value;

        // Monta lista de destinatarios
        const toRecipients = (item.to || []).map(
          (r: Office.EmailAddressDetails) => r.emailAddress
        );
        const ccRecipients = (item.cc || []).map(
          (r: Office.EmailAddressDetails) => r.emailAddress
        );

        // Monta lista de anexos
        const attachments: AttachmentInfo[] = (item.attachments || []).map(
          (att: Office.AttachmentDetails) => ({
            id: att.id,
            name: att.name,
            contentType: att.contentType,
            size: att.size,
            isInline: att.isInline,
          })
        );

        const emailData: EmailData = {
          subject: item.subject || '',
          body,
          sender: item.from?.displayName || '',
          senderEmail: item.from?.emailAddress || '',
          recipients: toRecipients,
          ccRecipients,
          date: item.dateTimeCreated?.toISOString() || new Date().toISOString(),
          conversationId: item.conversationId || '',
          internetMessageId: item.internetMessageId || '',
          attachments,
        };

        resolve(emailData);
      }
    );
  });
}

/**
 * Obtem o conteudo de um anexo pelo ID.
 * Retorna o conteudo em base64.
 */
export async function getAttachmentContent(
  attachmentId: string
): Promise<{ content: string; format: string }> {
  return new Promise((resolve, reject) => {
    const item = Office.context.mailbox.item;

    if (!item) {
      reject(new Error('Nenhum e-mail selecionado'));
      return;
    }

    item.getAttachmentContentAsync(
      attachmentId,
      (result: Office.AsyncResult<Office.AttachmentContent>) => {
        if (result.status === Office.AsyncResultStatus.Failed) {
          reject(
            new Error(`Erro ao obter anexo: ${result.error?.message}`)
          );
          return;
        }

        resolve({
          content: result.value.content,
          format: result.value.format.toString(),
        });
      }
    );
  });
}

/**
 * Registra callback para quando o e-mail selecionado muda (pane fixada).
 * Usa o evento Office.EventType.ItemChanged.
 */
export function onItemChanged(callback: () => void): void {
  Office.context.mailbox.addHandlerAsync(
    Office.EventType.ItemChanged,
    callback,
    (result: Office.AsyncResult<void>) => {
      if (result.status === Office.AsyncResultStatus.Failed) {
        console.error(
          '[mail-bridge] Erro ao registrar ItemChanged:',
          result.error?.message
        );
      }
    }
  );
}

/**
 * Remove o handler do evento ItemChanged.
 */
export function offItemChanged(): void {
  Office.context.mailbox.removeHandlerAsync(
    Office.EventType.ItemChanged,
    (result: Office.AsyncResult<void>) => {
      if (result.status === Office.AsyncResultStatus.Failed) {
        console.error(
          '[mail-bridge] Erro ao remover ItemChanged:',
          result.error?.message
        );
      }
    }
  );
}
