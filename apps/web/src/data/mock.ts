export type HistoryGroup = 'Hoje' | 'Últimos 7 dias' | 'Últimos 30 dias';

export const minuteHistory = [
  {
    id: 'hist-1',
    title: 'Análise Jurídica Comparativa entre Estudo Técnico Preliminar e Termo de Referência',
    date: '2025-11-18T02:30:00',
    group: 'Hoje' as HistoryGroup,
    jurisdiction: 'TJSP • Cível',
    tokens: 1860,
  },
  {
    id: 'hist-2',
    title: 'Requerimento de Nicholas Jacob na Comarca de São Paulo',
    date: '2025-11-16T23:03:00',
    group: 'Últimos 7 dias' as HistoryGroup,
    jurisdiction: 'TJSP • Fazendária',
    tokens: 920,
  },
  {
    id: 'hist-3',
    title: 'Petição Inicial de Nicholas Jacob para Processo Cível em São Paulo',
    date: '2025-11-16T21:25:00',
    group: 'Últimos 7 dias' as HistoryGroup,
    jurisdiction: 'TJSP • 3ª Vara Cível',
    tokens: 1320,
  },
  {
    id: 'hist-4',
    title: 'Análise de Comunicação via WhatsApp em Caso de Saúde',
    date: '2025-11-16T02:46:00',
    group: 'Últimos 7 dias' as HistoryGroup,
    jurisdiction: 'CNJ • Saúde',
    tokens: 640,
  },
  {
    id: 'hist-5',
    title: 'Análise da Admissibilidade da Prova Pericial nos Juizados Especiais',
    date: '2025-11-15T12:54:00',
    group: 'Últimos 30 dias' as HistoryGroup,
    jurisdiction: 'TRF3 • JEF',
    tokens: 1480,
  },
];

export const quickStats = [
  {
    label: 'Minutas Geradas',
    value: '248',
    trend: '+18% esta semana',
    color: 'from-blush to-primary',
  },
  {
    label: 'Documentos Importados',
    value: '112',
    trend: '8 pendentes de revisão',
    color: 'from-lavender to-primary',
  },
  {
    label: 'Modelos Preferidos',
    value: '32',
    trend: '5 atualizados',
    color: 'from-emerald to-primary',
  },
  {
    label: 'Tempo Médio',
    value: '3m12s',
    trend: 'por minuta gerada',
    color: 'from-primary to-clay',
  },
];

export const resourceShortcuts = [
  { id: 'podcasts', label: 'Podcasts', description: 'Resumo em áudio de decisões', icon: 'Mic' },
  { id: 'diagrams', label: 'Diagramas', description: 'Mapas mentais automáticos', icon: 'Share2' },
  { id: 'sharing', label: 'Compartilhamentos', description: 'Pastas e grupos', icon: 'Users' },
  { id: 'cnj', label: 'Metadados CNJ e Comunicacoes DJEN', description: 'Processos e publicacoes oficiais', icon: 'Newspaper' },
];

export const modelsBoard = [
  {
    id: 'model-1',
    title: 'Parecer • Novo RIC • Inexigibilidade',
    tokens: 10962,
    selected: false,
  },
  {
    id: 'model-2',
    title: 'Análise Técnica de Adesão • Saúde',
    tokens: 8421,
    selected: true,
  },
];

export const legislationSaved = [
  {
    id: 'leg-1',
    title: 'Lei Ordinária nº 14.133/2021',
    status: 'Atualizada em 34 minutos',
    articles: 192,
  },
  {
    id: 'leg-2',
    title: 'Lei Geral de Proteção de Dados',
    status: 'Consolidada',
    articles: 65,
  },
];

export const libraryItems = [
  {
    id: 'lib-1',
    name: 'Lei Ordinária nº 14.133/2021',
    type: 'Legislação',
    tokens: 6886,
    updatedAt: 'há 34 minutos',
  },
  {
    id: 'lib-2',
    name: '3B3E0C37379047BB344A50F4C30FE121.pdf',
    type: 'Documento',
    tokens: 1043,
    updatedAt: 'há 1 dia',
  },
  {
    id: 'lib-3',
    name: 'WhatsApp Chat • +55 11 99945-6401',
    type: 'Documento',
    tokens: 53,
    updatedAt: 'há 1 dia',
  },
];

export const documentUploads = [
  {
    id: 'doc-1',
    name: 'Contrato Social - Revisão Final.pdf',
    size: '2.4 MB',
    status: 'Processado',
  },
  {
    id: 'doc-2',
    name: 'Relatório Médico Assis.pdf',
    size: '1.1 MB',
    status: 'OCR em andamento',
  },
];

export const webQueries = [
  { id: 'web-1', query: 'Repercussão geral STF contratos administrativos', date: 'há 2 min' },
  { id: 'web-2', query: 'Temas repetitivos STJ saúde suplementar', date: 'há 12 min' },
];

export const quickActions = [
  {
    id: 'action-1',
    title: 'Nova Minuta',
    description: 'Gere petições completas com revisão cruzada',
    icon: 'Feather',
  },
  {
    id: 'action-2',
    title: 'Importar Documentos',
    description: 'Junte PDFs, DOCX, ZIP e imagens',
    icon: 'Upload',
  },
  {
    id: 'action-3',
    title: 'Buscar Jurisprudência STF',
    description: 'Entregue precedentes com repercussão geral',
    icon: 'Gavel',
  },
];

export const librarians = [
  {
    id: 'lib-routines',
    name: 'Rotinas Cíveis',
    description: 'Documentos, modelos e teses usados em demandas cíveis',
    resources: ['Documentos', 'Modelos', 'Jurisprudência'],
    updatedAt: 'há 2h',
  },
  {
    id: 'lib-saude',
    name: 'Saúde Suplementar',
    description: 'Base focada em planos de saúde e demandas consumeristas',
    resources: ['Documentos', 'Jurisprudência', 'Legislação'],
    updatedAt: 'há 1 dia',
  },
];

export const contextMentions = [
  { id: 'ctx-pje', label: '@PJe-Saude', description: 'Conjunto salvo para petições em saúde' },
  { id: 'ctx-biblio', label: '@Bibliotecário Cível', description: 'Ativa todos os recursos civis' },
  { id: 'ctx-modelo', label: '@Modelo Contrato', description: 'Modelo padronizado de contrato' },
];
