/**
 * Exemplo básico de uso do tribunais-playwright
 *
 * Demonstra os diferentes métodos de autenticação e peticionamento
 */

import { PJeClient } from '../src/index.js';

// ============================================
// Exemplo 1: Login com CPF e Senha (somente consulta)
// ============================================
async function exemploLoginSenha() {
  const pje = new PJeClient({
    baseUrl: 'https://pje.trt3.jus.br',
    auth: {
      type: 'password',
      cpf: '12345678900',
      senha: 'minhaSenha123',
    },
    playwright: {
      headless: true,
    },
  });

  await pje.init();
  await pje.login();

  // Consultar processo (permitido com senha)
  const processo = await pje.consultarProcesso('0001234-56.2025.5.03.0001');
  console.log('Processo:', processo);

  // Listar movimentações
  const movs = await pje.listarMovimentacoes('0001234-56.2025.5.03.0001');
  console.log('Movimentações:', movs);

  await pje.close();
}

// ============================================
// Exemplo 2: Login com Certificado A1 (automático)
// ============================================
async function exemploA1() {
  const pje = new PJeClient({
    baseUrl: 'https://pje.trt3.jus.br',
    auth: {
      type: 'certificate_a1',
      pfxPath: '/path/to/certificado-oab.pfx',
      passphrase: 'senha-do-certificado',
    },
    playwright: {
      headless: true,
    },
  });

  await pje.init();
  await pje.login();

  // Peticionar (totalmente automático com A1)
  const resultado = await pje.peticionar({
    numeroProcesso: '0001234-56.2025.5.03.0001',
    tipo: 'Petição Simples',
    arquivos: ['/path/to/peticao.pdf'],
    tiposDocumento: ['Petição'],
  });

  console.log('Protocolo:', resultado.numeroProtocolo);

  await pje.close();
}

// ============================================
// Exemplo 3: Login com A3 Físico (Token USB)
// ============================================
async function exemploA3Fisico() {
  const pje = new PJeClient({
    baseUrl: 'https://pje.trt3.jus.br',
    auth: {
      type: 'certificate_a3_physical',
      pinTimeout: 300000, // 5 minutos para digitar PIN

      // Callback quando PIN é necessário
      onPinRequired: async () => {
        console.log('⚠️  AÇÃO NECESSÁRIA: Digite o PIN do token na janela do sistema');
        // Aqui você pode enviar push notification, email, SMS, etc.
      },
    },
    playwright: {
      headless: false, // Precisa ser visível para ver a janela do PIN
    },

    // Webhook para notificações
    webhookUrl: 'https://meu-sistema.com/webhook/certificado',

    // Ou callback local
    onNotification: async (notif) => {
      console.log(`[${notif.type}] ${notif.message}`);

      // Enviar para frontend via WebSocket
      // ws.send(JSON.stringify(notif));
    },
  });

  await pje.init();

  // Escuta eventos
  pje.on('login:pin_required', ({ timeout }) => {
    console.log(`Aguardando PIN... (timeout: ${timeout / 1000}s)`);
  });

  pje.on('login:success', () => {
    console.log('✅ Login realizado!');
  });

  pje.on('peticao:signature_required', (info) => {
    console.log(`⚠️  ${info.message}`);
  });

  pje.on('peticao:success', (resultado) => {
    console.log(`✅ Petição protocolada: ${resultado.numeroProtocolo}`);
  });

  // Login (vai solicitar PIN)
  await pje.login();

  // Peticionar (vai solicitar PIN novamente para assinar)
  const resultado = await pje.peticionar({
    numeroProcesso: '0001234-56.2025.5.03.0001',
    tipo: 'Petição Simples',
    arquivos: ['/path/to/peticao.pdf'],
  });

  console.log('Resultado:', resultado);

  await pje.close();
}

// ============================================
// Exemplo 4: Login com A3 na Nuvem (Certisign, Serasa, etc.)
// ============================================
async function exemploA3Nuvem() {
  const pje = new PJeClient({
    baseUrl: 'https://pje.trt3.jus.br',
    auth: {
      type: 'certificate_a3_cloud',
      provider: 'certisign', // ou 'serasa', 'safeweb', 'soluti'
      approvalTimeout: 120000, // 2 minutos para aprovar no celular

      // Callback quando aprovação é necessária
      onApprovalRequired: async (info) => {
        console.log(`📱 ${info.message}`);
        console.log(`   Expira em: ${info.expiresIn}s`);

        // Enviar push notification para o celular do usuário
        // await sendPushNotification(userId, info);
      },
    },
    playwright: {
      headless: false,
    },

    // Webhook para integração com sistema
    webhookUrl: 'https://meu-sistema.com/webhook/assinatura',
  });

  await pje.init();

  // Eventos
  pje.on('login:approval_required', (info) => {
    console.log(`📱 Aprove o login no app ${info.provider}`);
  });

  pje.on('peticao:signature_required', (info) => {
    console.log(`📱 Aprove a assinatura no app ${info.provider}`);
  });

  // Login (vai solicitar aprovação no celular)
  await pje.login();

  // Peticionar (vai solicitar aprovação novamente)
  const resultado = await pje.peticionar({
    numeroProcesso: '0001234-56.2025.5.03.0001',
    tipo: 'Petição Simples',
    arquivos: ['/path/to/peticao.pdf'],
  });

  console.log('Resultado:', resultado);

  await pje.close();
}

// ============================================
// Exemplo 5: Sessão Persistente (login uma vez)
// ============================================
async function exemploSessaoPersistente() {
  const pje = new PJeClient({
    baseUrl: 'https://pje.trt3.jus.br',
    auth: {
      type: 'certificate_a3_cloud',
      provider: 'certisign',
    },
    playwright: {
      // Sessão persistente - mantém cookies/sessão entre execuções
      persistent: true,
      userDataDir: '~/.tribunais-playwright/pje-trt3',
      headless: false,
    },
  });

  await pje.init();

  // Verifica se já está logado
  const jaLogado = await pje.isSessionActive();

  if (jaLogado) {
    console.log('✅ Sessão ativa - pulando login');
  } else {
    console.log('Fazendo login...');
    await pje.login(); // Vai pedir aprovação no celular apenas na primeira vez
  }

  // A partir daqui, pode fazer operações sem pedir certificado novamente
  const docs = await pje.listarDocumentos('0001234-56.2025.5.03.0001');
  console.log('Documentos:', docs);

  // NÃO fecha o contexto para manter sessão
  // await pje.close();
}

// ============================================
// Executar exemplo
// ============================================
const exemplo = process.argv[2] ?? 'senha';

switch (exemplo) {
  case 'senha':
    exemploLoginSenha();
    break;
  case 'a1':
    exemploA1();
    break;
  case 'a3':
    exemploA3Fisico();
    break;
  case 'nuvem':
    exemploA3Nuvem();
    break;
  case 'persistente':
    exemploSessaoPersistente();
    break;
  default:
    console.log('Uso: tsx examples/basic.ts [senha|a1|a3|nuvem|persistente]');
}
