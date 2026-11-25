import { test, expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { demoSession, json } from './helpers';

// These are UI contract tests. Every API request is intercepted, and no Tripo
// provider request, real generation, or credit charge is permitted by the suite.
const model = 'v3.1-20260211';
const accessCode = 'test-only-generation-code';
const sessionPath = `/api/v1/sessions/${demoSession.id}`;
const photoBytes = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7hcAAAAASUVORK5CYII=', 'base64');
const sha256 = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex');

function triangleGlb() {
  // A tiny valid, self-contained triangle, explicitly not provider output.
  const binary = Buffer.alloc(44);
  [-.5, 0, 0, .5, 0, 0, 0, 1, 0].forEach((value, index) => binary.writeFloatLE(value, index * 4));
  [0, 1, 2].forEach((value, index) => binary.writeUInt16LE(value, 36 + index * 2));
  const document = JSON.stringify({
    asset: { version: '2.0', generator: 'Keepsake3D UI test fixture (not provider output)' },
    scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1 }] }],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: 36, target: 34962 }, { buffer: 0, byteOffset: 36, byteLength: 6, target: 34963 }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [-.5, 0, 0], max: [.5, 1, 0] }, { bufferView: 1, componentType: 5123, count: 3, type: 'SCALAR', min: [0], max: [2] }],
  });
  const documentBytes = Buffer.from(document.padEnd(Math.ceil(Buffer.byteLength(document) / 4) * 4, ' '));
  const glb = Buffer.alloc(12 + 8 + documentBytes.length + 8 + binary.length);
  glb.writeUInt32LE(0x46546c67, 0); glb.writeUInt32LE(2, 4); glb.writeUInt32LE(glb.length, 8);
  glb.writeUInt32LE(documentBytes.length, 12); glb.writeUInt32LE(0x4e4f534a, 16); documentBytes.copy(glb, 20);
  const offset = 20 + documentBytes.length;
  glb.writeUInt32LE(binary.length, offset); glb.writeUInt32LE(0x004e4942, offset + 4); binary.copy(glb, offset + 8);
  return glb;
}

const glbBytes = triangleGlb();
const artifact = { id: 'test-glb', kind: 'glb', url: `${sessionPath}/tripo/artifacts/test-glb`, sha256: sha256(glbBytes), size_bytes: glbBytes.length };
type ProviderState = 'NOT_STARTED' | 'QUEUED' | 'GENERATING' | 'READY' | 'FAILED' | 'SUBMISSION_UNCERTAIN' | 'WAITING_FOR_PROVIDER';
function status(state: ProviderState) {
  return {
    job_id: state === 'NOT_STARTED' ? null : 'test-tripo-job', state,
    progress: state === 'READY' ? 100 : state === 'GENERATING' ? 50 : 0,
    provider_task_id: ['READY', 'GENERATING', 'WAITING_FOR_PROVIDER'].includes(state) ? 'test-provider-task' : null,
    estimated_credits: 30, credits_consumed: state === 'READY' ? 30 : null,
    error: state === 'SUBMISSION_UNCERTAIN'
      ? { code: 'TRIPO_SUBMISSION_UNCERTAIN', message: 'Provider acceptance is unknown. Do not submit another generation.' }
      : state === 'FAILED' ? { code: 'TRIPO_FAILED', message: 'The provider could not finish this model.' } : null,
    artifacts: state === 'READY' ? [artifact] : [], model,
    photo_id: state === 'NOT_STARTED' ? null : 'test-photo-1',
  };
}

