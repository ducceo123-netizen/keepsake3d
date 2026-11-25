// Test-only harness: real CPU inference, with no application or model mocks.
import { FilesetResolver, FaceLandmarker, ImageSegmenter } from '/vision/vision_bundle.mjs';
import ModuleFactory from '/vision/wasm/vision_wasm_module_internal.js';

self.onmessage = async ({ data }) => {
  let face, segmenter;
  try {
    const vision = await FilesetResolver.forVisionTasks('/vision/wasm', true);
    globalThis.ModuleFactory = ModuleFactory;
    face = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: '/vision/face_landmarker.task', delegate: 'CPU' },
      runningMode: 'IMAGE', numFaces: 3, outputFacialTransformationMatrixes: true,
    });
    const images = await Promise.all(data.images.map(async ({ id, blob }) => ({ id, bitmap: await createImageBitmap(blob) })));
    const faces = images.map(({ id, bitmap }) => ({ id, ...face.detect(bitmap) }));
    face.close(); face = undefined;
    globalThis.ModuleFactory = ModuleFactory;
    segmenter = await ImageSegmenter.createFromOptions(vision, {
      baseOptions: { modelAssetPath: '/vision/selfie_multiclass_256x256.tflite', delegate: 'CPU' },
      runningMode: 'IMAGE', outputCategoryMask: true, outputConfidenceMasks: false,
    });
    const results = images.map(({ id, bitmap }, index) => {
      const segmentation = segmenter.segment(bitmap);
      const categories = [...new Set(segmentation.categoryMask.getAsUint8Array())];
      segmentation.close(); bitmap.close();
      return { id, faces: faces[index].faceLandmarks.length, landmarks: faces[index].faceLandmarks.map(points => points.length), categories };
    });
    self.postMessage({ type: 'result', results });
  } catch (error) {
    self.postMessage({ type: 'error', message: error.message, stack: error.stack });
  } finally { face?.close(); segmenter?.close(); }
};
