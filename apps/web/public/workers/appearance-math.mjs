// Authored mapping v1: visible 2D ratios -> bounded stylized controls.
// These are reviewable artistic mappings, not biometric identity or depth estimates.
export const clamp = (v, a = -1, b = 1) => Math.max(a, Math.min(b, v));
export const morphNames = [
  "face_width",
  "face_height",
  "jaw_width",
  "chin_length",
  "cheek_fullness",
  "eye_spacing",
  "eye_size",
  "brow_thickness",
  "brow_arch",
  "nose_width",
  "nose_projection",
  "mouth_width",
  "smile",
];
export const palettes = {
  hair_color_id: {
    black: [40, 32, 29],
    chestnut: [110, 66, 43],
    brown: [133, 96, 71],
    blonde: [196, 155, 86],
    silver: [170, 166, 160],
    auburn: [141, 63, 40],
  },
  skin_material_id: {
    light: [224, 172, 137],
    warm: [188, 128, 90],
    tan: [162, 104, 68],
    deep: [112, 69, 46],
  },
  outfit_palette_id: {
    cream: [232, 223, 201],
    blue: [76, 111, 136],
    rose: [183, 112, 119],
    sage: [128, 149, 121],
    black: [40, 40, 40],
    white: [241, 238, 232],
    gray: [144, 144, 144],
    red: [181, 73, 66],
    brown: [120, 81, 61],
    navy: [38, 61, 86],
    yellow: [211, 174, 79],
    purple: [128, 109, 152],
  },
};
const round = (n) => Math.round(n * 1000) / 1000;
export function defaultCharacter() {
  return {
    hair_style_asset_id: "short",
    hair_color_id: "chestnut",
    skin_material_id: "warm",
    outfit_palette_id: "cream",
    pants_palette_id: "navy",
    shoes_palette_id: "cream",
    facial_hair_id: "none",
    glasses_asset_id: "none",
    engraving_text: "",
    face_morphs: Object.fromEntries(morphNames.map((k) => [k, 0])),
  };
}
export function measureFace(landmarks, width, height, blends = []) {
  if (
    landmarks.length < 468 ||
    landmarks.some((p) => !Number.isFinite(p.x) || !Number.isFinite(p.y))
  )
    throw new Error("Invalid facial landmarks.");
  const pts = landmarks.map((p) => ({ x: p.x * width, y: p.y * height }));
  const dist = (i, j) => Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y);
  const fw = dist(234, 454),
    fh = dist(10, 152);
  if (fw < 1 || fh < 1) throw new Error("The face is too small to measure.");
  const roll = Math.atan2(pts[263].y - pts[33].y, pts[263].x - pts[33].x);
  const project = (p) => p.x * Math.cos(roll) + p.y * Math.sin(roll);
  const left = project(pts[234]),
    right = project(pts[454]);
  const yaw = Math.abs((project(pts[1]) - (left + right) / 2) / fw);
  const ratio = fw / fh;
  const measurements = {
    face_width_height: ratio,
    jaw_width_ratio: dist(172, 397) / fw,
    chin_ratio: dist(17, 152) / fh,
    eye_spacing_ratio: dist(133, 362) / fw,
    eye_width_ratio: (dist(33, 133) + dist(362, 263)) / (2 * fw),
    nose_width_ratio: dist(98, 327) / fw,
    mouth_width_ratio: dist(61, 291) / fw,
    face_pixels: Math.min(fw, fh),
    yaw_proxy: yaw,
    roll_degrees: Math.abs((roll * 180) / Math.PI),
  };
  const params = defaultCharacter(),
    m = params.face_morphs;
  m.face_width = clamp((ratio - 0.78) / 0.18);
  m.face_height = clamp((1 / ratio - 1.28) / 0.32);
  m.jaw_width = clamp((measurements.jaw_width_ratio - 0.78) / 0.18);
  m.chin_length = clamp((measurements.chin_ratio - 0.17) / 0.08);
  m.eye_spacing = clamp((measurements.eye_spacing_ratio - 0.24) / 0.08);
  m.eye_size = clamp((measurements.eye_width_ratio - 0.21) / 0.065);
  m.nose_width = clamp((measurements.nose_width_ratio - 0.24) / 0.08);
  m.mouth_width = clamp((measurements.mouth_width_ratio - 0.38) / 0.12);
  const smileScores = blends.filter((v) =>
    ["mouthSmileLeft", "mouthSmileRight"].includes(v.categoryName),
  );
  if (smileScores.length === 2)
    m.smile = clamp(smileScores.reduce((s, v) => s + v.score, 0) / 2, 0, 1);
  Object.keys(m).forEach((k) => (m[k] = round(m[k])));
  const xs = landmarks.slice(0, 468).map((p) => p.x),
    ys = landmarks.slice(0, 468).map((p) => p.y);
  const x = clamp(Math.min(...xs), 0, 1),
    y = clamp(Math.min(...ys), 0, 1);
  const bounds = {
    x,
    y,
    width: clamp(Math.max(...xs), 0, 1) - x,
    height: clamp(Math.max(...ys), 0, 1) - y,
  };
  const warnings = [];
  if (Math.min(fw, fh) < 80)
    warnings.push(
      "This face is too small. Use a closer photo with a face at least 80 pixels wide.",
    );
  if (yaw > 0.16)
    warnings.push(
      "This face is turned too far sideways. Choose a more front-facing photo.",
    );
  if (Math.abs(roll) > Math.PI / 5)
    warnings.push("This face is tilted too far. Choose an upright photo.");
  if (
    bounds.x < 0.005 ||
    bounds.y < 0.005 ||
    bounds.x + bounds.width > 0.995 ||
    bounds.y + bounds.height > 0.995
  )
    warnings.push(
      "The face reaches the edge of the photo. Use an uncropped face.",
    );
  return {
    params,
    bounds,
    measurements: Object.fromEntries(
      Object.entries(measurements).map(([k, v]) => [k, round(v)]),
    ),
    usable: warnings.length === 0,
    warnings,
    observed_fields: [
      "face_morphs.face_width",
      "face_morphs.face_height",
      "face_morphs.jaw_width",
      "face_morphs.chin_length",
      "face_morphs.eye_spacing",
      "face_morphs.eye_size",
      "face_morphs.nose_width",
      "face_morphs.mouth_width",
      ...(smileScores.length === 2 ? ["face_morphs.smile"] : []),
    ],
  };
}

// CIE Lab distance is less sensitive to brightness than a raw RGB distance.
function lab(rgb) {
  const [r, g, b] = rgb.map((v) => {
    v /= 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const f = (v) => (v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116);
  const x = f((r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047),
    y = f(r * 0.2126 + g * 0.7152 + b * 0.0722),
    z = f((r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883);
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}
export function nearestPalette(rgb, field) {
  const color = lab(rgb);
  return Object.entries(palettes[field])
    .map(([id, c]) => [
      id,
      Math.hypot(...lab(c).map((v, i) => (v - color[i]) * (i === 0 ? 0.7 : 1))),
    ])
    .sort((a, b) => a[1] - b[1])[0][0];
}
export function medianColor(pixels) {
  if (pixels.length < 30) return null;
  return [0, 1, 2].map(
    (k) =>
      pixels.map((p) => p[k]).sort((a, b) => a - b)[
        Math.floor(pixels.length / 2)
      ],
  );
}
