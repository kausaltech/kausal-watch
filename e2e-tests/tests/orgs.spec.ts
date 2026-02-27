import {
  expect,
  test,
  type Page,
} from '@playwright/test';

const listOrganizationsPath = '/admin/snippets/orgs/organization/';

const testData = {
  organization1: 'E2E test data: Test organization 1',
  organization2: 'E2E test data: Test organization 2',
  suborganization1: 'E2E test data: Suborganization 1',
  organization1Person: 'E2E test data: Organization 1 person',
}

test.describe('Test organization admin', () => {
  test.describe.configure({ mode: 'serial', timeout: 25000 });

  const newOrgIdentifier = crypto.randomUUID();
  const newOrgName = `Test root organization ${newOrgIdentifier}`;
  const newOrg2Name = `Test root organization 2 ${newOrgIdentifier}`;
  const newSubOrgName = `Test suborganization ${newOrgIdentifier}`;
  const newSubOrg2Name = `Test suborganization 2 ${newOrgIdentifier}`;

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

  async function addOrganization(page: Page, name: string, parentName?: string) {
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('table').getByText(name)).toBeHidden();

    if (parentName) {
      await page.getByRole('button', { name: `More options for '${parentName}'` }).click();
      await page.getByRole('link', { name: 'Add suborganization' }).click();
      await page.getByRole('textbox', { name: 'Name (EN)*' }).fill(name);
      await page.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(page.getByRole('table').getByText(name)).toBeVisible();

      // Test that the suborganization was added to the correct parent
      // organization by toggling the parent organization's suborganization
      // visibility
      await page.getByRole('cell', { name: parentName }).getByText('▼').click();
      await expect(page.getByRole('table').getByText(name)).toBeHidden();
    } else {
      await page.getByRole('link', { name: 'Add organization' }).click();
      await page.getByRole('textbox', { name: 'Name (EN)*' }).fill(name);
      await page.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(page.getByRole('table').getByText(name)).toBeVisible();
    }
  }

  test('Adding root organizations', async ({ page }) => {
    await addOrganization(page, newOrgName);
    await addOrganization(page, newOrg2Name);
  });

  test('Adding suborganizations', async ({ page }) => {
    await addOrganization(page, newSubOrgName, newOrgName);
    await addOrganization(page, newSubOrg2Name, newOrgName);
    return;
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('table').getByText(newSubOrgName)).toBeHidden();

    await expect(page.getByRole('table').getByText(newSubOrg2Name)).toBeHidden();

    await page.getByRole('button', { name: `More options for '${newOrgName}'` }).click();
    await page.getByRole('link', { name: 'Add suborganization' }).click();
    await page.getByRole('textbox', { name: 'Name (EN)*' }).fill(newSubOrg2Name);
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByRole('table').getByText(newSubOrg2Name)).toBeVisible();

    // Test that the suborganization was added to the correct parent
    // organization by toggling the parent organization's suborganization
    // visibility
    await page.getByRole('cell', { name: newOrgName }).getByText('▼').click();
    await expect(page.getByRole('table').getByText(newSubOrg2Name)).toBeHidden();
  });

  async function deleteOrganization(page: Page, name: string) {
    await page.goto(listOrganizationsPath);
    await expect(page.getByRole('table').getByText(name)).toBeVisible();
    await page.getByRole('button', { name: `More options for '${name}'` }).click();
    await page.getByRole('link', { name: 'Delete', exact: true }).click();
    await page.getByRole('button', { name: 'Yes, delete' }).click();
    await page.waitForURL(listOrganizationsPath);
    const orgTable = page.getByRole('table');
    await expect(orgTable).toBeVisible();
    await expect(orgTable.getByText(name)).toBeHidden();
  }

  test('Deleting an organization', async ({ page }) => {
    await deleteOrganization(page, newSubOrgName);
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
    await page.getByRole('button', { name: `More options for '${newSubOrg2Name}'` }).click();
    await expect(page.getByRole('link', { name: 'Include in active plan' })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Exclude from active plan' })).toBeHidden();
  });

  test('Editing an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('link', { name: `${newOrgName}` }).click();
    await expect(page.getByRole('heading', { name: `${newOrgName}` })).toBeVisible();

    await page.getByRole('textbox', { name: 'Name (EN)*' }).fill(`${newOrgName} edited`);
    await page.getByRole('textbox', { name: 'Name (FI)', exact: true }).fill(`${newOrgName} edited`);
    await page.locator('#id_parent').selectOption(newOrg2Name);

    // TODO: Edit logo

    await page.getByRole('textbox', { name: 'Short name (EN)'}).fill('Short name (EN) edited');
    await page.getByRole('textbox', { name: 'Short name (FI)' }).fill('Short name (FI) edited');
    await page.getByRole('textbox', { name: 'Internal abbreviation' }).fill('Internal abbreviation edited');
    await page.locator('.notranslate').describe('Description input').fill('Description edited');
    await page.getByRole('textbox', { name: 'URL' }).fill('https://edited.com');
    await page.getByRole('textbox', { name: 'Email address' }).fill('edited@example.com');
    await expect(page.getByRole('textbox', { name: 'Primary language' })).not.toBeEditable();
    // Skip editing location, it behaves strangely in Playwright

    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await page.waitForURL(listOrganizationsPath);
    await expect(page.getByRole('link', { name: `${newOrgName} edited` })).toBeVisible();
  });

  test('Adding a plan admin to an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('link', { name: newOrgName }).click();
    await page.getByRole('tab', { name: 'Permissions' }).click();
    await page.getByRole('button', { name: 'Add plan admin' }).click();
    await page.getByRole('button', { name: 'Choose a person' }).click();
    await page.getByRole('textbox', { name: 'Search term' }).fill(testData.organization1Person);
    await page.getByRole('link', { name: testData.organization1Person }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await page.waitForURL(listOrganizationsPath);
    // TODO: A proper check that the plan admin is taken into account
  });

  test('Adding a metadata admin to an organization', async ({ page }) => {
    await page.goto(listOrganizationsPath);
    await page.getByRole('link', { name: newOrgName }).click();
    await page.getByRole('tab', { name: 'Permissions' }).click();
    await page.getByRole('button', { name: 'Add metadata admin' }).click();
    await page.getByRole('button', { name: 'Choose a person' }).click();
    await page.getByRole('textbox', { name: 'Search term' }).fill(testData.organization1Person);
    await page.getByRole('link', { name: testData.organization1Person }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await page.waitForURL(listOrganizationsPath);
    // TODO: A proper check that the metadata admin is taken into account
  });

  test('Delete created organizations', async ({ page }) => {
    await deleteOrganization(page, newSubOrg2Name);
    await deleteOrganization(page, `${newOrgName} edited`);
    await deleteOrganization(page, newOrg2Name);
  });
})
