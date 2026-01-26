/**
 * Teste de Login no eproc TJMG
 *
 * Uso:
 *   # Login com senha (interativo)
 *   npx tsx examples/test-eproc-login.ts
 *
 *   # Login com senha (via linha de comando)
 *   npx tsx examples/test-eproc-login.ts --user CPF --senha SENHA
 *
 *   # Login com certificado A1
 *   npx tsx examples/test-eproc-login.ts --cert /path/to/cert.pfx --pass senha123
 *
 *   # Login com certificado A3 (token físico)
 *   npx tsx examples/test-eproc-login.ts --a3
 *
 *   # Login com certificado A3 na nuvem
 *   npx tsx examples/test-eproc-login.ts --cloud [certisign|serasa|safeweb|soluti]
 *
 *   # Modo headed (visível)
 *   npx tsx examples/test-eproc-login.ts --headed
 */

import * as readline from 'readline';
import { EprocClient } from '../src/eproc/client.js';
import type { AuthConfig, CertificateA3CloudAuth } from '../src/types/index.js';

const EPROC_1G_URL = 'https://eproc1g.tjmg.jus.br/eproc/';

// Parse argumentos
const args = process.argv.slice(2);
const headed = args.includes('--headed');
const useA3 = args.includes('--a3');
const useCloud = args.includes('--cloud');
const cloudIndex = args.indexOf('--cloud');
const cloudProvider = cloudIndex !== -1 ? (args[cloudIndex + 1] || 'certisign') : 'certisign';
const certIndex = args.indexOf('--cert');
const passIndex = args.indexOf('--pass');

const certPath = certIndex !== -1 ? args[certIndex + 1] : null;
const certPass = passIndex !== -1 ? args[passIndex + 1] : null;

// Credenciais via linha de comando
const userIndex = args.indexOf('--user');
const senhaIndex = args.indexOf('--senha');
const cmdUser = userIndex !== -1 ? args[userIndex + 1] : null;
const cmdSenha = senhaIndex !== -1 ? args[senhaIndex + 1] : null;

/**
 * Prompt interativo para credenciais
 */
async function askCredentials(): Promise<{ usuario: string; senha: string } | null> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    console.log('\n--- Login com Usuário e Senha ---');
    console.log('(Deixe vazio para usar certificado digital)\n');

    rl.question('Usuário (CPF): ', (usuario) => {
      if (!usuario.trim()) {
        rl.close();
        resolve(null);
        return;
      }

      rl.question('Senha: ', (senha) => {
        rl.close();
        resolve({ usuario: usuario.trim(), senha });
      });
    });
  });
}

/**
 * Configura autenticação baseado nos parâmetros
 */
async function getAuthConfig(): Promise<AuthConfig> {
  // Credenciais via linha de comando
  if (cmdUser && cmdSenha) {
    console.log(`\nUsando login com senha: ${cmdUser}`);
    return {
      type: 'password',
      cpf: cmdUser,
      senha: cmdSenha,
    };
  }

  // Certificado A1 via linha de comando
  if (certPath && certPass) {
    console.log(`\nUsando certificado A1: ${certPath}`);
    return {
      type: 'certificate_a1',
      pfxPath: certPath,
      passphrase: certPass,
    };
  }

  // Certificado A3 na nuvem
  if (useCloud) {
    const provider = cloudProvider as CertificateA3CloudAuth['provider'];
    console.log(`\nUsando certificado A3 na nuvem: ${provider}`);
    return {
      type: 'certificate_a3_cloud',
      provider,
      approvalTimeout: 120000, // 2 minutos
      onApprovalRequired: async (info) => {
        console.log('\n' + '='.repeat(50));
        console.log('   AÇÃO NECESSÁRIA NO CELULAR');
        console.log('='.repeat(50));
        console.log(`\n   ${info.message}`);
        console.log(`   Provider: ${info.provider}`);
        console.log(`   Tempo limite: ${info.expiresIn} segundos`);
        console.log('\n   Abra o app do certificado no celular');
        console.log('   e aprove a solicitação de assinatura.');
        console.log('\n' + '='.repeat(50) + '\n');
      },
    };
  }

  // Certificado A3 físico
  if (useA3) {
    console.log('\nUsando certificado A3 físico (token USB)');
    return {
      type: 'certificate_a3_physical',
      pinTimeout: 300000, // 5 minutos
      onPinRequired: async () => {
        console.log('\n========================================');
        console.log('   AÇÃO NECESSÁRIA: Digite o PIN do token');
        console.log('========================================\n');
      },
    };
  }

  // Tenta obter credenciais interativamente
  const creds = await askCredentials();

  if (creds) {
    return {
      type: 'password',
      cpf: creds.usuario,
      senha: creds.senha,
    };
  }

  // Fallback: certificado A3 nuvem
  console.log('\nNenhuma credencial informada. Usando certificado A3 na nuvem (Certisign).');
  return {
    type: 'certificate_a3_cloud',
    provider: 'certisign',
    approvalTimeout: 120000,
    onApprovalRequired: async (info) => {
      console.log('\n' + '='.repeat(50));
      console.log('   AÇÃO NECESSÁRIA NO CELULAR');
      console.log('='.repeat(50));
      console.log(`\n   ${info.message}`);
      console.log(`   Tempo limite: ${info.expiresIn} segundos`);
      console.log('\n' + '='.repeat(50) + '\n');
    },
  };
}

