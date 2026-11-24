# Browser regression suite

Status at authoring: **written and TypeScript checked, not executed**. No browser was launched while authoring this suite. Baseline images have not been generated or accepted after visual review. The root agent completed live CUA browser checks and inspected screenshots; those are separate browser evidence, not a passing Playwright run. See [the verification ledger](../../docs/VERIFICATION.md).

## Run functional checks

From the project root, after `bash scripts/setup.sh`:

```bash
npx playwright install chromium
npm run test:e2e -- --grep-invert @visual
```

The Playwright config starts the local Next.js server if needed and reuses it outside CI. Ordinary tests intercept their API calls and do not require a running FastAPI service. The real Blender lifecycle test is skipped by default. To test an already running frontend on another address, set `KEEPSAKE_WEB_BASE_URL`; the config then does not launch a server.

The suite covers home/studio overflow at 320, 390, 768, 1280 and 1440 pixels; serious/critical axe findings; keyboard file selection; unsupported/oversized file errors; name patterns; failed-session reload and parameter-preserving retry; polling recovery; and deletion during an in-flight status request.

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

This test uses the synthetic fixture, creates two real revisions, checks a downloaded GLB header/hash, exercises preview approval, rejects stale approval and deletes its private session in cleanup. It may take several minutes and requires the same installed Blender binary as the app. It does not call paid services, upload real-person photos, place orders or approve production.

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