async function installMock(page: Page, baseURL: string | undefined, available = true) {
  const origin = new URL(baseURL || 'http://127.0.0.1:3000').origin;
  const mock = {
    state: 'NOT_STARTED' as ProviderState,
    nextSubmitState: 'QUEUED' as ProviderState,
    loseSubmitResponse: false,
    submitHttpStatus: 202,
    sessionHttpStatus: 200,
    planLifetimeMs: 60_000,
    corruptArtifact: false,
    uploaded: 0,
    statusReads: 0,
    planBodies: [] as Array<Record<string, unknown>>,
    submits: [] as Array<{ body: Record<string, unknown>; key: string | undefined }>,
    artifactRequests: [] as string[],
    apiRequests: [] as string[],
    externalRequests: [] as string[],
    unexpectedRequests: [] as string[],
    pageErrors: [] as string[],
  };
  page.on('pageerror', error => mock.pageErrors.push(error.message));
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), pathname = url.pathname;
    if (!['http:', 'https:'].includes(url.protocol)) return route.continue();
    if (url.origin !== origin) {
      mock.externalRequests.push(`${request.method()} ${url.origin}${pathname}`);
      return route.abort('blockedbyclient');
    }
    if (!pathname.startsWith('/api/')) {
      if (pathname.startsWith('/vision/') || pathname.startsWith('/workers/appearance')) {
        mock.unexpectedRequests.push(`Tripo must not start face analysis: ${pathname}`);
        return route.abort('blockedbyclient');
      }
      return route.continue();
    }
    mock.apiRequests.push(`${request.method()} ${pathname}`);
    if (pathname === '/api/v1/tripo/config' && request.method() === 'GET') return json(route, {
      configured: available, available, reason: available ? null : 'The studio owner has not connected Tripo generation.',
      model, estimated_credits: 30, requires_access_code: true,
    });
    if (pathname === '/api/v1/customization-sessions' && request.method() === 'POST') return json(route, demoSession, 201);
    if (pathname.startsWith(`${sessionPath}/`)) {
      const authorization = request.headers().authorization;
      if (authorization !== `Bearer ${demoSession.token}`) {
        mock.unexpectedRequests.push(`Missing owner authorization: ${request.method()} ${pathname}`);
        return json(route, { detail: 'Private session owner authorization required.' }, 401);
      }
    }
    if (pathname === `${sessionPath}/photos` && request.method() === 'POST') {
      mock.uploaded++;
      return json(route, {}, 201);
    }
    if (pathname.startsWith(`${sessionPath}/photos/`) && request.method() === 'GET') return route.fulfill({ status: 200, contentType: 'image/png', body: photoBytes });
    if (pathname === `${sessionPath}/status` && request.method() === 'GET' && mock.sessionHttpStatus !== 200) return json(route, { detail: 'Previous private session is unavailable.' }, mock.sessionHttpStatus);
    if (pathname === `${sessionPath}/status` && request.method() === 'GET') return json(route, {
      id: demoSession.id, state: mock.uploaded ? 'PHOTO_UPLOADED' : 'CREATED', revision: 0,
      job_id: null, error: null, params: null, artifacts: [], qa: null, checksum: null, history: [],
      photos: Array.from({ length: mock.uploaded }, (_, index) => ({ id: `test-photo-${index + 1}`, width: 1, height: 1, sha256: sha256(photoBytes), url: `${sessionPath}/photos/test-photo-${index + 1}` })),
      expires_at: demoSession.expires_at,
    });
    if (pathname === `${sessionPath}/tripo/plan` && request.method() === 'POST') {
      const body = request.postDataJSON();
      mock.planBodies.push(body);
      return json(route, { id: `test-plan-${mock.planBodies.length}`, photo_id: body.photo_id, photo_sha256: body.photo_sha256,
        model, options: { texture: true }, estimated_credits: 30, expires_at: new Date(Date.now() + mock.planLifetimeMs).toISOString() });
    }
    if (pathname === `${sessionPath}/tripo/submit` && request.method() === 'POST') {
      mock.submits.push({ body: request.postDataJSON(), key: request.headers()['idempotency-key'] });
      if (mock.submitHttpStatus !== 202) return json(route, { detail: 'Generation access code is incorrect.' }, mock.submitHttpStatus);
      mock.state = mock.nextSubmitState;
      if (mock.loseSubmitResponse) return route.abort('connectionfailed');
      return json(route, status(mock.state), 202);
    }
    if (pathname === `${sessionPath}/tripo/status` && request.method() === 'GET') {
      mock.statusReads++;
      return json(route, status(mock.state));
    }
    if (pathname === artifact.url && request.method() === 'GET') {
      mock.artifactRequests.push(request.headers().authorization);
      return route.fulfill({ status: 200, contentType: 'model/gltf-binary', body: mock.corruptArtifact ? Buffer.from('corrupted test model') : glbBytes });
    }
    mock.unexpectedRequests.push(`${request.method()} ${pathname}`);
    return json(route, { detail: 'Unexpected endpoint in isolated Tripo UI fixture.' }, 500);
  });
  return mock;
}

