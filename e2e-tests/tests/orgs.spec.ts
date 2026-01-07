import {
  expect,
  test,
} from '@playwright/test';

const listOrganizationsPath = '/admin/snippets/orgs/organization/';
const editOrganizationPath = RegExp(`${listOrganizationsPath}edit/[0-9]+/`);

test.describe('Test organization admin', () => {
  test('Organizations appear in menu', async ({ page }) => {
    await page.goto('/admin/');
    const link = await page.getByRole('link', { name: 'Organizations' }).getAttribute('href');
    expect(link).toBe(listOrganizationsPath);
  });

  test('List organizations', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table')).toContainText('Kausal Oy');
  });

  test('Organization edit page has title', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('link', { name: 'Kausal Oy' }).click();
    await page.waitForURL(editOrganizationPath);
    await expect(page.locator('#header-title')).toContainText('Kausal Oy');
  });
})
