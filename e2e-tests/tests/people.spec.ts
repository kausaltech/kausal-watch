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
    await expect(page.getByRole('columnheader', { name: 'Is plan admin' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Participated in training' })).toBeVisible();
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

  test('Filter contact persons', async ({ page }) => {
    test.setTimeout(40000);
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'People', exact: true }).click();

    await expect(page.getByRole('heading', { name: 'Filter' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'For an action' })).toBeVisible();
    await page.getByRole('link', { name: 'For an action' }).click();
    await expect(page.getByText('Test User')).toBeHidden();
    await page.getByRole('link', { name: 'For same actions or indicators as me' }).click();
    await expect(page.getByText('Test User')).toBeHidden();
    await page.getByRole('link', { name: 'For an indicator' }).click();
    await expect(page.getByText('Test User')).toBeHidden();
    await page.getByRole('link', { name: 'Not a contact person' }).click();
    await expect(page.getByText('Test User')).toBeVisible();
    await page.getByRole('link', { name: 'All', exact: true }).click();
    await expect(page.getByText('Test User')).toBeVisible();
  });
});
