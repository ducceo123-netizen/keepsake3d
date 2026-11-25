import { test, expect, type Route } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { demoSession, json } from './helpers';

test('real browser models require explicit face assignment and reviewed appearance', async ({ page }) => {
  test.setTimeout(180_000);
  // Only HTTP session persistence is stubbed. Images and CPU WASM inference are real.
  const fixtures = await Promise.all(['astronaut.png', 'grace_hopper.jpg'].map(async (name, index) => {
    const bytes = await readFile(path.resolve('tests/vision/fixtures', name));
    return { name, bytes, id: String(index + 1).repeat(32), sha256: createHash('sha256').update(bytes).digest('hex') };
  }));
  let uploaded = 0, submitted = false;
  let profile: any;
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), pathname = new URL(req.url()).pathname;
    if (pathname.endsWith('/customization-sessions') && req.method() === 'POST') return json(route, demoSession);
    if (pathname.endsWith('/photos') && req.method() === 'POST') { uploaded++; return json(route, {}, 201); }
    const fixture = fixtures.find(item => pathname.endsWith(`/photos/${item.id}`));
    if (fixture) return route.fulfill({ status: 200, contentType: fixture.name.endsWith('png') ? 'image/png' : 'image/jpeg', body: fixture.bytes });
    if (pathname.endsWith('/status')) return json(route, {
      id: demoSession.id, state: submitted ? 'MODEL_BUILDING' : 'CREATED', revision: submitted ? 1 : 0,
      job_id: null, error: null, params: null, artifacts: [], qa: null, checksum: null, history: [],
      photos: fixtures.slice(0, uploaded).map(item => ({ id: item.id, width: 512, height: 512, sha256: item.sha256, url: `/api/v1/sessions/${demoSession.id}/photos/${item.id}` })),
    });
    if (pathname.endsWith('/appearance-profile')) { profile = req.postDataJSON(); return json(route, { id: 'a'.repeat(32), sha256: 'b'.repeat(64) }, 201); }
    if (pathname.endsWith('/submit')) { submitted = true; return json(route, {}, 202); }
    return json(route, { detail: 'Unexpected HTTP request in appearance UI fixture' }, 500);
  });
  await page.goto('/studio');
  await expect(page.getByRole('button', { name: 'Try a sample photo', exact: true })).toHaveCount(0);
  await page.getByLabel('Upload reference photos').setInputFiles(fixtures.map(item => ({ name: item.name, mimeType: item.name.endsWith('png') ? 'image/png' : 'image/jpeg', buffer: item.bytes })));
  await expect(page.getByRole('button', { name: 'Remove photo 2', exact: true })).toBeVisible();
  const analyze = page.getByRole('button', { name: 'Analyze photos', exact: true });
  const generate = page.getByRole('button', { name: 'Create my 3D preview', exact: true });
  await expect(analyze).toBeDisabled();
  await page.getByRole('checkbox', { name: /permission to use these photos/ }).check();
  await analyze.click();
  const left = page.getByRole('combobox', { name: 'Left character — reference face', exact: true });
  const right = page.getByRole('combobox', { name: 'Right character — reference face', exact: true });
  await expect(left).toBeVisible({ timeout: 120_000 });
  await expect(left).toHaveValue('');
  await expect(right).toHaveValue('');
  await expect(generate).toBeDisabled();
  await left.selectOption({ label: 'Photo 1 · Face 1' });
  await expect(right.locator(`option[value="${fixtures[0].id}:0"]`)).toBeDisabled();
  await right.selectOption({ label: 'Photo 2 · Face 1' });
  await expect(generate).toBeDisabled();
  const review = page.getByRole('checkbox', { name: /checked the left and right people/ });
  await review.check();
  await expect(generate).toBeEnabled();
  await page.getByRole('group', { name: 'Left character', exact: true }).getByRole('combobox', { name: 'Hair style', exact: true }).selectOption('long');
  await expect(review).not.toBeChecked();
  await expect(generate).toBeDisabled();
  await review.check();
  await generate.click();
  await expect.poll(() => submitted).toBe(true);
  expect(profile.source).toBe('browser-mediapipe-v1');
  expect(profile.parameters.schema_version).toBe('2.0');
  expect(profile.assignments.left.photo_sha256).toBe(fixtures[0].sha256);
  expect(profile.assignments.right.photo_sha256).toBe(fixtures[1].sha256);
  expect(profile.parameters.characters.left.face_morphs).not.toEqual(profile.parameters.characters.right.face_morphs);
  expect(profile.manual_overrides.characters.left.hair_style_asset_id).toBe('long');
  expect(JSON.stringify(profile)).not.toContain('faceLandmarks');
});

