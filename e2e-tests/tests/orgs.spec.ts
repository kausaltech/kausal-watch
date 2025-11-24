import {
  expect,
  test,
} from '@playwright/test';

test.describe('Test organization admin', () => {
  const organizationsPath = '/admin/snippets/orgs/organization/';

  test('Organizations appear in menu', async ({ page }) => {
    await page.goto('/admin/');
    const link = await page.getByRole('link', { name: 'Organizations' }).getAttribute('href');
    expect(link).toBe(organizationsPath);
  });

  test('List organizations', async ({ page }) => {
    await page.goto(organizationsPath);
    await expect(page.getByRole('table')).toContainText('Kausal Oy');
  });

  test('Organization edit page has title', async ({ page }) => {
    await page.goto(organizationsPath);
    await page.getByRole('link', { name: 'Kausal Oy' }).click();
    await page.waitForURL(RegExp(`${organizationsPath}edit/[0-9]+/`));
    await expect(page.locator('#header-title')).toContainText('Kausal Oy');
  });
})
