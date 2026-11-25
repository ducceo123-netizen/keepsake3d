# Real browser inference tests

Run from the repository root:

```sh
npm ci
node scripts/install-vision-assets.mjs --fixtures
npx playwright install chromium
node scripts/test-vision.mjs
```

This starts an isolated local static server, uses headless Chromium and the actual pinned CPU WebAssembly models in a module Web Worker, and closes both browser and server after testing. There is no model/API mock, API key, customer data, GPU service or external photo transfer. All runtime requests must remain on the test server's origin. The test server applies a CSP allowing WebAssembly compilation with `wasm-unsafe-eval`, without generic JavaScript `unsafe-eval`.

It checks the application's actual worker as well as both model APIs: distinct faces change bounded morphology; a blank photo produces no candidate; a distant background color change preserves sampled palettes; a color transformation changes palette suggestions while keeping similar proportions; and the page event loop remains responsive. All 22 browser palette swatches must equal the authored Blender manifest swatches. A successful run writes `evidence/vision-browser-verification.json` with measurements and the exact result, without image bytes or raw landmarks.

Fixtures are downloaded with SHA-256 validation and excluded from Git and the public app. Sources and rights are recorded in `THIRD_PARTY_NOTICES.md`. Keep fixture binaries out of the customer-facing public directory.

The model loader in MediaPipe 1.2.3 clears `globalThis.ModuleFactory` after creating each task. A module worker must restore the imported factory before each `createFromOptions`; otherwise the second model fails because repeated ES-module imports do not rerun initialization. Tests exercise both models in the same worker.

The model and runtime downloads total about 35.3 MB before HTTP compression. Browser RAM is additional and device-dependent. Run analysis off the UI thread, downscale input, release masks/bitmaps and terminate the worker on completion/cancellation. CPU browser inference does not consume the Render service's model-inference memory.
