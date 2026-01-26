/**
 * Teste do eproc TJMG
 *
 * Uso:
 *   npx tsx examples/test-eproc-mg.ts
 *   npx tsx examples/test-eproc-mg.ts --headed
 */

import { chromium } from 'playwright';

const EPROC_1G_URL = 'https://eproc1g.tjmg.jus.br/eproc/';
const EPROC_2G_URL = 'https://eproc2g.tjmg.jus.br/eproc/';

async function testarEprocMG() {
  const headed = process.argv.includes('--headed');

  console.log('='.repeat(60));
  console.log('Teste do eproc TJMG');
  console.log('='.repeat(60));
  console.log(`Modo: ${headed ? 'Headed (visível)' : 'Headless'}`);
  console.log('');

  const browser = await chromium.launch({
    headless: !headed,
    slowMo: headed ? 500 : 0,
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });

  const page = await context.newPage();

  try {
    // ==========================================
    // Teste 1: Acessar página inicial
    // ==========================================
    console.log('1. Acessando eproc 1º grau...');
    await page.goto(EPROC_1G_URL, { waitUntil: 'networkidle' });

    const title = await page.title();
    console.log(`   Título: ${title}`);
    console.log(`   URL: ${page.url()}`);

    // ==========================================
    // Teste 2: Capturar snapshot de acessibilidade
    // ==========================================
    console.log('\n2. Analisando estrutura da página...');

    // Tira screenshot
    await page.screenshot({
      path: 'examples/screenshots/eproc-mg-login.png',
      fullPage: true
    });
    console.log('   Screenshot salvo: examples/screenshots/eproc-mg-login.png');

    // ==========================================
    // Teste 3: Identificar elementos de login
    // ==========================================
    console.log('\n3. Buscando elementos de login...');

    // Campo de usuário
    const userInputs = await page.$$('input[type="text"], input[name*="usuario"], input[id*="usuario"], input[name*="login"]');
    console.log(`   Campos de texto encontrados: ${userInputs.length}`);
    for (const input of userInputs) {
      const id = await input.getAttribute('id');
      const name = await input.getAttribute('name');
      const placeholder = await input.getAttribute('placeholder');
      console.log(`     - id="${id}" name="${name}" placeholder="${placeholder}"`);
    }

    // Campo de senha
    const passwordInputs = await page.$$('input[type="password"]');
    console.log(`   Campos de senha encontrados: ${passwordInputs.length}`);
    for (const input of passwordInputs) {
      const id = await input.getAttribute('id');
      const name = await input.getAttribute('name');
      console.log(`     - id="${id}" name="${name}"`);
    }

    // Botões de login
    const buttons = await page.$$('button, input[type="submit"], input[type="button"]');
    console.log(`   Botões encontrados: ${buttons.length}`);
    for (const btn of buttons) {
      const text = await btn.textContent();
      const value = await btn.getAttribute('value');
      const id = await btn.getAttribute('id');
      console.log(`     - "${text?.trim() || value}" id="${id}"`);
    }

    // Links de certificado
    const certLinks = await page.$$('a[href*="certificado"], a[href*="token"], button:has-text("certificado")');
    console.log(`   Links de certificado encontrados: ${certLinks.length}`);
    for (const link of certLinks) {
      const text = await link.textContent();
      const href = await link.getAttribute('href');
      console.log(`     - "${text?.trim()}" href="${href}"`);
    }

    // ==========================================
    // Teste 4: Verificar captcha
    // ==========================================
    console.log('\n4. Verificando presença de captcha...');

    const captchaImage = await page.$('img[src*="captcha"], img[id*="captcha"], img[class*="captcha"]');
    const recaptcha = await page.$('.g-recaptcha, [data-sitekey], iframe[src*="recaptcha"]');
    const captchaInput = await page.$('input[name*="captcha"], input[id*="captcha"]');

    if (captchaImage) {
      console.log('   ⚠️  Captcha de IMAGEM detectado!');
      const src = await captchaImage.getAttribute('src');
      console.log(`      src="${src}"`);
    }
    if (recaptcha) {
      console.log('   ⚠️  reCAPTCHA detectado!');
    }
    if (captchaInput) {
      console.log('   ⚠️  Campo de captcha detectado!');
      const name = await captchaInput.getAttribute('name');
      const id = await captchaInput.getAttribute('id');
      console.log(`      name="${name}" id="${id}"`);
    }
    if (!captchaImage && !recaptcha && !captchaInput) {
      console.log('   ✅ Nenhum captcha detectado na página inicial');
    }

    // ==========================================
    // Teste 5: Verificar formulários
    // ==========================================
    console.log('\n5. Analisando formulários...');

    const forms = await page.$$('form');
    console.log(`   Formulários encontrados: ${forms.length}`);
    for (let i = 0; i < forms.length; i++) {
      const form = forms[i];
      const action = await form.getAttribute('action');
      const method = await form.getAttribute('method');
      const id = await form.getAttribute('id');
      console.log(`   Form ${i + 1}: action="${action}" method="${method}" id="${id}"`);
    }

    // ==========================================
    // Teste 6: Capturar HTML do login
    // ==========================================
    console.log('\n6. Estrutura do login...');

    // Tenta encontrar o container de login
    const loginContainer = await page.$('#divLogin, .login-container, form[name*="login"], #frmLogin');
    if (loginContainer) {
      const html = await loginContainer.innerHTML();
      console.log('   Container de login encontrado. Salvando em examples/eproc-mg-login.html');

      const fs = await import('fs');
      await fs.promises.mkdir('examples/screenshots', { recursive: true });
      await fs.promises.writeFile('examples/eproc-mg-login.html', html);
    }

    // ==========================================
    // Teste 7: ARIA Snapshot
    // ==========================================
    console.log('\n7. ARIA Snapshot (elementos interativos):');

    const interactiveElements = await page.evaluate(() => {
      const elements: Array<{ tag: string; role: string; name: string; type: string }> = [];
      const selector = 'button, input, select, a[href], [role="button"], [role="link"]';

      document.querySelectorAll(selector).forEach((el) => {
        const htmlEl = el as HTMLElement;
        elements.push({
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role') || '',
          name: htmlEl.getAttribute('aria-label') || htmlEl.getAttribute('title') || htmlEl.textContent?.trim().substring(0, 50) || '',
          type: (el as HTMLInputElement).type || '',
        });
      });

      return elements.slice(0, 20); // Limita a 20
    });

    for (const el of interactiveElements) {
      console.log(`   <${el.tag}${el.type ? ` type="${el.type}"` : ''}${el.role ? ` role="${el.role}"` : ''}> "${el.name}"`);
    }

    // ==========================================
    // Resumo
    // ==========================================
    console.log('\n' + '='.repeat(60));
    console.log('RESUMO');
    console.log('='.repeat(60));
    console.log(`URL: ${page.url()}`);
    console.log(`Título: ${title}`);
    console.log(`Campos de login: ${userInputs.length} texto, ${passwordInputs.length} senha`);
    console.log(`Captcha: ${captchaImage || recaptcha ? 'SIM' : 'NÃO'}`);
    console.log('');

    if (headed) {
      console.log('Pressione Ctrl+C para fechar...');
      await new Promise(() => {}); // Mantém aberto
    }

  } catch (error) {
    console.error('Erro:', error);
  } finally {
    if (!headed) {
      await browser.close();
    }
  }
}

testarEprocMG();
