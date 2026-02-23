import {
  expect,
  test,
} from '@playwright/test';
import crypto from 'node:crypto';

const listActionsPath = '/admin/actions/action/';

test.describe('Test admin', () => {
  test.describe.configure({ mode: 'serial', timeout: 5000 });
  test('List actions', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('link', { name: 'Actions', exact: true }).click();
    await expect(page.getByLabel('Filter actions')).toBeVisible();
  });

  test('Create action', async ({ page }) => {
    const identifier = crypto.randomInt(10, 2000);
    await page.goto(listActionsPath);
    await page.getByRole('link', { name: 'Add action' }).click();
    await page.getByRole('textbox', { name: 'Identifier' }).fill(`TA${identifier}`);
    await page.getByRole('textbox', { name: 'Name' }).fill(`Test action ${identifier}`);
    const descBox = page.getByRole('region', { name: 'Description' }).getByRole('textbox');
    await descBox.fill(`Test action ${identifier} description`);
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForURL(listActionsPath);
    const messages = page.locator('#main .messages');
    await expect(messages).toBeVisible();
    await expect(messages.locator('li.success')).toBeVisible();
    await expect(messages.locator('li.success').getByText(`Test action ${identifier}`)).toBeVisible();
  });

  test('Filter actions by name', async ({ page }) => {
    await page.goto(listActionsPath);
    await expect(page.getByText('Test action 1', { exact: true })).toBeVisible();
    await expect(page.getByText('Test action 2', { exact: true })).toBeVisible();

    await expect(page.getByRole('textbox', { name: 'Filter actions' })).toBeVisible();
    await page.getByRole('textbox', { name: 'Filter actions' }).fill('Test action 1');
    await expect(page.getByText('Test action 1', { exact: true })).toBeVisible();
    await expect(page.getByText('Test action 2', { exact: true })).toBeHidden();
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
