import { test, expect } from '@playwright/test';

test.describe('ActivityPanel (Harvey-like)', () => {
  test('running (expanded)', async ({ page }) => {
    await page.goto('/e2e/activity-panel?ui_lang=en&state=running&expanded=1');
    const panel = page.getByTestId('activity-panel');
    await expect(panel).toBeVisible();
    await expect(panel).toHaveScreenshot('activity-panel-running.png');
  });

  test('done (collapsed)', async ({ page }) => {
    await page.goto('/e2e/activity-panel?ui_lang=en&state=done&expanded=0');
    const panel = page.getByTestId('activity-panel');
    await expect(panel).toBeVisible();
    await expect(panel).toHaveScreenshot('activity-panel-done-collapsed.png');
  });
});
