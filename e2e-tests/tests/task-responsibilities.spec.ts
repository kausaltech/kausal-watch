import {
  expect,
  test,
  type Page,
} from '@playwright/test';
import crypto from 'node:crypto';

/**
 * Assigning a responsible organization to a task of an action.
 *
 * The assignment panels are inline panels nested inside the tasks panel. Everything below that — the
 * models, the formsets, the per-plan gating — is covered by `src/actions/tests/test_task_responsibilities.py`,
 * but only a browser exercises the nested formset's JavaScript: the "Add" button of a nested panel
 * clones an empty-form template, and a task row is itself such a clone.
 */

const listActionsPath = '/admin/actions/action/';

// From the E2E fixtures, and related to the test plan, so the form accepts it. An organization the plan
// cannot reach is rejected server-side; that path is covered by the Python tests.
const testOrganization = 'E2E test data: Test organization 1';

const suffix = crypto.randomInt(10, 100000);
const actionName = `Task responsibilities ${suffix}`;
const taskName = `Insulate the depot ${suffix}`;

const openTasksTab = async (page: Page) => {
  await page.goto(listActionsPath);
  await page.getByRole('link', { name: actionName }).click();
  await page.getByRole('tab', { name: 'Tasks' }).click();
};

const expectSaved = async (page: Page) => {
  await page.waitForURL(listActionsPath);
  const messages = page.locator('#main .messages');
  await expect(messages.locator('li.success')).toBeVisible();
};

test.describe('Assigning responsibilities to tasks', () => {
  test.describe.configure({ mode: 'serial', timeout: 30000 });

  test('Create an action to hold the task', async ({ page }) => {
    await page.goto(listActionsPath);
    await page.getByRole('link', { name: 'Add action' }).click();
    await page.getByRole('textbox', { name: 'Identifier' }).fill(`TR${suffix}`);
    await page.getByRole('textbox', { name: 'Name' }).fill(actionName);
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expectSaved(page);
  });

  test('Assign a responsible organization to a new task', async ({ page }) => {
    await openTasksTab(page);

    // The ids come from Wagtail's inline panel template: the add button is `id_<prefix>-ADD`, and the
    // cloned child form gets `<prefix>-0`.
    await page.locator('#id_tasks-ADD').click();
    await page.locator('#id_tasks-0-name').fill(taskName);
    await page.locator('#id_tasks-0-due_at').fill('2027-01-01');

    // The nested panel lives inside the task that was just added.
    await page.locator('#id_tasks-0-responsible_parties-ADD').click();
    const organizationField = page.locator(
      '#id_tasks-0-responsible_parties-FORMS [data-contentpath="organization"]',
    );
    await organizationField.getByRole('combobox').last().click();
    // This page carries several select2 widgets and select2 appends its dropdown to the body, so the
    // search box and the results are taken from whichever container is open rather than page-wide.
    const openDropdown = page.locator('.select2-container--open');
    await openDropdown.locator('.select2-search__field').fill(testOrganization);
    await openDropdown.locator('.select2-results__option', { hasText: testOrganization }).first().click();

    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expectSaved(page);
  });

  test('The assignment is still there after reopening the action', async ({ page }) => {
    await openTasksTab(page);

    await expect(page.locator('#id_tasks-0-name')).toHaveValue(taskName);
    await expect(
      page.locator('#id_tasks-0-responsible_parties-FORMS'),
    ).toContainText(testOrganization);
  });
});
