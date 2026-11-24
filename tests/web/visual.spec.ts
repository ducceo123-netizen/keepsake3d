import { test, expect } from '@playwright/test';
import { settleVisuals } from './helpers';

for (const width of [390, 1280]) {
  for (const [name, route] of [['homepage', '/'], ['studio-empty', '/studio']] as const) {
    test(`@visual ${name} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(route);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      if (route === '/studio') await expect(page.getByRole('button', { name: 'Choose photos', exact: true })).toBeVisible();
      await settleVisuals(page);
      await expect(page).toHaveScreenshot(`${name}-${width}.png`, { fullPage: true });
    });
  }
}
