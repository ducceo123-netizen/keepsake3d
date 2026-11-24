import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import { storageKey } from './helpers';

test('real fixture builds files, approves, corrects, rejects stale approval and deletes @blender', async ({ page, request }, testInfo) => {
  test.skip(process.env.KEEPSAKE_RUN_WEB_BLENDER_TESTS !== '1', 'Opt in with a running local API and Blender. This test uses only a synthetic fixture.');
  test.setTimeout(300_000);
  let session: { id: string; token: string } | null = null;
  try {
    await page.goto('/studio');
    await page.getByRole('button', { name: 'Try a sample photo', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Remove photo 1', exact: true })).toBeVisible();
    session = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!), storageKey);
    if (!session) throw new Error('The synthetic fixture did not create a session');
    const headers = { Authorization: `Bearer ${session.token}` };
    await page.getByLabel('First name', { exact: true }).fill('Alex');
    await page.getByLabel('Second name', { exact: true }).fill('Jamie');
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Create my 3D preview', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Approve this preview', exact: true })).toBeVisible({ timeout: 180_000 });
    const firstResponse = await request.get(`/api/v1/sessions/${session.id}/status`, { headers });
    expect(firstResponse.ok()).toBe(true);
    const first = await firstResponse.json();
    expect(first.state).toBe('PREVIEW_READY');
    expect(first.production_approved).toBe(false);
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
    await page.getByRole('button', { name: 'Save & create a new preview', exact: true }).click();
    await expect.poll(async () => {
      const value = await (await request.get(`/api/v1/sessions/${session!.id}/status`, { headers })).json();
      return { revision: value.revision, state: value.state };
    }, { timeout: 180_000, intervals: [1_000, 2_000] }).toEqual({ revision: first.revision + 1, state: 'PREVIEW_READY' });
    await expect(page.getByRole('button', { name: 'Approve this preview', exact: true })).toBeVisible();
    const second = await (await request.get(`/api/v1/sessions/${session.id}/status`, { headers })).json();
    expect(second.revision).toBe(first.revision + 1);
    expect(second.params.characters.left.engraving_text).toBe('Mira');
    expect(second.checksum).not.toBe(first.checksum);
    expect(second.production_approved).toBe(false);
    const stale = await request.post(`/api/v1/sessions/${session.id}/approve`, {
      headers, data: { model_revision: first.revision, job_checksum: first.checksum },
    });
    expect(stale.status()).toBe(409);
    await page.getByRole('button', { name: 'Delete session & photos', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Delete session & files', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Your favorite photos', exact: true })).toBeVisible();
    expect((await request.get(`/api/v1/sessions/${session.id}/status`, { headers })).status()).toBe(404);
  } finally {
    // The only server data created by this test is its synthetic fixture.
    if (session) await request.delete(`/api/v1/sessions/${session.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
  }
});
