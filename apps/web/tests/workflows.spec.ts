import { test, expect, Page, APIRequestContext } from '@playwright/test';

const API_BASE = 'http://127.0.0.1:8000/api';

let accessToken = '';
let refreshToken = '';
let workflowId = '';

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

const createWorkflow = async (request: APIRequestContext) => {
  const response = await request.post(`${API_BASE}/workflows`, {
    headers: authHeaders(),
    data: {
      name: 'Workflow E2E',
      description: 'Workflow criado para testes E2E',
      graph_json: { nodes: [], edges: [] },
      tags: ['e2e'],
    },
  });
  if (!response.ok()) {
    throw new Error(`Falha ao criar workflow: ${response.status()}`);
  }
  const data = await response.json();
  workflowId = data.id;
};

test.beforeAll(async ({ request }) => {
  const loginResponse = await request.post(`${API_BASE}/auth/login-test`);
  if (!loginResponse.ok()) {
    throw new Error(`Falha no login-test: ${loginResponse.status()}`);
  }
  const loginData = await loginResponse.json();
  accessToken = loginData.access_token;
  refreshToken = loginData.refresh_token;

  await createWorkflow(request);
});

test.afterAll(async ({ request }) => {
  if (workflowId) {
    await request.delete(`${API_BASE}/workflows/${workflowId}`, {
      headers: authHeaders(),
    });
  }
});

test.beforeEach(async ({ page }) => {
  await attachAuth(page);
});

test('lista workflows e abre detalhe', async ({ page }) => {
  await page.goto('/workflows');

  await expect(page.getByText('Crie e gerencie fluxos visuais com LangGraph')).toBeVisible();

  const workflowHeading = page.getByRole('heading', { name: 'Workflow E2E' }).first();
  await expect(workflowHeading).toBeVisible();
  await workflowHeading.click();

  await expect(page).toHaveURL(new RegExp(`/workflows/${workflowId}$`));
});
