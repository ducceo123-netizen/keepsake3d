# Render deployment

The existing free service serves a Next.js static export, FastAPI and one bounded CPU Blender executor in a single Docker container. Photo analysis runs on the customer's device, so no inference service or paid API key is required.

| Setting | Value |
| --- | --- |
| App | https://keepsake3d-demo.onrender.com |
| Source | https://github.com/ducceo123-netizen/keepsake3d |
| Service | `srv-dc2pe6uk1f9s738nh7r0` |
| Blueprint | `exs-dc2pc2mk1f9s738nb4k0` |
| Plan / region | Free / Singapore |
| Dockerfile / context | `apps/api/Dockerfile` / repository root |
| HTTP health check | `/api/v1/health` |
| Auto-deploy | Off; public Git URL uses manual deployment |
| Storage | Ephemeral `/tmp/keepsake-data`; no paid disk |

The source repository is public at the user's request. The Render Git source was connected using **Public Git Repository**, without requiring the browser account to own the GitHub repository. Keep that existing service; do not create a duplicate Blueprint for each release.

## Build and deploy

1. Run the checks in [VERIFICATION.md](VERIFICATION.md), including actual browser inference and a real Blender lifecycle.
2. Commit and push the reviewed source to `main`.
3. In the service's **Deploys** page choose **Manual Deploy → Deploy latest commit**. Confirm that the new deploy references the intended commit.
4. Follow that deploy through `live`, then test the hosted photo workflow. A successful trigger or HTTP health response alone does not prove 3D generation works.

The Docker build installs exact npm dependencies, downloads checksum-pinned official MediaPipe models/runtime, exports the static site and includes pinned Linux Blender 4.5.16. The image runs a genuine Blender export smoke test before publishing. The runtime is nonroot and serves one origin, with no Node server. WebAssembly execution is permitted by a narrow CSP directive; models and workers load only from the app's own origin. Public model assets are cached with revalidation; private API/photos/artifacts remain `no-store`.

## Runtime and limits

The checked-in `render.yaml` is the source of truth. It uses one active build, two total pending slots, one Blender thread, 512-pixel/8-sample CPU renders with denoising disabled, a 900-second Blender timeout and a 1000-second parent timeout. The API process must remain single-instance/single-worker because SQLite and the executor are local. Render's public hostname/origin are included explicitly; forwarded headers do not bypass per-socket limits.

`KEEPSAKE_OPERATOR_TOKEN` is a separate Render-generated secret. It is not needed for customer generation; do not expose it in client bundles, commands, logs or Git. No photo-provider key is needed.

This free service sleeps when idle and has limited CPU/memory. Generation can take minutes. Every deploy or restart may remove photos, appearance profiles, generated files and approvals before the configured 24-hour expiry. Download wanted artifacts promptly. Persistent customer records, a durable queue, managed storage and production accounts require a separately planned infrastructure change. No paid resources are created by this release.

See Render's current [deploy lifecycle](https://render.com/docs/deploys), [health checks](https://render.com/docs/health-checks) and [free service limits](https://render.com/docs/free) before changing infrastructure.

## Verify a release

- Confirm `/api/v1/health` reports the new design and `browser-mediapipe-v1`, with production disabled.
- Open `/studio/`, upload two public-domain test portraits, analyze them in the actual browser, choose distinct faces and review the details.
- Generate and download the real GLB/PNG/provenance, compare artifact checksums and profile binding, and inspect the model.
- Approve, make a correction, regenerate, and verify stale approval is rejected.
- Check invalid/no-face feedback, owner isolation, mobile layout and deletion of the disposable test session.
- Inspect the specific deploy/runtime logs if generation fails or the service restarts.

`python3 scripts/smoke-deployment.py URL --generate` is only an explicit technical-fixture pipeline check. It does **not** replace the real-photo browser test.

Actual deployment evidence is recorded in [VERIFICATION.md](VERIFICATION.md). The historical 0.1 hosted log is retained in `evidence/render-live-verification.txt` and must not be mistaken for evidence of photo interpretation.

GitHub Actions is not enabled: the existing publishing token lacks `workflow` scope. The checked-in `docs/ci/github-actions-checks.yml` is a template, not a running check. Local verification and the Docker build smoke are the executed paths. The optional Compose recipe has not been exercised in this environment.
