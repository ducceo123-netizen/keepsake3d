# Versioned appearance-driven Blender demo

Version `0.2.0-demo` makes reviewed appearance parameters visibly change the figurines. The web app measures observable face proportions locally in the browser; the Blender worker receives only validated parameters and inert provenance metadata. It does not analyze photos, identify people, reconstruct hidden anatomy, or claim precise likeness.

The product remains a stylized procedural engineering asset, not the supplied concept artwork or an approved commercial master. Neither joint fit nor physical printing has been validated.

## Reproduce the actual builds

From the repository root, install Blender 4.5 LTS and set `BLENDER_BIN` if it is not on PATH. The current workspace also autodetects its portable copy at `../../work/tools/blender/Blender.app/Contents/MacOS/Blender`.

```sh
python workers/blender/run.py --params assets/designs/better-together/0.2.0-demo/example-params.json --output evidence/appearance-v2/neutral --revision 1
python workers/blender/run.py --params assets/designs/better-together/0.2.0-demo/contrasting-params.json --output evidence/appearance-v2/contrasting --revision 2
"$BLENDER_BIN" --background --factory-startup --disable-autoexec --python-exit-code 1 --threads 2 --python workers/blender/validate_morphs.py -- --output evidence/appearance-v2/morph-stress.json
python -m pytest tests/pipeline -q
```

The runner validates the complete schema-2.0 parameter allowlist and source master hash, launches only checked-in scripts with automatic asset script execution disabled, and bounds execution time. It fails explicitly if Blender is unavailable or any required geometry check fails. It never substitutes invented model files.

Each successful build writes `model.glb`, `model.stl`, `preview.png`, `qa.json`, and `provenance.json`. `progress.json` records actual model-building, rendering and QA stages. The API owns final session readiness after independently verifying artifact hashes, reviewed-profile binding and authorization.

## Authored appearance contract

All thirteen finite controls range from -1 to 1, with 0 as the neutral authored default:

- Head shape: `face_width`, `face_height`, `jaw_width`, `chin_length`, `cheek_fullness`.
- Surface features: `eye_spacing`, `eye_size`, `brow_thickness`, `brow_arch`, `nose_width`, `nose_projection`, `mouth_width`, `smile`.

The five head shape keys are stored in the immutable source `.blend`. The other eight controls change bounded, checked-in feature-mesh recipes. Eyes, brows, nose, mouth and glasses follow the same deformed head surface. Neutral expression is a restrained smile. A partial photo cannot establish every attribute: the browser/API must disclose defaults or request manual review for uncertain features, including nose depth.

Hair has eight approved silhouettes: short, long, bun, bob, curly short, curly long, buzz and bald. Buzz uses a closed shell following the actual scalp; bald creates no hair geometry. Facial hair and glasses use approved asset choices. Top, pants and shoes have separate approved materials, while their geometry remains locked. `palette-swatches.json` is the shared sRGB source; Blender converts those values to linear material colors.

Names remain raised demonstration labels, not qualified engraving. They accept up to 12 ASCII letters, spaces or hyphens and fit a bounded width.

## Revision integrity and same-scene export

The API may pass `--appearance appearance.json`. This is a strictly validated metadata object with profile ID/revision, source-photo hashes, observation/manual-override hashes, explicit review and local-processing flags. It is copied as inert `appearance_profile` data into provenance and the job checksum. It cannot contain executable operations. Without this argument, a CLI fixture is honestly labeled `manual-fixture`.

Configured head shape keys are **baked into evaluated meshes before both GLB and STL export**. This avoids exporting raw neutral head vertices to STL while showing morphed geometry in GLB. Provenance binds parameters, master, rendering recipe, palette, configured geometry, reviewed appearance profile, outputs and model revision. Tests compare every exported GLB/STL vertex position after converting coordinate systems, within float32 rounding tolerance.

`ASSEMBLY_LEFT` and `ASSEMBLY_RIGHT` remain the GLB roots for separated viewing. GLB uses Y-up; STL uses source Z-up. Units are explicitly unscaled demo units, not manufacturing measurements. STL contains geometry only and does not carry GLB material colors.

## Locked geometry and validation

The version-0.2 master was upgraded from the original version-0.1 master without changing any of its 26 locked mesh/anchor fingerprints. Version-0.1 assets remain immutable. `master-upgrade-report.json` records old/new master hashes and exact before/after lock maps.

QA checks finite vertices, closed component edges, positive component volumes, baked head meshes, authored feature envelopes and exact locked mesh/transform fingerprints. The stress script tests both extremes of every control, every hairstyle, facial-hair/glasses combinations, and seeded combinations of extreme parameters. It also verifies that every geometry control actually changes the generated mesh.

These checks are not manufacturing qualification. The model still contains overlapping components; no mesh union, minimum wall-thickness proof, engineered connector clearance, slicer acceptance, physical print, finishing or likeness approval is claimed. Production approval always remains false.

## Master authoring only

```sh
"$BLENDER_BIN" --background --factory-startup --disable-autoexec --python-exit-code 1 --python workers/blender/scene.py -- --create-master
```

This intentionally reads the immutable version-0.1 master, upgrades editable assets, asserts every lock is unchanged, and writes the version-0.2 master/manifest/upgrade report. It is not an application-startup operation. Review and version these assets together and regenerate evidence after intentional authoring changes.

## Rendering resource profile

Local defaults remain 1000 pixels, 24 samples and denoising enabled. The Render free-demo profile uses `BLENDER_RENDER_RESOLUTION=512`, `BLENDER_RENDER_SAMPLES=8`, `BLENDER_DENOISE=0`, and `BLENDER_THREADS=1`. Geometry is unchanged. Render settings are recorded in provenance. Resolution accepts 256–1600; samples 1–64; thread count 1–8. Invalid settings fail.

The Docker image installs official Blender 4.5.16 Linux x86_64 with its published SHA256 and performs a real sample export during image build. Runtime storage is ephemeral on the free service. A Linux image-build success does not establish the live service's memory capacity; use actual runtime checks and the recorded resource measurement.
