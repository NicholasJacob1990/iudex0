/**
 * Utilitarios para exportacao de relatorios de auditoria de redlines.
 * Gap 8: Exportacao de Audit Log em JSON, CSV e PDF.
 */

import type { ClauseData, RedlineData, PlaybookRunStats } from './client';

export type ExportFormat = 'json' | 'csv' | 'pdf';

export interface AuditReportData {
  playbookRunId: string;
  playbookName: string;
  format: ExportFormat;
  clauses: ClauseData[];
  redlines: RedlineData[];
  appliedRedlines: string[];
  rejectedRedlines: string[];
  stats: PlaybookRunStats;
  summary: string;
}

interface AuditReportJson {
  playbook_run_id: string;
  playbook_name: string;
  generated_at: string;
  summary: {
    total_clauses: number;
    total_redlines: number;
    applied: number;
    rejected: number;
    pending: number;
    compliant: number;
    non_compliant: number;
    needs_review: number;
    not_found: number;
    risk_score: number;
  };
  analysis_summary: string;
  redlines: Array<{
    redline_id: string;
    rule_name: string;
    clause_type: string;
    classification: string;
    severity: string;
    status: 'applied' | 'rejected' | 'pending';
    original_text: string;
    suggested_text: string;
    explanation: string;
    confidence: number;
  }>;
}

/**
 * Gera e baixa o relatorio de auditoria no formato especificado.
 */
export async function exportAuditReport(data: AuditReportData): Promise<void> {
  const report = buildReport(data);

  switch (data.format) {
    case 'json':
      downloadJson(report, data.playbookRunId);
      break;
    case 'csv':
      downloadCsv(report, data.playbookRunId);
      break;
    case 'pdf':
      downloadPdf(report, data.playbookName, data.playbookRunId);
      break;
  }
}

function buildReport(data: AuditReportData): AuditReportJson {
  const appliedSet = new Set(data.appliedRedlines);
  const rejectedSet = new Set(data.rejectedRedlines);

  const redlinesWithStatus = data.redlines.map((r) => ({
    redline_id: r.redline_id,
    rule_name: r.rule_name,
    clause_type: r.clause_type,
    classification: r.classification,
    severity: r.severity,
    status: appliedSet.has(r.redline_id)
      ? 'applied' as const
      : rejectedSet.has(r.redline_id)
        ? 'rejected' as const
        : 'pending' as const,
    original_text: r.original_text,
    suggested_text: r.suggested_text,
    explanation: r.explanation,
    confidence: r.confidence,
  }));

  return {
    playbook_run_id: data.playbookRunId,
    playbook_name: data.playbookName,
    generated_at: new Date().toISOString(),
    summary: {
      total_clauses: data.clauses.length,
      total_redlines: data.redlines.length,
      applied: data.appliedRedlines.length,
      rejected: data.rejectedRedlines.length,
      pending: data.redlines.length - data.appliedRedlines.length - data.rejectedRedlines.length,
      compliant: data.stats.compliant,
      non_compliant: data.stats.non_compliant,
      needs_review: data.stats.needs_review,
      not_found: data.stats.not_found,
      risk_score: data.stats.risk_score,
    },
    analysis_summary: data.summary,
    redlines: redlinesWithStatus,
  };
}

function downloadJson(report: AuditReportJson, runId: string): void {
  const content = JSON.stringify(report, null, 2);
  const blob = new Blob([content], { type: 'application/json' });
  triggerDownload(blob, `audit-report-${runId}.json`);
}

