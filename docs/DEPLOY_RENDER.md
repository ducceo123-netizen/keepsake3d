# Render deployment — free engineering demo

This configuration deploys one Docker web service: a Next.js static export is built into the image and served by FastAPI, alongside the existing procedural Blender worker. The browser and API share one origin. There is no Node.js server, second service, database service or paid disk in the running deployment.

The included `render.yaml` explicitly selects `plan: free` in Singapore and disables automatic deploys. It is deployment configuration, not proof of a live or successfully verified deployment. Confirm the actual Render deploy status and run the checks below before reporting success.

GitHub Actions is not enabled in this repository. The authenticated GitHub connection can publish source but lacks the separate `workflow` scope. A ready workflow template is retained at `docs/ci/github-actions-checks.yml`; local checks and the Docker image's real Blender build check remain available without expanding that connection's permissions.

## Deploy from the private source repository

Connect Render to the Git provider account that owns this repository. In the Render dashboard, use **New → Blueprint**, choose the repository and branch, and select the root `render.yaml`. Review the service definition, including the explicitly free compute plan, then deploy. Render can manage the declared Docker service from this Blueprint. See [Render Blueprints](https://render.com/docs/infrastructure-as-code) and the [Blueprint reference](https://render.com/docs/blueprint-spec).

If creating a service directly through the dashboard or API instead of a Blueprint, mirror these values:

| Setting | Value |
| --- | --- |
| Service type | Web service |
| Runtime | Docker |
| Compute plan | `free` |
| Region | `singapore` |
| Dockerfile | `./apps/api/Dockerfile` |
| Build context | Repository root (`.`) |
| Health check | `/api/v1/health` |
| Environment | Copy the entries from `render.yaml` |
| Persistent disk | None |
| Automatic deploys | Off; deploy each reviewed source update deliberately |

The container must listen on `0.0.0.0:$PORT`; this Blueprint sets port 10000. Use the checked-in Docker startup path, with a single Uvicorn process. Render exposes one public HTTP port and terminates HTTPS at its load balancer. [Web service documentation](https://render.com/docs/web-services)

Keep the source repository private. A public Git URL is an alternative source path when a repository is intentionally public; it does not provide provider-authenticated automatic deploys. For an owned repository, Render recommends its linked Git-provider path. A prebuilt container is another option: Render accepts reachable public images or supported private registries, and requires **Linux/amd64** images, with compressed size at most 10 GB. Image tags do not trigger automatic redeploys; use a specific digest and deploy it deliberately. [Git source options](https://render.com/docs/web-services), [prebuilt-image requirements](https://render.com/docs/deploying-an-image)

Do not copy `.env`, `.data`, local session tokens, the macOS Blender application, Python virtual environments or Node dependencies into the source repository or Docker build context. The Dockerfile builds its own dependencies and downloads the compatible Linux renderer.

## Runtime settings

The Blueprint contains the agreed low-resource settings:

| Variable | Value and purpose |
| --- | --- |
| `KEEPSAKE_WEB_DIR` | `/app/public`: immutable static frontend |
| `KEEPSAKE_DATA_DIR` | `/tmp/keepsake-data`: temporary private database, photos and model outputs |
| `KEEPSAKE_DEPLOYMENT_MODE` | `public-demo`: hosted-demo behavior |
| `KEEPSAKE_STORAGE_MODE` | `ephemeral`: accurate storage messaging |
| `KEEPSAKE_RETENTION_HOURS` | `24`: maximum configured session lifetime, not a durability guarantee |
| `KEEPSAKE_BUILD_WORKERS` | `1`: one active model build |
| `KEEPSAKE_MAX_PENDING_BUILDS` | `2`: total accepted slots including the running build |
| `KEEPSAKE_BUILD_TIMEOUT_SECONDS` | `1000`: outer API job timeout |
| `KEEPSAKE_MAX_STORAGE_MB` | `512`: private storage quota |
| `KEEPSAKE_MAX_SESSIONS` | `100`: service session cap |
| `KEEPSAKE_MAX_BUILDS_PER_HOUR` | `30`: service build-rate cap |
| `BLENDER_THREADS` | `1` |
| `BLENDER_RENDER_RESOLUTION` | `512` square render |
| `BLENDER_RENDER_SAMPLES` | `8` |
| `BLENDER_DENOISE` | `0`: disabled for the free demo |
| `BLENDER_TIMEOUT_SECONDS` | `900`: renderer timeout, shorter than the outer job timeout |

`KEEPSAKE_OPERATOR_TOKEN` is generated as a Render secret. Retrieve it through authorized Render environment settings when operator access is needed; do not place it in the repository, URL, frontend bundle or logs. Leaving this variable unconfigured disables operator access. The API derives its allowed public origin/host from Render's supplied URL/hostname when an explicit override is absent.

The lower render settings change image quality and timing. They do not authorize production or change the demo's locked geometry. Appearance extraction remains mocked. The GLB, STL and PNG still must share a configured scene and valid provenance.

## What the free deployment can and cannot preserve

Render's free web-service compute is **0.1 CPU and 512 MB RAM**. It sleeps after 15 minutes without inbound traffic, can take about a minute to wake, and can restart at any time. Local SQLite records, uploads and generated files disappear on restart, redeploy or idle spin-down. Free services cannot attach persistent disks or provide shell/SSH access. Workspace usage includes 750 free instance hours per month; builds and bandwidth also count against workspace quotas, with documented billing or suspension behavior. [Free-service limits](https://render.com/docs/free), [compute plans](https://render.com/docs/compute-plans)

This is a disposable demonstration. Use the synthetic fixture for deployment checks and download desired artifacts promptly. “Up to 24 hours” describes the configured deletion deadline; a Render restart may remove a session much sooner.

One render thread, one active build, reduced image resolution and disabled denoising lower resource demand. A local macOS arm64 measurement of the low-resolution pipeline took 14.16 seconds with peak worker-plus-Blender descendant RSS of 157.45 MiB; this excludes the API process. The measurement is recorded in [resource-measurement.json](../evidence/render-budget-build/resource-measurement.json). These observations do **not** establish that Blender will fit within 512 MB on Render. Linux peak RSS and CPU throttling must be measured from the actual deployment; macOS render logs are not equivalent. A killed or timed-out worker must surface an actionable failure, not a fabricated preview. The app's CPU rendering can still take minutes on a 0.1-CPU instance.

## Verify the live service

After Render reports a successful deploy:

1. Request `/api/v1/health`; confirm the deployment/storage modes and disabled production behavior.
2. Open `/`, `/studio`, `/design-system` and `/admin` directly, then reload each path to test static routing.
3. Use the synthetic photo, consent and names; generate a real preview, inspect it and download GLB/provenance. Confirm artifact hashes and the model revision.
4. Approve the preview, make a supported correction and verify that the new revision requires a new approval.
5. Check a rejected invalid image, owner-only access and session deletion. Confirm no public static path exposes private data.
6. Inspect Render logs for out-of-memory exits, renderer errors and timeouts. A healthy HTTP endpoint alone does not prove Blender completed.
7. Check the hosted disclosure that sessions are ephemeral. Recheck mobile layout after static export.

This guide does not assert these hosted checks have passed. Record the live URL, deploy ID, source commit and observed results after they have actually completed.

Run the repeatable synthetic lifecycle check against your deployment:

```bash
python3 scripts/smoke-deployment.py https://YOUR-SERVICE.onrender.com --generate
```

It tests static routes, private-path isolation, owner authorization, two actual Blender revisions, artifact hashes, approval and stale-approval rejection, then deletes its disposable session. It never prints the session token. The same single-service path passed locally on macOS before deployment; that is not a hosted Linux verification.

## Optional upgrade for durable demo sessions

The prepared Blueprint does not purchase or create paid resources. If a durable demonstration is wanted later, a reasonable starting point to benchmark is the current **`1c-2g`** plan (1 CPU, 2 GB RAM), with one instance and a small persistent disk. This is an engineering recommendation, not a measured capacity guarantee. Current Render references list that compute size at $25/month and disks at $0.25/GB/month, so 1 GB would make the baseline approximately $25.25/month before other applicable usage. Recheck the account's quoted price before selecting it. [Current compute plans](https://render.com/docs/compute-plans), [Render hosting prices](https://render.com/hosting/docker), [storage pricing](https://render.com/pricing)

For that optional topology, mount a disk at `/var/data` and set `KEEPSAKE_DATA_DIR=/var/data/keepsake`, update the storage-mode disclosure and ensure the nonroot container user can write the mount. The disk must be initialized at runtime: Render does not expose it during image builds or pre-deploy commands. A disk can belong to only one service instance, prevents horizontal scaling, and introduces a short interruption on deploy. Keep the API and its local Blender executor together; a separate worker cannot read this disk. A durable production architecture would instead migrate to a real queue, database and private object storage. [Persistent disk constraints](https://render.com/docs/disks)

A split frontend/private-API topology is possible in a later revision. Services must be in the same region. Free web services can send private-network requests to paid services but cannot receive them; a private API requires paid compute. The current single-service static export avoids this wiring entirely. [Private networking](https://render.com/docs/private-network), [private services](https://render.com/docs/private-services)
