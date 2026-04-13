import {
  expect,
  test,
} from '@playwright/test';
import crypto from 'node:crypto';

const listIndicatorsPath = '/admin/indicators/indicator/';

test.describe('Test indicators', () => {
  test.describe.configure({ mode: 'serial' });

  test('Open indicator list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('button', { name: 'Indicators', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Indicators' })).toBeVisible();
  });

  const indicatorName = `Test indicator ${crypto.randomUUID().slice(0, 8)}`;

  test('Create a new indicator', async ({ page }, testInfo) => {
    testInfo.setTimeout(15000);
    await page.goto(listIndicatorsPath);
    await page.getByRole('link', { name: 'Add indicator' }).first().click();
    await page.waitForURL((url) => url.pathname.includes('/create'));

    await page.getByRole('textbox', { name: 'Name' }).fill(indicatorName);
    // Select a unit via the Select2 autocomplete dropdown:
    // Click the combobox to open the dropdown, then type in the search input that appears.
    const unitField = page.locator('[data-contentpath="unit"]');
    await unitField.getByRole('combobox').last().click();
    await page.locator('.select2-search__field').fill('t');
    await page.locator('.select2-results__option').first().click();
    // Save the indicator and wait for navigation away from the create page
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await page.waitForURL((url) => !url.pathname.includes('/create/'));
    // Verify no validation errors on the resulting page
    await expect(page.getByText('could not be created due to errors')).not.toBeVisible();
  });
})

test.describe('Test common indicators', () => {
  test('Open common indicators list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Common indicators' }).click();
    await expect(page.getByRole('heading', { name: 'Common indicators' })).toBeVisible();
  });
})

test.describe('Test indicator dimensions', () => {
  test('Open indicator dimensions list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Indicator dimensions' }).click();
    await expect(page.getByRole('heading', { name: 'Dimensions' })).toBeVisible();
  });
})

test.describe('Test units', () => {
  test('Open units list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Units' }).click();
    await expect(page.getByRole('heading', { name: 'Units' })).toBeVisible();
  });
})

test.describe('Test quantities', () => {
  test('Open quantities list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Quantities' }).click();
    await expect(page.getByRole('heading', { name: 'Quantities' })).toBeVisible();
  });
})
