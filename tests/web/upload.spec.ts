import { test, expect } from '@playwright/test';
import { focusByKeyboard } from './helpers';

test('keyboard upload reports an unsupported file and keeps generation disabled', async ({ page }) => {
  let sessionRequests = 0;
  await page.route('**/api/v1/**', async route => {
    sessionRequests++;
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Unexpected API request"}' });
  });
  await page.goto('/studio');
  await expect(page.getByRole('button', { name: 'Choose photos', exact: true })).toBeVisible();
  const choosePhotos = await focusByKeyboard(page, 'Choose photos');
  await expect(choosePhotos).toBeFocused();
  const chooser = page.waitForEvent('filechooser');
  await page.keyboard.press('Enter');
  await (await chooser).setFiles({ name: 'unsupported.txt', mimeType: 'text/plain', buffer: Buffer.from('This is not a photo.') });
  await expect(page.getByRole('alert').filter({ hasText: 'Please choose a JPEG, PNG, or WebP photo.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Create my 3D preview', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Upload reference photos')).toHaveValue('');
  expect(sessionRequests).toBe(0);
});

test('a file larger than 10 MB has a useful error before network upload', async ({ page }) => {
  await page.goto('/studio');
  await page.getByLabel('Upload reference photos').setInputFiles({
    name: 'oversized.png', mimeType: 'image/png', buffer: Buffer.alloc(10 * 1024 * 1024 + 1),
  });
  await expect(page.getByRole('alert').filter({ hasText: 'Each photo needs to be 10 MB or smaller.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Create my 3D preview', exact: true })).toBeDisabled();
});

test('name inputs accept the documented hyphen and reject unsupported characters', async ({ page }) => {
  await page.goto('/studio');
  const name = page.getByLabel('Left character name', { exact: true });
  await name.fill('Alex-Jamie');
  expect(await name.evaluate((element: HTMLInputElement) => element.validity.patternMismatch)).toBe(false);
  await name.fill('Alex123');
  expect(await name.evaluate((element: HTMLInputElement) => element.validity.patternMismatch)).toBe(true);
});