type Mock = Awaited<ReturnType<typeof installMock>>;
function expectIsolated(mock: Mock) {
  expect(mock.externalRequests, 'The browser must not contact Tripo or any other external origin').toEqual([]);
  expect(mock.unexpectedRequests, 'Only the explicit mock contract may be called').toEqual([]);
  expect(mock.pageErrors).toEqual([]);
}
async function upload(page: Page) {
  await page.getByLabel('Upload Tripo reference photo', { exact: true }).setInputFiles({ name: 'synthetic-ui-fixture.png', mimeType: 'image/png', buffer: photoBytes });
  await expect(page.getByRole('button', { name: 'Review generation cost', exact: true })).toBeEnabled();
}
async function approvePlan(page: Page) {
  await page.getByRole('button', { name: 'Review generation cost', exact: true }).click();
  await page.getByRole('checkbox', { name: /^I allow this selected photo to be sent to Tripo/ }).check();
  await page.getByRole('checkbox', { name: /^I accept the estimated cost of 30 Tripo credits/ }).check();
  await page.getByLabel('Generation access code', { exact: true }).fill(accessCode);
}

test('Tripo unavailable configuration explains setup and prevents photo upload or generation', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL, false);
  await page.goto('/studio/tripo');
  await expect(page.getByRole('status').filter({ hasText: 'Tripo generation is not connected yet' })).toBeVisible();
  await expect(page.getByText('The studio owner has not connected Tripo generation.', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Upload Tripo reference photo', { exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Review generation cost', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toHaveCount(0);
  expect(mock.apiRequests.every(request => request === 'GET /api/v1/tripo/config')).toBe(true);
  expectIsolated(mock);
});

for (const statusCode of [404, 410, 500]) {
  test(`restored session HTTP ${statusCode} ${statusCode === 500 ? 'preserves the pending-generation lock' : 'clears expired ownership and permits a fresh upload'}`, async ({ page, baseURL }) => {
    const mock = await installMock(page, baseURL);
    await page.goto('/studio/tripo');
    await expect(page.getByLabel('Upload Tripo reference photo', { exact: true })).toBeEnabled();
    await page.evaluate(session => {
      sessionStorage.setItem('keepsake-tripo-session-v1', JSON.stringify(session));
      sessionStorage.setItem(`keepsake-tripo-session-v1:attempt:${session.id}`, JSON.stringify({ key: 'previous-test-attempt', plan_id: 'previous-test-plan' }));
    }, demoSession);
    mock.sessionHttpStatus = statusCode;
    await page.reload();
    const uploader = page.getByLabel('Upload Tripo reference photo', { exact: true });
    if (statusCode === 500) {
      await expect(page.getByRole('alert').filter({ hasText: 'Previous private session is unavailable.' })).toBeVisible();
      await expect(uploader).toBeDisabled();
      expect(await page.evaluate(() => sessionStorage.getItem('keepsake-tripo-session-v1:attempt:test-private-session'))).not.toBeNull();
    } else {
      await expect(page.getByRole('alert').filter({ hasText: 'Your previous studio session has expired or was removed.' })).toBeVisible();
      await expect(uploader).toBeEnabled();
      expect(await page.evaluate(() => sessionStorage.getItem('keepsake-tripo-session-v1'))).toBeNull();
      expect(await page.evaluate(() => sessionStorage.getItem('keepsake-tripo-session-v1:attempt:test-private-session'))).toBeNull();
      mock.sessionHttpStatus = 200;
      await upload(page);
      expect(mock.apiRequests.filter(request => request === 'POST /api/v1/customization-sessions')).toHaveLength(1);
    }
    expect(mock.submits).toHaveLength(0);
    expectIsolated(mock);
  });
}