function downloadCsv(report: AuditReportJson, runId: string): void {
  // UTF-8 BOM para Excel
  const BOM = '\uFEFF';

  const headers = [
    'ID',
    'Regra',
    'Tipo',
    'Classificacao',
    'Severidade',
    'Status',
    'Texto Original',
    'Texto Sugerido',
    'Explicacao',
    'Confianca',
  ];

  const escapeCell = (value: string | number): string => {
    const str = String(value);
    // Se contem virgula, aspas ou quebra de linha, envolver em aspas
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const rows = report.redlines.map((r) => [
    r.redline_id,
    r.rule_name,
    r.clause_type,
    r.classification,
    r.severity,
    r.status === 'applied' ? 'Aplicado' : r.status === 'rejected' ? 'Rejeitado' : 'Pendente',
    r.original_text,
    r.suggested_text,
    r.explanation,
    r.confidence.toFixed(2),
  ]);

  // Adicionar linha de resumo no inicio
  const summaryRows = [
    ['Relatorio de Auditoria - Playbook:', report.playbook_name],
    ['Gerado em:', new Date(report.generated_at).toLocaleString('pt-BR')],
    [''],
    ['Resumo'],
    ['Total de clausulas:', report.summary.total_clauses.toString()],
    ['Total de redlines:', report.summary.total_redlines.toString()],
    ['Aplicados:', report.summary.applied.toString()],
    ['Rejeitados:', report.summary.rejected.toString()],
    ['Pendentes:', report.summary.pending.toString()],
    ['Risk Score:', report.summary.risk_score.toFixed(0)],
    [''],
    ['Detalhes dos Redlines'],
  ];

  const csvContent =
    BOM +
    summaryRows.map((row) => row.map(escapeCell).join(',')).join('\n') +
    '\n' +
    headers.map(escapeCell).join(',') +
    '\n' +
    rows.map((row) => row.map(escapeCell).join(',')).join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' });
  triggerDownload(blob, `audit-report-${runId}.csv`);
}

function downloadPdf(report: AuditReportJson, playbookName: string, runId: string): void {
  // Gerar HTML para imprimir como PDF
  const statusLabel = (status: string) =>
    status === 'applied'
      ? '<span style="color: green; font-weight: bold;">Aplicado</span>'
      : status === 'rejected'
        ? '<span style="color: red; font-weight: bold;">Rejeitado</span>'
        : '<span style="color: orange; font-weight: bold;">Pendente</span>';

  const severityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return '#dc2626';
      case 'high':
        return '#ea580c';
      case 'medium':
        return '#d97706';
      case 'low':
        return '#2563eb';
      default:
        return '#6b7280';
    }
  };

  const classificationColor = (classification: string) => {
    switch (classification) {
      case 'compliant':
      case 'conforme':
        return '#16a34a';
      case 'non_compliant':
      case 'nao_conforme':
        return '#dc2626';
      case 'needs_review':
        return '#d97706';
      default:
        return '#6b7280';
    }
  };

  const redlineRows = report.redlines
    .map(
      (r) => `
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">
          <strong>${escapeHtml(r.rule_name)}</strong><br>
          <small style="color: #6b7280;">${escapeHtml(r.clause_type)}</small>
        </td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">
          <span style="color: ${classificationColor(r.classification)}; font-weight: 500;">
            ${escapeHtml(r.classification)}
          </span>
        </td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">
          <span style="color: ${severityColor(r.severity)}; font-weight: 500;">
            ${escapeHtml(r.severity)}
          </span>
        </td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">
          ${statusLabel(r.status)}
        </td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; max-width: 300px;">
          <details>
            <summary style="cursor: pointer; color: #2563eb;">Ver detalhes</summary>
            <div style="margin-top: 8px; font-size: 12px;">
              <p><strong>Original:</strong> ${escapeHtml(r.original_text.slice(0, 200))}${r.original_text.length > 200 ? '...' : ''}</p>
              <p><strong>Sugerido:</strong> ${escapeHtml(r.suggested_text.slice(0, 200))}${r.suggested_text.length > 200 ? '...' : ''}</p>
              <p><strong>Explicacao:</strong> ${escapeHtml(r.explanation)}</p>
            </div>
          </details>
        </td>
      </tr>
    `
    )
    .join('');

  const html = `
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
      <meta charset="UTF-8">
      <title>Relatorio de Auditoria - ${escapeHtml(playbookName)}</title>
      <style>
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          line-height: 1.5;
          color: #1f2937;
          max-width: 1200px;
          margin: 0 auto;
          padding: 40px 20px;
        }
        h1 { color: #111827; margin-bottom: 8px; }
        .subtitle { color: #6b7280; margin-bottom: 24px; }
        .summary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 16px;
          margin-bottom: 32px;
        }
        .summary-card {
          background: #f9fafb;
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          padding: 16px;
        }
        .summary-card .value {
          font-size: 24px;
          font-weight: 700;
          color: #111827;
        }
        .summary-card .label {
          font-size: 12px;
          color: #6b7280;
          text-transform: uppercase;
        }
        .risk-score {
          font-size: 32px;
          font-weight: 700;
        }
        .risk-low { color: #16a34a; }
        .risk-medium { color: #d97706; }
        .risk-high { color: #dc2626; }
        table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 24px;
        }
        th {
          text-align: left;
          padding: 12px 8px;
          background: #f9fafb;
          border-bottom: 2px solid #e5e7eb;
          font-size: 12px;
          text-transform: uppercase;
          color: #6b7280;
        }
        @media print {
          body { padding: 20px; }
          details { display: block; }
          details summary { display: none; }
          details > div { display: block !important; margin-top: 0; }
        }
      </style>
    </head>
    <body>
      <h1>Relatorio de Auditoria</h1>
      <p class="subtitle">
        Playbook: <strong>${escapeHtml(playbookName)}</strong> |
        Gerado em: ${new Date(report.generated_at).toLocaleString('pt-BR')}
      </p>

      <div class="summary-grid">
        <div class="summary-card">
          <div class="value risk-score ${report.summary.risk_score >= 70 ? 'risk-high' : report.summary.risk_score >= 40 ? 'risk-medium' : 'risk-low'}">
            ${report.summary.risk_score.toFixed(0)}
          </div>
          <div class="label">Risk Score</div>
        </div>
        <div class="summary-card">
          <div class="value">${report.summary.total_redlines}</div>
          <div class="label">Total Redlines</div>
        </div>
        <div class="summary-card">
          <div class="value" style="color: #16a34a;">${report.summary.applied}</div>
          <div class="label">Aplicados</div>
        </div>
        <div class="summary-card">
          <div class="value" style="color: #dc2626;">${report.summary.rejected}</div>
          <div class="label">Rejeitados</div>
        </div>
        <div class="summary-card">
          <div class="value" style="color: #d97706;">${report.summary.pending}</div>
          <div class="label">Pendentes</div>
        </div>
      </div>

      ${report.analysis_summary ? `<p style="background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 12px 16px; margin-bottom: 24px;"><strong>Resumo da Analise:</strong> ${escapeHtml(report.analysis_summary)}</p>` : ''}

      <h2>Detalhes dos Redlines</h2>
      <table>
        <thead>
          <tr>
            <th>Regra</th>
            <th>Classificacao</th>
            <th>Severidade</th>
            <th>Status</th>
            <th>Detalhes</th>
          </tr>
        </thead>
        <tbody>
          ${redlineRows}
        </tbody>
      </table>

      <p style="margin-top: 40px; text-align: center; color: #9ca3af; font-size: 12px;">
        Gerado por Iudex - Plataforma Juridica com IA
      </p>
    </body>
    </html>
  `;

  // Abrir nova janela para impressao/salvamento como PDF
  const printWindow = window.open('', '_blank');
  if (printWindow) {
    printWindow.document.write(html);
    printWindow.document.close();
    // Dar tempo para carregar e depois abrir dialogo de impressao
    setTimeout(() => {
      printWindow.print();
    }, 500);
  } else {
    // Fallback: baixar como HTML
    const blob = new Blob([html], { type: 'text/html' });
    triggerDownload(blob, `audit-report-${runId}.html`);
  }
}

function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
