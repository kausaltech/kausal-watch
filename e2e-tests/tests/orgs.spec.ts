import {
  expect,
  test,
} from '@playwright/test';

const listOrganizationsPath = '/admin/snippets/orgs/organization/';

const testData = {
  organization1: 'E2E test data: Test organization 1',
  organization2: 'E2E test data: Test organization 2',
  suborganization1: 'E2E test data: Suborganization 1',
  deleteOrganization: 'E2E test data: Delete this organization',
  organization1Person: 'E2E test data: Organization 1 person',
  editOrganization: 'E2E test data: Edit this organization'
}

test.describe('Test organization admin', () => {
  test('Organizations appear in menu', async ({ page }) => {
    await page.goto('/admin/');
    const link = await page.getByRole('link', { name: 'Organizations' }).getAttribute('href');
    expect(link).toBe(listOrganizationsPath);
  });

  test('List organizations', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table')).toContainText('Kausal Oy');
  });

  test('Filter organizations by name', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await expect(page.getByText(testData.organization1)).toBeVisible();
    await expect(page.getByText(testData.organization2)).toBeVisible();

    await page.getByRole('textbox', { name: 'Filter organizations' }).fill(testData.organization1);
    await expect(page.getByText(testData.organization1)).toBeVisible();
    await expect(page.getByText(testData.organization2)).toBeHidden();
  });

  test('Toggling suborganization visibility', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await expect(page.getByText(testData.organization1)).toBeVisible();
    await expect(page.getByText(testData.suborganization1)).toBeVisible();

    await page.getByRole('cell', { name: testData.organization1 }).getByText('▼').click();
    await expect(page.getByText(testData.organization1)).toBeVisible();
    await expect(page.getByText(testData.suborganization1)).toBeHidden();
  });

  test('Adding an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('table').getByText('Added organization')).toBeHidden();

    await page.getByRole('link', { name: 'Add organization' }).click();
    await page.getByRole('textbox', { name: 'Name (EN)*' }).fill('Added organization');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('table').getByText('Added organization')).toBeVisible();
  });

  test('Adding a suborganization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('table').getByText('Added suborganization')).toBeHidden();

    await page.getByRole('button', { name: `More options for '${testData.organization1}'` }).click();
    await page.getByRole('link', { name: 'Add suborganization' }).click();
    await page.getByRole('textbox', { name: 'Name (EN)*' }).fill('Added suborganization');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('table').getByText('Added suborganization')).toBeVisible();

    // Test that the suborganization was added to the correct parent
    // organization by toggling the parent organization's suborganization
    // visibility
    await page.getByRole('cell', { name: testData.organization1 }).getByText('▼').click();
    await expect(page.getByRole('table').getByText('Added suborganization')).toBeHidden();
  });

  test('Deleting an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table').getByText(testData.deleteOrganization)).toBeVisible();

    await page.getByRole('button', { name: `More options for '${testData.deleteOrganization}'` }).click();
    await page.getByRole('link', { name: 'Delete', exact: true }).click();
    await page.getByRole('button', { name: 'Yes, delete' }).click();
    await page.waitForURL(listOrganizationsPath);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('table').getByText(testData.deleteOrganization)).toBeHidden();
  });

  test('Including/excluding an organization from active plan', async ({ page }) => {
    // Wether an organization is included in the active plan or not can be
    // checked by checking if the person is visible in the people list

    const personPath = '/admin/people/person/';

    await page.goto(personPath);
    await expect(page.getByText(testData.organization1Person)).toBeVisible();

    await page.goto(listOrganizationsPath);
    await page.getByRole('button', { name: `More options for '${testData.organization1}'` }).click();
    await page.getByRole('link', { name: 'Exclude from active plan' }).click();
    await page.getByRole('button', { name: 'Yes' }).click();
    await page.goto(personPath);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByText(testData.organization1Person)).toBeHidden();

    await page.goto(listOrganizationsPath);
    await page.getByRole('button', { name: `More options for '${testData.organization1}'` }).click();
    await page.getByRole('link', { name: 'Include in active plan' }).click();
    await page.getByRole('button', { name: 'Yes' }).click();
    await page.goto(personPath);
    await expect(page.getByText(testData.organization1Person)).toBeVisible();
  });

  test('Including/excluding from active plan is not available for suborganizations', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('button', { name: `More options for '${testData.suborganization1}'` }).click();
    await expect(page.getByRole('link', { name: 'Include in active plan' })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Exclude from active plan' })).toBeHidden();
  });

  test('Editing an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('link', { name: testData.editOrganization }).click();
    await expect(page.getByRole('heading', { name: testData.editOrganization })).toBeVisible();

    await page.getByRole('textbox', { name: 'Name (EN)*' }).fill('Name (EN) edited');
    await page.getByRole('textbox', { name: 'Name (FI)', exact: true }).fill('Name (FI) edited');
    await page.locator('#id_parent').selectOption(testData.organization1);
    // TODO: Edit logo
    await page.getByRole('textbox', { name: 'Short name (EN)'}).fill('Short name (EN) edited');
    await page.getByRole('textbox', { name: 'Short name (FI)' }).fill('Short name (FI) edited');
    await page.getByRole('textbox', { name: 'Internal abbreviation' }).fill('Internal abbreviation edited');
    await page.locator('.notranslate').describe('Description input').fill('Description edited');
    await page.getByRole('textbox', { name: 'URL' }).fill('https://edited.com');
    await page.getByRole('textbox', { name: 'Email address' }).fill('edited@example.com');
    await expect(page.getByRole('textbox', { name: 'Primary language' })).not.toBeEditable();
    // Skip editing location, it behaves strangely in Playwright

    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForURL(listOrganizationsPath);
    await expect(page.getByRole('link', { name: 'Name (EN) edited' })).toBeVisible();
  });

  test('Adding a plan admin to an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('link', { name: testData.organization1 }).click();
    await page.getByRole('tab', { name: 'Permissions' }).click();
    await page.getByRole('button', { name: 'Add plan admin' }).click();
    await page.getByRole('button', { name: 'Choose a person' }).click();
    await page.getByRole('textbox', { name: 'Search term' }).fill(testData.organization1Person);
    await page.getByRole('link', { name: testData.organization1Person }).click();
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForURL(listOrganizationsPath);
    // TODO: A proper check that the plan admin is taken into account
  });

  test('Adding a metadata admin to an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('link', { name: testData.organization1 }).click();
    await page.getByRole('tab', { name: 'Permissions' }).click();
    await page.getByRole('button', { name: 'Add metadata admin' }).click();
    await page.getByRole('button', { name: 'Choose a person' }).click();
    await page.getByRole('textbox', { name: 'Search term' }).fill(testData.organization1Person);
    await page.getByRole('link', { name: testData.organization1Person }).click();
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForURL(listOrganizationsPath);
    // TODO: A proper check that the metadata admin is taken into account
  });
})
