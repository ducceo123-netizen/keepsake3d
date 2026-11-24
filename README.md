# Keepsake 3D — Better Together

A photo-to-3D engineering demo built from the supplied Keepsake3D handoff. The storefront uses the supplied concept art and shared Soft Keepsake Editorial design system. The working path is private image upload (or synthetic fixture), deterministic **mock** appearance parameters, a procedural Blender model, genuine GLB/STL/PNG artifacts, geometry diagnostics and revision-bound customer preview approval.

The concept image is not the generated mesh. The procedural couple is a test asset, not the commercial Better Together product. No exact likeness, engineered connector, physical sample, price, delivery promise or production approval is represented. Checkout and supplier fulfillment are not enabled.

## Live demo and source

Open [Keepsake 3D on Render](https://keepsake3d-demo.onrender.com) or browse the [public GitHub repository](https://github.com/ducceo123-netizen/keepsake3d).

Render reports the free Singapore deployment **Live**, built from commit `ee604afa958a3ad281bb22a5ce56c34b072330de`. The Linux image build completed an actual Blender smoke build; the hosted homepage and studio opened without JavaScript errors. The hosted lifecycle check passed two real Blender revisions, artifact hashes, owner authorization, preview approval, stale-approval rejection and session cleanup. [Live verification log](evidence/render-live-verification.txt).

The hosted browser workflow also passed actual generation, interactive 3D/full-screen controls and preview approval without browser errors. This free demo uses temporary storage: sleeping, restarting or redeploying the service can clear sessions and files. Appearance analysis is mocked and checkout is disabled. Use **Try a sample photo** to explore it. See [deployment details and verification](docs/DEPLOY_RENDER.md).

## Run locally

The same source runs locally with the commands below. The Render [Blueprint](render.yaml) builds a single container that serves the static interface and API together and includes pinned Linux Blender.

Requirements: Node.js 22+ (24 recommended), Python 3.11+ (3.14 used during development), and Blender 4.5 LTS for actual model generation. Python and Node dependencies are pinned by the checked-in requirements and npm lockfile. No paid keys or cloud account are required.

From this directory:

```bash
bash scripts/setup.sh
```

Edit `.env` and set `BLENDER_BIN` to your installed Blender executable if it is not on PATH. On macOS, for example:

```dotenv
BLENDER_BIN=/Applications/Blender.app/Contents/MacOS/Blender
```

A development copy under the surrounding workspace's `work/tools/blender/Blender.app/Contents/MacOS/Blender` is also auto-detected when present. That portable binary is not part of the app source bundle. To obtain Blender on another machine, use the [official Blender downloads](https://www.blender.org/download/). The pipeline reports an explicit error when Blender is unavailable; it does not substitute fabricated artifacts.

Start the app and API together:

```bash
bash scripts/dev.sh
```

Open [the local storefront](http://127.0.0.1:3000). The development gallery is at [/design-system](http://127.0.0.1:3000/design-system). Interactive API documentation is at [FastAPI docs](http://127.0.0.1:8000/docs); the implemented routes and request shapes are documented in [API.md](docs/API.md). Press Ctrl-C to stop both services.

Use **Create Your Keepsake** and **Try a sample photo** for an end-to-end demo without personal photos. Choose names, give the displayed consent, generate a preview and wait for the real background job. The preview shows the actual model revision and allows supported corrections. Each parameter change generates a new revision; retrying identical parameters preserves that revision and records another attempt. Customer approval acknowledges the preview only.

### Separate processes

```bash
# Terminal 1, project root
set -a
source .env
set +a
.venv/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

# Terminal 2, project root
npm run dev
```

The web app proxies `/api/v1` to port 8000. `API_ORIGIN` can override that target when starting Next.js. Owner tokens are sent through authorization headers, not public artifact URLs. Private data defaults to `.data/private` and is ignored by Git.

## Reproduce the 3D build directly

```bash
# Export BLENDER_BIN first if Blender is not discoverable.
.venv/bin/python workers/blender/run.py \
  --params assets/designs/better-together/0.1.0-demo/example-params.json \
  --output evidence/demo-build \
  --revision 1
```

The build emits the model, geometry-only STL candidate, rendered PNG, `provenance.json` and `qa.json`. Provenance ties the files to one master, parameter set and revision; SHA256 values can be rechecked locally. QA findings are engineering diagnostics, not evidence of physical validation. Geometry colors shown in GLB/PNG are not embedded in STL.

## Checks and evidence

The original local combined API/pipeline run passed **35 tests**, including two real Blender revisions. TypeScript, design governance and the Next.js 16.4.6 production build passed. Live CUA browser QA verified upload, generation, approval, corrections, model controls and operations; storefront/upload/preview had no horizontal overflow at 320, 390, 768, 1280 and 1440 pixels.

```bash
bash scripts/test.sh
# Include the actual Blender lifecycle integration:
KEEPSAKE_RUN_BLENDER_TESTS=1 .venv/bin/python -m pytest tests/api tests/pipeline -q
npm run build
```

See [the verification ledger and acceptance matrix](docs/VERIFICATION.md) for exact results, limitations, artifact hashes and inspected screenshots. The public source includes the low-resolution fixture’s [rendered model](evidence/render-budget-build/preview.png), [GLB](evidence/render-budget-build/model.glb), [STL candidate](evidence/render-budget-build/model.stl), [provenance](evidence/render-budget-build/provenance.json) and [QA report](evidence/render-budget-build/qa.json).

The 23 Playwright definitions are authored and TypeScript checked, **not executed**. Their screenshot baselines have not been generated or reviewed. Start with the functional subset, which does not require baselines:

```bash
npx playwright install chromium
npm run test:e2e -- --grep-invert @visual
```

Generate visual baseline candidates separately:

```bash
npm run test:e2e -- --grep @visual --update-snapshots
```

Inspect and correct every candidate before retaining it as a baseline; an agent or developer can complete this implementation check. Generation alone does not constitute review. Then run `npm run test:e2e` without updating. The default config fails missing baselines. Full instructions, including the opt-in real browser/Blender lifecycle, are in [the browser-suite guide](tests/web/README.md).

## Optional container recipe

Render successfully built the single-service Docker image, including its Linux Blender export check. The optional `docker-compose.yml` provides a separate local web/API development layout using that image; its configuration was updated and YAML-checked, but Compose itself has **not** been run. Its API uses temporary `/tmp/keepsake-data` storage. Use the native commands above for the locally verified startup path.

## Architecture and project layout

| Directory | Responsibility |
| --- | --- |
| `apps/web` | Next.js/TypeScript storefront, upload, viewer, approval and component gallery |
| `apps/api` | FastAPI, private uploads, ownership, sessions, scheduling and revision approval |
| `workers/appearance` | Deterministic mock provider with explicit demo defaults |
| `workers/blender` | Checked-in procedural master and constrained exports |
| `workers/qa` | Geometry and provenance diagnostics |
| `packages/design-system` | Shared semantic tokens and UI primitives |
| `packages/schemas` | Strict appearance/design validation contracts |
| `assets/designs` | Versioned demo manifest, parameters and master |
| `docs/adr` | Decisions and scoped deviations from the suggested stack |

The local demo uses SQLite, private filesystem storage and a bounded background executor. It does not run Postgres/Supabase or Redis/Celery. See [ADR 0001](docs/adr/0001-local-vertical-slice.md) for why and for deployment implications. Shared semantic CSS and Radix primitives implement the brand without a Tailwind/shadcn layer; see [ADR 0004](docs/adr/0004-shared-ui-primitives.md).

## Local privacy and operator access

Uploads are validated and normalized to remove metadata. The API checks session ownership for each private photo, status and artifact read. Consent is required to submit a build. Retention defaults to 24 hours and is configurable; cleanup runs while the local service is operating. Stopping the service also stops automated cleanup. The synthetic fixture should be used for routine testing.

Set an independent, long random `KEEPSAKE_OPERATOR_TOKEN` in `.env` to enable the local read-only [operations view](http://127.0.0.1:3000/admin). Leaving it blank disables operator access. This is development access control, not a complete production account system. Never publish `.env`, session credentials or `.data`.

## Remaining commercial gates

- Professionally authored and approved modular Blender master, with engineered locks and feature envelopes.
- Verified dimensions, printer/material and text/connector constraints; slicer and physical sample validation.
- Real appearance provider with approved credentials, confidence/manual-review behavior and processor terms.
- Durable production queue, isolated render workers, account authentication, managed storage and scheduled deletion.
- Separately authorized Shopify integration, payment verification, production approval and supplier workflow.

The engineering demo is deployed on Render. Commercial manufacturing, Shopify checkout and supplier fulfillment remain disabled. See [development notes](docs/DEVELOPMENT.md) and [model provenance decision](docs/adr/0002-model-provenance.md).

On macOS, `Start Keepsake3D.command` is a convenience launcher for the same setup/dev commands. The verification server was stopped after testing; start the local app when you want to use it.
