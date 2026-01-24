export interface PreventiveMarkdownMeta {
    statusRaw: string | null;
    nota: number | null;
    gravidadeRaw: string | null;
    shouldBlock: boolean;
    label: string;
}

export interface PreventiveAuditStatus {
    statusLabel: string;
    statusVariant: 'destructive' | 'secondary' | 'outline';
    shouldBlock: boolean;
    shouldBlockDisplay: boolean;
    blockReason: string;
    meta: PreventiveMarkdownMeta;
}

export const parsePreventiveAuditMarkdownMeta = (content: string): PreventiveMarkdownMeta => {
    const statusMatch =
        content.match(/^\s*\*\*Status:\*\*\s*(.+)\s*$/mi) ||
        content.match(/^\s*Status:\s*(.+)\s*$/mi);
    const statusRaw = statusMatch?.[1]?.trim() || null;

    const notaMatch =
        content.match(/^\s*\*\*Nota de Fidelidade:\*\*\s*([0-9]+(?:[\\.,][0-9]+)?)\s*\/\s*10\s*$/mi) ||
        content.match(/^\s*Nota de Fidelidade:\s*([0-9]+(?:[\\.,][0-9]+)?)\s*\/\s*10\s*$/mi);
    const nota = notaMatch ? Number(String(notaMatch[1]).replace(',', '.')) : null;

    const gravidadeMatch =
        content.match(/^\s*\*\*Gravidade Geral:\*\*\s*(.+)\s*$/mi) ||
        content.match(/^\s*Gravidade Geral:\s*(.+)\s*$/mi);
    const gravidadeRaw = gravidadeMatch?.[1]?.trim() || null;

    const normalizedStatus = (statusRaw || '').toLowerCase();
    const shouldBlock =
        normalizedStatus.includes('requer') ||
        normalizedStatus.includes('revisão') ||
        content.toLowerCase().includes('pausar para revisão humana') ||
        content.toLowerCase().includes('pausar para revisão hil');

    let label = 'Relatório (MD)';
    if (statusRaw) {
        if (normalizedStatus.includes('aprovado')) label = 'Aprovado (MD)';
        else if (normalizedStatus.includes('revisão')) label = 'Revisão (MD)';
    }

    return { statusRaw, nota, gravidadeRaw, shouldBlock, label };
};

export const buildPreventiveAuditStatus = (input: {
    audit?: any | null;
    auditMarkdown?: string | null;
    loading?: boolean;
    recommendation?: any | null;
}): PreventiveAuditStatus => {
    const audit = input.audit ?? null;
    const auditMarkdown = input.auditMarkdown ?? '';
    const recommendation = input.recommendation ?? audit?.recomendacao_hil ?? null;
    const shouldBlock = Boolean(recommendation?.pausar_para_revisao);
    const blockReason = typeof recommendation?.motivo === 'string' && recommendation.motivo.trim()
        ? recommendation.motivo.trim()
        : 'Auditoria preventiva recomenda revisão humana.';

    const meta = parsePreventiveAuditMarkdownMeta(auditMarkdown || '');
    const shouldBlockDisplay = audit ? shouldBlock : Boolean(auditMarkdown && meta.shouldBlock);
    const statusLabel = audit
        ? (shouldBlock ? 'Revisão recomendada' : 'Sem alertas críticos')
        : input.loading
            ? 'Carregando'
            : auditMarkdown
                ? meta.label
                : 'Sem relatório';
    const statusVariant = shouldBlockDisplay ? 'destructive' : (audit || auditMarkdown) ? 'secondary' : 'outline';

    return {
        statusLabel,
        statusVariant,
        shouldBlock,
        shouldBlockDisplay,
        blockReason,
        meta,
    };
};
