# Browser regression suite

The suite includes actual CPU WebAssembly photo analysis, HTTP-fixture state checks, accessibility scans and an optional real API/Blender lifecycle. Visual snapshot baselines remain ungenerated and unreviewed. Test screenshots are evidence, not approved snapshot baselines. See [the verification ledger](../../docs/VERIFICATION.md) for recorded runs.

Verified locally on 2026-11-25 against the static export served by FastAPI on port 8000: 19 functional/accessibility/responsive tests passed in 10.4 seconds; the separate real two-revision photo/Blender lifecycle passed in 57.1 seconds. The latter records `evidence/photo-lifecycle-verification.json`. Populated analysis/viewer screenshots at 320/390px were inspected and had no horizontal overflow. These results do not establish resemblance accuracy or production print readiness.

After cancellation and correction-retry fixes, eight targeted photo-analysis/recovery checks passed in 12.9 seconds. These include four added regressions: cancellation during photo retrieval, consent revocation during retrieval, stable idempotency keys after a lost response, and no new build for unchanged corrections. Both cancellation cases also complete real CPU inference successfully on retry.

## Run functional checks

From the project root, after `bash scripts/setup.sh`:

```bash
npx playwright install chromium
node scripts/install-vision-assets.mjs --fixtures
npm run test:e2e -- --grep-invert @visual
```

The Playwright config starts the local Next.js server if needed and reuses it outside CI. Ordinary tests intercept their HTTP persistence calls and do not require a running FastAPI service. The photo-analysis test still executes the real pinned browser models on public-domain portrait fixtures; it does not mock inference. The real Blender lifecycle test is skipped by default. To test an already running frontend on another address, set `KEEPSAKE_WEB_BASE_URL`; the config then does not launch a server. Run only one Playwright command at a time against the default report/output directories.

The suite covers home/studio overflow at 320, 390, 768, 1280 and 1440 pixels; serious/critical axe findings; keyboard file selection; unsupported/oversized file errors; name patterns; failed-session reload and parameter-preserving retry; polling recovery; deletion during an in-flight status request; real photo measurements; explicit left/right face selection; duplicate-face prevention; and mandatory appearance review that resets after editing.

## Establish visual baselines deliberately

Four snapshot assertions cover the homepage and empty studio at 390px and 1280px. The default `updateSnapshots: 'none'` means missing baselines fail instead of becoming implicitly accepted.

Create candidate baseline files on the platform/browser used for future comparisons:

```bash
npm run test:e2e -- --grep @visual --update-snapshots
```

Inspect every image in `tests/web/visual.spec.ts-snapshots/` at its actual size. Check product labels, typography, control visibility, crop, spacing, overflow and mobile legibility. Correct defects, regenerate affected candidates, then commit only the images that were actually reviewed. Generating a candidate does not establish that it passed visual review. Platform-specific rendering can differ; keep the same environment for subsequent comparisons.

Visual baseline review is an implementation quality check that an agent or developer can complete; it does not require a new user permission gate. After review, run without updating:

```bash
npm run test:e2e
```

A visual diff must be investigated before using `--update-snapshots` again. Failure screenshots and traces are under `test-results/`; the HTML report is under `playwright-report/`.

## Opt into the actual Blender lifecycle

Start the API and frontend with Blender configured:

```bash
bash scripts/dev.sh
```

In a second terminal:

```bash
KEEPSAKE_RUN_WEB_BLENDER_TESTS=1 npm run test:e2e -- --grep @blender --workers=1
```

This test uploads two public-domain portrait fixtures, runs real browser inference, explicitly assigns and reviews both faces, creates two actual Blender revisions, checks a downloaded GLB header/hash, exercises preview approval, rejects stale approval and deletes its private session in cleanup. It records populated analysis and viewer screenshots at 320/390px plus desktop and checks for page errors. The portraits are engineering fixtures, never customer examples or endorsements; see [third-party notices](../../THIRD_PARTY_NOTICES.md). It does not use customer data, paid services, orders or production approval.

To test the same-origin static export/FastAPI deployment and its CSP, point at that running service:

```sh
KEEPSAKE_WEB_BASE_URL=http://127.0.0.1:8000 KEEPSAKE_RUN_WEB_BLENDER_TESTS=1 \
  npm run test:e2e -- --grep-invert @visual --workers=2
```

The independent model and application-worker check also verifies pinned asset hashes, material palette equality, no-face handling, photo-dependent proportions/colors, unrelated background stability, UI-thread responsiveness and zero external requests:

```sh
node scripts/test-vision.mjs
```

For a hosted free-instance check, allow its slower CPU a separate deadline and keep the session cleanup enabled:

```sh
KEEPSAKE_WEB_BASE_URL=https://keepsake3d-demo.onrender.com \
KEEPSAKE_RUN_WEB_BLENDER_TESTS=1 KEEPSAKE_WEB_BUILD_TIMEOUT_MS=300000 \
KEEPSAKE_WEB_LIFECYCLE_TIMEOUT_MS=900000 \
  npm run test:e2e -- tests/web/blender-lifecycle.spec.ts --workers=1
```

This command performs real uploads and builds on the named deployment, so run it only against the app instance being verified. The generated report records the base URL. Deadline settings are test patience, not a generation-time promise.

The existing Python integration test is another independently runnable path:

```bash
KEEPSAKE_RUN_BLENDER_TESTS=1 .venv/bin/python -m pytest tests/api/test_blender_integration.py -q
```

## Source-only validation

The following verifies TypeScript compilation without starting a server or browser:

```bash
./node_modules/.bin/tsc --noEmit --target ES2022 --module NodeNext \
  --moduleResolution NodeNext --esModuleInterop --skipLibCheck \
  playwright.config.ts tests/web/*.ts
```
