/**
 * Exemplo de uso do SEIWatcher
 * Monitor de novos processos, documentos e comunicações
 *
 * Execute: npx tsx examples/watcher.ts
 */

import { SEIClient, SEIWatcher } from '../src/index.js';

async function main() {
  // ============================================
  // Configuração do Cliente
  // ============================================

  const sei = new SEIClient({
    baseUrl: process.env.SEI_BASE_URL ?? 'https://sei.mg.gov.br',
    browser: {
      usuario: process.env.SEI_USUARIO ?? '',
      senha: process.env.SEI_SENHA ?? '',
    },
    playwright: {
      headless: process.env.HEADLESS !== 'false',
      timeout: 30000,
    },
  });

  try {
    console.log('🚀 Inicializando cliente SEI...');
    await sei.init();

    console.log('🔐 Realizando login...');
    const loggedIn = await sei.login();
    if (!loggedIn) {
      throw new Error('Falha no login');
    }
    console.log('✅ Login realizado com sucesso!\n');

    // ============================================
    // Configuração do Watcher
    // ============================================

    const watcher = new SEIWatcher(sei, {
      // Intervalo de verificação: 30 segundos
      interval: 30000,

      // Tipos para monitorar
      types: [
        'processos_recebidos',  // Novos processos na caixa de entrada
        'blocos_assinatura',    // Blocos pendentes de assinatura
        'retornos_programados', // Retornos programados
        'prazos',               // Processos com prazo
      ],

      // Máximo de itens para rastrear por tipo
      maxItems: 100,

      // Tentar SOAP primeiro (mais rápido) se disponível
      preferSoap: true,
    });

    // ============================================
    // Handlers de Eventos
    // ============================================

    // Novos processos recebidos
    watcher.on('processos_recebidos', (event) => {
      console.log('\n📥 NOVOS PROCESSOS RECEBIDOS!');
      console.log(`   Fonte: ${event.source.toUpperCase()}`);
      console.log(`   Quantidade: ${event.items.length}`);

      for (const item of event.items) {
        const processo = item as import('../src/watcher.js').ProcessoRecebido;
        console.log(`\n   📋 ${processo.numero}`);
        console.log(`      Tipo: ${processo.tipo}`);
        console.log(`      Remetente: ${processo.remetente}`);
        console.log(`      Data: ${processo.dataRecebimento}`);
        if (processo.urgente) {
          console.log(`      ⚠️  URGENTE!`);
        }
        if (processo.anotacao) {
          console.log(`      📝 ${processo.anotacao}`);
        }
      }

      // Aqui você pode:
      // - Enviar notificação push
      // - Enviar email
      // - Atualizar dashboard
      // - Disparar workflow automático
    });

    // Blocos de assinatura
    watcher.on('blocos_assinatura', (event) => {
      console.log('\n✍️  NOVOS BLOCOS DE ASSINATURA!');
      console.log(`   Quantidade: ${event.items.length}`);

      for (const item of event.items) {
        const bloco = item as import('../src/watcher.js').BlocoAssinatura;
        console.log(`\n   📦 Bloco ${bloco.numero}`);
        console.log(`      Descrição: ${bloco.descricao}`);
        console.log(`      Documentos: ${bloco.quantidadeDocumentos}`);
        console.log(`      Origem: ${bloco.unidadeOrigem}`);
      }
    });

    // Retornos programados
    watcher.on('retornos_programados', (event) => {
      console.log('\n📅 RETORNOS PROGRAMADOS!');

      for (const item of event.items) {
        console.log(`   📋 ${item.numero} - Retorno: ${item.data}`);
      }
    });

    // Processos com prazo
    watcher.on('prazos', (event) => {
      console.log('\n⏰ PROCESSOS COM PRAZO!');

      for (const item of event.items) {
        const emoji = item.urgente ? '🔴' : '🟡';
        console.log(`   ${emoji} ${item.numero} - Prazo: ${item.data}`);
      }
    });

    // Eventos de sistema
    watcher.on('started', () => {
      console.log('👀 Watcher iniciado - monitorando SEI...\n');
    });

    watcher.on('stopped', () => {
      console.log('\n🛑 Watcher parado');
    });

    watcher.on('check', (type, source) => {
      const now = new Date().toLocaleTimeString('pt-BR');
      console.log(`[${now}] Verificando ${type} via ${source}...`);
    });

    watcher.on('error', (error) => {
      console.error('❌ Erro no watcher:', error.message);
    });

    // ============================================
    // Iniciar Monitoramento
    // ============================================

    watcher.start();

    // Manter rodando
    console.log('Pressione Ctrl+C para parar.\n');

    // Graceful shutdown
    process.on('SIGINT', async () => {
      console.log('\n\nEncerrando...');
      watcher.stop();
      await sei.close();
      process.exit(0);
    });

    // Manter processo vivo
    await new Promise(() => {}); // Aguarda indefinidamente

  } catch (error) {
    console.error('❌ Erro:', error);
    await sei.close();
    process.exit(1);
  }
}

// Exemplo de integração com sistema de notificações
async function sendNotification(title: string, body: string) {
  // Implementar conforme necessidade:
  // - Push notification (Firebase, OneSignal, etc.)
  // - Email (Nodemailer, SendGrid, etc.)
  // - Slack/Teams webhook
  // - SMS (Twilio, etc.)

  console.log(`📢 NOTIFICAÇÃO: ${title}\n   ${body}`);
}

// Executar
main();
