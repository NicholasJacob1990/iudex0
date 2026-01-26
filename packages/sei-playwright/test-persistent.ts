/**
 * Teste de Persistent Context - Mantém sessão entre execuções
 *
 * Primeira execução: Abre Chrome visível, faz login manual
 * Próximas execuções: Sessão já está salva, pula login
 *
 * Uso:
 *   npx tsx test-persistent.ts          # Primeira vez (faz login)
 *   npx tsx test-persistent.ts          # Segunda vez (já logado!)
 *   npx tsx test-persistent.ts headless # Depois de logado, pode rodar headless
 */

import { SEIClient } from './src/client.js';

async function main() {
  const headless = process.argv.includes('headless');

  console.log('🚀 Iniciando com Persistent Context...');
  console.log(`   Modo: ${headless ? 'headless' : 'visível'}`);
  console.log(`   Perfil: ~/.sei-playwright/chrome-profile`);

  const client = new SEIClient({
    baseUrl: 'https://www.sei.mg.gov.br',
    browser: {
      usuario: process.env.SEI_USER,
      senha: process.env.SEI_PASS,
      orgao: process.env.SEI_ORGAO || 'CODEMGE',
    },
    playwright: {
      persistent: true, // <-- Mantém sessão!
      channel: 'chrome', // <-- Usa Chrome instalado
      headless,
      timeout: 60000,
    },
  });

  try {
    await client.init();

    // Verifica se já está logado
    const alreadyLoggedIn = await client.isLoggedIn();

    if (alreadyLoggedIn) {
      console.log('✅ Já logado! (sessão persistente funcionando)');
    } else {
      console.log('🔐 Fazendo login...');

      // Se não tiver credenciais, espera login manual
      if (!process.env.SEI_USER || !process.env.SEI_PASS) {
        console.log('');
        console.log('⚠️  Credenciais não configuradas!');
        console.log('   Faça login manualmente no navegador.');
        console.log('   Depois feche este script (Ctrl+C).');
        console.log('   Na próxima execução, a sessão estará salva.');
        console.log('');

        // Aguarda 5 minutos para login manual
        await new Promise((resolve) => setTimeout(resolve, 300000));
      } else {
        const success = await client.login();
        if (success) {
          console.log('✅ Login OK!');
        } else {
          console.log('❌ Falha no login');
          return;
        }
      }
    }

    // Demonstra que está funcionando
    const browserClient = client.getBrowserClient();
    if (browserClient) {
      const page = browserClient.getPage();
      const title = await page.title();
      console.log(`📄 Página atual: ${title}`);

      // Captura screenshot
      const screenshot = await client.screenshot();
      console.log(`📸 Screenshot: ${screenshot.substring(0, 50)}... (${screenshot.length} chars base64)`);
    }

    console.log('');
    console.log('💡 Dica: Na próxima execução, você já estará logado!');
    console.log('   Execute novamente: npx tsx test-persistent.ts');
    console.log('   Ou headless: npx tsx test-persistent.ts headless');

  } catch (error) {
    console.error('❌ Erro:', error);
  } finally {
    console.log('🔚 Fechando...');
    await client.close();
  }
}

main();