for (const cancellation of ['cancel button', 'consent revocation']) {
  test(`${cancellation} aborts a delayed private-photo fetch before the worker starts and permits retry`, async ({ page }) => {
    test.setTimeout(180_000);
    const bytes = await readFile(path.resolve('tests/vision/fixtures/astronaut.png'));
    const photo = { id: '1'.repeat(32), width: 512, height: 512, sha256: createHash('sha256').update(bytes).digest('hex'), url: `/api/v1/sessions/${demoSession.id}/photos/${'1'.repeat(32)}` };
    let uploaded = false, delayPhoto = false;
    const delayed: Route[] = [];
    await page.addInitScript(() => {
      (window as any).__appearanceWorkerStarts = 0;
      const NativeWorker = window.Worker;
      window.Worker = class extends NativeWorker {
        constructor(url: string | URL, options?: WorkerOptions) {
          if (String(url).includes('/workers/appearance.js')) (window as any).__appearanceWorkerStarts++;
          super(url, options);
        }
      };
    });
    await page.route('**/api/v1/**', async route => {
      const req = route.request(), pathname = new URL(req.url()).pathname;
      if (pathname.endsWith('/customization-sessions') && req.method() === 'POST') return json(route, demoSession);
      if (pathname.endsWith('/photos') && req.method() === 'POST') { uploaded = true; return json(route, {}, 201); }
      if (pathname === photo.url) {
        if (delayPhoto) { delayed.push(route); return; }
        return route.fulfill({ status: 200, contentType: 'image/png', body: bytes });
      }
      if (pathname.endsWith('/status')) return json(route, {
        id: demoSession.id, state: uploaded ? 'PHOTO_UPLOADED' : 'CREATED', revision: 0,
        job_id: null, error: null, params: null, artifacts: [], qa: null, checksum: null, history: [], photos: uploaded ? [photo] : [],
      });
      return json(route, { detail: 'Unexpected HTTP request in cancellation fixture' }, 500);
    });
    await page.goto('/studio');
    await page.getByLabel('Upload reference photos').setInputFiles({ name: 'astronaut.png', mimeType: 'image/png', buffer: bytes });
    await expect(page.getByAltText('Your private reference photo 1', { exact: true })).toBeVisible();
    const consent = page.getByRole('checkbox', { name: /permission to use these photos/ });
    const analyze = page.getByRole('button', { name: 'Analyze photos', exact: true });
    await consent.check();
    delayPhoto = true;
    await analyze.click();
    await expect.poll(() => delayed.length).toBe(1);
    const cancel = page.getByRole('button', { name: 'Cancel analysis', exact: true });
    await expect(cancel).toBeVisible();
    if (cancellation === 'cancel button') await cancel.click();
    else await consent.uncheck();
    await expect(cancel).toHaveCount(0, { timeout: 2000 });
    if (cancellation === 'cancel button') await expect(analyze).toBeEnabled();
    else await expect(analyze).toBeDisabled();
    expect(await page.evaluate(() => (window as any).__appearanceWorkerStarts)).toBe(0);
    delayPhoto = false;
    await Promise.all(delayed.map(route => route.fulfill({ status: 200, contentType: 'image/png', body: bytes }).catch(() => undefined)));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.getByAltText('Photo 1, face 1', { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => (window as any).__appearanceWorkerStarts)).toBe(0);
    await consent.check();
    await analyze.click();
    await expect(page.getByAltText('Photo 1, face 1', { exact: true })).toBeVisible({ timeout: 120_000 });
    expect(await page.evaluate(() => (window as any).__appearanceWorkerStarts)).toBe(1);
  });
}
