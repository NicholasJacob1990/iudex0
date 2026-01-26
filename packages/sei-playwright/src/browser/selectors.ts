/**
 * Seletores CSS para o SEI!
 * Compatível com SEI 4.x (baseado em sei-mcp)
 */

export const SEI_SELECTORS = {
  // ============================================
  // Login
  // ============================================
  login: {
    form: '#frmLogin, form[name="frmLogin"]',
    usuario: '#txtUsuario, input[name="txtUsuario"]',
    // SEI MG: campo visível tem id=pwdSenha, class=masked, SEM name
    // SEI MG: campo oculto (display:none) tem name=pwdSenha, SEM id
    // Prioriza o campo visível (com class masked) sobre o oculto
    senha: 'input#pwdSenha.masked, input#pwdSenha:not([type="password"]), input[name="pwdSenha"]:not([style*="none"])',
    orgao: '#selOrgao, select[name="selOrgao"]',
    // SEI MG usa #Acessar, outros SEIs usam #sbmLogin
    submit: '#Acessar, #sbmLogin, input[name="sbmLogin"], button[type="submit"]',
    error: '.infraException, .msgErro, #divInfraExcecao',
  },

  // ============================================
  // Navegação Principal
  // ============================================
  nav: {
    menu: '#infraMenu, .infraMenu',
    pesquisa: '#txtPesquisaRapida, input[name="txtPesquisaRapida"]',
    btnPesquisa: '#btnPesquisaRapida, a[onclick*="pesquisar"]',
    controleProcessos: '#lnkControleProcessos, a[href*="procedimento_controlar"]',
    iniciarProcesso: '#lnkIniciarProcesso, a[href*="procedimento_escolher_tipo"]',
    usuario: '#lnkUsuarioSistema, #spanUsuario, .usuario-logado',
    unidade: '#selInfraUnidades, select[name="selInfraUnidades"]',
    logout: '#lnkSairSistema, a[href*="usuario_externo_logar"], a[href*="logout"]',
  },

  // ============================================
  // Lista de Processos
  // ============================================
  processList: {
    container: '#divArvore, #tblProcessosRecebidos, .infraTable',
    rows: 'tr[class*="infraTr"], .processo-item',
    link: 'a[href*="procedimento_trabalhar"]',
    numero: '.numero-processo, td:first-child a',
    tipo: '.tipo-processo, td:nth-child(2)',
    especificacao: '.especificacao, td:nth-child(3)',
  },

  // ============================================
  // Árvore do Processo
  // ============================================
  processTree: {
    container: '#divArvore, #arvore',
    root: '#anchor0, .infraArvoreNo',
    documents: '.infraArvoreNo a, #divArvore a[href*="documento"]',
    documentLink: 'a[href*="documento_visualizar"], a[href*="editor"]',
    selected: '.infraArvoreNoSelecionado, .selected',
  },

  // ============================================
  // Barra de Ações do Processo
  // ============================================
  processActions: {
    container: '#divInfraBarraComandosSuperior, .barra-acoes',
    incluirDocumento: 'a[href*="documento_escolher_tipo"], img[title*="Incluir Documento"]',
    enviarProcesso: 'a[href*="procedimento_enviar"], img[title*="Enviar Processo"]',
    concluirProcesso: 'a[href*="procedimento_concluir"], img[title*="Concluir"]',
    reabrirProcesso: 'a[href*="procedimento_reabrir"], img[title*="Reabrir"]',
    anexarProcesso: 'a[href*="procedimento_anexar"], img[title*="Anexar"]',
    relacionarProcesso: 'a[href*="procedimento_relacionar"], img[title*="Relacionar"]',
    atribuirProcesso: 'a[href*="procedimento_atribuir"], img[title*="Atribuir"]',
    gerarPdf: 'a[href*="procedimento_gerar_pdf"], img[title*="Gerar PDF"]',
    anotacoes: 'a[href*="anotacao"], img[title*="Anotações"]',
    ciencia: 'a[href*="procedimento_registrar_ciencia"], img[title*="Ciência"]',
    consultarAndamento: 'a[href*="procedimento_consultar_andamento"], img[title*="Consultar Andamento"]',
    blocoAssinatura: 'a[href*="bloco"], img[title*="Bloco"]',
  },

  // ============================================
  // Formulário de Novo Processo
  // ============================================
  newProcess: {
    form: '#frmProcedimentoGerar, form[name="frmProcedimentoGerar"]',
    tipo: '#selTipoProcedimento, select[name="selTipoProcedimento"]',
    tipoSearch: '#txtPalavrasPesquisaTipoProcedimento',
    especificacao: '#txtEspecificacao, input[name="txtEspecificacao"]',
    interessado: '#txtInteressadoProcedimento, input[name="txtInteressadoProcedimento"]',
    interessadoAdd: '#btnAdicionarInteressado, a[onclick*="adicionarInteressado"]',
    observacao: '#txaObservacoes, textarea[name="txaObservacoes"]',
    nivelAcesso: {
      publico: '#optPublico, input[value="0"]',
      restrito: '#optRestrito, input[value="1"]',
      sigiloso: '#optSigiloso, input[value="2"]',
    },
    hipoteseLegal: '#selHipoteseLegal, select[name="selHipoteseLegal"]',
    salvar: '#btnSalvar, button[name="sbmCadastrarProcedimento"]',
  },

  // ============================================
  // Formulário de Novo Documento
  // ============================================
  newDocument: {
    form: '#frmDocumentoGerar, form[name="frmDocumentoGerar"]',

    // Seleção de tipo
    tipoContainer: '#divTipoDocumento, .tipo-documento-container',
    tipoSearch: '#txtPalavrasPesquisaTipo, input[name="txtPalavrasPesquisaTipo"]',
    tipoSelect: '#selSerie, select[name="selSerie"]',
    tipoLinks: 'a[href*="documento_gerar"], .tipo-documento a',

    // Texto inicial
    textoInicial: {
      nenhum: '#optSemTexto, input[value="N"]',
      modelo: '#optTextoPadrao, input[value="M"]',
      padrao: '#optTextoModelo, input[value="T"]',
    },
    textoPadraoSelect: '#selTextoPadrao, select[name="selTextoPadrao"]',
    documentoModeloInput: '#txtProtocolo, input[name="txtProtocolo"]',

    // Campos básicos
    descricao: '#txtDescricao, input[name="txtDescricao"]',
    numero: '#txtNumero, input[name="txtNumero"]',
    nomeArvore: '#txtNomeArvore, input[name="txtNomeArvore"]',

    // Interessados
    interessadoInput: '#txtInteressado, input[name="txtInteressado"]',
    interessadoAdd: '#btnAdicionarInteressado, a[onclick*="adicionarInteressado"]',
    interessadosList: '#tblInteressados, .lista-interessados',

    // Destinatários
    destinatarioInput: '#txtDestinatario, input[name="txtDestinatario"]',
    destinatarioAdd: '#btnAdicionarDestinatario, a[onclick*="adicionarDestinatario"]',
    destinatariosList: '#tblDestinatarios, .lista-destinatarios',

    // Assuntos
    assuntoBtn: '#btnPesquisarAssunto, a[href*="assunto_selecionar"]',
    assuntoInput: '#txtAssunto, input[name="txtAssunto"]',

    // Observações
    observacao: '#txaObservacoes, textarea[name="txaObservacoes"]',

    // Nível de acesso
    nivelAcesso: {
      publico: '#optPublico, input[value="0"]',
      restrito: '#optRestrito, input[value="1"]',
      sigiloso: '#optSigiloso, input[value="2"]',
    },
    hipoteseLegal: '#selHipoteseLegal, select[name="selHipoteseLegal"]',

    // Ações
    salvar: '#btnSalvar, button[name="sbmCadastrarDocumento"]',
    confirmar: '#btnConfirmar, button[name="sbmConfirmar"]',
  },

  // ============================================
  // Upload de Documento Externo
  // ============================================
  upload: {
    form: '#frmDocumentoExterno, form[name="frmDocumentoExterno"]',
    arquivo: '#filArquivo, input[type="file"]',
    formato: '#selFormato, select[name="selFormato"]',
    tipoConferencia: '#selTipoConferencia, select[name="selTipoConferencia"]',
    salvar: '#btnSalvar, button[name="sbmCadastrarDocumentoExterno"]',
  },

  // ============================================
  // Editor de Documento
  // ============================================
  editor: {
    frame: '#ifrArvoreHtml, iframe[name="ifrArvoreHtml"]',
    ckeditor: '.cke_editable, #cke_txtConteudo',
    textarea: '#txtConteudo, textarea[name="txtConteudo"]',
    salvar: '#btnSalvar, button[name="sbmSalvar"]',
  },

  // ============================================
  // Assinatura
  // ============================================
  signature: {
    form: '#frmDocumentoAssinar, form[name="frmDocumentoAssinar"]',
    senha: '#pwdSenha, input[name="pwdSenha"]',
    cargo: '#selCargo, select[name="selCargo"]',
    assinar: '#btnAssinar, button[name="sbmAssinar"]',
    confirmar: '#btnConfirmar',
  },

  // ============================================
  // Tramitação (Enviar Processo)
  // ============================================
  forward: {
    form: '#frmEnviarProcesso, form[name="frmEnviarProcesso"]',
    unidadeInput: '#txtUnidade, input[name="txtUnidade"]',
    unidadeSelect: '#selUnidades, select[name="selUnidades"]',
    unidadeAdd: '#btnAdicionarUnidade, a[onclick*="adicionarUnidade"]',
    manterAberto: '#chkManterAberto, input[name="chkManterAberto"]',
    removerAnotacoes: '#chkRemoverAnotacoes, input[name="chkRemoverAnotacoes"]',
    enviarEmail: '#chkEnviarEmail, input[name="chkEnviarEmail"]',
    dataRetorno: '#txtDataRetorno, input[name="txtDataRetorno"]',
    enviar: '#btnEnviar, button[name="sbmEnviar"]',
  },

  // ============================================
  // Bloco de Assinatura
  // ============================================
  block: {
    container: '#divBlocos, .blocos-container',
    novo: 'a[href*="bloco_cadastrar"], #btnNovoBloco',
    lista: '#tblBlocos, .lista-blocos',
    incluirDocumento: 'a[href*="bloco_incluir_documento"]',
    disponibilizar: 'a[href*="bloco_disponibilizar"]',
    assinar: 'a[href*="bloco_assinar"]',
    formNovo: {
      descricao: '#txtDescricao, input[name="txtDescricao"]',
      unidadeInput: '#txtUnidade, input[name="txtUnidade"]',
      salvar: '#btnSalvar, button[name="sbmSalvar"]',
    },
  },

  // ============================================
  // Andamento / Histórico
  // ============================================
  history: {
    container: '#divAndamentos, .historico-container',
    table: '#tblHistorico, .infraTable',
    rows: 'tr[class*="infraTr"]',
    data: 'td:first-child',
    unidade: 'td:nth-child(2)',
    usuario: 'td:nth-child(3)',
    descricao: 'td:nth-child(4)',
  },

  // ============================================
  // Elementos Comuns
  // ============================================
  common: {
    loading: '#divInfraCarregando, .infraCarregando',
    modal: '#divInfraModal, .infraModal',
    alert: '.infraException, .msgErro, .alert-danger',
    success: '.msgSucesso, .alert-success',
    iframe: 'iframe[name="ifrVisualizacao"], iframe[name="ifrConteudo"]',
    close: '#btnFechar, a[onclick*="fechar"], .btn-close',
    confirm: '#btnConfirmar, button[name="sbmConfirmar"]',
    cancel: '#btnCancelar, button[name="sbmCancelar"]',
  },
};

export default SEI_SELECTORS;
