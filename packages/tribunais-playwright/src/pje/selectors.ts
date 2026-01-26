/**
 * Seletores semânticos ARIA para o PJe
 * Compatível com múltiplas versões do sistema
 */

import type { TribunalSelectors } from '../types/index.js';

export const PJE_SELECTORS: TribunalSelectors = {
  login: {
    cpfInput: {
      role: 'textbox',
      name: /cpf|usu[aá]rio|login/i,
      fallback: '#username, input[name="username"], input[name="cpf"], #txtUsuario',
    },
    senhaInput: {
      role: 'textbox',
      name: /senha|password/i,
      fallback: '#password, input[name="password"], input[type="password"]',
    },
    certificadoBtn: {
      role: 'button',
      name: /certificado|digital|token/i,
      fallback: '#btnCertificado, .btn-certificado, a[href*="certificado"]',
    },
    entrarBtn: {
      role: 'button',
      name: /entrar|acessar|login|submit/i,
      fallback: '#btnEntrar, button[type="submit"], input[type="submit"]',
    },
    logoutLink: {
      role: 'link',
      name: /sair|logout|desconectar/i,
      fallback: 'a[href*="logout"], .logout, #linkSair',
    },
  },

  processo: {
    searchInput: {
      role: 'textbox',
      name: /n[uú]mero.*processo|processo|pesquis/i,
      fallback: '#fPP\\:numProcesso-inputNumeroProcessoDecoration\\:numProcesso-inputNumeroProcesso, input[id*="numProcesso"], input[name*="processo"]',
    },
    searchBtn: {
      role: 'button',
      name: /pesquisar|buscar|consultar/i,
      fallback: '#fPP\\:searchProcessos, button[id*="search"], input[type="submit"]',
    },
    resultTable: {
      role: 'table',
      name: /resultado|processos/i,
      fallback: '.rich-table, .lista-processos, table[id*="processos"]',
    },
    detailsLink: {
      role: 'link',
      name: /visualizar|detalhes|abrir|\d{7}/i,
      fallback: 'a[id*="lnkVisualizar"], .link-processo, table tbody tr a',
    },
  },

  peticao: {
    novaBtn: {
      role: 'button',
      name: /nova.*peti[cç][aã]o|peticionar|incluir.*peti[cç][aã]o/i,
      fallback: '#btnNovaPeticao, a[id*="peticao"], .btn-peticionar',
    },
    tipoSelect: {
      role: 'combobox',
      name: /tipo.*peti[cç][aã]o|tipo.*documento|classe/i,
      fallback: 'select[id*="tipoPeticao"], select[id*="tipoDocumento"], #selectTipo',
    },
    descricaoInput: {
      role: 'textbox',
      name: /descri[cç][aã]o|assunto|observa[cç]/i,
      fallback: 'textarea[id*="descricao"], input[id*="descricao"], #txtDescricao',
    },
    anexarBtn: {
      role: 'button',
      name: /anexar|adicionar.*arquivo|upload|incluir.*documento/i,
      fallback: '#btnAnexar, .btn-anexar, button[id*="upload"]',
    },
    fileInput: {
      role: 'textbox', // type=file não tem role específico
      name: /arquivo|documento/i,
      fallback: 'input[type="file"]',
    },
    assinarBtn: {
      role: 'button',
      name: /assinar|assinatura/i,
      fallback: '#btnAssinar, .btn-assinar, button[id*="assinar"]',
    },
    enviarBtn: {
      role: 'button',
      name: /enviar|protocolar|confirmar|salvar/i,
      fallback: '#btnEnviar, #btnProtocolar, .btn-enviar, button[type="submit"]',
    },
    protocoloText: {
      role: 'alert',
      name: /protocolo|sucesso|enviado/i,
      fallback: '.mensagem-sucesso, .alert-success, [class*="protocolo"], .numero-protocolo',
    },
  },

  common: {
    loadingIndicator: {
      role: 'img',
      name: /carregando|loading|aguarde/i,
      fallback: '.loading, .spinner, .rich-mpnl-mask, [class*="loading"]',
    },
    successAlert: {
      role: 'alert',
      name: /sucesso|confirmado|realizado/i,
      fallback: '.alert-success, .mensagem-sucesso, [class*="sucesso"]',
    },
    errorAlert: {
      role: 'alert',
      name: /erro|falha|inv[aá]lido/i,
      fallback: '.alert-danger, .alert-error, .mensagem-erro, [class*="erro"]',
    },
    modalClose: {
      role: 'button',
      name: /fechar|close|cancelar/i,
      fallback: '.modal-close, .btn-close, button[class*="close"]',
    },
  },
};

/**
 * URLs conhecidas do PJe por tribunal
 */
export const PJE_URLS: Record<string, string> = {
  // Justiça do Trabalho
  'trt1': 'https://pje.trt1.jus.br',
  'trt2': 'https://pje.trt2.jus.br',
  'trt3': 'https://pje.trt3.jus.br',
  'trt4': 'https://pje.trt4.jus.br',
  'trt5': 'https://pje.trt5.jus.br',
  'trt6': 'https://pje.trt6.jus.br',
  'trt7': 'https://pje.trt7.jus.br',
  'trt8': 'https://pje.trt8.jus.br',
  'trt9': 'https://pje.trt9.jus.br',
  'trt10': 'https://pje.trt10.jus.br',
  'trt11': 'https://pje.trt11.jus.br',
  'trt12': 'https://pje.trt12.jus.br',
  'trt13': 'https://pje.trt13.jus.br',
  'trt14': 'https://pje.trt14.jus.br',
  'trt15': 'https://pje.trt15.jus.br',
  'trt16': 'https://pje.trt16.jus.br',
  'trt17': 'https://pje.trt17.jus.br',
  'trt18': 'https://pje.trt18.jus.br',
  'trt19': 'https://pje.trt19.jus.br',
  'trt20': 'https://pje.trt20.jus.br',
  'trt21': 'https://pje.trt21.jus.br',
  'trt22': 'https://pje.trt22.jus.br',
  'trt23': 'https://pje.trt23.jus.br',
  'trt24': 'https://pje.trt24.jus.br',
  'tst': 'https://pje.tst.jus.br',

  // Justiça Federal
  'trf1': 'https://pje1g.trf1.jus.br',
  'trf2': 'https://pje.trf2.jus.br',
  'trf3': 'https://pje1g.trf3.jus.br',
  'trf4': 'https://pje.trf4.jus.br',
  'trf5': 'https://pje.trf5.jus.br',
  'trf6': 'https://pje.trf6.jus.br',

  // Justiça Estadual (alguns exemplos)
  'tjmg': 'https://pje.tjmg.jus.br',
  'tjsp': 'https://pje.tjsp.jus.br',
  'tjrj': 'https://pje.tjrj.jus.br',
  'tjrs': 'https://pje.tjrs.jus.br',
  'tjpr': 'https://pje.tjpr.jus.br',
  'tjsc': 'https://pje.tjsc.jus.br',
  'tjba': 'https://pje.tjba.jus.br',
  'tjpe': 'https://pje.tjpe.jus.br',
  'tjce': 'https://pje.tjce.jus.br',
  'tjgo': 'https://pje.tjgo.jus.br',
  'tjdf': 'https://pje.tjdft.jus.br',

  // CNJ
  'cnj': 'https://www.cnj.jus.br/pjecnj',
};
