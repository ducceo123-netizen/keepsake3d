import type { Character } from "./api";
export const designVersion = "0.2.0-demo";
const clothing = [
  "cream",
  "blue",
  "rose",
  "sage",
  "black",
  "white",
  "gray",
  "red",
  "brown",
  "navy",
  "yellow",
  "purple",
];
export const correctionOptions: Record<string, string[]> = {
  hair_style_asset_id: [
    "short",
    "long",
    "bun",
    "bob",
    "curly_short",
    "curly_long",
    "buzz",
    "bald",
  ],
  hair_color_id: ["chestnut", "black", "blonde", "silver", "auburn", "brown"],
  skin_material_id: ["light", "warm", "tan", "deep"],
  outfit_palette_id: clothing,
  pants_palette_id: clothing,
  shoes_palette_id: clothing,
  facial_hair_id: ["none", "stubble", "moustache", "beard"],
  glasses_asset_id: ["none", "round", "rectangular"],
};
export const correctionLabels: Record<string, string> = {
  hair_style_asset_id: "Hair style",
  hair_color_id: "Hair color",
  skin_material_id: "Skin color",
  outfit_palette_id: "Top color",
  pants_palette_id: "Trouser color",
  shoes_palette_id: "Shoe color",
  facial_hair_id: "Facial hair",
  glasses_asset_id: "Glasses",
};
export const morphLabels: Record<string, string> = {
  face_width: "Face width",
  face_height: "Face height",
  jaw_width: "Jaw width",
  chin_length: "Chin length",
  cheek_fullness: "Cheek fullness",
  eye_spacing: "Eye spacing",
  eye_size: "Eye size",
  brow_thickness: "Brow thickness",
  brow_arch: "Brow arch",
  nose_width: "Nose width",
  nose_projection: "Nose depth",
  mouth_width: "Mouth width",
  smile: "Smile",
};
export type FaceCandidate = {
  id: string;
  photo_id: string;
  photo_sha256: string;
  face_index: number;
  face_count: number;
  photo_number: number;
  bounds: { x: number; y: number; width: number; height: number };
  usable: boolean;
  warnings: string[];
  params: Character;
  observed_fields: string[];
  measurements: Record<string, number>;
};
export type AppearanceDraft = {
  consent: true;
  reviewed: true;
  source: "browser-mediapipe-v1";
  analysis_version: "1.0";
  assignments: Record<
    "left" | "right",
    {
      photo_id: string;
      photo_sha256: string;
      face_index: number;
      face_count: number;
      box: number[];
    }
  >;
  parameters: {
    schema_version: "2.0";
    characters: { left: Character; right: Character };
  };
  observations: Record<
    "left" | "right",
    {
      measurements: Record<string, number>;
      confidence: null;
      confidence_basis: "heuristic-quality-not-model-probability";
      observed_fields: string[];
      warnings: string[];
    }
  >;
  manual_overrides: {
    characters: { left: Partial<Character>; right: Partial<Character> };
  };
};
