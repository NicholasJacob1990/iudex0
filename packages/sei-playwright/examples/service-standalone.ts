/**
 * Exemplo: Serviço SEI Standalone
 * Execute: npx tsx examples/service-standalone.ts
 */

import { SEIServiceAPI } from '../src/index.js';

async function main() {
  // ============================================
  // Configuração
  // ============================================

  const api = new SEIServiceAPI({
    // Armazenamento de dados
    dataPath: './data',
    masterPassword: process.env.MASTER_PASSWORD ?? 'sua-senha-mestre-segura',

    // Configuração de email (opcional)
    email: process.env.SMTP_HOST ? {
      host: process.env.SMTP_HOST,
      port: parseInt(process.env.SMTP_PORT ?? '587'),
      secure: process.env.SMTP_SECURE === 'true',
      auth: {
        user: process.env.SMTP_USER ?? '',
        pass: process.env.SMTP_PASS ?? '',
      },
      from: process.env.SMTP_FROM ?? 'noreply@iudex.com',
      fromName: 'SEI Notificações',
    } : undefined,

    // Intervalo de polling
    pollInterval: 60000, // 1 minuto

    // Tipos para monitorar
    watchTypes: [
      'processos_recebidos',
      'blocos_assinatura',
      'prazos',
      'retornos_programados',
    ],

    // Playwright
    playwright: {
      headless: true,
      timeout: 30000,
    },

    // API
    port: 3001,
    host: 'localhost',
    apiKey: process.env.API_KEY,
  });

  // ============================================
  // Event Handlers
  // ============================================

  const service = api.getService();

  service.on('started', () => {
    console.log('🚀 Serviço iniciado');
  });

  service.on('stopped', () => {
    console.log('🛑 Serviço parado');
  });

  service.on('user:added', (user) => {
    console.log(`✅ Usuário adicionado: ${user.nome} (${user.id})`);
  });

  service.on('user:error', (userId, error) => {
    console.error(`❌ Erro no usuário ${userId}:`, error.message);
  });

  service.on('notification:sent', (userId, type) => {
    console.log(`📧 Notificação enviada: ${userId} - ${type}`);
  });

  service.on('notification:error', (userId, error) => {
    console.error(`❌ Erro na notificação ${userId}:`, error.message);
  });

  // ============================================
  // Iniciar API
  // ============================================

  try {
    await api.start();

    console.log(`
╔════════════════════════════════════════════════════════════════╗
║                    SEI Notification Service                     ║
╠════════════════════════════════════════════════════════════════╣
║                                                                 ║
║  API rodando em: http://localhost:3001                         ║
║                                                                 ║
║  Endpoints:                                                     ║
║                                                                 ║
║  GET  /status              - Status do serviço                  ║
║  GET  /users               - Listar usuários                    ║
║  POST /users               - Adicionar usuário                  ║
║  GET  /users/:id           - Obter usuário                      ║
║  PUT  /users/:id           - Atualizar usuário                  ║
║  DEL  /users/:id           - Remover usuário                    ║
║  PUT  /users/:id/credentials - Atualizar credenciais            ║
║  POST /users/:id/start     - Iniciar monitoramento              ║
║  POST /users/:id/stop      - Parar monitoramento                ║
║  POST /start               - Iniciar todos                      ║
║  POST /stop                - Parar todos                        ║
║                                                                 ║
╚════════════════════════════════════════════════════════════════╝
    `);

    // Graceful shutdown
    process.on('SIGINT', async () => {
      console.log('\n\nEncerrando...');
      await api.stop();
      process.exit(0);
    });

  } catch (error) {
    console.error('Erro ao iniciar:', error);
    process.exit(1);
  }
}

main();
