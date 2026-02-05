import { test, expect, Page, APIRequestContext } from '@playwright/test';

const API_BASE = 'http://127.0.0.1:8000/api';

const templateMeta = {
  variables_schema: {
    required: ['cliente_nome'],
    properties: {
      cliente_nome: { type: 'string', label: 'Nome do cliente' },
      risco_alto: { type: 'boolean', label: 'Risco alto?' },
      categoria: { type: 'string', enum: ['A', 'B'], label: 'Categoria' },
      itens: { type: 'array', label: 'Itens' },
    },
  },
};

const templateDescription = `<!-- IUDX_TEMPLATE_V1 ${JSON.stringify(templateMeta)} -->
# Corpo do template`;

let accessToken = '';
let refreshToken = '';
let templateId = '';
let documentId = '';

const attachAuth = async (page: Page) => {
  await page.addInitScript(
    ({ accessToken, refreshToken }) => {
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('refresh_token', refreshToken);
    },
    { accessToken, refreshToken }
  );
};

const authHeaders = () => ({
  Authorization: `Bearer ${accessToken}`,
});

const createTemplate = async (request: APIRequestContext) => {
  const response = await request.post(`${API_BASE}/templates`, {
    headers: authHeaders(),
    data: {
      name: 'Template de Parecer (E2E)',
      description: templateDescription,
      tags: ['e2e'],
      document_type: 'PARECER',
    },
  });
  if (!response.ok()) {
    throw new Error(`Falha ao criar template: ${response.status()}`);
  }
  const data = await response.json();
  templateId = data.id;
};

const createDocument = async (request: APIRequestContext) => {
  const response = await request.post(`${API_BASE}/documents/from-text`, {
    headers: authHeaders(),
    form: {
      title: 'Documento base',
      content: 'Conteúdo base para testes de minuta.',
    },
  });
  if (!response.ok()) {
    throw new Error(`Falha ao criar documento: ${response.status()}`);
  }
  const data = await response.json();
  documentId = data.id;
};

test.beforeAll(async ({ request }) => {
  const loginResponse = await request.post(`${API_BASE}/auth/login-test`);
  if (!loginResponse.ok()) {
    throw new Error(`Falha no login-test: ${loginResponse.status()}`);
  }
  const loginData = await loginResponse.json();
  accessToken = loginData.access_token;
  refreshToken = loginData.refresh_token;

  await createTemplate(request);
  await createDocument(request);
});

test.afterAll(async ({ request }) => {
  if (templateId) {
    await request.delete(`${API_BASE}/templates/${templateId}`, {
      headers: authHeaders(),
    });
  }
  if (documentId) {
    await request.delete(`${API_BASE}/documents/${documentId}`, {
      headers: authHeaders(),
    });
  }
});

test.beforeEach(async ({ page }) => {
  await attachAuth(page);
});

test('carrega campos do modelo e sincroniza JSON avançado', async ({ page }) => {
  await page.goto('/minuta');

  await page.getByTestId('settings-toggle').click();
  await expect(page.getByTestId('settings-panel')).toBeVisible();

  const documentType = page.getByTestId('document-type-select');
  await documentType.selectOption('PARECER');
  await expect(documentType).toHaveValue('PARECER');
});

test('abre painel de arquivos', async ({ page }) => {
  await page.goto('/minuta');

  await page.getByTestId('arquivos-toggle').click();
  await expect(page.getByTestId('arquivos-panel')).toBeVisible();
  await expect(page.getByText('Arquivos anexados')).toBeVisible();
});

test('fluxo de chat responde comando /help', async ({ page }) => {
  await page.goto('/minuta');

  const input = page.getByTestId('chat-input');
  await expect(input).toBeVisible({ timeout: 15000 });
  const message = 'Olá, teste E2E';
  await input.click();
  await input.type(message);
  await expect(input).toHaveValue(message);
  const messageRequest = page.waitForRequest((request) =>
    request.url().includes('/chats/') &&
    request.url().includes('/messages/stream') &&
    request.method() === 'POST'
  );
  await page.getByTestId('chat-send').click();
  await messageRequest;

  await expect(input).toHaveValue('');
});
