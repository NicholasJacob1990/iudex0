/**
 * Seletores semânticos ARIA para o eproc
 * Baseado na análise do eproc TJMG (versão 9.18.2)
 */

import type { TribunalSelectors } from '../types/index.js';

/**
 * Seletores específicos para eproc TJMG
 * Baseado na análise de https://eproc1g.tjmg.jus.br/eproc/
 */
export const EPROC_TJMG_SELECTORS: TribunalSelectors = {
  login: {
    cpfInput: {
      role: 'textbox',
      name: /usu[aá]rio/i,
      fallback: '#txtUsuario, input[name="txtUsuario"]',
    },
    senhaInput: {
      role: 'textbox',
      name: /senha/i,
      fallback: 'input[name="pwdSenha"], #pwdSenha',
    },
    certificadoBtn: {
      role: 'button',
      name: /certificado.*digital/i,
      fallback: 'button:has-text("Certificado Digital"), #btnCertificado',
    },
    entrarBtn: {
      role: 'button',
      name: /entrar/i,
      fallback: '#sbmEntrar, button[type="submit"]',
    },
    logoutLink: {
      role: 'link',
      name: /sair|logout/i,
      fallback: 'a[href*="logout"], a:has-text("Sair"), #lnkSair',
    },
  },

  processo: {
    searchInput: {
      role: 'textbox',
      name: /n[uú]mero.*processo|processo/i,
      fallback: '#txtNumProcesso, input[name*="numProcesso"], input[name*="processo"]',
    },
    searchBtn: {
      role: 'button',
      name: /pesquisar|consultar|buscar/i,
      fallback: '#btnPesquisar, button[type="submit"]:has-text("Pesquisar")',
    },
    resultTable: {
      role: 'table',
      fallback: '#tblProcessos, .infraTable, table.resultado',
    },
    detailsLink: {
      role: 'link',
      name: /visualizar|abrir|detalhes|\d{7}/i,
      fallback: 'a[href*="processo_visualizar"], a.link-processo, table tbody tr td a',
    },
  },

  peticao: {
    novaBtn: {
      role: 'button',
      name: /peticionar|nova.*peti[cç][aã]o|protocolar/i,
      fallback: '#btnPeticionar, a:has-text("Peticionar"), a[href*="peticao"]',
    },
    tipoSelect: {
      role: 'combobox',
      name: /tipo.*peti[cç][aã]o|tipo.*documento|classe/i,
      fallback: '#selTipoPeticao, #selTipoDocumento, select[name*="tipo"]',
    },
    descricaoInput: {
      role: 'textbox',
      name: /descri[cç][aã]o|assunto|observa[cç]/i,
      fallback: '#txtDescricao, textarea[name*="descricao"]',
    },
    anexarBtn: {
      role: 'button',
      name: /anexar|adicionar.*arquivo|upload/i,
      fallback: '#btnAnexar, button:has-text("Anexar"), a:has-text("Adicionar Documento")',
    },
    fileInput: {
      role: 'textbox',
      fallback: 'input[type="file"]',
    },
    assinarBtn: {
      role: 'button',
      name: /assinar/i,
      fallback: '#btnAssinar, button:has-text("Assinar")',
    },
    enviarBtn: {
      role: 'button',
      name: /enviar|protocolar|confirmar|salvar/i,
      fallback: '#btnEnviar, #btnProtocolar, button:has-text("Enviar")',
    },
    protocoloText: {
      role: 'alert',
      name: /protocolo|sucesso|enviado/i,
      fallback: '.alert-success, .mensagem-sucesso, .sucesso, [class*="sucesso"]',
    },
  },

  common: {
    loadingIndicator: {
      role: 'img',
      name: /carregando|loading|aguarde/i,
      fallback: '.loading, .spinner, .aguarde, [class*="loading"]',
    },
    successAlert: {
      role: 'alert',
      name: /sucesso/i,
      fallback: '.alert-success, .mensagem-sucesso, .sucesso',
    },
    errorAlert: {
      role: 'alert',
      name: /erro|falha/i,
      fallback: '.alert-danger, .mensagem-erro, .erro, [class*="erro"]',
    },
    modalClose: {
      role: 'button',
      name: /fechar|close|cancelar/i,
      fallback: '.btn-close, button:has-text("Fechar"), .modal-close',
    },
  },

  captcha: {
    imageContainer: {
      role: 'img',
      fallback: '[class*="captcha"], #divCaptcha, .captcha-container',
    },
    image: {
      role: 'img',
      fallback: 'img[src*="captcha"], img[id*="captcha"]',
    },
    input: {
      role: 'textbox',
      name: /captcha|c[oó]digo.*imagem/i,
      fallback: 'input[name*="captcha"], input[id*="captcha"]',
    },
    refreshBtn: {
      role: 'button',
      name: /atualizar|refresh|novo/i,
      fallback: 'a[href*="captcha"], button[title*="atualizar"]',
    },
  },
};

// Alias para compatibilidade
export const EPROC_SELECTORS = EPROC_TJMG_SELECTORS;

/**
 * URLs conhecidas do eproc por tribunal
 */
export const EPROC_URLS: Record<string, { '1g': string; '2g'?: string }> = {
  // Minas Gerais
  'tjmg': {
    '1g': 'https://eproc1g.tjmg.jus.br/eproc/',
    '2g': 'https://eproc2g.tjmg.jus.br/eproc/',
  },

  // TRF4 e Justiça Federal da 4ª Região
  'trf4': {
    '1g': 'https://eproc.trf4.jus.br/eproc2trf4',
    '2g': 'https://eproc.trf4.jus.br/eproc2trf4',
  },
  'jfrs': {
    '1g': 'https://eproc.jfrs.jus.br/eprocV2',
  },
  'jfsc': {
    '1g': 'https://eproc.jfsc.jus.br/eprocV2',
  },
  'jfpr': {
    '1g': 'https://eproc.jfpr.jus.br/eprocV2',
  },

  // Rio Grande do Sul
  'tjrs': {
    '1g': 'https://eproc1g.tjrs.jus.br/eproc/',
    '2g': 'https://eproc2g.tjrs.jus.br/eproc/',
  },
};
