import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

const API_BASE = 'http://127.0.0.1:8000/api';

let accessToken = '';
let refreshToken = '';

const attachAuth = async (page: Page) => {
  await page.addInitScript(
    ({ accessToken, refreshToken }) => {
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('refresh_token', refreshToken);
    },
    { accessToken, refreshToken },
  );
};

const loginTestUser = async (request: APIRequestContext) => {
  const response = await request.post(`${API_BASE}/auth/login-test`);
  if (!response.ok()) {
    throw new Error(`Falha no login-test: ${response.status()}`);
  }
  const payload = await response.json();
  accessToken = payload.access_token;
  refreshToken = payload.refresh_token;
};

const openAskAndGetToolbar = async (page: Page) => {
  await page.goto('/ask');
  const toolbar = page.locator('header').first();
  await expect(toolbar).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole('button', { name: 'Share' })).toBeVisible({ timeout: 20000 });
  return toolbar;
};

test.describe('Ask Toolbar Layout', () => {
  test.beforeAll(async ({ request }) => {
    await loginTestUser(request);
  });

  test.beforeEach(async ({ page }) => {
    await attachAuth(page);
  });

  test('desktop snapshot', async ({ page }) => {
    const toolbar = await openAskAndGetToolbar(page);
    await expect(toolbar).toHaveScreenshot('ask-toolbar-desktop.png');
  });

  test('mobile snapshot', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const toolbar = await openAskAndGetToolbar(page);
    await expect(toolbar).toHaveScreenshot('ask-toolbar-mobile.png');
  });
});