async function main() {
  console.log('='.repeat(60));
  console.log('Teste de Login - eproc TJMG');
  console.log('='.repeat(60));
  console.log(`URL: ${EPROC_1G_URL}`);
  console.log(`Modo: ${headed ? 'Headed (visível)' : 'Headless'}`);

  const authConfig = await getAuthConfig();

  console.log(`\nTipo de autenticação: ${authConfig.type}`);
  console.log('');

  // Cria cliente
  const client = new EprocClient({
    baseUrl: EPROC_1G_URL,
    auth: authConfig,
    tribunal: 'tjmg',
    instancia: '1g',
    playwright: {
      headless: !headed,
      slowMo: headed ? 300 : 0,
      timeout: 60000,
    },
    // Handler de notificações
    onNotification: async (notification) => {
      console.log(`[NOTIFICAÇÃO] ${notification.type}: ${notification.message}`);
    },
  });

  // Registra eventos
  client.on('login:success', ({ usuario }) => {
    console.log(`\n✅ Login realizado com sucesso! Usuário: ${usuario}`);
  });

  client.on('login:error', ({ error }) => {
    console.log(`\n❌ Erro no login: ${error}`);
  });

  client.on('login:pin_required', ({ timeout }) => {
    console.log(`\n⏳ Aguardando PIN do token... (timeout: ${timeout / 1000}s)`);
  });

  client.on('login:approval_required', (info) => {
    console.log(`\n📱 Aprovação necessária: ${info.message}`);
  });

  client.on('captcha:detected', (captcha) => {
    console.log(`\n🔐 Captcha detectado: ${captcha.type}`);
  });

  try {
    // Inicializa
    console.log('Inicializando cliente...');
    await client.init();
    console.log('Cliente inicializado.');

    // Faz login
    console.log('\nIniciando login...');
    const loginSuccess = await client.login();

    if (loginSuccess) {
      console.log('\n' + '='.repeat(60));
      console.log('LOGIN BEM SUCEDIDO!');
      console.log('='.repeat(60));

      // Captura screenshot
      const screenshotPath = 'examples/screenshots/eproc-logado.png';
      await client.screenshot(screenshotPath);
      console.log(`Screenshot salvo: ${screenshotPath}`);

      // Mostra URL atual
      console.log(`URL atual: ${client.getCurrentUrl()}`);

      // Mantém aberto se headed
      if (headed) {
        console.log('\nNavegador aberto. Pressione Ctrl+C para fechar.');
        await new Promise(() => {}); // Aguarda indefinidamente
      }
    } else {
      console.log('\n' + '='.repeat(60));
      console.log('LOGIN FALHOU');
      console.log('='.repeat(60));

      // Captura screenshot do erro
      const screenshotPath = 'examples/screenshots/eproc-login-erro.png';
      await client.screenshot(screenshotPath);
      console.log(`Screenshot do erro salvo: ${screenshotPath}`);
    }
  } catch (error) {
    console.error('\nErro durante execução:', error);

    // Tenta capturar screenshot
    try {
      await client.screenshot('examples/screenshots/eproc-erro.png');
    } catch {
      // Ignora
    }
  } finally {
    if (!headed) {
      await client.close();
      console.log('\nCliente fechado.');
    }
  }
}

main().catch(console.error);
