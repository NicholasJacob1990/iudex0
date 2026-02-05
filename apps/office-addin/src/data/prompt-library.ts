/**
 * Biblioteca de prompts curados para edicao de documentos juridicos.
 *
 * Gap 10: Fornece templates de instrucoes pre-definidas para o DraftPanel,
 * organizados por categoria para facilitar a navegacao.
 */

export type PromptCategory = 'drafting' | 'editing' | 'analysis' | 'translation' | 'compliance';

export interface PromptTemplate {
  id: string;
  name: string;
  description: string;
  category: PromptCategory;
  prompt: string;
  /** Icone opcional (nome do icone ou emoji) */
  icon?: string;
  /** Tags para busca */
  tags?: string[];
}

/**
 * Biblioteca de prompts curados para uso no Word Add-in.
 * Todos os prompts sao focados em contexto juridico brasileiro.
 */
export const PROMPT_LIBRARY: PromptTemplate[] = [
  // ── Categoria: Editing (Edicao de texto) ──────────────────────

  {
    id: 'simplify-legal',
    name: 'Simplificar linguagem',
    description: 'Torna o texto mais acessivel mantendo precisao juridica',
    category: 'editing',
    prompt:
      'Simplifique este texto juridico para linguagem mais acessivel ao leigo, mantendo a precisao tecnica e os termos legais essenciais. Evite jargoes desnecessarios e use frases mais curtas.',
    icon: 'simplify',
    tags: ['simplificar', 'acessivel', 'leigo', 'clareza'],
  },
  {
    id: 'formalize',
    name: 'Formalizar texto',
    description: 'Adiciona formalidade e rigor tecnico',
    category: 'editing',
    prompt:
      'Formalize este texto com linguagem juridica adequada, adicionando os termos tecnicos apropriados e estrutura formal. Mantenha a precisao e adicione referencias a institutos juridicos quando pertinente.',
    icon: 'formal',
    tags: ['formal', 'tecnico', 'juridico'],
  },
  {
    id: 'improve-clarity',
    name: 'Melhorar clareza',
    description: 'Corrige erros e melhora a redacao',
    category: 'editing',
    prompt:
      'Melhore a clareza e redacao deste texto, corrigindo erros gramaticais, eliminando ambiguidades e tornando as frases mais diretas. Mantenha o significado original e o tom juridico.',
    icon: 'clarity',
    tags: ['clareza', 'gramatica', 'redacao'],
  },
  {
    id: 'make-concise',
    name: 'Tornar mais conciso',
    description: 'Remove redundancias e prolixidade',
    category: 'editing',
    prompt:
      'Torne este texto mais conciso, removendo redundancias, repeticoes e prolixidade desnecessaria. Mantenha todas as informacoes essenciais em menos palavras.',
    icon: 'concise',
    tags: ['conciso', 'resumir', 'reduzir'],
  },
  {
    id: 'add-definitions',
    name: 'Adicionar definicoes',
    description: 'Sugere definicoes para termos tecnicos',
    category: 'editing',
    prompt:
      'Identifique os termos tecnicos neste texto que precisam de definicao e sugira definicoes claras e precisas para cada um, no formato padrao de clausula de definicoes.',
    icon: 'definitions',
    tags: ['definicoes', 'termos', 'glossario'],
  },

  // ── Categoria: Drafting (Redacao de clausulas) ────────────────

  {
    id: 'expand-clause',
    name: 'Expandir clausula',
    description: 'Adiciona detalhes e protecoes',
    category: 'drafting',
    prompt:
      'Expanda esta clausula adicionando detalhes, excecoes, condicoes e protecoes tipicas para este tipo de disposicao contratual. Considere cenarios de inadimplemento e remedios disponiveis.',
    icon: 'expand',
    tags: ['expandir', 'detalhar', 'protecao'],
  },
  {
    id: 'add-penalty-clause',
    name: 'Adicionar penalidades',
    description: 'Cria clausula de penalidades por descumprimento',
    category: 'drafting',
    prompt:
      'Crie ou aprimore esta clausula adicionando penalidades proporcionais por descumprimento, incluindo multa moratoria, multa compensatoria e possibilidade de resolucao contratual.',
    icon: 'penalty',
    tags: ['multa', 'penalidade', 'descumprimento'],
  },
  {
    id: 'add-confidentiality',
    name: 'Clausula de confidencialidade',
    description: 'Adiciona protecao de informacoes confidenciais',
    category: 'drafting',
    prompt:
      'Crie ou aprimore uma clausula de confidencialidade robusta, definindo informacoes confidenciais, obrigacoes das partes, prazo de vigencia, excecoes e penalidades por violacao.',
    icon: 'confidential',
    tags: ['confidencialidade', 'sigilo', 'NDA'],
  },
  {
    id: 'add-termination',
    name: 'Clausula de rescisao',
    description: 'Adiciona hipoteses de rescisao contratual',
    category: 'drafting',
    prompt:
      'Crie ou aprimore uma clausula de rescisao contratual completa, incluindo hipoteses de rescisao por justa causa, sem justa causa, por inadimplemento, prazos de aviso previo e efeitos da rescisao.',
    icon: 'termination',
    tags: ['rescisao', 'terminacao', 'encerramento'],
  },
  {
    id: 'add-force-majeure',
    name: 'Clausula de forca maior',
    description: 'Adiciona protecao para eventos imprevisiveis',
    category: 'drafting',
    prompt:
      'Crie ou aprimore uma clausula de forca maior e caso fortuito, definindo eventos qualificadores, procedimentos de notificacao, efeitos sobre as obrigacoes e limites de aplicacao.',
    icon: 'force-majeure',
    tags: ['forca maior', 'caso fortuito', 'imprevisto'],
  },
  {
    id: 'add-dispute-resolution',
    name: 'Clausula de resolucao de disputas',
    description: 'Adiciona mecanismos de solucao de conflitos',
    category: 'drafting',
    prompt:
      'Crie ou aprimore uma clausula de resolucao de disputas, incluindo negociacao direta, mediacao como etapa previa, arbitragem ou foro judicial, com definicao de prazos e procedimentos.',
    icon: 'dispute',
    tags: ['disputa', 'arbitragem', 'foro', 'mediacao'],
  },
  {
    id: 'protect-contractor',
    name: 'Proteger contratante',
    description: 'Adiciona protecoes para quem contrata',
    category: 'drafting',
    prompt:
      'Revise este texto adicionando protecoes para o contratante (parte que paga/recebe servicos), incluindo garantias, prazos, penalidades por atraso e direitos de fiscalizacao.',
    icon: 'shield',
    tags: ['contratante', 'protecao', 'garantia'],
  },
  {
    id: 'protect-contractor-party',
    name: 'Proteger contratado',
    description: 'Adiciona protecoes para quem presta servico',
    category: 'drafting',
    prompt:
      'Revise este texto adicionando protecoes para o contratado (parte que presta servicos), incluindo limitacao de responsabilidade, condicoes de pagamento e direitos de propriedade intelectual.',
    icon: 'shield-alt',
    tags: ['contratado', 'prestador', 'limitacao'],
  },

  // ── Categoria: Analysis (Analise) ─────────────────────────────

  {
    id: 'summarize',
    name: 'Resumir',
    description: 'Cria resumo executivo do texto',
    category: 'analysis',
    prompt:
      'Crie um resumo executivo deste texto, destacando os pontos principais, obrigacoes das partes, prazos importantes e implicacoes juridicas. Use bullet points para clareza.',
    icon: 'summary',
    tags: ['resumo', 'sumario', 'sintese'],
  },
  {
    id: 'find-risks',
    name: 'Identificar riscos',
    description: 'Analisa riscos e pontos de atencao',
    category: 'analysis',
    prompt:
      'Analise este texto e identifique potenciais riscos juridicos, ambiguidades, lacunas e pontos que requerem atencao especial. Sugira mitigacoes para cada risco identificado.',
    icon: 'risk',
    tags: ['risco', 'analise', 'atencao'],
  },
  {
    id: 'check-compliance',
    name: 'Verificar conformidade',
    description: 'Analisa conformidade legal',
    category: 'analysis',
    prompt:
      'Analise este texto quanto a conformidade com a legislacao brasileira aplicavel, identificando potenciais violacoes ou clausulas que podem ser consideradas abusivas ou nulas.',
    icon: 'compliance',
    tags: ['conformidade', 'legalidade', 'abusiva'],
  },
  {
    id: 'compare-versions',
    name: 'Comparar com padrao',
    description: 'Compara com praticas de mercado',
    category: 'analysis',
    prompt:
      'Compare esta clausula com as praticas padrao de mercado para este tipo de contrato, identificando pontos que estao abaixo ou acima do padrao usual.',
    icon: 'compare',
    tags: ['comparar', 'padrao', 'mercado'],
  },
  {
    id: 'extract-obligations',
    name: 'Extrair obrigacoes',
    description: 'Lista obrigacoes de cada parte',
    category: 'analysis',
    prompt:
      'Extraia e liste todas as obrigacoes de cada parte mencionada neste texto, organizadas por parte (contratante/contratado) e tipo de obrigacao (fazer, nao fazer, dar).',
    icon: 'list',
    tags: ['obrigacoes', 'partes', 'extrair'],
  },

  // ── Categoria: Translation (Traducao) ─────────────────────────

  {
    id: 'translate-pt-en',
    name: 'Traduzir PT -> EN',
    description: 'Traducao juridica para ingles',
    category: 'translation',
    prompt:
      'Traduza este texto juridico do portugues para o ingles americano, mantendo a terminologia legal apropriada e adaptando conceitos do direito brasileiro para equivalentes do common law quando aplicavel.',
    icon: 'translate',
    tags: ['ingles', 'english', 'traduzir'],
  },
  {
    id: 'translate-en-pt',
    name: 'Traduzir EN -> PT',
    description: 'Traducao juridica para portugues',
    category: 'translation',
    prompt:
      'Traduza este texto juridico do ingles para o portugues brasileiro, mantendo a terminologia legal apropriada e adaptando conceitos do common law para equivalentes do direito brasileiro.',
    icon: 'translate',
    tags: ['portugues', 'brazilian', 'traduzir'],
  },
  {
    id: 'translate-es-pt',
    name: 'Traduzir ES -> PT',
    description: 'Traducao juridica do espanhol',
    category: 'translation',
    prompt:
      'Traduza este texto juridico do espanhol para o portugues brasileiro, mantendo a terminologia legal apropriada e adaptando termos do direito hispano-americano para o brasileiro.',
    icon: 'translate',
    tags: ['espanhol', 'spanish', 'traduzir'],
  },

  // ── Categoria: Compliance (LGPD e Regulatorio) ────────────────

  {
    id: 'add-lgpd-clause',
    name: 'Clausula LGPD',
    description: 'Adiciona clausula de protecao de dados',
    category: 'compliance',
    prompt:
      'Crie ou aprimore uma clausula de protecao de dados pessoais conforme a LGPD, definindo papeis (controlador/operador), finalidades do tratamento, medidas de seguranca e direitos dos titulares.',
    icon: 'privacy',
    tags: ['LGPD', 'dados', 'privacidade'],
  },
  {
    id: 'add-anticorruption',
    name: 'Clausula anticorrupcao',
    description: 'Adiciona compromissos de compliance',
    category: 'compliance',
    prompt:
      'Crie ou aprimore uma clausula anticorrupcao conforme a Lei Anticorrupcao (Lei 12.846/2013) e FCPA, incluindo declaracoes, compromissos e direito de auditoria.',
    icon: 'anticorruption',
    tags: ['anticorrupcao', 'compliance', 'FCPA'],
  },
  {
    id: 'add-esocial',
    name: 'Conformidade trabalhista',
    description: 'Verifica aspectos trabalhistas',
    category: 'compliance',
    prompt:
      'Analise este texto quanto a conformidade trabalhista, verificando se ha riscos de vinculo empregaticio, terceirizacao irregular ou descumprimento de normas de saude e seguranca.',
    icon: 'labor',
    tags: ['trabalhista', 'CLT', 'terceirizacao'],
  },
];

