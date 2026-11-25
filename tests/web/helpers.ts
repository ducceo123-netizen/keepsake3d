import { expect, type Page, type Route } from '@playwright/test';

export const storageKey = 'keepsake-local-session-v2';
export const demoSession = {
  id: 'test-private-session',
  token: 'test-only-owner-token-not-a-real-credential',
  expires_at: '2030-11-25T08:00:00+00:00',
};
const neutralMorphs = Object.fromEntries(['face_width', 'face_height', 'jaw_width', 'chin_length', 'cheek_fullness', 'eye_spacing', 'eye_size', 'brow_thickness', 'brow_arch', 'nose_width', 'nose_projection', 'mouth_width', 'smile'].map(key => [key, 0]));
export const demoCharacters = {
  left: {
    hair_style_asset_id: 'long', hair_color_id: 'silver', facial_hair_id: 'none',
    glasses_asset_id: 'round', skin_material_id: 'warm', outfit_palette_id: 'sage',
    pants_palette_id: 'navy', shoes_palette_id: 'cream',
    face_morphs: { ...neutralMorphs, face_width: .2 }, engraving_text: 'Mira',
  },
  right: {
    hair_style_asset_id: 'short', hair_color_id: 'black', facial_hair_id: 'beard',
    glasses_asset_id: 'none', skin_material_id: 'deep', outfit_palette_id: 'blue',
    pants_palette_id: 'brown', shoes_palette_id: 'white',
    face_morphs: { ...neutralMorphs, jaw_width: -.3 }, engraving_text: 'Sam',
  },
};
export function demoStatus(state = 'FAILED') {
  return {
    id: demoSession.id, state, revision: 3, job_id: 'test-job-3',
    error: state === 'FAILED' ? { code: 'BUILD_FAILED', message: 'The local demo worker stopped. Please retry this preview.' } : null,
    photos: [{ id: 'synthetic-photo', width: 640, height: 480, sha256: '0'.repeat(64), url: `/api/v1/sessions/${demoSession.id}/photos/synthetic-photo` }],
    params: { schema_version: '2.0', characters: structuredClone(demoCharacters) },
    artifacts: [], qa: null, checksum: null, history: [],
    expires_at: demoSession.expires_at, quality_level: 'DEMO', production_approved: false,
  };
}
export async function seedSession(page: Page) {
  await page.addInitScript(({ key, session }) => {
    sessionStorage.setItem(key, JSON.stringify(session));
  }, { key: storageKey, session: demoSession });
}
export async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}
export async function settleVisuals(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(Array.from(document.images, image => image.decode().catch(() => undefined)));
  });
}
export async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport + 1);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport + 1);
}
export async function focusByKeyboard(page: Page, accessibleName: string) {
  const target = page.getByRole('button', { name: accessibleName, exact: true });
  for (let tab = 0; tab < 45; tab++) {
    await page.keyboard.press('Tab');
    if (await target.evaluate(element => element === document.activeElement)) return target;
  }
  throw new Error(`Could not reach the ${accessibleName} button with the keyboard`);
}