test('Tripo requires a selected-photo plan, both explicit consents and a nonblank access code', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL);
  await page.goto('/studio/tripo');
  await expect(page.getByRole('button', { name: 'Review generation cost', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toHaveCount(0);
  await upload(page);
  expect(mock.planBodies).toHaveLength(0);
  await page.getByRole('button', { name: 'Review generation cost', exact: true }).click();
  const create = page.getByRole('button', { name: 'Create with Tripo', exact: true });
  const transfer = page.getByRole('checkbox', { name: /^I allow this selected photo to be sent to Tripo/ });
  const cost = page.getByRole('checkbox', { name: /^I accept the estimated cost of 30 Tripo credits/ });
  const code = page.getByLabel('Generation access code', { exact: true });
  await expect(transfer).not.toBeChecked();
  await expect(cost).not.toBeChecked();
  await expect(create).toBeDisabled();
  await code.fill(accessCode);
  await transfer.check();
  await expect(create).toBeDisabled();
  await cost.check();
  await transfer.uncheck();
  await expect(create).toBeDisabled();
  await transfer.check();
  await code.fill('   ');
  await expect(create).toBeDisabled();
  expect(mock.submits).toHaveLength(0);
  await code.fill(accessCode);
  await expect(create).toBeEnabled();
  expect(mock.planBodies).toEqual([{ photo_id: 'test-photo-1', photo_sha256: sha256(photoBytes) }]);
  await create.click();
  await expect.poll(() => mock.submits.length).toBe(1);
  expect(mock.submits[0].body).toEqual({ plan_id: 'test-plan-1', consent: true, cost_accepted: true, access_code: accessCode });
  expect(mock.submits[0].key).toMatch(/^[\da-f]{8}-[\da-f-]{27}$/i);
  await expect(create).toHaveCount(0);
  await expect(page.getByLabel('Upload Tripo reference photo', { exact: true })).toBeDisabled();
  const persisted = await page.evaluate(() => JSON.stringify({ session: { ...sessionStorage }, local: { ...localStorage } }));
  expect(persisted).not.toContain(accessCode);
  expectIsolated(mock);
});

test('changing the selected reference invalidates the quote and clears consent', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL);
  await page.goto('/studio/tripo');
  await upload(page);
  await upload(page);
  await approvePlan(page);
  expect(mock.planBodies[0].photo_id).toBe('test-photo-2');
  await page.getByRole('radio', { name: /Photo 1$/ }).check();
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Review generation cost', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: /^I allow this selected photo/ })).not.toBeChecked();
  await expect(page.getByRole('checkbox', { name: /^I accept the estimated cost/ })).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toBeDisabled();
  expect(mock.planBodies[1].photo_id).toBe('test-photo-1');
  expect(mock.submits).toHaveLength(0);
  expectIsolated(mock);
});

test('an expired Tripo plan cannot be submitted without a new cost review', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL);
  mock.planLifetimeMs = -100;
  await page.goto('/studio/tripo');
  await upload(page);
  await page.getByRole('button', { name: 'Review generation cost', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'This cost plan expired.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toHaveCount(0);
  expect(mock.submits).toHaveLength(0);
  expectIsolated(mock);
});

