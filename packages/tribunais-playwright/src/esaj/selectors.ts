/**
 * Seletores semânticos ARIA para o e-SAJ
 */

import type { TribunalSelectors } from '../types/index.js';

export const ESAJ_SELECTORS: TribunalSelectors = {
  login: {
    cpfInput: {
      role: 'textbox',
      name: /cpf|cnpj|usu[aá]rio/i,
      fallback: '#usernameForm, input[name="username"], #txtCpfCnpj',
    },
    senhaInput: {
      role: 'textbox',
      name: /senha/i,
      fallback: '#passwordForm, input[name="password"], input[type="password"]',
    },
    certificadoBtn: {
      role: 'button',
      name: /certificado|digital/i,
      fallback: '#certificadoButton, a[href*="certificado"]',
    },
    entrarBtn: {
      role: 'button',
      name: /entrar|acessar/i,
      fallback: '#pbEntrar, button[type="submit"]',
    },
    logoutLink: {
      role: 'link',
      name: /sair|logout/i,
      fallback: 'a[href*="logout"], #linkSair',
    },
  },

  processo: {
    searchInput: {
      role: 'textbox',
      name: /n[uú]mero|processo|unificado/i,
      fallback: '#nuProcessoAntigoFormatado, #nuProcesso, input[name*="processo"]',
    },
    searchBtn: {
      role: 'button',
      name: /consultar|pesquisar/i,
      fallback: '#pbConsultar, #botaoConsultarProcessos, button[type="submit"]',
    },
    resultTable: {
      role: 'table',
      fallback: '#tabelaResultado, .resultTable, table.spwTabelaGrid',
    },
    detailsLink: {
      role: 'link',
      name: /visualizar|detalhes|\d{7}/i,
      fallback: 'a.linkProcesso, table tbody tr td a',
    },
  },

  peticao: {
    novaBtn: {
      role: 'button',
      name: /peticionar|nova.*peti[cç][aã]o/i,
      fallback: '#pbPeticionar, a[href*="peticao"]',
    },
    tipoSelect: {
      role: 'combobox',
      name: /tipo|classe/i,
      fallback: '#classeDocumento, select[name*="tipo"]',
    },
    descricaoInput: {
      role: 'textbox',
      name: /descri[cç][aã]o/i,
      fallback: '#descricaoDocumento, textarea[name*="descricao"]',
    },
    anexarBtn: {
      role: 'button',
      name: /anexar|adicionar/i,
      fallback: '#pbAnexar, .btnAnexar',
    },
    fileInput: {
      role: 'textbox',
      fallback: 'input[type="file"]',
    },
    assinarBtn: {
      role: 'button',
      name: /assinar/i,
      fallback: '#pbAssinar, .btnAssinar',
    },
    enviarBtn: {
      role: 'button',
      name: /enviar|protocolar/i,
      fallback: '#pbEnviar, #pbProtocolar',
    },
    protocoloText: {
      role: 'alert',
      name: /protocolo|sucesso/i,
      fallback: '.mensagemSucesso, #msgSucesso, .alert-success',
    },
  },

  common: {
    loadingIndicator: {
      role: 'img',
      fallback: '.aguarde, .loading, #divAguarde',
    },
    successAlert: {
      role: 'alert',
      fallback: '.mensagemSucesso, .alert-success',
    },
    errorAlert: {
      role: 'alert',
      fallback: '.mensagemErro, .alert-danger',
    },
    modalClose: {
      role: 'button',
      name: /fechar|close/i,
      fallback: '.modal-close, .btn-close',
    },
  },
};

export const ESAJ_URLS: Record<string, string> = {
  'tjsp': 'https://esaj.tjsp.jus.br',
  'tjmt': 'https://esaj.tjmt.jus.br',
  'tjms': 'https://esaj.tjms.jus.br',
  'tjac': 'https://esaj.tjac.jus.br',
  'tjal': 'https://esaj.tjal.jus.br',
  'tjam': 'https://esaj.tjam.jus.br',
  'tjsc': 'https://esaj.tjsc.jus.br', // alguns usam e-SAJ
};
