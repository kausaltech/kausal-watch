import {
  expect,
  test,
} from '@playwright/test';

test.describe('Test indicators', () => {
  test('open indicator list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('button', { name: 'Indicators', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Indicators' })).toBeVisible();
  });
})

test.describe('Test common indicators', () => {
  test('open common indicators list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Common indicators' }).click();
    await expect(page.getByRole('heading', { name: 'Common indicators' })).toBeVisible();
  });
})

test.describe('Test indicator dimensions', () => {
  test('open indicator dimensions list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Indicator dimensions' }).click();
    await expect(page.getByRole('heading', { name: 'Dimensions' })).toBeVisible();
  });
})

test.describe('Test units', () => {
  test('open units list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Units' }).click();
    await expect(page.getByRole('heading', { name: 'Units' })).toBeVisible();
  });
})

test.describe('Test quantities', () => {
  test('open quantities list', async ({ page }) => {
    await page.goto('/admin/');
    await page.getByRole('button', { name: 'Indicators'}).click();
    await page.getByRole('link', { name: 'Quantities' }).click();
    await expect(page.getByRole('heading', { name: 'Quantities' })).toBeVisible();
  });
})
