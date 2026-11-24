import { defineConfig, devices } from '@playwright/test';

const externalBaseURL = process.env.KEEPSAKE_WEB_BASE_URL;

export default defineConfig({
  testDir: './tests/web',
  timeout: 30_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.01 },
  },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  outputDir: 'test-results',
  // A missing baseline is a failure. Creating it requires an explicit command
  // and human review; this repository does not silently approve new images.
  updateSnapshots: 'none',
  use: {
    baseURL: externalBaseURL || 'http://127.0.0.1:3000',
    locale: 'en-US',
    timezoneId: 'Asia/Ho_Chi_Minh',
    reducedMotion: 'reduce',
    colorScheme: 'light',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 10_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: externalBaseURL ? undefined : {
    command: 'npm run dev',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { NEXT_TELEMETRY_DISABLED: '1' },
  },
});
