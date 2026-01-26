#!/usr/bin/env npx tsx
/**
 * Script para iniciar o SEI Daemon
 *
 * MODO 1 - Browser próprio (precisa credenciais):
 *   SEI_USER=xxx SEI_PASS=xxx npx tsx start-daemon.ts
 *
 * MODO 2 - CDP (conecta ao Chrome já aberto e logado):
 *   # Terminal 1: Inicie o Chrome com debugging
 *   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
 *
 *   # Faça login no SEI manualmente
 *
 *   # Terminal 2: Inicie o daemon
 *   SEI_CDP=http://localhost:9222 npx tsx start-daemon.ts
 *
 * Variáveis de ambiente:
 *   SEI_URL       - URL do SEI (padrão: https://www.sei.mg.gov.br)
 *   SEI_CDP       - Endpoint CDP (ex: http://localhost:9222) - se definido, usa Chrome já aberto
 *   SEI_USER      - Usuário (não necessário se usar CDP com sessão já logada)
 *   SEI_PASS      - Senha
 *   SEI_ORGAO     - Órgão
 *   SEI_HEADLESS  - true/false (padrão: false, ignorado em CDP)
 *   SEI_INTERVAL  - Intervalo em ms (padrão: 60000)
 *   SEI_WEBHOOK   - URL do webhook (opcional)
 *   SMTP_HOST     - Host SMTP (opcional)
 *   SMTP_PORT     - Porta SMTP
 *   SMTP_USER     - Usuário SMTP
 *   SMTP_PASS     - Senha SMTP
 *   SMTP_FROM     - Email remetente
 *   NOTIFY_EMAIL  - Email para notificações
 *   NOTIFY_NAME   - Nome do destinatário
 */

import { SEIDaemon, type DaemonConfig } from './src/daemon.js';

// Detecta modo CDP
const cdpEndpoint = process.env.SEI_CDP;
const isCdpMode = !!cdpEndpoint;

// Carrega configuração do ambiente
const config: DaemonConfig = {
  baseUrl: process.env.SEI_URL || 'https://www.sei.mg.gov.br',

  // Credenciais (opcionais em modo CDP se já estiver logado)
  credentials: (process.env.SEI_USER && process.env.SEI_PASS) ? {
    usuario: process.env.SEI_USER,
    senha: process.env.SEI_PASS,
    orgao: process.env.SEI_ORGAO,
  } : undefined,

  watch: {
    types: ['processos_recebidos', 'blocos_assinatura', 'prazos'],
    interval: parseInt(process.env.SEI_INTERVAL || '60000', 10),
  },

  browser: {
    headless: process.env.SEI_HEADLESS === 'true',
    timeout: 60000,
    cdpEndpoint: cdpEndpoint,
  },

  notifications: {
    // Email (se configurado)
    email: process.env.SMTP_HOST ? {
      host: process.env.SMTP_HOST,
      port: parseInt(process.env.SMTP_PORT || '587', 10),
      secure: process.env.SMTP_PORT === '465',
      auth: {
        user: process.env.SMTP_USER || '',
        pass: process.env.SMTP_PASS || '',
      },
      from: process.env.SMTP_FROM || '',
    } : undefined,

    // Webhook (se configurado)
    webhook: process.env.SEI_WEBHOOK,

    // Destinatários
    recipients: process.env.NOTIFY_EMAIL ? [{
      userId: 'default',
      email: process.env.NOTIFY_EMAIL,
      nome: process.env.NOTIFY_NAME || 'Usuário',
    }] : [],
  },
};

// Valida configuração
if (!isCdpMode && !config.credentials) {
  console.error('❌ Credenciais não configuradas!');
  console.error('');
  console.error('OPÇÃO 1 - Modo CDP (recomendado para monitoramento):');
  console.error('  # Inicie Chrome com debugging:');
  console.error('  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222');
  console.error('  # Faça login no SEI manualmente');
  console.error('  # Depois execute:');
  console.error('  SEI_CDP=http://localhost:9222 npx tsx start-daemon.ts');
  console.error('');
  console.error('OPÇÃO 2 - Modo tradicional (com credenciais):');
  console.error('  export SEI_USER="seu.usuario"');
  console.error('  export SEI_PASS="sua.senha"');
  console.error('  export SEI_ORGAO="CODEMGE"');
  console.error('  npx tsx start-daemon.ts');
  process.exit(1);
}

if (isCdpMode) {
  console.log('🔌 Modo CDP: Conectando ao Chrome em', cdpEndpoint);
}

// Inicia daemon
const daemon = new SEIDaemon(config);

// Handlers de eventos
daemon.on('started', () => {
  console.log('');
  console.log('='.repeat(50));
  console.log('SEI Daemon rodando!');
  console.log('='.repeat(50));
  console.log('');
});

daemon.on('event', (event) => {
  console.log(`\n🔔 NOVO EVENTO: ${event.type}`);
  console.log(`   Timestamp: ${event.timestamp.toLocaleString('pt-BR')}`);
  console.log(`   Itens: ${event.items.length}`);
  for (const item of event.items) {
    console.log(`   - ${item.numero || item.id}: ${item.descricao || item.tipo || ''}`);
  }
});

daemon.on('notification', (payload) => {
  console.log(`   📤 Notificação enviada para ${payload.email || 'webhook'}`);
});

daemon.on('sessionExpired', () => {
  console.log('\n⚠️ Sessão expirada, reconectando...');
});

daemon.on('relogin', () => {
  console.log('✅ Reconectado com sucesso!');
});

daemon.on('error', (error) => {
  console.error(`\n❌ Erro: ${error.message}`);
});

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n\n🛑 Recebido SIGINT, encerrando...');
  await daemon.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n\n🛑 Recebido SIGTERM, encerrando...');
  await daemon.stop();
  process.exit(0);
});

// Inicia
daemon.start().catch((error) => {
  console.error('❌ Falha ao iniciar daemon:', error);
  process.exit(1);
});
