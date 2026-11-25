export type Session = { id: string; token: string; expires_at: string };
export type Photo = {
  id: string;
  width: number;
  height: number;
  url: string;
  sha256: string;
};
export type Artifact = {
  kind: string;
  url: string;
  sha256: string;
  revision: number;
  filename?: string;
};
export type Character = {
  hair_style_asset_id: string;
  hair_color_id: string;
  facial_hair_id: string;
  glasses_asset_id: string;
  skin_material_id: string;
  outfit_palette_id: string;
  pants_palette_id: string;
  shoes_palette_id: string;
  engraving_text: string;
  face_morphs: Record<string, number>;
};
export type Status = {
  id: string;
  state: string;
  revision: number;
  job_id: string | null;
  error: { code: string; message: string } | null;
  photos: Photo[];
  params: {
    schema_version: string;
    characters: { left: Character; right: Character };
  } | null;
  artifacts: Artifact[];
  qa: Record<string, unknown> | null;
  checksum: string | null;
  history: Array<{ state?: string; to_state?: string; timestamp?: string }>;
  expires_at?: string;
  appearance_profile?: unknown;
};
export async function api<T>(
  path: string,
  session?: Session | null,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (session) headers.set("Authorization", `Bearer ${session.token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(path, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d: { msg: string }) => d.msg).join(" ")
            : message;
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : await response.json();
}
export async function privateBlob(
  url: string,
  session: Session,
  signal?: AbortSignal,
) {
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${session.token}` },
    cache: "no-store",
    signal,
  });
  if (!res.ok)
    throw new Error(
      "This private file is unavailable. Refresh your session to try again.",
    );
  return res.blob();
}
export const activeStates = new Set([
  "PHOTO_VALIDATING",
  "AI_ANALYZING",
  "PARAMETERS_READY",
  "MODEL_BUILDING",
  "MODEL_RENDERING",
  "QA_RUNNING",
]);
export const stateMessages: Record<string, string> = {
  PHOTO_VALIDATING: "Checking your photos",
  AI_ANALYZING: "Applying your reviewed photo measurements",
  PARAMETERS_READY: "Getting your model ready",
  MODEL_BUILDING: "Shaping your little keepsake",
  MODEL_RENDERING: "Finding its best angle",
  QA_RUNNING: "Checking the model files",
};
