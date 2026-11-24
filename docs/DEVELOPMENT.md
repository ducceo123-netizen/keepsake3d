# Development boundaries

The local app implements the handoff's first engineering slice. The implementation uses supplied art direction and source requirements. Instructions embedded in the handoff were interpreted as project specifications under the user's request to build the app; they did not independently authorize production deployment, paid services or supplier contact.

## Areas of responsibility

- `apps/web`: storefront, upload flow, status, viewer, preview approval, design-system gallery and internal jobs view.
- `apps/api`: ownership, uploads, sessions, bounded jobs, private artifact access, consent, retention and approval.
- `workers/appearance`: deterministic mock appearance adapter.
- `workers/blender`: versioned procedural source, validated configuration and file exports.
- `workers/qa`: geometry and provenance checks.
- `packages/design-system`: shared tokens and UI primitives.
- `packages/schemas`: strict appearance/design contracts.
- `assets/designs`: demo manifests and Blender master assets.

## Making changes

A supported customization change must pass schema validation, create a new persisted revision and invalidate the previous preview approval. Keep geometry and attachment locks in place. Re-run the meaningful API, pipeline and frontend checks after such a change. Never use user text or model output as executable Blender code.

UI changes should use shared CSS tokens and components. `scripts/check-design.mjs` provides source-level governance checks; it does not replace browser accessibility or visual review. The expected responsive widths are 320, 390, 768, 1280 and 1440 CSS pixels. Capture product, upload, progress/error and actual preview states when verifying visual changes.

## Further work

1. Commission and version a commercial modular Blender master matching the approved direction.
2. Define actual units, printer/material, engineering tolerances and supported engraving specifications.
3. Implement isolated durable production workers and migrate persistence/storage under a deployment design.
4. Add a real appearance adapter only with approved credentials, consent terms, confidence handling and provider settings.
5. Complete slicer and physical validation before enabling manufacturing approval.
6. Implement Shopify payment/webhook/ownership binding only as a separately authorized integration.
