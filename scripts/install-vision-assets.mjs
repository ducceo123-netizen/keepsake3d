import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir, rename } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const version = '1.2.3';
export const assets = [
  { file: 'LICENSE-MEDIAPIPE.txt', sha256: '8707eef0533987efc5b155d64761eeb6e20793f50b9bd1a68dad1cf4719d0ed8', bytes: 12331,
    url: 'https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.2.3/LICENSE' },
  { file: 'vision_bundle.mjs', sha256: 'fb0c02c296f44ce0cc324ba16bd646d8773eb4a7847db4019cc4d0430db7a9b5', bytes: 155990 },
  { file: 'wasm/vision_wasm_module_internal.js', sha256: 'd29996249490361715c769c6a49b43ad47e6ac9a28a8e8bce8d02b238e897851', bytes: 336662 },
  { file: 'wasm/vision_wasm_module_internal.wasm', sha256: 'a269e84b12aefc93c9d6a4d62b01f41e5434a9fa941533bb8e75b1e3d1669e46', bytes: 14665738 },
  { file: 'face_landmarker.task', sha256: '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff', bytes: 3758596,
    url: 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task' },
  { file: 'selfie_multiclass_256x256.tflite', sha256: 'c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0', bytes: 16371837,
    url: 'https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite' },
];
export const fixtures = [
  { file: 'astronaut.png', sha256: '88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5', bytes: 791555,
    url: 'https://raw.githubusercontent.com/scikit-image/scikit-image/v0.24.0/skimage/data/astronaut.png' },
  { file: 'grace_hopper.jpg', sha256: 'a8ca6d734765703b09728ab47fe59f473d93ae3967fc24c7c0288c3c7adb7130', bytes: 61306,
    url: 'https://raw.githubusercontent.com/matplotlib/matplotlib/v3.10.8/lib/matplotlib/mpl-data/sample_data/grace_hopper.jpg' },
];
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
async function materialize(item, destination, checkOnly) {
  const path = resolve(destination, item.file);
  try {
    const existing = await readFile(path);
    if (existing.length === item.bytes && digest(existing) === item.sha256) return;
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (checkOnly) throw new Error(`Missing or invalid pinned asset: ${item.file}. Run node scripts/install-vision-assets.mjs${destination.includes('fixtures') ? ' --fixtures' : ''}`);
  const bytes = item.url
    ? Buffer.from(await (async () => {
        const response = await fetch(item.url, { signal: AbortSignal.timeout(120000) });
        if (!response.ok) throw new Error(`Download failed ${response.status}: ${item.url}`);
        return response.arrayBuffer();
      })())
    : await readFile(resolve(root, 'node_modules/@mediapipe/tasks-vision', item.file));
  if (bytes.length !== item.bytes || digest(bytes) !== item.sha256) throw new Error(`Checksum mismatch: ${item.file}; refusing to install changed bytes`);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(`${path}.tmp`, bytes);
  await rename(`${path}.tmp`, path);
}
export async function install({ checkOnly = false, includeFixtures = false } = {}) {
  const packagePath = resolve(root, 'node_modules/@mediapipe/tasks-vision/package.json');
  const metadata = JSON.parse(await readFile(packagePath, 'utf8'));
  if (metadata.version !== version) throw new Error(`Expected @mediapipe/tasks-vision ${version}; run npm ci`);
  for (const item of assets) await materialize(item, resolve(root, 'apps/web/public/vision'), checkOnly);
  if (includeFixtures) for (const item of fixtures) await materialize(item, resolve(root, 'tests/vision/fixtures'), checkOnly);
  console.log(`Verified ${assets.length} pinned MediaPipe assets${includeFixtures ? ' and 2 public-domain test fixtures' : ''}.`);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  install({ checkOnly: process.argv.includes('--check'), includeFixtures: process.argv.includes('--fixtures') }).catch(error => { console.error(error.message); process.exitCode = 1; });
}
