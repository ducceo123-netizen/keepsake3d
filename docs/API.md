# Local API contract

The running service publishes its complete generated schema at `http://127.0.0.1:8000/openapi.json` and interactive documentation at `http://127.0.0.1:8000/docs`.

All routes below use the `/api/v1` prefix. The Next.js development app proxies that prefix to the API, so browser calls use the same web origin.

## Session and file ownership

`POST /customization-sessions` accepts `{"design_id":"better-together","design_version":"0.1.0-demo"}` and returns a new `id`, opaque `token`, state, revision and expiry/retention information. Save the token privately. Each subsequent session route requires `Authorization: Bearer <token>` for the session owner. The token is not a public download URL or an operator credential.

| Method and route | Purpose |
| --- | --- |
| `GET /health` | Local demo health and enabled-mode information |
| `GET /designs` | Available demo designs |
| `GET /designs/better-together` | Current strict demo manifest |
| `POST /customization-sessions` | Create an owner session |
| `POST /sessions/{id}/photos` | Multipart upload, field name `file` |
| `POST /sessions/{id}/fixture` | Add a synthetic reference with no real people |
| `GET /sessions/{id}/photos/{photo_id}` | Read a private normalized photo |
| `DELETE /sessions/{id}/photos/{photo_id}` | Remove a photo before generation |
| `POST /sessions/{id}/submit` | Consent and submit/retry a build |
| `GET /sessions/{id}/status` | Current state, parameters, artifacts, QA, history and error |
| `GET /sessions/{id}/preview` | Alias of the current status response |
| `POST /sessions/{id}/corrections` | Validate supported changes and build a model revision |
| `POST /sessions/{id}/approve` | Approve the specified preview revision/checksum |
| `GET /sessions/{id}/artifacts/{artifact_id}` | Read an owner-authenticated model/render/report file |
| `DELETE /sessions/{id}` | Delete session data and cancel associated local work |
| `GET /admin/jobs` | Read recent jobs using the separate configured operator token |

There is no public production approval, checkout, payment or supplier export endpoint in this slice.

## Submission and corrections

Submission requires an `Idempotency-Key` header (8–128 ASCII characters) and a JSON body such as:

```json
{"consent":true,"names":["Alex","Jamie"]}
```

The same key with the same request identifies the existing work. Reusing a key with different input is rejected. A deliberate retry uses a new key. Retry limits and bounded worker capacity prevent unbounded render jobs.

Corrections also require an idempotency key. The body contains only whitelisted values, for example:

```json
{"characters":{"left":{"hair_style_asset_id":"bun","outfit_palette_id":"sage"}}}
```

The full supported enums are in `packages/schemas/models.py` and the generated OpenAPI document. The demo allows up to 12 ASCII letters, spaces or hyphens for names. It has no authored face morphs, so nonempty face morph data is rejected. User text and appearance parameters never become executable Blender code.

## Status and approval

A status response includes `state`, `revision`, `job_id`, `photos`, `params`, `artifacts`, `qa`, `checksum`, `history` and `expires_at`. Failure information uses **`error: {"code":"...","message":"..."}` or `null`**, not a plain string. The frontend must render `error.message` and preserve a recovery path.

Each artifact descriptor has a protected `url`, `kind`, SHA256, revision and provenance metadata. Fetch it with the same owner authorization, then use a browser object URL if required by the viewer. The API does not serve raw photos or generated files from a public static folder.

Approval binds both fields from the current ready status:

```json
{"model_revision":1,"job_checksum":"<64-character checksum returned by status>"}
```

A stale revision/checksum is rejected. Approval updates only the customer's digital-preview state. The response continues to identify the quality level as `DEMO` and `production_approved` as `false`.

## Upload and retention limits

Uploads support still JPEG, PNG and WebP images, up to 10 MB each and at most three photos per session. Decoded dimensions must be 64–6000 pixels per side and no more than 20 megapixels. The server checks file signatures and decoded image data, and stores a normalized PNG without EXIF metadata.

`KEEPSAKE_RETENTION_HOURS` defaults to 24 and is clamped by the local service to 1–168 hours. The create/status responses provide session expiry. Cleanup runs at startup and periodically while the service runs. `DELETE /sessions/{id}` is the immediate removal action. These local limits are not a production privacy/retention service.

## Operator access

`GET /admin/jobs` requires `Authorization: Bearer <KEEPSAKE_OPERATOR_TOKEN>`. The endpoint is disabled when that environment variable is empty. Its token is independent from customer ownership. The response contains recent job metadata and `production_enabled: false`.
