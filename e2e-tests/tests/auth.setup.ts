import fs from 'node:fs';
import {
  expect,
  test as setup,
  type Page,
} from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { ApolloClient, gql, HttpLink, InMemoryCache } from '@apollo/client';
import playwrightConfig from '../playwright.config';


const authFile = 'playwright-state/user.json';

const testUserEmail = process.env.TEST_USER_EMAIL;
const testUserPassword = process.env.TEST_USER_PASSWORD;

const CREATE_TEST_USER_MUTATION = gql`
  mutation CreateTestUser($input: TestUserInput!) {
    testMode {
      createTestUser(input: $input) {
        ... on User {
          id
        }
        ... on OperationInfo {
          messages {
            message
            code
            field
          }
        }
      }
    }
  }
`;

enum TestUserRole {
  SUPERUSER,
  PLAN_ADMIN,
  ACTION_CONTACT
}

async function createTestUser(page: Page, role: TestUserRole = TestUserRole.SUPERUSER): Promise<{ email: string, password: string }> {
  const baseURL = playwrightConfig.use?.baseURL;
  if (!baseURL) {
    throw new Error('Base URL is not set');
  }
  const link = new HttpLink({
    uri: baseURL + '/v1/graphql/',
  });
  const client = new ApolloClient({
    link,
    cache: new InMemoryCache(),
  });
  const email = `${randomUUID()}@example.com`;
  const password = randomUUID();
  if (role === TestUserRole.ACTION_CONTACT) {
    throw new Error('ACTION_CONTACT role is not supported yet');
  }
  const { data } = await client.mutate({
    mutation: CREATE_TEST_USER_MUTATION,
    variables: {
      input: {
        email,
        password,
        isSuperuser: role === TestUserRole.SUPERUSER,
        defaultAdminPlanId: role === TestUserRole.SUPERUSER ? 'end-to-end-test-plan' : undefined,
        roles: role === TestUserRole.PLAN_ADMIN ? [
          {
            kind: 'PLAN_ADMIN',
            targetId: 'end-to-end-test-plan',
          }
        ] : [],
      },
    },
  });
  const resp = data.testMode.createTestUser;
  if (resp.__typename === 'OperationInfo') {
    throw new Error(resp.messages.map((m) => m.message).join('\n'));
  }
  return {
    email,
    password,
  };
}

const ensureTestUser = async (page: Page): Promise<{ email: string, password: string }> => {
  if (!testUserEmail || !testUserPassword) {
    console.log('Creating test user');
    const { email, password } = await createTestUser(page);
    return {
      email,
      password,
    };
  }
  return {
    email: testUserEmail,
    password: testUserPassword,
  };
};

setup('Authenticate', async ({ page, context }) => {
  if (fs.existsSync(authFile)) {
    return;
  }
  const { email, password } = await ensureTestUser(page);
  await page.goto('/admin/login/');
  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', { name: 'Sign in' }).click();

  const passwordField = page.getByLabel('Password');
  await expect(passwordField).toBeVisible();
  await passwordField.fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await page.waitForURL('/admin/');
  await page.context().storageState({ path: authFile });
});
