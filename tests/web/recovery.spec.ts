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
  await expect(page.getByRole('alert')).toContainText('The local demo worker stopped.');
  await expect(page.getByRole('button', { name: 'Try the build again', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Try the build again', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Shaping your little keepsake', exact: true })).toBeVisible();
  const withoutMorphs = (character: typeof demoCharacters.left) => {
    const { face_morphs: _, ...allowed } = character;
    return allowed;
  };
  expect(retryBody).toEqual({ characters: {
    left: withoutMorphs(demoCharacters.left), right: withoutMorphs(demoCharacters.right),
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
  await expect(page.getByRole('alert')).toContainText('We lost the connection to your build.');
  mode = 'recovering';
  await page.getByRole('button', { name: 'Refresh status', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Polling reconnected and received the final build result.');
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
