# Blender technical demo

The bundled `master.blend` is a procedural mannequin asset authored for this local engineering slice. It is not the supplied concept artwork, an approved commercial master, or a print-ready model. The two halves demonstrate an interlocking contour, without validated joint tolerance or magnets.

## Reproduce a build

From the repository root, install Blender 4.5 LTS and point `BLENDER_BIN` at its executable if it is not on PATH. The current workspace also autodetects its portable copy at `../../work/tools/blender/Blender.app/Contents/MacOS/Blender`.

```sh
python workers/blender/run.py --params assets/designs/better-together/0.1.0-demo/example-params.json --output evidence/demo-build --revision 1
python workers/blender/run.py --params tests/pipeline/variant-params.json --output evidence/variant-build --revision 2
python -m pytest tests/pipeline -q
```

The runner validates the complete parameter allowlist and source master hash, launches only `scene.py` with Blender automatic script execution disabled, and limits process time. Each job imports the exact versioned master. It creates GLB, geometry-only STL and a rendered PNG from that configured scene; writes QA and provenance hashes; then verifies every artifact hash and the QA verdict. It fails explicitly when Blender is unavailable or geometry checks fail. It does not create substitute model files.

`progress.json` records actual model building, rendering and QA stages. The API owns the final session state after its independent provenance and authorization checks.

## Verified source

The implementation was exercised with official Blender 4.5.16 LTS, arm64, build `3f6797307da5`. Download: [Blender's archive](https://download.blender.org/release/Blender4.5/). The downloaded `blender-4.5.16-macos-arm64.dmg` SHA256 was verified against Blender's published checksums:

```
c5cd40979f30033bc55ca84fccd00f2c1ddebb1d2f41618f220ef1f596d8b0f6
```

No system-wide application installation was performed. The Blender application is a development dependency and is not included in the application source archive.

## Contract and limitations

The source manifest is in `assets/designs/better-together/0.1.0-demo/manifest.json`. Its strict Pydantic model and generated JSON Schema are in `packages/schemas`. No face morphs are authored for this demo; any nonempty face-morph input is rejected. Hair, glasses, facial hair and material variants are finite allowlisted choices. Name labels accept up to 12 ASCII letters, spaces or hyphens, and are scaled to a demonstration width envelope. These are raised demo labels, not qualified engraving.

`ASSEMBLY_LEFT` and `ASSEMBLY_RIGHT` are the exported GLB root nodes for optional separated viewing. GLB uses its standard Y-up convention; the STL uses the scene's Z-up coordinates. Units are explicitly unscaled demo units, not a manufacturing measurement.

QA checks finite vertices, closed component edges, positive component volumes and exact locked mesh/transform fingerprints. A checked demo still contains intersecting mannequin components: no mesh union, wall-thickness proof, manufacturing clearance proof, slicer acceptance or physical print approval is claimed. Both QA and provenance retain `print_approved: false` or `DEMO_NOT_PRINT_APPROVED`.

## Authoring only

Regenerating a master changes its source hash and is not part of normal application startup. To intentionally reauthor this procedural demo:

```sh
"$BLENDER_BIN" --background --factory-startup --disable-autoexec --python-exit-code 1 --python workers/blender/scene.py -- --create-master
```

Review and version the resulting master and manifest together; regenerate evidence afterward. Never point this command at a production design.

## Render container profile

The Docker image installs checksum-verified official Blender 4.5.16 for Linux x86_64 and performs a real sample export/render during the image build. It serves the static Next.js export through FastAPI, with one ASGI worker and one active Blender job. It runs application and Blender processes as UID 10001.

Deployment-only environment settings reduce render cost without changing GLB or STL geometry: `BLENDER_RENDER_RESOLUTION=512`, `BLENDER_RENDER_SAMPLES=8`, `BLENDER_DENOISE=0`, and `BLENDER_THREADS=1`. Local defaults remain 1000 pixels, 24 samples, denoising enabled, and two Blender threads. Render settings are included in each job's checksum-bound provenance. Thread limits accept 1–8; image resolution accepts 256–1600; samples accept 1–64; invalid settings fail the build.

`BLENDER_TIMEOUT_SECONDS=900` is shorter than the deployment API supervisor timeout of 1000 seconds. The free demo uses ephemeral `/tmp/keepsake-data`; restarts or redeploys can remove sessions and uploads. This hosting profile does not change the application's manufacturing approval status.

A local macOS arm64 measurement of the reduced render completed in 14.16 seconds with a sampled peak of 157.45 MiB for the worker and Blender descendants. It excludes the API process and does not establish Linux or Render memory requirements. The live 512 MiB service must still be checked for memory exhaustion.
