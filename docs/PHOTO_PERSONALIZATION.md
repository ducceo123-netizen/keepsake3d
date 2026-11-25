# Photo personalization — version 0.2

The initial 0.1 demo ignored uploaded photos when selecting appearance. Version 0.2 replaces that customer path with actual on-device analysis and a required review. It produces a constrained stylized figurine, not a face scan, photorealistic reconstruction or exact likeness.

## What the customer does

1. Upload 1–3 consented JPEG/PNG/WebP reference photos.
2. Confirm permission and click **Analyze photos**. Models load from this app's own origin. No image is sent to an external AI service and no API key is needed.
3. Choose a distinct detected face for **Left character** and **Right character**. There is no automatic person matching across photos and neither slot is preselected.
4. Check suggested colors and choose hair style, facial hair, glasses, trousers and shoes. Optionally adjust bounded face controls. Confirm the review, then build.
5. Inspect the real GLB/rendered image. Corrections create another revision; approval is bound to the current model checksum.

## Measured, defaulted and reviewed fields

MediaPipe Face Landmarker 1.2.3 supplies 478 landmark points; its expression coefficients are not identity morphs. The authored mapping uses visible 2D ratios for face width/height, jaw, chin, eye spacing/size, nose width and mouth width. Smile uses expression coefficients. Ratios are measured in pixel coordinates so image aspect ratio is respected; roll is removed for the yaw proxy. Every resulting morph is finite and clamped to [-1,1]. The mapping is an artistic calibration, not a validated likeness metric.

A CPU Selfie Multiclass Segmenter separates hair, face skin and clothing within each selected head/upper-torso region. Neighboring face midpoints limit cross-person color contamination. High-confidence region samples are reduced to a median color and matched to authored sRGB palettes in Lab space. These are **suggestions**: lighting, hats, collars, patterned clothes and occlusion can lead to an unsuitable color. Fewer than 30 confident samples leave a disclosed default. The customer reviews every result.

Hair silhouette, facial hair, glasses, pants and shoe colors are not automatically classified. Cheek volume, brow thickness/arch and nose depth start at neutral sculpted defaults. These controls remain editable, with overrides recorded separately from measured fields. The master preserves the pose, bodies, hands, contact anchors and puzzle base. Source 0.1 assets remain intact; design 0.2 has its own master hash and migration report.

## Failure handling and privacy

No detected face, a very small face, excessive side turn/roll or a cropped face requires a better photo. A failed/unsupported/slow browser analysis reports an error; it never silently substitutes sample characters. The analysis runs in a module Web Worker and releases the detector/segmenter before the 3D viewer starts. First loading is approximately 35 MB before compression. Modern WebAssembly, Web Workers and OffscreenCanvas support is required; the automated runtime evidence is Chromium, not an all-device certification.

The server normalizes uploads and returns a checksum. The browser verifies those exact bytes before measuring. Only bounded appearance values, quality measurements and explicit assignments are persisted; raw landmarks, face embeddings and thumbnail crops are not sent back. Browser measurements are untrusted customization input, not server-certified evidence or identity verification. The API checks ownership, source photo checksums, distinct selected faces, review/consent and schema bounds. Immutable profile revisions and their hashes are bound into build provenance.

Photos and derived files remain owner-only. The current Render free service is ephemeral: a restart or deployment may clear sessions before their 24-hour expiry. This is still a beta without checkout, print approval, durable storage or production accounts.

## Reproducible evidence

- `node scripts/install-vision-assets.mjs --fixtures`: verified official models/runtime plus public-domain test portraits.
- `node scripts/test-vision.mjs`: actual CPU WASM, two different portraits, blank-image rejection, background/color perturbations, bounded output, UI-thread responsiveness and no external requests.
- `npm run test:e2e -- --grep-invert @visual`: functional UI tests; persistence stubs are explicitly confined to test fixtures.
- `KEEPSAKE_RUN_WEB_BLENDER_TESTS=1 npm run test:e2e -- tests/web/blender-lifecycle.spec.ts`: opt-in real uploads → browser inference → API review → Blender → approval/correction lifecycle against running local services.
- `KEEPSAKE_RUN_BLENDER_TESTS=1 .venv/bin/python -m pytest tests/api tests/pipeline -q`: API, provenance and geometry checks, including actual exports.

See [third-party licenses](../THIRD_PARTY_NOTICES.md), [actual vision evidence](../evidence/vision-browser-verification.json) and the [verification ledger](VERIFICATION.md). Public-domain portrait fixtures are test-only; their subjects do not endorse this application.
