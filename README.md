# Keepsake 3D — Better Together

A photo-personalized, stylized couple figurine studio built from the supplied Keepsake3D handoff. The customer uploads photos, runs private on-device face analysis, explicitly assigns two faces, reviews appearance, then receives real Blender GLB/STL/PNG files and revision-bound approval.

[Open the Render studio](https://keepsake3d-demo.onrender.com/studio/) · [Public source](https://github.com/ducceo123-netizen/keepsake3d)

## What changed in version 0.2

The original demo used fixed appearance settings and did not interpret photos. The new customer flow uses actual MediaPipe face landmarks and segmentation in a CPU Web Worker. Bounded face proportions and suggested hair/skin/top colors affect the 3D scene. Hair style, facial hair, glasses and other clothing choices require review. Missing or unusable faces produce actionable feedback; there is no silent mock fallback.

All models are pinned, verified and self-hosted. Photos never go to an external AI provider and no paid API key is needed. The server checks photo ownership/checksums and bounded parameters, and retains immutable appearance profiles tied to artifact provenance. Browser inference is customization input, not biometric authentication or independently verified server evidence.

The result is a stylized interpretation with a fixed body, pose and puzzle base. It does not guarantee exact likeness or reproduce the concept illustration. The beta has no checkout or manufacturing approval. The current free Render service has temporary storage; restarting or redeploying may clear sessions and files before their 24-hour expiry.

Read [photo personalization and its limits](docs/PHOTO_PERSONALIZATION.md), [API contract](docs/API.md), [verification](docs/VERIFICATION.md) and [Render deployment](docs/DEPLOY_RENDER.md).

## Run locally

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
