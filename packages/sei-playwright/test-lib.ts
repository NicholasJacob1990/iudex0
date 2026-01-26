/**
 * Script de teste da biblioteca sei-playwright
 *
 * Uso:
 *   SEI_USER=seu.usuario SEI_PASS=suaSenha npx tsx test-lib.ts
 */

import { SEIClient } from './src/client.js';

async function main() {
  const usuario = process.env.SEI_USER;
  const senha = process.env.SEI_PASS;
  const orgao = process.env.SEI_ORGAO;

  if (!usuario || !senha) {
    console.error('❌ Configure as variáveis de ambiente:');
    console.error('   SEI_USER=seu.usuario SEI_PASS=suaSenha npx tsx test-lib.ts');
    process.exit(1);
  }

  console.log('🚀 Iniciando teste da biblioteca sei-playwright...\n');

  const client = new SEIClient({
    baseUrl: 'https://www.sei.mg.gov.br',
    browser: {
      usuario,
      senha,
      orgao,
    },
    playwright: {
      headless: false, // Mostrar navegador para debug
      timeout: 60000,
    },
  });

  try {
    // 1. Inicializar
    console.log('1️⃣ Inicializando cliente...');
    await client.init();
    console.log('   ✅ Cliente inicializado\n');

    // 2. Login
    console.log('2️⃣ Fazendo login...');
    const loggedIn = await client.login();
    if (!loggedIn) {
      throw new Error('Falha no login');
    }
    console.log('   ✅ Login realizado com sucesso\n');

    // 3. Listar tipos de processo
    console.log('3️⃣ Listando tipos de processo...');
    const tiposProcesso = await client.listProcessTypes();
    console.log(`   ✅ ${tiposProcesso.length} tipos encontrados`);
    console.log(`   Exemplos: ${tiposProcesso.slice(0, 3).map(t => t.nome || t).join(', ')}\n`);

    // 4. Listar unidades
    console.log('4️⃣ Listando unidades...');
    const unidades = await client.listUnits();
    console.log(`   ✅ ${unidades.length} unidades encontradas`);
    console.log(`   Exemplos: ${unidades.slice(0, 3).map(u => u.Sigla || u).join(', ')}\n`);

    // 5. Screenshot
    console.log('5️⃣ Capturando screenshot...');
    const screenshot = await client.screenshot();
    console.log(`   ✅ Screenshot capturado (${Math.round(screenshot.length / 1024)}KB base64)\n`);

    // 6. Listar meus processos (se disponível)
    console.log('6️⃣ Listando processos da unidade...');
    const browserClient = client.getBrowserClient();
    if (browserClient) {
      try {
        const meusProcessos = await browserClient.listMeusProcessos('abertos', 5);
        console.log(`   ✅ ${meusProcessos.length} processos encontrados`);
        for (const p of meusProcessos.slice(0, 3)) {
          console.log(`      - ${p.numero}: ${p.tipo}`);
        }
      } catch (e) {
        console.log(`   ⚠️ Não foi possível listar processos: ${e}`);
      }
    }
    console.log('');

    console.log('═══════════════════════════════════════');
    console.log('✅ TODOS OS TESTES PASSARAM!');
    console.log('═══════════════════════════════════════\n');

  } catch (error) {
    console.error('❌ Erro:', error);
  } finally {
    console.log('🔚 Fechando cliente...');
    await client.close();
    console.log('   Finalizado.\n');
  }
}

main();
