import {
  FaceLandmarker,
  ImageSegmenter,
  FilesetResolver,
} from "/vision/vision_bundle.mjs";
import ModuleFactory from "/vision/wasm/vision_wasm_module_internal.js";
import {
  measureFace,
  nearestPalette,
  medianColor,
  clamp,
} from "./appearance-math.mjs";

// The only input is a normalized image Blob fetched by its owner. No credentials,
// image URLs, camera frames, embeddings or landmarks leave this worker.
self.onmessage = async ({ data }) => {
  let detector, segmenter;
  const progress = (message) => self.postMessage({ type: "progress", message });
  try {
    if (
      !Array.isArray(data.photos) ||
      data.photos.length < 1 ||
      data.photos.length > 3
    )
      throw new Error("Choose 1–3 reference photos.");
    if (typeof OffscreenCanvas === "undefined")
      throw new Error(
        "Photo analysis needs a newer browser. Try the latest Chrome, Edge, Firefox or Safari.",
      );
    progress(
      "Loading private photo analysis (about 35 MB on the first visit)…",
    );
    const vision = await FilesetResolver.forVisionTasks("/vision/wasm", true);
    // The runtime clears this factory after initialization. Restore it because
    // repeated ES-module imports reuse the module and do not rerun its side effect.
    globalThis.ModuleFactory = ModuleFactory;
    detector = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "/vision/face_landmarker.task",
        delegate: "CPU",
      },
      runningMode: "IMAGE",
      numFaces: 6,
      minFaceDetectionConfidence: 0.65,
      minFacePresenceConfidence: 0.65,
      outputFaceBlendshapes: true,
    });
    globalThis.ModuleFactory = ModuleFactory;
    segmenter = await ImageSegmenter.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "/vision/selfie_multiclass_256x256.tflite",
        delegate: "CPU",
      },
      runningMode: "IMAGE",
      outputCategoryMask: false,
      outputConfidenceMasks: true,
    });
    const faces = [],
      warnings = [];
    for (let p = 0; p < data.photos.length; p++) {
      const photo = data.photos[p];
      progress(`Finding faces in photo ${p + 1} of ${data.photos.length}…`);
      const bitmap = await createImageBitmap(photo.blob);
      try {
        const scale = Math.min(1, 1280 / Math.max(bitmap.width, bitmap.height));
        const canvas = new OffscreenCanvas(
          Math.round(bitmap.width * scale),
          Math.round(bitmap.height * scale),
        );
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx) throw new Error("Your browser could not open the photo.");
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        const result = detector.detect(canvas);
        if (!result.faceLandmarks.length)
          warnings.push(
            `No clear face found in photo ${p + 1}. Use a well-lit, front-facing portrait.`,
          );
        for (let i = 0; i < result.faceLandmarks.length; i++) {
          const measured = measureFace(
            result.faceLandmarks[i],
            canvas.width,
            canvas.height,
            result.faceBlendshapes[i]?.categories,
          );
          const face = {
            ...measured,
            id: `${photo.id}:${i}`,
            photo_id: photo.id,
            photo_sha256: photo.sha256,
            face_index: i,
            face_count: result.faceLandmarks.length,
            photo_number: p + 1,
          };
          if (face.usable) {
            progress(`Reading face proportions and colors in photo ${p + 1}…`);
            // Isolate the selected head and upper torso. Neighbor midpoints keep
            // another person's hair/shirt out of this candidate's color samples.
            const b = face.bounds,
              cx = b.x + b.width / 2;
            let x0 = clamp(cx - b.width * 0.85, 0, 1),
              x1 = clamp(cx + b.width * 0.85, 0, 1);
            for (let j = 0; j < result.faceLandmarks.length; j++)
              if (j !== i) {
                const other = result.faceLandmarks[j][1];
                if (
                  Math.abs(other.y - (b.y + b.height * 0.5)) <
                  b.height * 1.5
                ) {
                  if (other.x < cx) x0 = Math.max(x0, (other.x + cx) / 2);
                  else x1 = Math.min(x1, (other.x + cx) / 2);
                }
              }
            const y0 = clamp(b.y - b.height * 0.55, 0, 1),
              y1 = clamp(b.y + b.height * 2.7, 0, 1);
            const crop = new OffscreenCanvas(
              256,
              Math.max(
                128,
                Math.min(
                  512,
                  Math.round(
                    (256 * (y1 - y0) * canvas.height) /
                      ((x1 - x0) * canvas.width),
                  ),
                ),
              ),
            );
            const cropCtx = crop.getContext("2d", { willReadFrequently: true });
            cropCtx.drawImage(
              canvas,
              x0 * canvas.width,
              y0 * canvas.height,
              (x1 - x0) * canvas.width,
              (y1 - y0) * canvas.height,
              0,
              0,
              crop.width,
              crop.height,
            );
            const colors = { 1: [], 3: [], 4: [] };
            segmenter.segment(crop, (seg) => {
              if (!seg.confidenceMasks || seg.confidenceMasks.length < 5)
                return;
              const rgba = cropCtx.getImageData(
                0,
                0,
                crop.width,
                crop.height,
              ).data;
              for (const cat of [1, 3, 4]) {
                const mask = seg.confidenceMasks[cat],
                  values = mask.getAsFloat32Array();
                for (let y = 0; y < mask.height; y += 2)
                  for (let x = 0; x < mask.width; x += 2) {
                    if (values[y * mask.width + x] < 0.75) continue;
                    const imgY = y0 + (y / mask.height) * (y1 - y0);
                    if (cat === 1 && imgY > b.y + b.height * 1.2) continue;
                    if (cat === 3 && (imgY < b.y || imgY > b.y + b.height))
                      continue;
                    if (cat === 4 && imgY < b.y + b.height) continue;
                    const k =
                      (Math.min(
                        crop.height - 1,
                        Math.floor((y / mask.height) * crop.height),
                      ) *
                        crop.width +
                        Math.min(
                          crop.width - 1,
                          Math.floor((x / mask.width) * crop.width),
                        )) *
                      4;
                    colors[cat].push([rgba[k], rgba[k + 1], rgba[k + 2]]);
                  }
              }
            });
            for (const [cat, field, label] of [
              [1, "hair_color_id", "Hair color"],
              [3, "skin_material_id", "Skin color"],
              [4, "outfit_palette_id", "Top color"],
            ]) {
              const rgb = medianColor(colors[cat]);
              face.measurements[`${field}_sample_count`] = colors[cat].length;
              if (rgb) {
                face.params[field] = nearestPalette(rgb, field);
                face.observed_fields.push(field);
              } else
                face.warnings.push(
                  `${label} was unclear; review the starting color.`,
                );
            }
          }
          face.warnings.push(
            "Choose hair style, facial hair, glasses, trousers and shoes yourself. Unseen depth uses the sculpted default.",
          );
          faces.push(face);
        }
      } finally {
        bitmap.close();
      }
    }
    self.postMessage({ type: "result", faces, warnings });
  } catch (error) {
    self.postMessage({
      type: "error",
      message:
        error instanceof Error
          ? error.message
          : "Photo analysis failed. Please try a clearer photo.",
    });
  } finally {
    detector?.close();
    segmenter?.close();
    self.close();
  }
};
