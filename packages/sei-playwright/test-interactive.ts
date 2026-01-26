/**
 * Teste interativo da biblioteca sei-playwright
 *
 * Execute: npx tsx test-interactive.ts
 */

import { SEIClient } from './src/index.js';
import * as readline from 'readline';

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

function ask(question: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(question, resolve);
  });
}

async function main() {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║          Teste Interativo - sei-playwright                 ║
╚════════════════════════════════════════════════════════════╝
`);

  // Coletar credenciais
  const seiUrl = await ask('URL do SEI (ex: https://sei.mg.gov.br): ');
  const usuario = await ask('Usuário: ');
  const senha = await ask('Senha: ');
  const orgao = await ask('Órgão (deixe vazio se não aplicável): ');

  console.log('\n⏳ Iniciando navegador...\n');

  const sei = new SEIClient({
    baseUrl: seiUrl,
    browser: {
      usuario,
      senha,
      orgao: orgao || undefined,
    },
    playwright: {
      headless: false, // Mostra o navegador para visualizar
      timeout: 30000,
    },
  });

  try {
    await sei.init();
    console.log('✅ Navegador iniciado\n');

    console.log('⏳ Fazendo login...\n');
    const loggedIn = await sei.login();

    if (!loggedIn) {
      console.log('❌ Login falhou. Verifique as credenciais.');
      await sei.close();
      rl.close();
      return;
    }

    console.log('✅ Login realizado com sucesso!\n');

    // Menu de testes
    while (true) {
      console.log(`
┌────────────────────────────────────────┐
│  Escolha uma operação para testar:     │
├────────────────────────────────────────┤
│  1. Listar tipos de processo           │
│  2. Listar tipos de documento          │
│  3. Abrir processo por número          │
│  4. Listar documentos do processo      │
│  5. Consultar andamentos               │
│  6. Capturar screenshot                │
│  7. Listar blocos de assinatura        │
│  0. Sair                               │
└────────────────────────────────────────┘
`);

      const opcao = await ask('Opção: ');

      switch (opcao) {
        case '1': {
          console.log('\n⏳ Listando tipos de processo...\n');
          try {
            const tipos = await sei.listProcessTypes();
            console.log('Tipos de processo:');
            tipos.slice(0, 10).forEach((t, i) => {
              console.log(`  ${i + 1}. ${t.Nome}`);
            });
            if (tipos.length > 10) {
              console.log(`  ... e mais ${tipos.length - 10} tipos`);
            }
          } catch (err) {
            console.log('❌ Erro:', (err as Error).message);
          }
          break;
        }

        case '2': {
          console.log('\n⏳ Listando tipos de documento...\n');
          try {
            const tipos = await sei.listDocumentTypes();
            console.log('Tipos de documento:');
            tipos.slice(0, 10).forEach((t, i) => {
              console.log(`  ${i + 1}. ${t.Nome}`);
            });
            if (tipos.length > 10) {
              console.log(`  ... e mais ${tipos.length - 10} tipos`);
            }
          } catch (err) {
            console.log('❌ Erro:', (err as Error).message);
          }
          break;
        }

        case '3': {
          const numero = await ask('Número do processo (ex: 5030.01.0001234/2025-00): ');
          console.log('\n⏳ Abrindo processo...\n');
          try {
            const opened = await sei.openProcess(numero);
            if (opened) {
              console.log('✅ Processo aberto!');
            } else {
              console.log('❌ Processo não encontrado');
            }
          } catch (err) {
            console.log('❌ Erro:', (err as Error).message);
          }
          break;
        }

        case '4': {
          console.log('\n⏳ Listando documentos do processo atual...\n');
          try {
            const docs = await sei.listDocuments();
            console.log('Documentos:');
            docs.forEach((d, i) => {
              console.log(`  ${i + 1}. [${d.tipo}] ${d.titulo} (ID: ${d.id})`);
            });
            if (docs.length === 0) {
              console.log('  Nenhum documento encontrado. Abra um processo primeiro.');
            }
          } catch (err) {
            console.log('❌ Erro:', (err as Error).message);
          }
          break;
        }

        case '5': {
          const numero = await ask('Número do processo: ');
          console.log('\n⏳ Consultando andamentos...\n');
          try {
            const andamentos = await sei.listAndamentos(numero);
            console.log('Últimos andamentos:');
            andamentos.slice(0, 5).forEach((a, i) => {
              console.log(`  ${i + 1}. ${a.data} | ${a.unidade} | ${a.descricao.substring(0, 50)}...`);
            });
          } catch (err) {
            console.log('❌ Erro:', (err as Error).message);
          }
          break;
        }

        case '6': {
          const path = './screenshot.png';
          console.log('\n⏳ Capturando screenshot...\n');
          try {
            await sei.screenshot(path);
            console.log(`✅ Screenshot salvo em: ${path}`);
          } catch (err) {
            console.log('❌ Erro:', (err as Error).message);
          }
          break;
        }

        case '7': {
          console.log('\n⏳ Listando blocos de assinatura...\n');
          try {
            const blocos = await sei.listBlocos();
            console.log('Blocos:');
            blocos.forEach((b, i) => {
              console.log(`  ${i + 1}. ${b.descricao} (${b.quantidade} docs) - ${b.unidade}`);
            });
            if (blocos.length === 0) {
              console.log('  Nenhum bloco encontrado.');
            }
          } catch (err) {
            console.log('❌ Erro:', (err as Error).message);
          }
          break;
        }

        case '0': {
          console.log('\n⏳ Encerrando...\n');
          await sei.close();
          rl.close();
          console.log('✅ Teste finalizado!');
          return;
        }

        default:
          console.log('\n❌ Opção inválida\n');
      }
    }
  } catch (error) {
    console.error('❌ Erro:', error);
    await sei.close();
    rl.close();
  }
}

main();
