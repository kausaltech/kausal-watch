import {
  expect,
  test,
} from '@playwright/test';

test.describe('Test people', () => {
  test('List people', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'People', exact: true }).click();

    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'First name' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Last name' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Title' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Organization' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Role', exact: true })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Attended training' })).toBeVisible();
    await expect(page.locator('header').getByRole('link', { name: 'Add person' })).toBeVisible();
    await expect(page.getByText('Test User')).toBeVisible();
 });

 test('Search person', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'People', exact: true }).click();

    await expect(page.getByRole('textbox', { name: 'Search for' })).toBeVisible();
    await page.getByPlaceholder('Search people').fill('Rest Yser');
    await page.keyboard.press('Enter');
    await expect(page.getByText('Test User')).toBeHidden();
    await expect(page.getByText('Sorry, there are no people matching your search parameters.')).toBeVisible();
    await page.getByPlaceholder('Search people').fill('Test User');
    await page.keyboard.press('Enter');
    await expect(page.getByText('Test User')).toBeVisible();
  });

  test('Filter by role', async ({ page }) => {
    test.setTimeout(40000);
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'People', exact: true }).click();

    await expect(page.getByRole('heading', { name: 'Filter' })).toBeVisible();
    const filters = page.locator('.changelist-filter');
    // The test user has no role in the test plan
    for (const role of ['Plan admin', 'Organization admin', 'Contact person', 'Viewer']) {
      await filters.getByRole('link', { name: role, exact: true }).click();
      await expect(page.getByText('Test User')).toBeHidden();
    }
    await filters.getByRole('link', { name: 'No role', exact: true }).click();
    await expect(page.getByText('Test User')).toBeVisible();
    await filters.getByRole('link', { name: 'All', exact: true }).click();
    await expect(page.getByText('Test User')).toBeVisible();
  });
});
