import { test, expect, type Route } from '@playwright/test';
import { demoCharacters, demoSession, demoStatus, json, seedSession, storageKey } from './helpers';

test('a reloaded FAILED session renders its error and retries the saved parameters', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  let current = demoStatus();
  let retryBody: unknown;
  let retryKey = '';
  let submitRequests = 0;
  await seedSession(page);
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname.endsWith('/status')) return json(route, current);
    if (pathname.endsWith('/corrections')) {
      expect(request.headers().authorization).toBe(`Bearer ${demoSession.token}`);
      retryBody = request.postDataJSON();
      retryKey = request.headers()['idempotency-key'] || '';
      current = demoStatus('MODEL_BUILDING');
      return json(route, current, 202);
    }
    if (pathname.endsWith('/submit')) submitRequests++;
    return json(route, { detail: 'Unexpected request in failed-session fixture' }, 500);
  });
  await page.goto('/studio');
  await page.reload();
  await expect(page.getByRole('alert').filter({ hasText: 'The local demo worker stopped.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Try the build again', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Try the build again', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Shaping your little keepsake', exact: true })).toBeVisible();
  expect(retryBody).toEqual({ characters: {
    left: demoCharacters.left, right: demoCharacters.right,
  } });
  expect(retryKey.length).toBeGreaterThanOrEqual(8);
  expect(submitRequests).toBe(0);
  expect(pageErrors).toEqual([]);
});

test('Refresh status resumes polling even when the build state is unchanged', async ({ page }) => {
  await seedSession(page);
  // Use explicit network phases so React development-mode effect replays do
  // not consume a brittle fixed sequence of initial status responses.
  let mode: 'initial' | 'offline' | 'recovering' = 'initial';
  let recoveryReads = 0;
  await page.route('**/api/v1/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (!pathname.endsWith('/status')) return json(route, { detail: 'Unexpected fixture request' }, 500);
    if (mode === 'offline') return json(route, { detail: 'Temporary connection failure' }, 503);
    if (mode === 'recovering') {
      recoveryReads++;
      if (recoveryReads >= 2) {
        const recovered = demoStatus();
        recovered.error = { code: 'BUILD_FAILED', message: 'Polling reconnected and received the final build result.' };
        return json(route, recovered);
      }
    }
    return json(route, demoStatus('MODEL_BUILDING'));
  });
  await page.goto('/studio');
  await expect(page.getByRole('heading', { name: 'Shaping your little keepsake', exact: true })).toBeVisible();
  mode = 'offline';
  await expect(page.getByRole('alert').filter({ hasText: 'We lost the connection to your build.' })).toBeVisible();
  mode = 'recovering';
  await page.getByRole('button', { name: 'Refresh status', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Polling reconnected and received the final build result.' })).toBeVisible();
  expect(recoveryReads).toBeGreaterThanOrEqual(2);
});

test('an in-flight response cannot restore a deleted session', async ({ page }) => {
  await seedSession(page);
  let statusReads = 0;
  let delayedStatus: Route | undefined;
  await page.route('**/api/v1/**', async route => {
    if (route.request().method() === 'DELETE') return route.fulfill({ status: 204 });
    if (new URL(route.request().url()).pathname.endsWith('/status')) {
      statusReads++;
      if (statusReads === 1) return json(route, demoStatus('MODEL_BUILDING'));
      delayedStatus = route;
      return;
    }
    return json(route, { detail: 'Unexpected fixture request' }, 500);
  });
  await page.goto('/studio');
  await expect.poll(() => Boolean(delayedStatus)).toBe(true);
  await page.getByRole('button', { name: 'Delete session & photos', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete session & files', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your favorite photos', exact: true })).toBeVisible();
  const staleResponse = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/status'));
  await json(delayedStatus!, demoStatus('MODEL_BUILDING'));
  await (await staleResponse).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByRole('heading', { name: 'Your favorite photos', exact: true })).toBeVisible();
  expect(await page.evaluate(key => sessionStorage.getItem(key), storageKey)).toBeNull();
});

test('lost correction responses reuse the request key until the edited parameters change', async ({ page }) => {
  await seedSession(page);
  const attempts: Array<{ key: string; body: unknown }> = [];
  await page.route('**/api/v1/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith('/status')) return json(route, demoStatus('PREVIEW_READY'));
    if (pathname.endsWith('/corrections')) {
      attempts.push({ key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON() });
      return route.abort('connectionfailed');
    }
    return json(route, { detail: 'Unexpected request in correction-retry fixture' }, 500);
  });
  await page.goto('/studio');
  await page.getByRole('button', { name: 'Adjust the details', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const name = dialog.getByLabel('Name', { exact: true }).first();
  const save = dialog.getByRole('button', { name: 'Save & create a new preview', exact: true });
  await name.fill('First');
  await save.click();
  await expect.poll(() => attempts.length).toBe(1);
  await expect(save).toBeEnabled();
  await save.click();
  await expect.poll(() => attempts.length).toBe(2);
  expect(attempts[0].key.length).toBeGreaterThanOrEqual(8);
  expect(attempts[1]).toEqual(attempts[0]);
  await expect(save).toBeEnabled();
  await name.fill('Second');
  await save.click();
  await expect.poll(() => attempts.length).toBe(3);
  expect(attempts[2].key).not.toBe(attempts[0].key);
  expect(attempts[2].body).toEqual({ characters: { left: { engraving_text: 'Second' }, right: {} } });
});

test('saving an unchanged correction closes the dialog without requesting a build', async ({ page }) => {
  await seedSession(page);
  let correctionRequests = 0;
  await page.route('**/api/v1/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith('/status')) return json(route, demoStatus('PREVIEW_READY'));
    if (pathname.endsWith('/corrections')) correctionRequests++;
    return json(route, { detail: 'No new build should be requested' }, 500);
  });
  await page.goto('/studio');
  await page.getByRole('button', { name: 'Adjust the details', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Save & create a new preview', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(correctionRequests).toBe(0);
});
