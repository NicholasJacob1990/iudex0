export interface HilIssue {
    id: string;
    type: string;
    fix_type?: string;
    severity?: string;
    description?: string;
    suggestion?: string;
    reference?: string;
    suggested_section?: string;
    compression_ratio?: number;
    raw_evidence?: Array<string | { snippet?: string; text?: string }>;
    evidence_formatted?: string;
    verdict?: string;
    source?: string;
    origin?: string;
    [key: string]: any;
}

const hashString = (value: string) => {
    let hash = 0;
    for (let i = 0; i < value.length; i += 1) {
        hash = (hash << 5) - hash + value.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash);
};

const truncateText = (value: string, max = 180) => {
    if (!value) return '';
    const cleaned = String(value).replace(/\s+/g, ' ').trim();
    if (cleaned.length <= max) return cleaned;
    return `${cleaned.slice(0, max)}...`;
};

export const buildPreventiveHilIssues = (audit: any): HilIssue[] => {
    if (!audit || typeof audit !== 'object') return [];
    const issues: HilIssue[] = [];

    const asList = (value: any) => (Array.isArray(value) ? value : []);
    const asText = (value: any) => {
        if (value === null || value === undefined) return '';
        if (typeof value === 'string') return value.trim();
        return String(value).trim();
    };
    const buildId = (prefix: string, seed: string, idx: number) => {
        const base = seed || `${prefix}_${idx}`;
        return `${prefix}_${hashString(base)}`;
    };
    const mapSeverity = (value?: string) => {
        const normalized = String(value || '').toLowerCase();
        if (normalized.includes('crit') || normalized.includes('alta')) return 'warning';
        if (normalized.includes('media') || normalized.includes('média')) return 'warning';
        return 'info';
    };
    const buildEvidence = (snippet: string) => {
        const cleaned = asText(snippet);
        if (!cleaned) return undefined;
        return [{ snippet: cleaned }];
    };

    asList(audit.omissoes_criticas).forEach((item: any, idx: number) => {
        const isObj = item && typeof item === 'object' && !Array.isArray(item);
        const tipo = isObj ? asText(item.tipo) : '';
        const gravidade = isObj ? asText(item.gravidade) : '';
        const impacto = isObj ? asText(item.impacto) : '';
        const local = isObj ? asText(item.localizacao_formatado) : '';
        const rawSnippet = isObj ? asText(item.trecho_raw) : '';
        const formattedSnippet = isObj ? asText(item.trecho_formatado) : ''; // New: Extract formatted snippet if available
        const veredito = isObj ? asText(item.veredito) : ''; // New: Extract verdict if available
        const fallback = !isObj ? asText(item) : '';
        const baseDesc = impacto || fallback || 'Conteudo presente no RAW nao apareceu no texto formatado.';
        const description = `Omissao critica${tipo ? ` (${tipo})` : ''}: ${truncateText(baseDesc, 220)}`;
        const suggestion = rawSnippet
            ? 'Inserir o trecho omitido com base no RAW.'
            : 'Revisar e inserir o conteudo omitido.';
        const seed = isObj ? JSON.stringify(item) : baseDesc;
        const issue: HilIssue = {
            id: buildId('preventive_omissao', seed, idx),
            type: 'preventive_omissao',
            fix_type: 'content',
            severity: mapSeverity(gravidade),
            description,
            suggestion,
            source: 'preventive_audit',
            origin: 'preventive_audit',
            verdict: veredito || 'Em análise', // New
            evidence_formatted: formattedSnippet, // New
        };
        if (local) issue.suggested_section = local;
        const evidence = buildEvidence(rawSnippet);
        if (evidence) issue.raw_evidence = evidence;
        issues.push(issue);
    });

    asList(audit.distorcoes).forEach((item: any, idx: number) => {
        const isObj = item && typeof item === 'object' && !Array.isArray(item);
        const tipo = isObj ? asText(item.tipo) : '';
        const gravidade = isObj ? asText(item.gravidade) : '';
        const rawSnippet = isObj ? asText(item.trecho_raw) : '';
        const formattedSnippet = isObj ? asText(item.trecho_formatado) : '';
        const correcao = isObj ? asText(item.correcao) : '';
        const veredito = isObj ? asText(item.veredito) : ''; // New
        const fallback = !isObj ? asText(item) : '';
        const detailParts = [
            rawSnippet ? `RAW: "${truncateText(rawSnippet, 120)}"` : '',
            formattedSnippet ? `Formatado: "${truncateText(formattedSnippet, 120)}"` : '',
            correcao ? `Correcao: ${truncateText(correcao, 140)}` : '',
        ].filter(Boolean);
        const baseDesc = detailParts.join(' | ') || fallback || 'Revisar diferenca entre RAW e formatado.';
        const description = `Distorcao${tipo ? ` (${tipo})` : ''}: ${truncateText(baseDesc, 240)}`;
        const suggestion = correcao
            ? `Corrigir para: ${truncateText(correcao, 180)}`
            : 'Corrigir conforme RAW.';
        const seed = isObj ? JSON.stringify(item) : baseDesc;
        const issue: HilIssue = {
            id: buildId('preventive_distorcao', seed, idx),
            type: 'preventive_distorcao',
            fix_type: 'content',
            severity: mapSeverity(gravidade),
            description,
            suggestion,
            source: 'legal_audit',
            origin: 'preventive_audit',
            verdict: veredito || 'Em análise', // New
            evidence_formatted: formattedSnippet, // New
        };
        const evidence = buildEvidence(rawSnippet);
        if (evidence) issue.raw_evidence = evidence;
        issues.push(issue);
    });

    asList(audit.alucinacoes).forEach((item: any, idx: number) => {
        const isObj = item && typeof item === 'object' && !Array.isArray(item);
        const confianca = isObj ? asText(item.confianca) : '';
        const trechoFormatado = isObj ? asText(item.trecho_formatado) : '';
        const acao = isObj ? asText(item.acao_sugerida) : '';
        const veredito = isObj ? asText(item.veredito) : ''; // New
        const fallback = !isObj ? asText(item) : '';
        const baseDesc = trechoFormatado || fallback || 'Trecho inexistente no RAW.';
        const description = `Possivel alucinacao${confianca ? ` (${confianca})` : ''}: ${truncateText(baseDesc, 220)}`;
        const suggestion = acao
            ? `Acao sugerida: ${acao}`
            : 'Revisar e remover se nao houver suporte no RAW.';
        const seed = isObj ? JSON.stringify(item) : baseDesc;
        issues.push({
            id: buildId('preventive_alucinacao', seed, idx),
            type: 'preventive_alucinacao',
            fix_type: 'content',
            severity: mapSeverity(confianca),
            description,
            suggestion,
            source: 'legal_audit',
            origin: 'preventive_audit',
            verdict: veredito || 'Em análise', // New
            evidence_formatted: trechoFormatado, // New
        });
    });

    asList(audit.problemas_estruturais).forEach((item: any, idx: number) => {
        const isObj = item && typeof item === 'object' && !Array.isArray(item);
        const tipo = isObj ? asText(item.tipo) : '';
        const local = isObj ? asText(item.localizacao) : '';
        const descricao = isObj ? asText(item.descricao) : '';
        const veredito = isObj ? asText(item.veredito) : ''; // New
        const fallback = !isObj ? asText(item) : '';
        const baseDesc = descricao || fallback || local || 'Revisar estrutura do documento.';
        const description = `Problema estrutural${tipo ? ` (${tipo})` : ''}: ${truncateText(baseDesc, 220)}`;
        const suggestion = local
            ? `Revisar estrutura em: ${truncateText(local, 140)}`
            : 'Ajustar estrutura conforme descricao.';
        const seed = isObj ? JSON.stringify(item) : baseDesc;
        const issue: HilIssue = {
            id: buildId('preventive_estrutural', seed, idx),
            type: 'preventive_estrutural',
            fix_type: 'structural',
            severity: 'info',
            description,
            suggestion,
            source: 'legal_audit',
            origin: 'preventive_audit',
            verdict: veredito || 'Em análise', // New
        };
        if (local) issue.suggested_section = local;
        issues.push(issue);
    });

    asList(audit.problemas_contexto).forEach((item: any, idx: number) => {
        const isObj = item && typeof item === 'object' && !Array.isArray(item);
        const tipo = isObj ? asText(item.tipo) : '';
        const local = isObj ? asText(item.localizacao) : '';
        const sugestao = isObj ? asText(item.sugestao) : '';
        const veredito = isObj ? asText(item.veredito) : ''; // New
        const fallback = !isObj ? asText(item) : '';
        const baseDesc = local || fallback || 'Revisar contexto e transicoes.';
        const description = `Problema de contexto${tipo ? ` (${tipo})` : ''}: ${truncateText(baseDesc, 220)}`;
        const suggestion = sugestao
            ? truncateText(sugestao, 200)
            : 'Ajustar transicao/contexto conforme necessario.';
        const seed = isObj ? JSON.stringify(item) : baseDesc;
        const issue: HilIssue = {
            id: buildId('preventive_contexto', seed, idx),
            type: 'preventive_contexto',
            fix_type: 'content',
            severity: 'info',
            description,
            suggestion,
            source: 'legal_audit',
            origin: 'preventive_audit',
            verdict: veredito || 'Em análise', // New
        };
        if (local) issue.suggested_section = local;
        issues.push(issue);
    });

    return issues;
};

