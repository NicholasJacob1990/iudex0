/**
 * Teste CDP - Conecta ao Chrome já aberto
 *
 * 1. Abra o Chrome com: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
 * 2. Faça login no SEI manualmente
 * 3. Execute este script
 */

import { SEIClient } from './src/client.js';

async function main() {
  console.log('🚀 Conectando ao Chrome via CDP...');
  console.log('   Endpoint: http://localhost:9222');
  console.log('');

  const client = new SEIClient({
    baseUrl: 'https://www.sei.mg.gov.br',
    playwright: {
      cdpEndpoint: 'http://localhost:9222',
      timeout: 60000,
    },
  });

  try {
    await client.init();
    console.log('✅ Conectado ao Chrome!');

    const browserClient = client.getBrowserClient();
    if (browserClient) {
      const page = browserClient.getPage();
      const url = page.url();
      const title = await page.title();

      console.log(`📄 URL atual: ${url}`);
      console.log(`📄 Título: ${title}`);

      // Verifica se está logado
      const loggedIn = await client.isLoggedIn();
      console.log(`🔐 Logado: ${loggedIn ? 'Sim' : 'Não'}`);

      if (loggedIn) {
        // Lista processos
        console.log('');
        console.log('📋 Testando operações...');

        // Abre um processo
        const processo = '5030.01.0002527/2025-32';
        console.log(`   Abrindo processo ${processo}...`);
        await client.openProcess(processo);

        const docs = await client.listDocuments();
        console.log(`   Documentos encontrados: ${docs.length}`);
      }
    }

  } catch (error: any) {
    if (error.message?.includes('ECONNREFUSED')) {
      console.log('❌ Chrome não está rodando com debugging habilitado!');
      console.log('');
      console.log('Execute primeiro:');
      console.log('/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222');
    } else {
      console.error('❌ Erro:', error);
    }
  } finally {
    // Não fecha o browser! É o Chrome do usuário
    console.log('');
    console.log('💡 Browser não fechado (é seu Chrome)');
  }
}

main();
