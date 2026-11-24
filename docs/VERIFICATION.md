# Verification ledger

Verified on 2026-11-24. This distinguishes executed checks, inspected live UI evidence, authored tests and remaining production gates.

## Executed automated checks

The root build agent ran the final combined API/pipeline suite, including the opt-in real Blender integration:

```bash
KEEPSAKE_RUN_BLENDER_TESTS=1 .venv/bin/python -m pytest tests/api tests/pipeline -q
```

**Result: 35 passed in 48.11 seconds**, with one upstream Starlette/httpx deprecation warning. This comprises 23 API tests, 11 pipeline tests and one actual Blender lifecycle integration. The integration creates two real revisions and verifies private artifact access, preview approval, correction, stale-approval rejection and deletion.

The root agent also completed these commands successfully:

```bash
npm run typecheck
npm run check:design
npm run build
```

The final Next.js 16.4.6 build includes `/`, `/studio`, `/design-system` and `/admin`. Source-tooling syntax checks also passed: `bash -n scripts/setup.sh scripts/dev.sh scripts/test.sh` and `node --check scripts/check-design.mjs`.

The pipeline agent built the default and alternate parameter fixtures with real Blender. Their provenance records show 26 locked mesh/anchor fingerprints preserved. The documentation check independently re-read the bundled default artifact files, recalculated their SHA256 values and matched them to the provenance record below.

## Live browser QA

The root agent used CUA against the running app and inspected the actual screenshots. This was live browser verification, separate from the unexecuted Playwright suite.

Observed successful paths:

- Synthetic sample upload → actual Blender preview → customer approval → correction of the sage outfit, right character's round glasses and name `Alex-J` → revision 2 ready. The earlier preview approval was reset.
- Front, reset and separated viewing controls; full-screen viewer; Escape dismissal returning keyboard focus to **Expand**.
- Operator authentication, display of three jobs and locking the operations view again.
- Malformed PNG rejection followed by successful sample-photo recovery.
- Storefront, upload and actual model preview at 320, 390, 768, 1280 and 1440 CSS pixels. All 15 final measurements report no horizontal overflow. The narrow upload grid was corrected before those final measurements.

The [responsive measurement record](../evidence/screenshots/responsive-checks.json) contains the final viewport and scroll-width values. This coverage does not establish complete WCAG conformance or a cross-browser audit.

### Inspected screenshots

| UI state | Evidence |
| --- | --- |
| Storefront | [Desktop hero](../evidence/screenshots/storefront-hero.jpg), [390px](../evidence/screenshots/storefront-390.jpg) |
| Upload | [320px](../evidence/screenshots/upload-320.jpg), [invalid image error](../evidence/screenshots/upload-error.jpg) |
| Processing | [Actual generation state](../evidence/screenshots/processing.jpg) |
| Model preview | [1440px](../evidence/screenshots/preview-1440.jpg), [320px](../evidence/screenshots/preview-320.jpg) |
| Approval and correction | [Approved preview](../evidence/screenshots/approved-desktop.jpg), [correction dialog](../evidence/screenshots/corrections.jpg) |
| Internal and component views | [Operations](../evidence/screenshots/operations.jpg), [design-system gallery](../evidence/screenshots/design-system.jpg) |

Additional captures for all measured widths are retained alongside these files.

## Bundled actual model artifacts

The default fixture is design `better-together:0.1.0-demo`, model revision 1, rendered with **Blender 4.5.16 LTS**. See the complete [provenance record](../evidence/demo-build/provenance.json) and [QA report](../evidence/demo-build/qa.json).

- Master SHA256: `94fa36d7aca0d4fee3f4242bcc42f190dbd0cf57866622ad687b4cc53d6eb3ba`
- Parameter SHA256: `8cb1765fcce2b1233796de6d5109e22a82e31a4a6f1b1022c8a2106206bd84af`
- QA outcome: `DEMO_GEOMETRY_CHECKED`; `print_approved: false`.

| File | Bytes | Verified SHA256 |
| --- | ---: | --- |
| [model.glb](../evidence/demo-build/model.glb) | 1,549,312 | `9b8dadbf7c23f43208348458f867359348c909e96bcf5e749df42c0105557df6` |
| [model.stl](../evidence/demo-build/model.stl) | 3,680,484 | `aff1de1bd1913555c6950b9ff01929879229f91a8ea608224753e2f498a39731` |
| [preview.png](../evidence/demo-build/preview.png) | 1,058,427 | `67a0fef651d9947f1d570bd37fd4d8685df14bf28200e042db03bb367c356003` |
| [qa.json](../evidence/demo-build/qa.json) | 14,101 | `34ab5a15c21746a1d62046b193bf2f48e006b4318ffe5d53bc3a851fc95eb141` |

