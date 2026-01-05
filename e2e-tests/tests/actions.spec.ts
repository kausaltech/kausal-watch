import {
  expect,
  test,
} from '@playwright/test';

const listActionsPath = '/admin/actions/action/';

test.describe('Test admin', () => {
  test('List actions', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'Actions', exact: true }).click();
    await expect(page.getByLabel('Filter actions')).toBeVisible();
  });

  test('Filter actions by name', async ({ page }) => {
    await page.goto(listActionsPath);
    await expect(page.getByText('Test action 1')).toBeVisible();
    await expect(page.getByText('Test action 2')).toBeVisible();

    await expect(page.getByRole('textbox', { name: 'Filter actions' })).toBeVisible();
    await page.getByRole('textbox', { name: 'Filter actions' }).fill('Test action 1');
    await expect(page.getByText('Test action 1')).toBeVisible();
    await expect(page.getByText('Test action 2')).toBeHidden();
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
