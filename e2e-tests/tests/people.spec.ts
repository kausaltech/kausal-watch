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

    const search = page.getByRole('textbox', { name: 'Search term' });
    await expect(search).toBeVisible();
    await search.fill('Rest Yser');
    await page.keyboard.press('Enter');
    await expect(page.getByText('Test User')).toBeHidden();
    await expect(page.getByText('No people match your query.')).toBeVisible();
    await search.fill('Test User');
    await page.keyboard.press('Enter');
    await expect(page.getByText('Test User')).toBeVisible();
  });

  test('Filter by role', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'People', exact: true }).click();
    const listingUrl = page.url();

    const filterByRole = async (role: string) => {
      await page.goto(listingUrl);
      await page.getByRole('button', { name: 'Show filters' }).click();
      await page.getByRole('button', { name: 'Role', exact: true }).click();
      await page.getByLabel('Role').selectOption({ label: role });
    };
    // The test user has no role in the test plan
    for (const role of ['Plan admin', 'Organization admin', 'Contact person', 'Viewer']) {
      await filterByRole(role);
      await expect(page.getByText('Test User')).toBeHidden();
    }
    await filterByRole('No role');
    await expect(page.getByText('Test User')).toBeVisible();
    await page.goto(listingUrl);
    await expect(page.getByText('Test User')).toBeVisible();
  });
});
