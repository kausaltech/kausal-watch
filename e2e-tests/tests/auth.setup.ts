import {
  expect,
  test as setup,
} from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

setup('Authenticate', async ({ page }) => {
  await page.goto('/admin/login/');
  await page.getByLabel('Email address').fill('test@example.com');
  await page.getByRole('button', { name: 'Sign in' }).click();

  const password_field = await page.getByLabel('Password');
  await expect(password_field).toBeVisible();
  password_field.fill('test');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await page.waitForURL('/admin/');
  await page.context().storageState({ path: authFile });
});
