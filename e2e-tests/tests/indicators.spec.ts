import {
  expect,
  test,
  type Page,
} from '@playwright/test';
import crypto from 'node:crypto';

const listIndicatorsPath = '/admin/indicators/indicator/';

async function setIndicatorFactorsFlag(page: Page, enabled: boolean) {
  await page.goto('/admin/');
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('link', { name: 'Plan features', exact: true }).click();
  const checkbox = page.getByLabel('Enable indicator factors');
  if (enabled !== await checkbox.isChecked()) {
    enabled ? await checkbox.check() : await checkbox.uncheck();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
  }
}

async function createIndicator(page: Page, name: string): Promise<string> {
  await page.goto(listIndicatorsPath);
  await page.getByRole('link', { name: 'Add indicator' }).first().click();
  await page.waitForURL((url) => url.pathname.includes('/create'));
  await page.getByRole('textbox', { name: 'Name' }).fill(name);
  const unitField = page.locator('[data-contentpath="unit"]');
  await unitField.getByRole('combobox').last().click();
  await page.locator('.select2-search__field').fill('t');
  await page.locator('.select2-results__option').first().click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.includes('/create/'));
  // Verify no validation errors on the resulting page
  await expect(page.getByText('could not be created due to errors')).not.toBeVisible();

  // After create, Wagtail shows a success notification with an 'Edit' link to the new instance
  await page.getByRole('alert').getByRole('link', { name: 'Edit' }).click();
  await page.waitForURL(/\/edit\//);
  return page.url().split('#')[0];
}

test.describe('Test indicators', () => {
  test.describe.configure({ mode: 'serial', timeout: 15000 });

  test('Open indicator list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('button', { name: 'Indicators', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Indicators' })).toBeVisible();
  });

  const indicatorName = `Test indicator ${crypto.randomUUID().slice(0, 8)}`;

  test('Create a new indicator', async ({ page }) => {
    await createIndicator(page, indicatorName);
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

const factorRedirectIndicatorName = `E2E factor redirect ${crypto.randomUUID().slice(0, 8)}`;
let factorRedirectEditUrl = '';

test.describe('Indicator factor redirect', () => {
  test.describe.configure({ mode: 'serial', timeout: 30000 });

  test('Saving with a new factor redirects to the factors panel', async ({ page }) => {
    await setIndicatorFactorsFlag(page, true);
    factorRedirectEditUrl = await createIndicator(page, factorRedirectIndicatorName);

    await page.getByRole('tab', { name: 'Relationships' }).click();
    await page.getByRole('button', { name: 'Add factor' }).click();
    const factorsSection = page.getByRole('region', { name: 'Factors' });
    await factorsSection.getByLabel('Name').last().fill('Test factor');
    await factorsSection.getByLabel('Result').last().fill('Test result');
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    await expect(page).toHaveURL(factorRedirectEditUrl + '#panel-child-relationships-factors-section');
  });

  test('Saving without new factors does not redirect to the factors panel', async ({ page }) => {
    await page.goto(factorRedirectEditUrl);
    await page.waitForURL(/\/edit\//);

    await page.getByRole('tab', { name: 'Relationships' }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    await expect(page).toHaveURL(listIndicatorsPath);
  });

  test('Flag disabled: saving on Relationships tab does not redirect to the factors panel', async ({ page }) => {
    await setIndicatorFactorsFlag(page, false);

    await page.goto(factorRedirectEditUrl);
    await page.waitForURL(/\/edit\//);

    await page.getByRole('tab', { name: 'Relationships' }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    await expect(page).toHaveURL(listIndicatorsPath);
  });
});
