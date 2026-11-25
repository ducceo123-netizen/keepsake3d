# Photo analysis dependencies and test images

Photo analysis runs in the browser using Google's MediaPipe Tasks Vision 1.2.3 (Apache License 2.0). The application serves its JavaScript, WebAssembly and model assets from its own origin. `scripts/install-vision-assets.mjs` pins each asset's source, byte length and SHA-256 and refuses changed content. The installer includes the upstream license at `/vision/LICENSE-MEDIAPIPE.txt`; keep it with redistributed assets. npm's lockfile pins the package tarball.

| Model | Official source | License evidence |
| --- | --- | --- |
| Face Landmarker, float16, version 1 | [Google model](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) | [Google Face Mesh V2 model card, page 1](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf), Apache 2.0 |
| Selfie Multiclass Segmenter, float32, version 1 | [Google model](https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite) | [Google model card, page 1](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Multiclass%20Segmentation.pdf), Apache 2.0 |

[MediaPipe source license](https://github.com/google-ai-edge/mediapipe/blob/v1.2.3/LICENSE), [official browser setup](https://developers.google.com/edge/mediapipe/solutions/setup_web), [Face Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker), [Image Segmenter documentation](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter).

Landmarks provide estimated visible facial proportions. Expression blendshape scores do not reconstruct a person's identity or unseen anatomy. The segmentation model estimates hair, skin and clothing regions; neither it nor palette matching guarantees accurate colors under difficult lighting. Model output is restricted to authored parameters and must be reviewed. Hair style, facial hair and glasses require manual choices.

The following photographs are downloaded only by `node scripts/install-vision-assets.mjs --fixtures` into `tests/vision/fixtures`. They are engineering fixtures, never customer examples, endorsements, production orders or storefront imagery.

| Fixture | Attribution and source | License/provenance |
| --- | --- | --- |
| `astronaut.png` | NASA portrait of Eileen Collins; unmodified bytes from [scikit-image v0.24.0](https://raw.githubusercontent.com/scikit-image/scikit-image/v0.24.0/skimage/data/astronaut.png) | [scikit-image's image documentation](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) records its NASA source and public-domain status. |
| `grace_hopper.jpg` | James S. Davis, U.S. Navy official portrait of Grace M. Hopper (NH 96919-KN); Matplotlib's reduced sample from [v3.10.8](https://raw.githubusercontent.com/matplotlib/matplotlib/v3.10.8/lib/matplotlib/mpl-data/sample_data/grace_hopper.jpg) | U.S. government work, public domain in the United States; [image provenance and attribution](https://commons.wikimedia.org/wiki/File:Grace_Hopper.jpg), [Naval History and Heritage Command original record](https://www.history.navy.mil/our-collections/photography/numerical-list-of-images/nhhc-series/nh-series/NH-96000/NH-96919-KN.html). |

The fixtures cover distinct visible faces and clothing, not population diversity. Passing them is a functional inference smoke test, not a fairness, resemblance or demographic quality certification. Derived color/background variants exist only in test-browser memory and are identified as test transformations.
