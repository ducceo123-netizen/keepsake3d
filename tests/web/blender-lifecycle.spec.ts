import { test, expect, request as requestFactory, type APIRequestContext } from '@playwright/test';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { storageKey } from './helpers';
import { expectNoHorizontalOverflow } from './helpers';

const buildTimeoutMs = Number(process.env.KEEPSAKE_WEB_BUILD_TIMEOUT_MS || 180_000);

async function waitForPreview(request: APIRequestContext, session: { id: string; token: string }, revision: number) {
  const deadline = Date.now() + buildTimeoutMs;
  while (Date.now() < deadline) {
    const response = await request.get(`/api/v1/sessions/${session.id}/status`, { headers: { Authorization: `Bearer ${session.token}` } });
    expect(response.ok()).toBe(true);
    const status = await response.json();
    if (['FAILED', 'MANUAL_REVIEW_REQUIRED'].includes(status.state)) throw new Error(`Actual Blender revision ${status.revision} failed: ${JSON.stringify(status.error)}`);
    if (status.revision === revision && status.state === 'PREVIEW_READY') return status;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error(`Actual Blender revision ${revision} did not finish within ${buildTimeoutMs / 1000} seconds`);
}

test('real photo analysis builds files, approves, corrects, rejects stale approval and deletes @blender', async ({ page, request }, testInfo) => {
  test.skip(process.env.KEEPSAKE_RUN_WEB_BLENDER_TESTS !== '1', 'Opt in with a running local API, Blender and downloaded public-domain photo fixtures.');
  test.setTimeout(Number(process.env.KEEPSAKE_WEB_LIFECYCLE_TIMEOUT_MS || Math.max(300_000, buildTimeoutMs * 2 + 60_000)));
  const browserErrors: string[] = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  const hosted = !['localhost', '127.0.0.1', '[::1]'].includes(new URL(testInfo.project.use.baseURL || 'http://127.0.0.1:3000').hostname);
  const evidencePrefix = hosted ? 'hosted-' : '';
  const screenshots = path.resolve('evidence/screenshots');
  await fs.mkdir(screenshots, { recursive: true });
  let session: { id: string; token: string } | null = null;
  try {
    await page.goto('/studio', { timeout: hosted ? 120_000 : 30_000 });
    await page.getByLabel('Upload reference photos').setInputFiles(['astronaut.png', 'grace_hopper.jpg'].map(file => path.resolve('tests/vision/fixtures', file)));
    await expect.poll(() => page.evaluate(key => Boolean(sessionStorage.getItem(key)), storageKey), { timeout: hosted ? 60_000 : 10_000 }).toBe(true);
    session = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!), storageKey);
    if (!session) throw new Error('The public-domain fixtures did not create a session');
    await expect(page.getByRole('button', { name: 'Remove photo 2', exact: true })).toBeVisible({ timeout: hosted ? 60_000 : 10_000 });
    const headers = { Authorization: `Bearer ${session.token}` };
    await page.getByLabel('Left character name', { exact: true }).fill('Alex');
    await page.getByLabel('Right character name', { exact: true }).fill('Jamie');
    await page.getByRole('checkbox', { name: /permission to use these photos/ }).check();
    await page.getByRole('button', { name: 'Analyze photos', exact: true }).click();
    const left = page.getByRole('combobox', { name: 'Left character — reference face', exact: true });
    const right = page.getByRole('combobox', { name: 'Right character — reference face', exact: true });
    await expect(left).toBeVisible({ timeout: 120_000 });
    await expect(left).toHaveValue('');
    await expect(right).toHaveValue('');
    await left.selectOption({ label: 'Photo 1 · Face 1' });
    await right.selectOption({ label: 'Photo 2 · Face 1' });
    await page.getByRole('checkbox', { name: /checked the left and right people/ }).check();
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expectNoHorizontalOverflow(page);
      await page.screenshot({ path: path.join(screenshots, `${evidencePrefix}photo-analysis-${width}.jpg`), fullPage: true, type: 'jpeg', quality: 85 });
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    const firstBuildStartedAt = Date.now();
    await page.getByRole('button', { name: 'Create my 3D preview', exact: true }).click();
    const first = await waitForPreview(request, session, 1);
    const firstSubmitToReadyMs = Date.now() - firstBuildStartedAt;
    console.log(`Revision ${first.revision} ready in ${(firstSubmitToReadyMs / 1000).toFixed(1)}s from submit`);
    await expect(page.getByRole('button', { name: 'Approve this preview', exact: true })).toBeVisible();
    expect(first.state).toBe('PREVIEW_READY');
    expect(first.production_approved).toBe(false);
    expect(first.appearance.source).toBe('browser-mediapipe-v1');
    expect(first.params.characters.left.face_morphs).not.toEqual(first.params.characters.right.face_morphs);
    await expect(page.locator('.three-canvas canvas')).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('.viewer-loading')).toHaveCount(0, { timeout: 60_000 });
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expectNoHorizontalOverflow(page);
      await page.screenshot({ path: path.join(screenshots, `${evidencePrefix}photo-preview-${width}.jpg`), fullPage: true, type: 'jpeg', quality: 85 });
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: path.join(screenshots, `${evidencePrefix}photo-preview-desktop.jpg`), fullPage: true, type: 'jpeg', quality: 85 });
    expect(first.artifacts.map((artifact: { kind: string }) => artifact.kind)).toEqual(expect.arrayContaining(['glb', 'stl', 'png', 'qa', 'provenance']));
    await page.getByText('Model files & revision details', { exact: true }).click();
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: 'GLB', exact: true }).click();
    const download = await downloadEvent;
    const downloadedPath = testInfo.outputPath('actual-demo-model.glb');
    await download.saveAs(downloadedPath);
    const bytes = await fs.readFile(downloadedPath);
    expect(bytes.subarray(0, 4).toString()).toBe('glTF');
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(first.artifacts.find((artifact: { kind: string }) => artifact.kind === 'glb').sha256);
    await page.getByRole('button', { name: 'Approve this preview', exact: true }).click();
    await expect(page.getByText(`Revision ${first.revision} approved`, { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Adjust the details', exact: true }).click();
    await page.getByRole('dialog').getByLabel('Name', { exact: true }).first().fill('Mira');
    if (hosted) {
      // Exercise the richer asset combination within the second planned build.
      const character = page.getByRole('dialog').getByRole('group', { name: 'Left character', exact: true });
      await character.getByRole('combobox', { name: 'Hair style', exact: true }).selectOption('curly_long');
      await character.getByRole('combobox', { name: 'Facial hair', exact: true }).selectOption('beard');
      await character.getByRole('combobox', { name: 'Glasses', exact: true }).selectOption('rectangular');
    }
    const secondBuildStartedAt = Date.now();
    await page.getByRole('button', { name: 'Save & create a new preview', exact: true }).click();
    const second = await waitForPreview(request, session, first.revision + 1);
    const secondSubmitToReadyMs = Date.now() - secondBuildStartedAt;
    console.log(`Revision ${second.revision} ready in ${(secondSubmitToReadyMs / 1000).toFixed(1)}s from correction submit`);
    await expect(page.getByRole('button', { name: 'Approve this preview', exact: true })).toBeVisible();
    expect(second.revision).toBe(first.revision + 1);
    expect(second.params.characters.left.engraving_text).toBe('Mira');
    expect(second.params.characters.left.face_morphs).toEqual(first.params.characters.left.face_morphs);
    expect(second.params.characters.right).toEqual(first.params.characters.right);
    if (hosted) {
      expect(second.params.characters.left.hair_style_asset_id).toBe('curly_long');
      expect(second.params.characters.left.facial_hair_id).toBe('beard');
      expect(second.params.characters.left.glasses_asset_id).toBe('rectangular');
    }
    expect(second.checksum).not.toBe(first.checksum);
    expect(second.production_approved).toBe(false);
    const secondGlb = second.artifacts.find((artifact: { kind: string }) => artifact.kind === 'glb');
    const secondDownload = await request.get(secondGlb.url, { headers });
    expect(secondDownload.ok()).toBe(true);
    const secondBytes = await secondDownload.body();
    expect(secondBytes.subarray(0, 4).toString()).toBe('glTF');
    const secondGlbSha256 = createHash('sha256').update(secondBytes).digest('hex');
    expect(secondGlbSha256).toBe(secondGlb.sha256);
    expect(secondGlbSha256).not.toBe(createHash('sha256').update(bytes).digest('hex'));
    await expect(page.locator('.three-canvas canvas')).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('.viewer-loading')).toHaveCount(0, { timeout: 60_000 });
    await page.screenshot({ path: path.join(screenshots, `${evidencePrefix}photo-preview-revision-2.jpg`), fullPage: true, type: 'jpeg', quality: 85 });
    const stale = await request.post(`/api/v1/sessions/${session.id}/approve`, {
      headers, data: { model_revision: first.revision, job_checksum: first.checksum },
    });
    expect(stale.status()).toBe(409);
    await page.getByRole('button', { name: 'Delete session & photos', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Delete session & files', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Your favorite photos', exact: true })).toBeVisible();
    expect((await request.get(`/api/v1/sessions/${session.id}/status`, { headers })).status()).toBe(404);
    expect(browserErrors).toEqual([]);
    await fs.writeFile(path.resolve(`evidence/${evidencePrefix}photo-lifecycle-verification.json`), JSON.stringify({
      passed: true, verified_at: new Date().toISOString(), base_url: testInfo.project.use.baseURL, source: first.appearance.source,
      first_revision: first.revision, second_revision: second.revision,
      first_submit_to_ready_ms: firstSubmitToReadyMs, second_submit_to_ready_ms: secondSubmitToReadyMs,
      first_checksum: first.checksum, second_checksum: second.checksum,
      glb_sha256: createHash('sha256').update(bytes).digest('hex'),
      second_glb_sha256: secondGlbSha256,
      second_left_details: {
        name: second.params.characters.left.engraving_text,
        hair_style: second.params.characters.left.hair_style_asset_id,
        facial_hair: second.params.characters.left.facial_hair_id,
        glasses: second.params.characters.left.glasses_asset_id,
      },
      photo_morphs_retained_after_correction: true,
      stale_approval_status: stale.status(), private_session_deleted: true,
      responsive_widths: [320, 390], browserErrors,
    }, null, 2) + '\n');
  } finally {
    // Always remove the test session and its public-domain portrait fixtures.
    if (session) {
      // Independent HTTP context can still clean up after a page/test timeout.
      const cleanup = await requestFactory.newContext({ baseURL: testInfo.project.use.baseURL });
      try { await cleanup.delete(`/api/v1/sessions/${session.id}`, { headers: { Authorization: `Bearer ${session.token}` } }); }
      finally { await cleanup.dispose(); }
    }
  }
});
