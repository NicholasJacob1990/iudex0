/**
 * Script para baixar último documento de um processo
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
    console.log('Inicializando...');
    await client.init();

    console.log('Fazendo login...');
    const loggedIn = await client.login();
    if (!loggedIn) throw new Error('Falha no login');

    console.log(`Abrindo processo ${processo}...`);
    const browserClient = client.getBrowserClient();
    if (!browserClient) throw new Error('BrowserClient não disponível');

    const opened = await browserClient.openProcess(processo);
    if (!opened) throw new Error('Processo não encontrado');

    console.log('Listando documentos...');
    const docs = await browserClient.listDocuments();
    console.log(`Encontrados ${docs.length} documentos`);

    if (docs.length === 0) {
      console.log('Nenhum documento encontrado');
      return;
    }

    // Último documento
    const lastDoc = docs[docs.length - 1];
    console.log(`Último documento: ${lastDoc.tipo} - ${lastDoc.titulo} (ID: ${lastDoc.id})`);

    // Tenta baixar
    console.log('Baixando documento...');
    const content = await browserClient.downloadDocument(lastDoc.id);

    if (content) {
      const filename = `documento_${lastDoc.id}.pdf`;
      fs.writeFileSync(filename, Buffer.from(content, 'base64'));
      console.log(`✅ Documento salvo em: ${filename}`);
    } else {
      console.log('❌ Não foi possível baixar o documento');
    }

  } catch (error) {
    console.error('Erro:', error);
  } finally {
    console.log('Fechando...');
    await client.close();
  }
}

main();
