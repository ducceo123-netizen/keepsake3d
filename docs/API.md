# Photo personalization API

The current contract is design `better-together:0.2.0-demo`, parameter schema `2.0`. Central identifiers and supported values live in `packages/schemas/constants.py`; generated JSON Schemas are in `packages/schemas/`. Local OpenAPI is `/openapi.json` and `/docs` when documentation is enabled. Public-demo deployments disable documentation by default.

All routes below use `/api/v1`. Normal photo submission requires a reviewed, immutable appearance profile. It never silently substitutes mock appearances.

## Ownership and photo inputs

`POST /customization-sessions` accepts `{}` or the explicit current design ID/version. It returns an opaque `id`, one-time `token`, state, revision, and expiry. Every subsequent session, photo, profile, and artifact route requires `Authorization: Bearer <token>`. Keep the token out of URLs, telemetry, and logs.

Upload one to three still JPEG, PNG, or WebP files with `POST /sessions/{id}/photos`, multipart field `file`. Responses and the session status include each normalized photo's `id`, `sha256`, width, height, and authenticated `url`. Fetch this normalized private PNG with the same token and give its blob to the browser analysis worker; do not analyze the original upload and then claim its pixels match the normalized image hash.

Images are limited to 10 MB, 64–6000 pixels per side, and the configured decoded pixel ceiling (8 MP in public mode; 20 MP locally unless overridden). The stored PNG has EXIF removed and is resized to at most 2048 pixels on its longest side. Two concurrent HTTP uploads, bounded decoding, and request size/time limits protect the demo instance.

## Analyze, assign, review, then generate

1. After explicit local-processing consent, the browser runs self-hosted MediaPipe model/WASM assets on the private photo blob. There is no external AI photo request.
2. The shopper explicitly selects the face assigned to the left figurine and the face assigned to the right figurine. Different photos can each contain one selected face. The server does not identify people or match their identity across photos.
3. The browser shows detected details and warnings for review. Unsupported or unreliable details remain declared defaults or explicit manual choices. Heuristic quality is not a calibrated model probability.
4. Save the reviewed appearance using `POST /sessions/{id}/appearance-profile`.
5. Submit its returned ID and SHA256 using `POST /sessions/{id}/submit`.

The profile input is described completely by `packages/schemas/appearance-profile.schema.json`:

| Field | Contract |
| --- | --- |
| `source` | Exactly `browser-mediapipe-v1` |
| `analysis_version` | `1.0` |
| `consent`, `reviewed` | Both explicitly `true` |
| `assignments.left`, `assignments.right` | Each has `photo_id`, `photo_sha256`, `face_index`, `face_count`, and `box: [x, y, width, height]` |
| Face assignment | Photo belongs to this session and SHA matches stored pixels; index is within a nonzero face count; slots select distinct faces; normalized box fits the image and is at least 24 pixels in each dimension |
| `parameters` | Complete schema-2.0 `{schema_version, characters: {left, right}}`; every character field and all 13 face controls are explicit |
| `observations.left`, `observations.right` | Bounded numeric `measurements`, required `observed_fields`, optional `defaulted_fields`, `manual_fields`, and bounded warning strings |
| `confidence` inside observations | `low`, `medium`, `high`, or absent/null; its basis is `heuristic-quality-not-model-probability` |
| Appearance field names | Character field names such as `hair_color_id`, or a specific control such as `face_morphs.face_width` |
| `manual_overrides` | `{characters: {left?: <partial character>, right?: <partial character>}}`; supplied choices must match the final reviewed parameters |

The server rejects missing selections, absent faces, unreviewed input, unknown geometry controls, nonfinite numbers, out-of-range morphs, mismatched photo hashes, and raw landmark arrays. Omitted reviewed parameters are not silently defaulted. It records all fields not observed or manually chosen as defaults. Client-supplied analysis remains **untrusted customization input**: validation does not prove that the browser actually ran inference or establish likeness accuracy.

A successful profile response includes `id`, `revision`, `sha256`, `parameters`, assignments, observations, default/manual attribution, consent policy, and `external_transfer: false`. Identical canonical input in the same session returns the same persisted profile even after its build has started. Changed reviewed input creates an immutable profile revision. Read a profile using `GET /sessions/{id}/appearance-profile/{profile_id}`.

Submission requires an `Idempotency-Key` header of 8–128 ASCII characters:

```json
{
  "consent": true,
  "names": ["Alex", "Jamie"],
  "appearance_profile_id": "<returned profile ID>",
  "appearance_profile_sha256": "<returned profile SHA256>"
}
```

The profile hash, assignments, and photo ownership are validated again. Names can contain up to 12 ASCII letters, spaces, or hyphens. Name changes create a derived profile that records the engraving override. The queued build enters `PARAMETERS_READY` and then the real Blender stages; the server does not pretend it is running browser analysis.

