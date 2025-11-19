/**
 * Constantes compartilhadas do Iudex
 */

export const APP_NAME = 'Iudex';
export const APP_DESCRIPTION = 'Plataforma Jurídica com IA Multi-Agente';
export const APP_VERSION = '0.1.0';

// Limites
export const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB
export const MAX_DOCUMENTS_PER_USER = 1000;
export const MAX_AUDIO_SIZE = 500 * 1024 * 1024; // 500MB
export const MAX_CONTEXT_TOKENS = 3000000; // 3 milhões de tokens

// Tokens e custos (estimados)
export const TOKEN_COSTS = {
  CLAUDE_SONNET_4_5: {
    input: 0.000003, // $3 por 1M tokens
    output: 0.000015, // $15 por 1M tokens
  },
  GEMINI_2_5_PRO: {
    input: 0.00000125, // $1.25 por 1M tokens
    output: 0.000005, // $5 por 1M tokens
  },
  GPT_5: {
    input: 0.000005, // $5 por 1M tokens (estimado)
    output: 0.000015, // $15 por 1M tokens (estimado)
  },
};

// Formatos de arquivo suportados
export const SUPPORTED_DOCUMENT_FORMATS = [
  'pdf',
  'docx',
  'doc',
  'odt',
  'txt',
  'rtf',
  'html',
];

export const SUPPORTED_IMAGE_FORMATS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'];

export const SUPPORTED_AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac'];

export const SUPPORTED_VIDEO_FORMATS = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'];

// Tribunais brasileiros
export const TRIBUNAIS_SUPERIORES = ['STF', 'STJ', 'TST', 'TSE', 'STM'];

export const TRIBUNAIS_REGIONAIS_FEDERAIS = ['TRF1', 'TRF2', 'TRF3', 'TRF4', 'TRF5', 'TRF6'];

export const TRIBUNAIS_TRABALHO = [
  'TRT1',
  'TRT2',
  'TRT3',
  'TRT4',
  'TRT5',
  'TRT6',
  'TRT7',
  'TRT8',
  'TRT9',
  'TRT10',
  'TRT11',
  'TRT12',
  'TRT13',
  'TRT14',
  'TRT15',
  'TRT16',
  'TRT17',
  'TRT18',
  'TRT19',
  'TRT20',
  'TRT21',
  'TRT22',
  'TRT23',
  'TRT24',
];

export const ESTADOS_BRASILEIROS = [
  { sigla: 'AC', nome: 'Acre' },
  { sigla: 'AL', nome: 'Alagoas' },
  { sigla: 'AP', nome: 'Amapá' },
  { sigla: 'AM', nome: 'Amazonas' },
  { sigla: 'BA', nome: 'Bahia' },
  { sigla: 'CE', nome: 'Ceará' },
  { sigla: 'DF', nome: 'Distrito Federal' },
  { sigla: 'ES', nome: 'Espírito Santo' },
  { sigla: 'GO', nome: 'Goiás' },
  { sigla: 'MA', nome: 'Maranhão' },
  { sigla: 'MT', nome: 'Mato Grosso' },
  { sigla: 'MS', nome: 'Mato Grosso do Sul' },
  { sigla: 'MG', nome: 'Minas Gerais' },
  { sigla: 'PA', nome: 'Pará' },
  { sigla: 'PB', nome: 'Paraíba' },
  { sigla: 'PR', nome: 'Paraná' },
  { sigla: 'PE', nome: 'Pernambuco' },
  { sigla: 'PI', nome: 'Piauí' },
  { sigla: 'RJ', nome: 'Rio de Janeiro' },
  { sigla: 'RN', nome: 'Rio Grande do Norte' },
  { sigla: 'RS', nome: 'Rio Grande do Sul' },
  { sigla: 'RO', nome: 'Rondônia' },
  { sigla: 'RR', nome: 'Roraima' },
  { sigla: 'SC', nome: 'Santa Catarina' },
  { sigla: 'SP', nome: 'São Paulo' },
  { sigla: 'SE', nome: 'Sergipe' },
  { sigla: 'TO', nome: 'Tocantins' },
];

// Rotas da API
export const API_ROUTES = {
  AUTH: {
    LOGIN: '/api/auth/login',
    REGISTER: '/api/auth/register',
    LOGOUT: '/api/auth/logout',
    REFRESH: '/api/auth/refresh',
    ME: '/api/auth/me',
  },
  DOCUMENTS: {
    LIST: '/api/documents',
    UPLOAD: '/api/documents/upload',
    GET: '/api/documents/:id',
    DELETE: '/api/documents/:id',
    DOWNLOAD: '/api/documents/:id/download',
    OCR: '/api/documents/:id/ocr',
    SUMMARY: '/api/documents/:id/summary',
    TRANSCRIBE: '/api/documents/:id/transcribe',
    PODCAST: '/api/documents/:id/podcast',
  },
  CHAT: {
    LIST: '/api/chats',
    CREATE: '/api/chats',
    GET: '/api/chats/:id',
    DELETE: '/api/chats/:id',
    MESSAGE: '/api/chats/:id/message',
    GENERATE: '/api/chats/:id/generate',
  },
  JURISPRUDENCE: {
    SEARCH: '/api/jurisprudence/search',
    GET: '/api/jurisprudence/:id',
  },
  LEGISLATION: {
    SEARCH: '/api/legislation/search',
    GET: '/api/legislation/:id',
  },
  LIBRARY: {
    ITEMS: '/api/library/items',
    FOLDERS: '/api/library/folders',
    LIBRARIANS: '/api/library/librarians',
    SHARE: '/api/library/share',
  },
};

// WebSocket events
export const WS_EVENTS = {
  CONNECT: 'connect',
  DISCONNECT: 'disconnect',
  MESSAGE: 'message',
  GENERATION_START: 'generation:start',
  GENERATION_PROGRESS: 'generation:progress',
  GENERATION_COMPLETE: 'generation:complete',
  GENERATION_ERROR: 'generation:error',
  DOCUMENT_PROCESSING: 'document:processing',
  DOCUMENT_READY: 'document:ready',
  NOTIFICATION: 'notification',
};

