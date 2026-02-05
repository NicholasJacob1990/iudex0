import { test, expect, Page, APIRequestContext } from '@playwright/test';

const API_BASE = 'http://127.0.0.1:8000/api';

let accessToken = '';
let refreshToken = '';
let playbookId = '';

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

const createPlaybook = async (request: APIRequestContext) => {
  const response = await request.post(`${API_BASE}/playbooks`, {
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    data: JSON.stringify({
      name: 'Playbook E2E',
      description: 'Playbook criado para testes E2E',
      area: 'ti',
      scope: 'personal',
      party_perspective: 'neutro',
      rules: [],
    }),
  });
  if (!response.ok()) {
    const detail = await response.text();
    throw new Error(`Falha ao criar playbook: ${response.status()} ${detail}`);
  }
  const data = await response.json();
  playbookId = data.id;
};

test.beforeAll(async ({ request }) => {
  const loginResponse = await request.post(`${API_BASE}/auth/login-test`);
  if (!loginResponse.ok()) {
    throw new Error(`Falha no login-test: ${loginResponse.status()}`);
  }
  const loginData = await loginResponse.json();
  accessToken = loginData.access_token;
  refreshToken = loginData.refresh_token;

  await createPlaybook(request);
});

test.afterAll(async ({ request }) => {
  if (playbookId) {
    await request.delete(`${API_BASE}/playbooks/${playbookId}`, {
      headers: authHeaders(),
    });
  }
});

test.beforeEach(async ({ page }) => {
  await attachAuth(page);
});

test('lista playbooks e abre detalhe', async ({ page }) => {
  await page.goto('/playbooks');

  await expect(page.getByText('Regras de revisao de contratos.')).toBeVisible();

  const playbookHeading = page.getByRole('heading', { name: 'Playbook E2E' }).first();
  await expect(playbookHeading).toBeVisible();
  await playbookHeading.click();

  await expect(page).toHaveURL(new RegExp(`/playbooks/${playbookId}$`));
});
