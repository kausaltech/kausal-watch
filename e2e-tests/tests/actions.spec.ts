import {
  expect,
  test,
} from '@playwright/test';

test.describe('Test admin', () => {
  test('List actions', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'Actions', exact: true }).click();
    await expect(page.getByLabel('Filter actions')).toBeVisible();
  });
})

test.describe('Test admin after customizing Action term', () => {
  test('List actions', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Settings', exact: true }).click();
    await page.getByRole('link', { name: 'Site settings', exact: true }).click();
    await page.locator('#id_action_term').selectOption('strategy');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await page.getByRole('link', { name: 'Actions', exact: true }).click();
    await expect(page.getByLabel('Filter actions')).toBeVisible();
  });
})
