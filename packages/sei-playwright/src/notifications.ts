/**
 * Serviço de Notificações SEI
 * Envia emails e webhooks com informações de processos/documentos
 */

import { createTransport, type Transporter } from 'nodemailer';
import type { WatchEvent, WatchItem, ProcessoRecebido, BlocoAssinatura } from './watcher.js';

export interface EmailConfig {
  /** Host SMTP */
  host: string;
  /** Porta SMTP */
  port: number;
  /** Usar SSL/TLS */
  secure: boolean;
  /** Credenciais */
  auth: {
    user: string;
    pass: string;
  };
  /** Email do remetente */
  from: string;
  /** Nome do remetente */
  fromName?: string;
}

export interface NotificationPayload {
  /** Tipo do evento */
  type: string;
  /** Usuário destinatário */
  userId: string;
  /** Email do destinatário */
  email: string;
  /** Nome do destinatário */
  nome: string;
  /** Itens do evento */
  items: EnrichedItem[];
  /** Timestamp */
  timestamp: Date;
  /** URL base do SEI */
  seiUrl: string;
}

export interface EnrichedItem extends WatchItem {
  /** Teor/conteúdo do documento */
  teor?: string;
  /** Prazo (se existir) */
  prazo?: PrazoInfo;
  /** Documentos para download */
  documentos?: DocumentoDownload[];
  /** Link para o processo */
  linkProcesso?: string;
}

export interface PrazoInfo {
  /** Data limite */
  dataLimite: string;
  /** Dias restantes (negativo = vencido) */
  diasRestantes: number;
  /** Tipo: úteis ou corridos */
  tipo: 'util' | 'corrido';
  /** Status */
  status: 'normal' | 'proximo' | 'vencendo_hoje' | 'vencido';
}

export interface DocumentoDownload {
  /** ID do documento */
  id: string;
  /** Nome do documento */
  nome: string;
  /** Tipo */
  tipo: string;
  /** Data */
  data: string;
  /** Caminho do arquivo baixado */
  filePath?: string;
  /** Conteúdo em base64 */
  base64?: string;
}

/**
 * Serviço de notificações
 *
 * @example
 * ```typescript
 * const notifier = new SEINotificationService({
 *   email: {
 *     host: 'smtp.gmail.com',
 *     port: 587,
 *     secure: false,
 *     auth: { user: 'x', pass: 'y' },
 *     from: 'noreply@iudex.com',
 *   },
 * });
 *
 * await notifier.send({
 *   type: 'processos_recebidos',
 *   userId: 'user-123',
 *   email: 'joao@email.com',
 *   nome: 'João',
 *   items: [...],
 *   timestamp: new Date(),
 *   seiUrl: 'https://sei.mg.gov.br',
 * });
 * ```
 */
export class SEINotificationService {
  private emailConfig?: EmailConfig;
  private transporter?: Transporter;

  constructor(options: { email?: EmailConfig }) {
    this.emailConfig = options.email;

    if (this.emailConfig) {
      this.transporter = createTransport({
        host: this.emailConfig.host,
        port: this.emailConfig.port,
        secure: this.emailConfig.secure,
        auth: this.emailConfig.auth,
      });
    }
  }

  /** Envia notificação por email */
  async sendEmail(payload: NotificationPayload): Promise<boolean> {
    if (!this.transporter || !this.emailConfig) {
      console.warn('Email não configurado');
      return false;
    }

    const html = this.buildEmailHtml(payload);
    const subject = this.buildSubject(payload);

    // Preparar anexos se houver
    const attachments = payload.items
      .flatMap((item) => item.documentos ?? [])
      .filter((doc) => doc.filePath || doc.base64)
      .map((doc) => ({
        filename: doc.nome,
        path: doc.filePath,
        content: doc.base64 ? Buffer.from(doc.base64, 'base64') : undefined,
      }));

    try {
      await this.transporter.sendMail({
        from: `"${this.emailConfig.fromName ?? 'SEI Notificações'}" <${this.emailConfig.from}>`,
        to: payload.email,
        subject,
        html,
        attachments: attachments.length > 0 ? attachments : undefined,
      });
      return true;
    } catch (error) {
      console.error('Erro ao enviar email:', error);
      return false;
    }
  }