GLB, STL and PNG originate from the same configured scene. STL contains geometry only. The demo uses unscaled scene units and overlapping mannequin components; it is not a fused, engineered production mesh. Connector fit, thickness and raised-name labels remain unvalidated for manufacturing. Slicer validation is explicitly `NOT_RUN` and physical validation is `NOT_APPROVED`.

## Authored browser suite: not executed

The 23 Playwright test definitions in `tests/web/` were **authored and TypeScript checked, but not run**. They cover responsive layouts, axe scans, upload validation, error/retry recovery, deletion races, four visual snapshots and an opt-in real Blender lifecycle. Their existence is not a passing browser-test result.

No Playwright screenshot baseline has been generated or accepted after visual review. The config uses `updateSnapshots: 'none'`, so missing baselines fail. On a configured machine, start with the functional subset:

```bash
npx playwright install chromium
npm run test:e2e -- --grep-invert @visual
```

To create baseline candidates separately:

```bash
npm run test:e2e -- --grep @visual --update-snapshots
```

Inspect every candidate at its actual dimensions, correct any defect and retain only reviewed files. This is an implementation quality check that an agent or developer can complete; it does not require a new user permission gate. Generating files alone is not visual review. Then run `npm run test:e2e` without updating. See [the browser-suite guide](../tests/web/README.md) for full setup, platform consistency and real-Blender opt-in commands.

## Acceptance coverage

| Handoff requirement | Current coverage |
| --- | --- |
| Runnable local first slice | Implemented and exercised with the synthetic fixture |
| Strict manifests, allowed parameters and mock appearance | Automated tests passed; no real photo analysis is claimed |
| Private uploads, metadata normalization and session ownership | API tests passed; malformed upload and recovery exercised live |
| Idempotency, bounded jobs and failure/cancellation handling | API tests passed for the single-process local implementation |
| Actual Blender GLB/STL/PNG and revision provenance | Generated, hash-verified and exercised through the API |
| Locked geometry and broken-geometry diagnostics | Pipeline tests passed for the procedural demo; manufacturing constraints remain pending |
| Revision-bound approval and corrections | Two-revision API integration and live browser flow verified |
| Shared design system and responsive UI | Source checks passed; gallery and 15 viewport measurements inspected |
| Keyboard/accessibility behavior | Live dialog focus behavior verified; automated axe/Playwright suite remains unrun; full WCAG audit pending |
| Visual regression coverage | Tests authored; no reviewed Playwright baselines yet |
| Container recipe | Provided but unverified because Docker was unavailable; Linux Blender is not bundled |
| Production master, print profile, slicer and physical sample | Pending external assets, engineering and physical validation |
| Real appearance provider | Pending approved provider integration, credentials and confidence/manual-review behavior |
| Shopify, paid-order binding and supplier fulfillment | Outside the implemented first slice; no live integration or production deployment |

## Environment and scope

The observed development environment supplied Node.js 24.14.1, npm 11.11.0 and Python 3.14. The renderer is a workspace-local Blender 4.5.16 LTS binary; the pipeline agent verified its official download SHA256. The source bundle includes the versioned demonstration master and generated evidence, not the Blender application. All 13 hashes in the supplied handoff manifest matched their extracted files.

No commercial master, physical print, engineered connector tolerance, verified engraving profile, slicer profile or live Shopify integration was supplied. The appearance provider remains deterministic and mocked, and the supplied concept image remains distinct from the actual procedural output. No production deployment or store change was made.

## Documented startup smoke check

The final source was also exercised using `bash scripts/setup.sh` (exit 0; npm installed 73 packages from the lockfile) and `bash scripts/dev.sh`. The combined launcher started both services successfully. The storefront returned HTTP 200 and the proxied health endpoint reported `status: ok`, `mode: local-demo`, `appearance_provider: mock-defaults-v1`, and `production_enabled: false`. The development processes were stopped after verification. Restart with `bash scripts/dev.sh` when opening the local application.

Raw final build/setup output is retained in `evidence/build-output.txt` and `evidence/setup-output.txt`.
