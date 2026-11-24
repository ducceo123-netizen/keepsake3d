import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { expectNoHorizontalOverflow, settleVisuals } from './helpers';

for (const width of [320, 390, 768, 1280, 1440]) {
  for (const route of ['/', '/studio']) {
    test(`${route} fits a ${width}px viewport`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(route);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      if (route === '/studio') await expect(page.getByRole('button', { name: 'Choose photos', exact: true })).toBeVisible();
      await settleVisuals(page);
      await expectNoHorizontalOverflow(page);
      if (route === '/') {
        await expect(page.getByRole('link', { name: 'Create your keepsake', exact: true })).toBeVisible();
      }
    });
  }
}

for (const route of ['/', '/studio']) {
  test(`${route} has no serious or critical WCAG scan findings`, async ({ page }) => {
    await page.goto(route);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await settleVisuals(page);
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    expect(results.violations.filter(item => item.impact === 'serious' || item.impact === 'critical')).toEqual([]);
  });
}