test('a lost submission response stays locked across status refresh and reload without another POST', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL);
  mock.loseSubmitResponse = true;
  mock.nextSubmitState = 'NOT_STARTED'; // A temporarily stale GET must not unlock credit spending.
  await page.goto('/studio/tripo');
  await upload(page);
  await approvePlan(page);
  await page.getByRole('button', { name: 'Create with Tripo', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'No second generation has been submitted.' })).toBeVisible();
  await expect.poll(() => mock.statusReads).toBeGreaterThan(0);
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Review generation cost', exact: true })).toHaveCount(0);
  mock.state = 'SUBMISSION_UNCERTAIN';
  await page.getByRole('button', { name: 'Refresh Tripo status', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Checking whether Tripo accepted this request' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('status').filter({ hasText: 'Checking whether Tripo accepted this request' })).toBeVisible();
  await expect(page.getByLabel('Upload Tripo reference photo', { exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toHaveCount(0);
  mock.state = 'WAITING_FOR_PROVIDER';
  await page.getByRole('button', { name: 'Refresh Tripo status', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Still waiting for Tripo' })).toBeVisible();
  const readsBeforePolling = mock.statusReads;
  await expect.poll(() => mock.statusReads, { timeout: 6000 }).toBeGreaterThan(readsBeforePolling);
  expect(mock.submits).toHaveLength(1);
  expect(mock.planBodies).toHaveLength(1);
  expectIsolated(mock);
});

test('an explicitly rejected access code permits a deliberate corrected retry only after NOT_STARTED status', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL);
  mock.submitHttpStatus = 403;
  await page.goto('/studio/tripo');
  await upload(page);
  await approvePlan(page);
  const create = page.getByRole('button', { name: 'Create with Tripo', exact: true });
  await create.click();
  await expect(page.getByRole('alert').filter({ hasText: 'Generation access code is incorrect.' })).toBeVisible();
  await expect(create).toBeEnabled();
  expect(mock.statusReads).toBeGreaterThan(0);
  expect(mock.submits).toHaveLength(1);
  expect(await page.evaluate(() => sessionStorage.getItem('keepsake-tripo-session-v1:attempt:test-private-session'))).toBeNull();
  mock.submitHttpStatus = 202;
  await page.getByLabel('Generation access code', { exact: true }).fill('test-only-corrected-code');
  expect(mock.submits).toHaveLength(1);
  await create.click();
  await expect(page.getByRole('status').filter({ hasText: 'Your model is queued' })).toBeVisible();
  expect(mock.submits).toHaveLength(2);
  expect(mock.submits[1].body.access_code).toBe('test-only-corrected-code');
  expect(mock.submits[1].key).not.toBe(mock.submits[0].key);
  expectIsolated(mock);
});

test('a ready Tripo model renders and downloads only authenticated checksum-matched GLB bytes', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL);
  mock.nextSubmitState = 'READY';
  await page.goto('/studio/tripo');
  await upload(page);
  await approvePlan(page);
  await page.getByRole('button', { name: 'Create with Tripo', exact: true }).click();
  const download = page.getByRole('button', { name: 'Download GLB', exact: true });
  await expect(download).toBeVisible();
  await expect(page.locator('.three-canvas canvas')).toBeVisible();
  await expect(page.getByText('Loading your model…', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Show separated halves', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Toggle rendered image', exact: true })).toHaveCount(0);
  const completed = page.waitForEvent('download');
  await download.click();
  const file = await completed;
  expect(file.suggestedFilename()).toBe('keepsake-tripo-model.glb');
  expect(file.url()).toMatch(/^blob:/);
  expect(await file.failure()).toBeNull();
  const saved = await file.path();
  expect(saved).not.toBeNull();
  expect(sha256(await readFile(saved!))).toBe(artifact.sha256);
  expect(mock.artifactRequests.length).toBeGreaterThanOrEqual(2); // Viewer and download both use the private endpoint.
  expect(mock.artifactRequests.every(header => header === `Bearer ${demoSession.token}`)).toBe(true);
  const furtherDownloads: string[] = [];
  page.on('download', file => furtherDownloads.push(file.suggestedFilename()));
  mock.corruptArtifact = true;
  await download.click();
  await expect(page.getByRole('alert').filter({ hasText: 'The model checksum did not match.' })).toBeVisible();
  expect(furtherDownloads).toEqual([]);
  expect(mock.submits).toHaveLength(1);
  expectIsolated(mock);
});

test('a terminal provider failure shows its error without an automatic paid retry', async ({ page, baseURL }) => {
  const mock = await installMock(page, baseURL);
  mock.nextSubmitState = 'FAILED';
  await page.goto('/studio/tripo');
  await upload(page);
  await approvePlan(page);
  await page.getByRole('button', { name: 'Create with Tripo', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Tripo could not finish this model' })).toContainText('The provider could not finish this model.');
  await page.getByRole('button', { name: 'Refresh Tripo status', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('status').filter({ hasText: 'Tripo could not finish this model' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Create with Tripo', exact: true })).toHaveCount(0);
  expect(mock.submits).toHaveLength(1);
  expectIsolated(mock);
});