  /** Envia notificação via webhook */
  async sendWebhook(url: string, payload: NotificationPayload): Promise<boolean> {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event: payload.type,
          userId: payload.userId,
          timestamp: payload.timestamp.toISOString(),
          items: payload.items.map((item) => ({
            ...item,
            // Remover base64 do webhook para não sobrecarregar
            documentos: item.documentos?.map(({ base64, ...doc }) => doc),
          })),
        }),
      });
      return response.ok;
    } catch (error) {
      console.error('Erro ao enviar webhook:', error);
      return false;
    }
  }

  /** Constrói assunto do email */
  private buildSubject(payload: NotificationPayload): string {
    const count = payload.items.length;

    switch (payload.type) {
      case 'processos_recebidos':
        return `📥 SEI: ${count} novo${count > 1 ? 's' : ''} processo${count > 1 ? 's' : ''} recebido${count > 1 ? 's' : ''}`;
      case 'blocos_assinatura':
        return `✍️ SEI: ${count} bloco${count > 1 ? 's' : ''} de assinatura pendente${count > 1 ? 's' : ''}`;
      case 'prazos':
        const urgentes = payload.items.filter((i) => i.prazo?.status === 'vencido' || i.prazo?.status === 'vencendo_hoje').length;
        if (urgentes > 0) {
          return `⚠️ SEI: ${urgentes} prazo${urgentes > 1 ? 's' : ''} URGENTE${urgentes > 1 ? 'S' : ''}!`;
        }
        return `⏰ SEI: ${count} processo${count > 1 ? 's' : ''} com prazo`;
      case 'retornos_programados':
        return `📅 SEI: ${count} retorno${count > 1 ? 's' : ''} programado${count > 1 ? 's' : ''}`;
      default:
        return `🔔 SEI: Nova notificação`;
    }
  }

  /** Constrói HTML do email */
  private buildEmailHtml(payload: NotificationPayload): string {
    const items = payload.items.map((item) => this.buildItemHtml(item, payload)).join('');

    return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
    .container { max-width: 600px; margin: 0 auto; background: #fff; }
    .header { background: #1a365d; color: #fff; padding: 20px; text-align: center; }
    .header h1 { margin: 0; font-size: 24px; }
    .content { padding: 20px; }
    .item { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    .item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .item-title { font-size: 16px; font-weight: 600; color: #1a365d; margin: 0; }
    .badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
    .badge-urgente { background: #fed7d7; color: #c53030; }
    .badge-normal { background: #e2e8f0; color: #4a5568; }
    .badge-prazo { background: #fefcbf; color: #975a16; }
    .meta { color: #718096; font-size: 14px; margin-bottom: 8px; }
    .teor { background: #f7fafc; border-left: 4px solid #4299e1; padding: 12px; margin: 12px 0; font-size: 14px; color: #2d3748; }
    .prazo { background: #fffaf0; border: 1px solid #ed8936; border-radius: 4px; padding: 12px; margin: 12px 0; }
    .prazo-vencido { background: #fff5f5; border-color: #c53030; }
    .prazo-hoje { background: #fffff0; border-color: #d69e2e; }
    .documentos { margin-top: 12px; }
    .documento { display: flex; align-items: center; padding: 8px; background: #f7fafc; border-radius: 4px; margin-bottom: 8px; }
    .documento-icon { margin-right: 8px; }
    .actions { margin-top: 16px; }
    .btn { display: inline-block; padding: 10px 20px; background: #4299e1; color: #fff; text-decoration: none; border-radius: 4px; font-weight: 500; margin-right: 8px; }
    .btn-secondary { background: #e2e8f0; color: #4a5568; }
    .footer { background: #f7fafc; padding: 16px; text-align: center; color: #718096; font-size: 12px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>${this.getHeaderTitle(payload.type)}</h1>
    </div>
    <div class="content">
      <p>Olá, <strong>${payload.nome}</strong>!</p>
      <p>${this.getIntroText(payload)}</p>

      ${items}

    </div>
    <div class="footer">
      <p>Esta notificação foi enviada automaticamente pelo sistema Iudex.</p>
      <p>SEI: ${payload.seiUrl}</p>
    </div>
  </div>
</body>
</html>
    `.trim();
  }

  /** Constrói HTML de um item */
  private buildItemHtml(item: EnrichedItem, payload: NotificationPayload): string {
    const processo = item as ProcessoRecebido;
    const bloco = item as BlocoAssinatura;

    // Badge de urgência
    let badge = '';
    if (item.urgente) {
      badge = '<span class="badge badge-urgente">URGENTE</span>';
    } else if (item.prazo?.status === 'vencido') {
      badge = '<span class="badge badge-urgente">PRAZO VENCIDO</span>';
    } else if (item.prazo?.status === 'vencendo_hoje') {
      badge = '<span class="badge badge-prazo">VENCE HOJE</span>';
    }

    // Metadados
    let meta = '';
    if (processo.remetente) {
      meta += `<div class="meta">📤 Remetente: <strong>${processo.remetente}</strong></div>`;
    }
    if (processo.dataRecebimento) {
      meta += `<div class="meta">📅 Recebido em: ${processo.dataRecebimento}</div>`;
    }
    if (item.tipo) {
      meta += `<div class="meta">📋 Tipo: ${item.tipo}</div>`;
    }
    if (bloco.quantidadeDocumentos) {
      meta += `<div class="meta">📄 Documentos: ${bloco.quantidadeDocumentos}</div>`;
    }

    // Teor do documento
    let teor = '';
    if (item.teor) {
      const teorTruncado = item.teor.length > 500 ? item.teor.substring(0, 500) + '...' : item.teor;
      teor = `
        <div class="teor">
          <strong>Teor:</strong><br>
          ${teorTruncado.replace(/\n/g, '<br>')}
        </div>
      `;
    }

    // Prazo
    let prazo = '';
    if (item.prazo) {
      const prazoClass = item.prazo.status === 'vencido' ? 'prazo-vencido' :
                        item.prazo.status === 'vencendo_hoje' ? 'prazo-hoje' : '';
      prazo = `
        <div class="prazo ${prazoClass}">
          <strong>⏰ Prazo:</strong> ${item.prazo.dataLimite}<br>
          <strong>Dias restantes:</strong> ${item.prazo.diasRestantes} (${item.prazo.tipo === 'util' ? 'úteis' : 'corridos'})
        </div>
      `;
    }

    // Documentos
    let documentos = '';
    if (item.documentos && item.documentos.length > 0) {
      const docList = item.documentos.map(doc => `
        <div class="documento">
          <span class="documento-icon">📄</span>
          <span>${doc.nome} (${doc.tipo}) - ${doc.data}</span>
        </div>
      `).join('');

      documentos = `
        <div class="documentos">
          <strong>Documentos da data:</strong>
          ${docList}
        </div>
      `;
    }

    // Ações
    const linkProcesso = item.linkProcesso ?? `${payload.seiUrl}/sei/controlador.php?acao=procedimento_trabalhar&id_procedimento=${item.id}`;

    return `
      <div class="item">
        <div class="item-header">
          <h3 class="item-title">${item.numero ?? item.descricao ?? `ID: ${item.id}`}</h3>
          ${badge}
        </div>
        ${meta}
        ${teor}
        ${prazo}
        ${documentos}
        <div class="actions">
          <a href="${linkProcesso}" class="btn" target="_blank">Abrir no SEI</a>
        </div>
      </div>
    `;
  }

  /** Título do header por tipo */
  private getHeaderTitle(type: string): string {
    switch (type) {
      case 'processos_recebidos': return '📥 Novos Processos Recebidos';
      case 'blocos_assinatura': return '✍️ Blocos de Assinatura';
      case 'prazos': return '⏰ Alertas de Prazo';
      case 'retornos_programados': return '📅 Retornos Programados';
      default: return '🔔 Notificação SEI';
    }
  }

  /** Texto introdutório */
  private getIntroText(payload: NotificationPayload): string {
    const count = payload.items.length;
    switch (payload.type) {
      case 'processos_recebidos':
        return `Você recebeu <strong>${count}</strong> novo${count > 1 ? 's' : ''} processo${count > 1 ? 's' : ''} no SEI.`;
      case 'blocos_assinatura':
        return `Você tem <strong>${count}</strong> bloco${count > 1 ? 's' : ''} de assinatura aguardando.`;
      case 'prazos':
        return `Atenção! <strong>${count}</strong> processo${count > 1 ? 's' : ''} com prazo requer${count > 1 ? 'em' : ''} sua atenção.`;
      case 'retornos_programados':
        return `Você tem <strong>${count}</strong> retorno${count > 1 ? 's' : ''} programado${count > 1 ? 's' : ''}.`;
      default:
        return `Você tem <strong>${count}</strong> nova${count > 1 ? 's' : ''} notificaç${count > 1 ? 'ões' : 'ão'}.`;
    }
  }

  /** Verifica conexão com servidor de email */
  async verify(): Promise<boolean> {
    if (!this.transporter) return false;
    try {
      await this.transporter.verify();
      return true;
    } catch {
      return false;
    }
  }
}

export default SEINotificationService;