The same idempotency key and request return existing work. Reusing a key with changed input returns 409. A retry after failure uses a new key; unchanged parameters and profile preserve the model revision while incrementing the attempt. The limits are three attempts per revision and 12 builds per session, in addition to deployment-wide capacity/rate limits.

## Corrections, provenance, and approval

`POST /sessions/{id}/corrections` also requires an idempotency key. It accepts only supported fields, for example:

```json
{
  "characters": {
    "left": {
      "pants_palette_id": "navy",
      "face_morphs": {"nose_width": -0.2}
    }
  }
}
```

Partial face corrections merge with existing controls rather than resetting other measurements. A correction creates an immutable derived profile and new model revision, preserving the original observations and documenting manual overrides.

The 13 finite face controls range from -1 to 1, with neutral 0: `face_width`, `face_height`, `jaw_width`, `chin_length`, `cheek_fullness`, `eye_spacing`, `eye_size`, `brow_thickness`, `brow_arch`, `nose_width`, `nose_projection`, `mouth_width`, and `smile`. These controls operate only within the authored demo template. No identity reconstruction, arbitrary mesh generation, or executable user/AI code is accepted.

`GET /sessions/{id}/status` returns state, model revision, job, photos, final parameters, appearance metadata, artifacts, QA, checksum, history, and expiry. Errors are either `null` or `{code, message}`. The appearance metadata distinguishes browser-derived profiles from technical fixtures, and distinguishes observations, defaults, and manual choices.

The worker receives a bounded inert appearance-provenance record. The exported provenance binds the appearance profile ID/revision/hash, source photo hashes, observations/assignment/manual-override hashes, parameter hash, source master hash, and model revision. The API independently validates that record and all artifact hashes before exposing a ready preview. Source photos and generated files never live under the public static directory.

Read each artifact's protected URL with owner authorization; create browser object URLs for the viewer when needed. Approval uses:

```json
{"model_revision":1,"job_checksum":"<checksum from current ready status>"}
```

A stale model/checksum returns 409. Customer approval concerns the digital preview only. Quality remains `DEMO`; `production_approved` remains `false`.

## Route reference

| Method and route | Purpose |
| --- | --- |
| `GET /health` | API mode, storage mode, browser analysis provider, and Blender availability |
| `GET /designs` | Current registered design |
| `GET /designs/better-together` | Strict current manifest |
| `POST /customization-sessions` | Create an owner session |
| `POST /sessions/{id}/photos` | Private multipart upload |
| `GET /sessions/{id}/photos/{photo_id}` | Read normalized private PNG |
| `DELETE /sessions/{id}/photos/{photo_id}` | Remove a photo before generation |
| `POST /sessions/{id}/appearance-profile` | Validate and persist reviewed browser observations |
| `GET /sessions/{id}/appearance-profile/{profile_id}` | Read an owner-scoped immutable profile |
| `POST /sessions/{id}/submit` | Submit a reviewed profile or retry |
| `GET /sessions/{id}/status` | Current state, profile metadata, artifacts, QA, and error |
| `GET /sessions/{id}/preview` | Status alias |
| `POST /sessions/{id}/corrections` | Create a derived profile and model revision |
| `POST /sessions/{id}/approve` | Approve the bound digital revision |
| `GET /sessions/{id}/artifacts/{artifact_id}` | Read private model/render/report |
| `DELETE /sessions/{id}` | Cancel owned work and purge photos, profiles, artifacts, and records |
| `GET /admin/jobs` | Read jobs with a separate configured operator token |

## Technical fixture testing

`POST /sessions/{id}/fixture` is an internal pipeline test helper. It creates a synthetic illustration with no real people. Rendering it requires the explicit submit mode `technical-fixture`, consent, and exclusively server-created synthetic fixtures in that session. This path is labeled technical fixture in the profile and provenance and never claims photo extraction. Ordinary photo submission without a reviewed browser profile returns 422, including when a synthetic fixture exists.

`scripts/smoke-deployment.py --generate` checks this explicitly labeled technical pipeline path. It does **not** validate browser photo analysis. Browser end-to-end tests with documented, authorized portraits separately verify actual photo-to-parameter behavior.

## Storage and release limits

Profiles and jobs persist in the same private SQLite store as their session. Retention defaults to 24 hours; deletion removes derived appearance data too. Cleanup runs on startup, expiry checks, and periodically while active. The free Render deployment uses ephemeral storage, so data may disappear on restart or redeploy before the retention deadline; this is not durable order storage.

Public model/WASM assets under `/vision/` and worker code under `/workers/` permit cache revalidation. Every API response remains `Cache-Control: no-store`. Only the bounded self-hosted WASM permission is added to script CSP; no external analysis origin is allowed.

There is no production approval, live checkout, payment, or supplier-export endpoint. Operator access is disabled without a configured secret and remains separate from customer sessions.
