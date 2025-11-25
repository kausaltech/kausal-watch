import {
  expect,
  test,
} from '@playwright/test';

const listDataSourcesPath = '/admin/datasets/datasource/';
const addDataSourcePath = `${listDataSourcesPath}add/`;
const editDataSourcePath = RegExp(`${listDataSourcesPath}edit/[0-9]+/`);
const deleteDataSourcePath = RegExp(`${listDataSourcesPath}delete/[0-9]+/`);

test.describe('Test data sources', () => {
  test('List data sources', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Settings' }).click();
    await page.getByRole('link', { name: 'Data sources' }).click();
    await expect(page.getByRole('heading', { name: 'Data sources' })).toBeVisible();
  });

  test('Add a new data source', async ({ page }) => {
    await page.goto(listDataSourcesPath);
    await expect(page.getByRole('link', { name: 'Test name, Test authority Test edition' })).toBeHidden();

    await page.getByRole('link', { name: 'Add data source' }).click();
    await page.waitForURL(addDataSourcePath);
    await page.getByRole('textbox', { name: 'Name' }).fill('Test name');
    await page.getByRole('textbox', { name: 'Edition' }).fill('Test edition');
    await page.getByRole('textbox', { name: 'Authority' }).fill('Test authority');
    await page.getByRole('textbox', { name: 'Description' }).fill('Test description');
    await page.getByRole('textbox', { name: 'URL' }).fill('https://test-url.com');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForURL(listDataSourcesPath);
    await expect(page.getByRole('link', { name: 'Test name, Test authority Test edition' })).toBeVisible();
  });

  test('Adding a data source without a name leads to an error', async ({ page }) => {
    await page.goto(addDataSourcePath);
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('The Data source could not be created due to errors.')).toBeVisible();
    await expect(page.locator('#panel-child-name-errors').getByText('This field is required.')).toBeVisible();
  });

  test('Edit a data source', async ({ page }) => {
    await page.goto(listDataSourcesPath);
    await page.getByRole('link', { name: 'Test name, Test authority Test edition' }).click();
    await page.waitForURL(editDataSourcePath);
    await page.getByRole('textbox', { name: 'Name' }).fill('Edited Test name');
    await page.getByRole('textbox', { name: 'Edition' }).fill('Edited Test edition');
    await page.getByRole('textbox', { name: 'Authority' }).fill('Edited Test authority');
    await page.getByRole('textbox', { name: 'Description' }).fill('Edited Test description');
    await page.getByRole('textbox', { name: 'URL' }).fill('https://edited-test-url.com');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForURL(listDataSourcesPath);
    await expect(page.getByRole('link', { name: 'Edited Test name, Edited Test authority Edited Test edition' })).toBeVisible();
  });

  test('Delete a data source', async ({ page }) => {
    await page.goto(listDataSourcesPath);
    await page.getByRole('button', { name: 'More options for \'Edited Test name, Edited Test authority Edited Test edition\'' }).click();
    await page.getByRole('link', { name: 'Delete \'Edited Test name, Edited Test authority Edited Test edition\'' }).click();
    await page.waitForURL(deleteDataSourcePath);
    await page.getByRole('button', { name: 'Yes, delete' }).click();
    await page.waitForURL(listDataSourcesPath);
    await expect(page.getByRole('link', { name: 'Edited Test name, Edited Test authority Edited Test edition' })).toBeHidden();
  });
})
