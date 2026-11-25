# Keepsake 3D — Better Together

A photo-personalized, stylized couple figurine studio built from the supplied Keepsake3D handoff. The customer uploads photos, runs private on-device face analysis, explicitly assigns two faces, reviews appearance, then receives real Blender GLB/STL/PNG files and revision-bound approval.

[Open the Render studio](https://keepsake3d-demo.onrender.com/studio/) · [Public source](https://github.com/ducceo123-netizen/keepsake3d)

## What changed in version 0.2

The original demo used fixed appearance settings and did not interpret photos. The new customer flow uses actual MediaPipe face landmarks and segmentation in a CPU Web Worker. Bounded face proportions and suggested hair/skin/top colors affect the 3D scene. Hair style, facial hair, glasses and other clothing choices require review. Missing or unusable faces produce actionable feedback; there is no silent mock fallback.

The sculpted preview's analysis models are pinned, verified and self-hosted. That flow sends no photos to an external AI provider and needs no paid API key. The server checks photo ownership/checksums and bounded parameters, and retains immutable appearance profiles tied to artifact provenance. Browser inference is customization input, not biometric authentication or independently verified server evidence.

The result is a stylized interpretation with a fixed body, pose and puzzle base. It does not guarantee exact likeness or reproduce the concept illustration. The beta has no checkout or manufacturing approval. The current free Render service has temporary storage; restarting or redeploying may clear sessions and files before their 24-hour expiry.

Read [photo personalization and its limits](docs/PHOTO_PERSONALIZATION.md), [API contract](docs/API.md), [verification](docs/VERIFICATION.md) and [Render deployment](docs/DEPLOY_RENDER.md).

## Run locally

### Optional Tripo image-to-model studio

`/studio/tripo/` is a separate, explicitly consented workflow: select one uploaded image, review a server-issued cost plan, approve transfer to Tripo and credit usage, then receive a private textured GLB. It bypasses the local face-selection gate. It does not promise the authored couple pose, puzzle base, engraving, independently editable characters, exact likeness or printability.

The pinned H3.1 request (`v3.1-20260211`, standard texture, 50,000-face target) is estimated at 30 credits. There are no automatic paid retries. The server stores the submission boundary, remote task ID and a spend ledger; known tasks resume after restart, while an uncertain creation blocks another submission. Actual billed credits remain visible even when a returned model fails ingestion checks.

Configure `TRIPO_API_KEY` and `TRIPO_GENERATION_CODE` only as backend secrets. The generation code authorizes customer credit use; it is not the API key. Local CLI login does not configure a hosted server. Public deployments additionally require persistent private session/photo storage (`KEEPSAKE_STORAGE_MODE=persistent`, `TRIPO_DURABLE_STATE=1`); `TRIPO_STATE_DIR` must live beneath `KEEPSAKE_DATA_DIR` on the persistent mount. The current Free Blueprint leaves Tripo generation disabled. [Prepared Render settings](deploy/tripo-render-settings.json) are a reviewable proposal, not an applied infrastructure change. Default limits are one remote job at a time and three requests per hour across sessions.

No provider-generated asset has been verified for this integration yet: automated Tripo tests use explicit HTTP fixtures and spend no credits. Deleting a session removes local photos/models and retains a minimal billing record; it cannot guarantee cancellation or deletion at Tripo.

### Development server

Requires Node 24, Python 3.14 and Blender 4.5 LTS (the pinned renderer is 4.5.16). Dependencies are pinned in npm/Python locks. From this directory:

```bash
bash scripts/setup.sh
# Set BLENDER_BIN in .env if Blender is not on PATH.
bash scripts/dev.sh
```

Open [localhost:3000](http://127.0.0.1:3000). The frontend proxies `/api/v1` to the local FastAPI process on port 8000. Development commands install the verified self-hosted vision assets automatically; the first install needs internet access. A local Blender under the surrounding workspace's `work/tools/blender/Blender.app/Contents/MacOS/Blender` is also auto-detected. That binary is not part of the repository.

To build the same static site served on Render:

```bash
KEEPSAKE_STATIC_EXPORT=1 npm run build
# Serve apps/web/out through FastAPI using KEEPSAKE_WEB_DIR.
```

Use clear, front-facing photos of both people. Confirm permission, click **Analyze photos**, select the left/right faces, review the appearance and build. Modern WebAssembly, Web Workers and OffscreenCanvas support is required. The first model load is about 35 MB before compression. CPU generation on the free server can take minutes.

## Checks

```bash
npm run typecheck
npm run check:design
node scripts/install-vision-assets.mjs --fixtures
node scripts/test-vision.mjs
.venv/bin/python -m pytest tests/api tests/pipeline -q
# Include real Blender exports:
KEEPSAKE_RUN_BLENDER_TESTS=1 .venv/bin/python -m pytest tests/api tests/pipeline -q
# Functional browser checks (install Chromium first):
npx playwright install chromium
npm run test:e2e -- --grep-invert @visual
# Real browser inference + running API + Blender:
KEEPSAKE_RUN_WEB_BLENDER_TESTS=1 npm run test:e2e -- tests/web/blender-lifecycle.spec.ts
```

Public-domain portraits are used only as test fixtures. They are checksum-pinned and are not presented as customer examples or endorsements. See [third-party notices](THIRD_PARTY_NOTICES.md). Screenshot baseline tests are separate; missing/unreviewed baselines do not count as passed verification.

A direct geometry build is available for engineering checks:

```bash
.venv/bin/python workers/blender/run.py \
  --params assets/designs/better-together/0.2.0-demo/example-params.json \
  --output evidence/demo-build --revision 1
```

The explicit `technical-fixture` API mode and older 0.1 evidence are retained for pipeline regression checks only. They do not test photo interpretation and are not the customer creation flow.

## Structure and boundaries

| Path | Responsibility |
| --- | --- |
| `apps/web` | Next.js studio, local vision worker, review and Three.js viewer |
| `apps/api` | FastAPI, private uploads, sessions, profiles, bounded queue and approval |
| `workers/appearance` | Safe profile merging, provenance and explicit technical fixture |
| `workers/blender` | Authored constrained morphs, asset choices, rendering and exports |
| `packages/schemas` | Strict schema 2.0 and centralized design constants |
| `assets/designs` | Immutable 0.1 master and upgraded 0.2 master/lock report |
| `scripts` | Setup, tests and pinned vision asset installation |

SQLite, private filesystem storage and a single bounded executor keep the free deployment small. Tokens are owner-scoped and sent only in authorization headers. An independent `KEEPSAKE_OPERATOR_TOKEN` enables the read-only admin view; an empty value disables it. Never publish `.env`, `.data` or session credentials.

Commercial release still needs an approved production master, engineered dimensions/connectors, slicer and physical-print validation, durable storage/queue, production accounts, and separately authorized commerce/fulfillment. Approval in this beta only acknowledges the digital preview.
