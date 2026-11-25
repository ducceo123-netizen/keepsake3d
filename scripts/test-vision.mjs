import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { install, fixtures } from './install-vision-assets.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
await install({ checkOnly: true, includeFixtures: true });
const swatches = JSON.parse(await readFile(resolve(root, 'assets/designs/better-together/0.2.0-demo/palette-swatches.json'), 'utf8'));
const { palettes } = await import('../apps/web/public/workers/appearance-math.mjs');
let paletteSwatchesChecked = 0;
for (const [group, field] of [['hair', 'hair_color_id'], ['skin', 'skin_material_id'], ['clothing', 'outfit_palette_id']]) {
  assert.deepEqual(Object.keys(palettes[field]).sort(), Object.keys(swatches[group]).sort(), `${group}: browser/model palette IDs must match`);
  for (const [id, hex] of Object.entries(swatches[group])) {
    const rgb = [1, 3, 5].map(index => Number.parseInt(hex.slice(index, index + 2), 16));
    assert.deepEqual(palettes[field][id], rgb, `${field}.${id}: browser samples must match authored sRGB material`);
    paletteSwatchesChecked++;
  }
}
const csp = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; img-src 'self' blob: data:; object-src 'none'; base-uri 'none'";
const server = createServer(async (req, res) => {
  res.setHeader('Content-Security-Policy', csp);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.url === '/') { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>Actual MediaPipe CPU WASM tests</title>'); return; }
  const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const base = path.startsWith('/fixtures/') ? resolve(root, 'tests/vision') : path.startsWith('/test/') ? resolve(root, 'tests/vision') : resolve(root, 'apps/web/public');
  const relative = path.startsWith('/test/') ? path.slice(6) : path.slice(1);
  const target = resolve(base, relative);
  if (!target.startsWith(`${base}${sep}`)) { res.writeHead(403).end(); return; }
  try {
    const data = await readFile(target);
    res.setHeader('Content-Type', ({ '.mjs': 'text/javascript', '.js': 'text/javascript', '.wasm': 'application/wasm', '.png': 'image/png', '.jpg': 'image/jpeg' })[extname(target)] || 'application/octet-stream');
    res.end(data);
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const foreign = [], errors = [];
  context.on('request', req => { if (!req.url().startsWith(`${origin}/`)) foreign.push(req.url()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin);
  const results = await page.evaluate(async (metadata) => {
    const images = await Promise.all(metadata.map(async item => ({ id: item.file, blob: await (await fetch(`/fixtures/${item.file}`)).blob() })));
    return await new Promise((resolve, reject) => {
      const worker = new Worker('/test/engine-worker.mjs', { type: 'module' });
      const timer = setTimeout(() => { worker.terminate(); reject(new Error('Actual WASM inference timed out')); }, 120000);
      worker.onerror = error => { clearTimeout(timer); worker.terminate(); reject(new Error(error.message)); };
      worker.onmessage = ({ data }) => { clearTimeout(timer); worker.terminate(); data.type === 'error' ? reject(new Error(data.message)) : resolve(data); };
      worker.postMessage({ images });
    });
  }, fixtures);
  for (const result of results.results) {
    assert.equal(result.faces, 1, `${result.id}: expected one actual detected face`);
    assert.equal(result.landmarks[0], 478);
    assert.ok(result.categories.includes(3), 'Real segmentation includes face skin');
    assert.ok(result.categories.includes(4), 'Real segmentation includes clothes');
  }
  const application = await page.evaluate(async (metadata) => {
    const originals = await Promise.all(metadata.map(async item => ({ id: item.file, sha256: item.sha256, blob: await (await fetch(`/fixtures/${item.file}`)).blob() })));
    const wrap = async (id, blob) => ({ id, blob, sha256: [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(n => n.toString(16).padStart(2, '0')).join('') });
    const bitmap = await createImageBitmap(originals[0].blob);
    const makeVariant = async (kind) => {
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height), ctx = canvas.getContext('2d');
      ctx.drawImage(bitmap, 0, 0);
      if (kind === 'background') { ctx.fillStyle = '#00ff00'; ctx.fillRect(bitmap.width * .9, 0, bitmap.width * .1, bitmap.height); }
      else {
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
        for (let k = 0; k < pixels.data.length; k += 4) [pixels.data[k], pixels.data[k+2]] = [pixels.data[k+2], pixels.data[k]];
        ctx.putImageData(pixels, 0, 0);
      }
      return wrap(kind, await canvas.convertToBlob({ type: 'image/png' }));
    };
    const variants = await Promise.all(['background', 'color-swap'].map(makeVariant));
    bitmap.close();
    const blank = new OffscreenCanvas(512, 512); blank.getContext('2d').fillRect(0, 0, 512, 512);
    const blankPhoto = await wrap('no-face', await blank.convertToBlob({ type: 'image/png' }));
    let ticks = 0;
    const tickTimer = setInterval(() => ticks++, 20);
    const run = photos => new Promise((resolve, reject) => {
      const worker = new Worker('/workers/appearance.js', { type: 'module' });
      const timer = setTimeout(() => { worker.terminate(); reject(new Error('Application inference timed out')); }, 120000);
      worker.onerror = error => { clearTimeout(timer); worker.terminate(); reject(new Error(error.message)); };
      worker.onmessage = ({ data }) => {
        if (data.type === 'progress') return;
        clearTimeout(timer); worker.terminate(); data.type === 'error' ? reject(new Error(data.message)) : resolve(data);
      };
      worker.postMessage({ photos });
    });
    try { return { baseline: await run([...originals, blankPhoto]), variants: await run(variants), mainThreadTicks: ticks }; }
    finally { clearInterval(tickTimer); }
  }, fixtures);
  assert.equal(application.baseline.faces.length, 2, 'Distinct real portrait fixtures produce two candidates; blank produces none');
  assert.equal(application.variants.faces.length, 2, 'Both transformed photo variants remain detectable');
  assert.ok(application.baseline.warnings.some(warning => warning.includes('No clear face')), 'Blank photo yields actionable warning');
  assert.ok(application.mainThreadTicks > 2, 'Worker inference keeps the page event loop responsive');
  for (const face of [...application.baseline.faces, ...application.variants.faces]) {
    assert.equal(face.usable, true, `${face.id}: expected usable face; ${face.warnings.join('; ')}`);
    assert.ok(face.observed_fields.includes('skin_material_id'), 'Actual skin region samples are observed');
    assert.ok(face.observed_fields.includes('outfit_palette_id'), 'Actual garment region samples are observed');
    assert.equal(face.params.face_morphs.nose_projection, 0, 'Unseen depth remains authored default');
    assert.ok(Object.values(face.params.face_morphs).every(value => Number.isFinite(value) && value >= -1 && value <= 1));
    assert.ok(face.bounds.x >= 0 && face.bounds.y >= 0 && face.bounds.width > 0 && face.bounds.height > 0);
    assert.ok(!JSON.stringify(face).includes('faceLandmarks'), 'Raw landmarks are not emitted to the application');
  }
  const [original, different] = application.baseline.faces;
  const [background, colorSwap] = application.variants.faces;
  assert.notDeepEqual(original.params.face_morphs, different.params.face_morphs, 'Different real faces change bounded morphology');
  for (const field of ['hair_color_id', 'skin_material_id', 'outfit_palette_id']) assert.equal(original.params[field], background.params[field], `${field}: unrelated background change must not recolor the face`);
  assert.ok(['hair_color_id', 'skin_material_id', 'outfit_palette_id'].some(field => original.params[field] !== colorSwap.params[field]), 'Photo color changes affect the mapped palette');
  assert.ok(Math.abs(original.measurements.face_width_height - colorSwap.measurements.face_width_height) < .1, 'Color transformation does not substantially change face proportions');
  assert.deepEqual(foreign, [], 'No external requests permitted');
  assert.deepEqual(errors, [], 'No browser errors permitted');
  const report = { passed: true, verified_at: new Date().toISOString(), delegate: 'CPU', worker: 'module', paletteSwatchesChecked, externalRequests: foreign.length, engine: results, application };
  await mkdir(resolve(root, 'evidence'), { recursive: true });
  await writeFile(resolve(root, 'evidence/vision-browser-verification.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ passed: true, delegate: 'CPU', paletteSwatchesChecked, portraits: results.results.length, applicationCandidates: application.baseline.faces.length, mainThreadTicks: application.mainThreadTicks, externalRequests: foreign.length, report: 'evidence/vision-browser-verification.json' }, null, 2));
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