/**
 * Agrupa prompts por categoria.
 */
export function getPromptsByCategory(): Record<PromptCategory, PromptTemplate[]> {
  const grouped: Record<PromptCategory, PromptTemplate[]> = {
    editing: [],
    drafting: [],
    analysis: [],
    translation: [],
    compliance: [],
  };

  for (const prompt of PROMPT_LIBRARY) {
    grouped[prompt.category].push(prompt);
  }

  return grouped;
}

/**
 * Busca prompts por texto (nome, descricao ou tags).
 */
export function searchPrompts(query: string): PromptTemplate[] {
  const lowerQuery = query.toLowerCase();

  return PROMPT_LIBRARY.filter((p) => {
    const inName = p.name.toLowerCase().includes(lowerQuery);
    const inDescription = p.description.toLowerCase().includes(lowerQuery);
    const inTags = p.tags?.some((t) => t.toLowerCase().includes(lowerQuery));
    return inName || inDescription || inTags;
  });
}

/**
 * Retorna labels amigaveis para as categorias.
 */
export const CATEGORY_LABELS: Record<PromptCategory, string> = {
  editing: 'Edicao',
  drafting: 'Redacao',
  analysis: 'Analise',
  translation: 'Traducao',
  compliance: 'Compliance',
};

/**
 * Retorna icones para as categorias.
 */
export const CATEGORY_ICONS: Record<PromptCategory, string> = {
  editing: 'edit',
  drafting: 'file-text',
  analysis: 'search',
  translation: 'globe',
  compliance: 'shield-check',
};
