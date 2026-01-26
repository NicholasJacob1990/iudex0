/**
 * Baixa o último documento de um processo usando a biblioteca sei-playwright
 */

import { SEIClient } from './src/client.js';
import * as fs from 'fs';

async function main() {
  const processo = '5030.01.0002527/2025-32';

  const client = new SEIClient({
    baseUrl: 'https://www.sei.mg.gov.br',
    browser: {
      usuario: process.env.SEI_USER!,
      senha: process.env.SEI_PASS!,
      orgao: process.env.SEI_ORGAO,
    },
    playwright: {
      headless: false,
      timeout: 60000,
    },
  });

  try {
    console.log('🚀 Inicializando...');
    await client.init();

    console.log('🔐 Fazendo login...');
    const loggedIn = await client.login();
    if (!loggedIn) throw new Error('Falha no login');
    console.log('   ✅ Login OK');

    const browserClient = client.getBrowserClient();
    if (!browserClient) throw new Error('BrowserClient não disponível');

    console.log(`📂 Abrindo processo ${processo}...`);
    const page = browserClient.getPage();

    // Usa pesquisa rápida com locator semântico
    const searchBox = page.getByRole('textbox', { name: /pesquisar/i }).first();
    await searchBox.fill(processo);
    await searchBox.press('Enter');

    // Aguarda carregar
    await page.waitForTimeout(3000);

    console.log('📋 Listando documentos...');

    // Acessa iframe da árvore
    const treeFrame = page.frameLocator('iframe[name="ifrArvore"]');

    // Busca todos os links de documentos (têm número entre parênteses)
    const docLinks = await treeFrame.getByRole('link').filter({ hasText: /\(\d+\)/ }).all();

    console.log(`   Encontrados ${docLinks.length} documentos`);

    if (docLinks.length === 0) {
      console.log('❌ Nenhum documento encontrado');
      return;
    }

    // Pega o último documento
    const lastDoc = docLinks[docLinks.length - 1];
    const docText = await lastDoc.textContent();
    console.log(`📄 Último documento: ${docText}`);

    // Clica no documento
    await lastDoc.click();
    await page.waitForTimeout(2000);

    // Acessa iframe de visualização e clica em gerar PDF
    const viewFrame = page.frameLocator('iframe[name="ifrVisualizacao"]');
    const pdfButton = viewFrame.getByRole('link', { name: /gerar.*pdf.*documento/i });

    // Configura listener de download
    const downloadPromise = page.waitForEvent('download');

    await pdfButton.click();
    await page.waitForTimeout(1000);

    // Clica no botão Gerar do modal
    const gerarButton = viewFrame.getByRole('button', { name: /gerar/i });
    await gerarButton.click();

    // Aguarda download
    console.log('⬇️ Baixando...');
    const download = await downloadPromise;

    const filename = download.suggestedFilename();
    const destPath = `/Users/nicholasjacob/Downloads/${filename}`;
    await download.saveAs(destPath);

    console.log(`✅ Documento salvo em: ${destPath}`);

  } catch (error) {
    console.error('❌ Erro:', error);
  } finally {
    console.log('🔚 Fechando...');
    await client.close();
  }
}

main();