export const buildQualityHilIssues = (analysis?: {
    missing_laws?: string[];
    missing_sumulas?: string[];
    missing_decretos?: string[];
    missing_julgados?: string[];
    compression_warning?: string;
} | null): HilIssue[] => {
    if (!analysis) return [];
    const issues: HilIssue[] = [];
    const asList = (value: any) => (Array.isArray(value) ? value : []);
    const buildId = (prefix: string, seed: string, idx: number) => {
        const base = seed || `${prefix}_${idx}`;
        return `${prefix}_${hashString(base)}`;
    };
    const addIssue = (prefix: string, type: string, reference: string, description: string, suggestion: string, severity = "warning") => {
        issues.push({
            id: buildId(prefix, `${type}:${reference}`, issues.length),
            type,
            fix_type: "content",
            severity,
            reference,
            description: truncateText(description, 220),
            suggestion: truncateText(suggestion, 200),
            source: "quality",
            origin: "quality",
        });
    };

    asList(analysis.missing_laws).forEach((law: any) => {
        const ref = String(law || "").trim();
        if (!ref) return;
        addIssue(
            "quality_missing_law",
            "missing_law",
            ref,
            `Lei possivelmente ausente: ${ref}`,
            `Inserir referência contextual à Lei ${ref} se foi mencionada no áudio.`,
            "warning"
        );
    });

    asList(analysis.missing_sumulas).forEach((sumula: any) => {
        const ref = String(sumula || "").trim();
        if (!ref) return;
        addIssue(
            "quality_missing_sumula",
            "missing_sumula",
            ref,
            `Súmula possivelmente ausente: ${ref}`,
            `Inserir referência contextual à ${ref} se foi mencionada no áudio.`,
            "warning"
        );
    });

    asList(analysis.missing_julgados).forEach((julgado: any) => {
        const ref = String(julgado || "").trim();
        if (!ref) return;
        addIssue(
            "quality_missing_julgado",
            "missing_julgado",
            ref,
            `Julgado possivelmente ausente: ${ref}`,
            "Inserir referência contextual ou revisar o trecho correspondente.",
            "info"
        );
    });

    asList(analysis.missing_decretos).forEach((decreto: any) => {
        const ref = String(decreto || "").trim();
        if (!ref) return;
        addIssue(
            "quality_missing_decreto",
            "missing_decreto",
            ref,
            `Decreto possivelmente ausente: ${ref}`,
            `Inserir referência contextual ao Decreto ${ref} se foi mencionado no áudio.`,
            "info"
        );
    });

    return issues;
};
