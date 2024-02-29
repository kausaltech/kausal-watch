import { test, expect } from '@playwright/test';




test.describe('Test admin', () => {
  const baseUrl = 'http://localhost:8000';

  test.beforeAll(async () => {
  })
  test('list actions', async ({ page }) => {
    await page.goto(`${baseUrl}/admin/`);
    await page.getByRole('link', { name: 'Actions', exact: true }).click();
    await expect(page.getByLabel('Filter actions')).toBeVisible();
  });
})
