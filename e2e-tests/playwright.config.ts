import {
  defineConfig,
  devices,
} from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({path: '.env', quiet: true});

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// require('dotenv').config();

const deviceForBrowser: Record<string, string> = {
  chromium: 'Desktop Chrome',
  firefox: 'Desktop Firefox',
  // edge: 'Desktop Edge', // also needs channel: 'msedge'
};

/**
 * Browsers to exercise, as a comma-separated list in E2E_BROWSERS.
 *
 * Firefox roughly doubles the wall clock of the suite for byte-identical assertions
 * against the Wagtail admin (78.6s vs. 58.5s for chromium, measured in CI), so CI runs
 * it only on main and on the deployment branches. See .github/workflows/ci.yaml.
 */
const browsers = (process.env.E2E_BROWSERS ?? Object.keys(deviceForBrowser).join(','))
  .split(',')
  .map((name) => name.trim())
  .filter(Boolean);

if (!browsers.length) {
  // Without this the run would silently reduce to the login setup project and pass.
  throw new Error('E2E_BROWSERS is set but empty; it must name at least one browser');
}

const browserProject = (name: string) => {
  const device = deviceForBrowser[name];
  if (!device) {
    throw new Error(
      `Unknown browser '${name}' in E2E_BROWSERS; expected one of ${Object.keys(deviceForBrowser).join(', ')}`,
    );
  }
  return {
    name,
    use: {
      ...devices[device],
      storageState: 'playwright-state/user.json',
    },
    dependencies: ['login'],
  }
}

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './tests',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 1 : 0,
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : 2,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: 'html',
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.TEST_BASE_URL || 'http://localhost:8000',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: process.env.CI ? 'on-first-retry' : 'on',
  },

  /* Configure projects for major browsers */
  projects: [
    {
        name: 'login',
        testMatch: /auth\.setup\.ts/,
        //teardown: 'cleanup db',
    },
    ...browsers.map(browserProject),
  ],

  /* Run your local dev server before starting the tests */
  // webServer: {
  //   command: 'npm run start',
  //   url: 'http://127.0.0.1:3000',
  //   reuseExistingServer: !process.env.CI,
  // },
});
