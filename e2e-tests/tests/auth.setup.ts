import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';


const baseUrl = 'http://localhost:8000';


setup('authenticate', async ({ page }) => {
  // Perform authentication steps. Replace these actions with your own.
  await page.goto(`${baseUrl}/admin/login/`);
  await page.getByLabel('Email address').fill('test@example.com');
  await page.getByRole('button', { name: 'Sign in' }).click();
  
  const pw = await page.getByLabel('Password');
  await expect(pw).toBeVisible();
  pw.fill('test');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await page.waitForURL(`${baseUrl}/admin/`);
  await page.context().storageState({ path: authFile });
});
