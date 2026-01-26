/**
 * Exemplo básico de uso do sei-playwright
 *
 * Execute: pnpm example
 */

import { SEIClient } from '../src/index.js';
import * as fs from 'fs/promises';
import * as path from 'path';

async function main() {
  // ============================================
  // Configuração
  // ============================================

  const sei = new SEIClient({
    baseUrl: 'https://sei.mg.gov.br',

    // Para usar SOAP (requer cadastro do sistema no SEI)
    // soap: {
    //   siglaSistema: 'MEU_SISTEMA',
    //   identificacaoServico: 'MinhaChave123',
    // },

    // Para usar browser
    browser: {
      usuario: process.env.SEI_USUARIO ?? '',
      senha: process.env.SEI_SENHA ?? '',
    },

    // Opções do Playwright
    playwright: {
      headless: process.env.HEADLESS !== 'false',
      timeout: 30000,
      // userDataDir: '/tmp/sei-session', // Para persistir sessão
    },
  });

  try {
    // ============================================
    // Inicialização
    // ============================================

    console.log('Inicializando cliente SEI...');
    await sei.init();

    // Login (se não usar userDataDir)
    console.log('Realizando login...');
    const loggedIn = await sei.login();
    if (!loggedIn) {
      throw new Error('Falha no login');
    }
    console.log('Login realizado com sucesso!');

    // ============================================
    // Exemplo 1: Abrir processo e listar documentos
    // ============================================

    const numeroProcesso = '5030.01.0002527/2025-32';
    console.log(`\nAbrindo processo ${numeroProcesso}...`);

    const opened = await sei.openProcess(numeroProcesso);
    if (!opened) {
      throw new Error('Processo não encontrado');
    }

    const docs = await sei.listDocuments();
    console.log(`Documentos encontrados: ${docs.length}`);
    docs.forEach((doc, i) => {
      console.log(`  ${i + 1}. [${doc.tipo}] ${doc.titulo} (ID: ${doc.id})`);
    });

    // ============================================
    // Exemplo 2: Criar documento
    // ============================================

    console.log('\nCriando documento...');
    const docId = await sei.createDocument(numeroProcesso, {
      idSerie: 'Despacho',
      descricao: 'Despacho de teste via sei-playwright',
      interessados: ['CODEMGE'],
      observacao: 'Documento criado automaticamente',
      nivelAcesso: 0, // Público
      conteudoHtml: `
        <p>Este é um documento de teste criado automaticamente.</p>
        <p>Data: ${new Date().toLocaleDateString('pt-BR')}</p>
      `,
    });

    if (docId) {
      console.log(`Documento criado com ID: ${docId}`);
    }

    // ============================================
    // Exemplo 3: Upload de arquivo
    // ============================================

    // Lê um arquivo PDF para upload (exemplo)
    const pdfPath = process.env.PDF_PATH;
    if (pdfPath) {
      console.log(`\nFazendo upload de ${path.basename(pdfPath)}...`);

      const pdfBuffer = await fs.readFile(pdfPath);
      const pdfBase64 = pdfBuffer.toString('base64');

      const uploadId = await sei.uploadDocument(
        numeroProcesso,
        path.basename(pdfPath),
        pdfBase64,
        {
          descricao: 'Documento externo via sei-playwright',
          nivelAcesso: 0,
        }
      );

      if (uploadId) {
        console.log(`Upload concluído com ID: ${uploadId}`);
      }
    }

    // ============================================
    // Exemplo 4: Screenshot
    // ============================================

    console.log('\nCapturando screenshot...');
    const screenshotPath = '/tmp/sei-screenshot.png';
    await sei.screenshot(screenshotPath);
    console.log(`Screenshot salvo em: ${screenshotPath}`);

    // ============================================
    // Exemplo 5: Tramitação (comentado para segurança)
    // ============================================

    // console.log('\nTramitando processo...');
    // await sei.forwardProcess(numeroProcesso, {
    //   unidadesDestino: ['GENSU'],
    //   manterAberto: true,
    //   enviarEmailNotificacao: false,
    // });

    console.log('\n✅ Exemplos concluídos com sucesso!');
  } catch (error) {
    console.error('❌ Erro:', error);
    process.exit(1);
  } finally {
    // ============================================
    // Limpeza
    // ============================================

    console.log('\nFechando cliente...');
    await sei.close();
  }
}

// Executa
main();
