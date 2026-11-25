"use client";
import { useEffect, useRef, useState } from "react";
import { ScanFace, Check } from "lucide-react";
import { BrandButton, ErrorState, GenerationStatus } from "@design/primitives";
import {
  privateBlob,
  type Character,
  type Photo,
  type Session,
} from "@/lib/api";
import { type AppearanceDraft, type FaceCandidate } from "@/lib/appearance";
import AppearanceFields from "./appearance-fields";
const slots = ["left", "right"] as const;

async function thumbnail(blob: Blob, face: FaceCandidate) {
  const bitmap = await createImageBitmap(blob);
  try {
    const b = face.bounds,
      pad = 0.24;
    const x = Math.max(0, b.x - b.width * pad),
      y = Math.max(0, b.y - b.height * pad);
    const w = Math.min(1 - x, b.width * (1 + 2 * pad)),
      h = Math.min(1 - y, b.height * (1 + 2 * pad));
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 180;
    canvas
      .getContext("2d")!
      .drawImage(
        bitmap,
        x * bitmap.width,
        y * bitmap.height,
        w * bitmap.width,
        h * bitmap.height,
        0,
        0,
        160,
        180,
      );
    const result = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (b) =>
          b ? resolve(b) : reject(new Error("Could not show a face crop.")),
        "image/jpeg",
        0.85,
      ),
    );
    return URL.createObjectURL(result);
  } finally {
    bitmap.close();
  }
}
export default function PhotoAnalysis({
  photos,
  session,
  consent,
  disabled,
  onReady,
  onEditPhotos,
}: {
  photos: Photo[];
  session: Session;
  consent: boolean;
  disabled: boolean;
  onReady: (draft: AppearanceDraft | null) => void;
  onEditPhotos: () => void;
}) {
  const [faces, setFaces] = useState<FaceCandidate[]>([]),
    [images, setImages] = useState<Record<string, string>>({}),
    [warnings, setWarnings] = useState<string[]>([]),
    [error, setError] = useState(""),
    [progress, setProgress] = useState(""),
    [running, setRunning] = useState(false),
    [analyzed, setAnalyzed] = useState(false),
    [reviewed, setReviewed] = useState(false);
  const [selection, setSelection] = useState({ left: "", right: "" }),
    [characters, setCharacters] = useState<{
      left: Character | null;
      right: Character | null;
    }>({ left: null, right: null });
  const worker = useRef<Worker | null>(null),
    alive = useRef(true),
    urls = useRef<string[]>([]),
    cancel = useRef<(() => void) | null>(null),
    generation = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      worker.current?.terminate();
      cancel.current?.();
      urls.current.forEach(URL.revokeObjectURL);
      urls.current = [];
    };
  }, []);
  useEffect(() => {
    if (!consent) {
      cancel.current?.();
      setReviewed(false);
      onReady(null);
    }
  }, [consent, onReady]);
  useEffect(() => {
    if (
      !reviewed ||
      !consent ||
      running ||
      !characters.left ||
      !characters.right ||
      selection.left === selection.right
    ) {
      onReady(null);
      return;
    }
    const selected = slots.map((slot) =>
      faces.find((f) => f.id === selection[slot]),
    );
    if (selected.some((f) => !f?.usable)) {
      onReady(null);
      return;
    }
    const assignments = {} as AppearanceDraft["assignments"],
      observations = {} as AppearanceDraft["observations"],
      manual = {} as AppearanceDraft["manual_overrides"]["characters"];
    slots.forEach((slot, i) => {
      const f = selected[i]!,
        c = characters[slot]!;
      assignments[slot] = {
        photo_id: f.photo_id,
        photo_sha256: f.photo_sha256,
        face_index: f.face_index,
        face_count: f.face_count,
        box: [f.bounds.x, f.bounds.y, f.bounds.width, f.bounds.height],
      };
      observations[slot] = {
        measurements: f.measurements,
        confidence: null,
        confidence_basis: "heuristic-quality-not-model-probability",
        observed_fields: f.observed_fields,
        warnings: f.warnings,
      };
      manual[slot] = Object.fromEntries(
        Object.entries(c).filter(
          ([key, v]) =>
            !["engraving_text", "face_morphs"].includes(key) &&
            v !== f.params[key as keyof Character],
        ),
      );
      const changedMorphs = Object.fromEntries(
        Object.entries(c.face_morphs).filter(
          ([key, v]) => v !== f.params.face_morphs[key],
        ),
      );
      if (Object.keys(changedMorphs).length)
        manual[slot].face_morphs = changedMorphs;
    });
    onReady({
      consent: true,
      reviewed: true,
      source: "browser-mediapipe-v1",
      analysis_version: "1.0",
      assignments,
      parameters: {
        schema_version: "2.0",
        characters: { left: characters.left, right: characters.right },
      },
      observations,
      manual_overrides: { characters: manual },
    });
  }, [reviewed, consent, running, selection, characters, faces, onReady]);
  async function analyze() {
    if (running || !consent) return;
    const run = ++generation.current;
    const controller = new AbortController();
    let rejectWorker: ((error: Error) => void) | null = null;
    const current = () =>
      alive.current && generation.current === run && !controller.signal.aborted;
    const cancelRun = () => {
      if (generation.current !== run) return;
      generation.current++;
      controller.abort();
      worker.current?.terminate();
      worker.current = null;
      rejectWorker?.(
        new DOMException("Photo analysis was cancelled.", "AbortError"),
      );
      cancel.current = null;
      urls.current.forEach(URL.revokeObjectURL);
      urls.current = [];
      if (alive.current) {
        setRunning(false);
        setProgress("");
        setFaces([]);
        setAnalyzed(false);
        setImages({});
        setSelection({ left: "", right: "" });
        setCharacters({ left: null, right: null });
        setReviewed(false);
        onReady(null);
      }
    };
    // Cancellation covers photo fetches, hashing, inference, and face thumbnails.
    cancel.current = cancelRun;
    onReady(null);
    setError("");
    setReviewed(false);
    setRunning(true);
    setFaces([]);
    setAnalyzed(false);
    setSelection({ left: "", right: "" });
    setCharacters({ left: null, right: null });
    setWarnings([]);
    setProgress("Opening your private reference photos…");
    urls.current.forEach(URL.revokeObjectURL);
    urls.current = [];
    setImages({});
    try {
      if (!window.Worker || !window.crypto?.subtle)
        throw new Error(
          "Photo analysis needs a current browser over a secure connection.",
        );
      const inputs: Array<{ id: string; sha256: string; blob: Blob }> = [];
      for (const photo of photos) {
        const blob = await privateBlob(photo.url, session, controller.signal);
        if (!current()) return;
        const hash = Array.from(
          new Uint8Array(
            await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
          ),
          (v) => v.toString(16).padStart(2, "0"),
        ).join("");
        if (!current()) return;
        if (!photo.sha256 || hash !== photo.sha256)
          throw new Error(
            "This photo has changed or belongs to an older session. Please start a fresh session and upload it again.",
          );
        inputs.push({ id: photo.id, sha256: hash, blob });
      }
      if (!current()) return;
      const result = await new Promise<{
        faces: FaceCandidate[];
        warnings: string[];
      }>((resolve, reject) => {
        const w = new Worker("/workers/appearance.js", { type: "module" });
        worker.current = w;
        const done = () => {
          clearTimeout(timer);
          w.onmessage = null;
          w.onerror = null;
          w.terminate();
          if (worker.current === w) worker.current = null;
          rejectWorker = null;
        };
        const timer = setTimeout(() => {
          done();
          reject(
            new Error(
              "Photo analysis took too long. Check your connection and try a smaller, clearer photo.",
            ),
          );
        }, 180000);
        rejectWorker = (error) => {
          done();
          reject(error);
        };
        w.onmessage = ({ data }) => {
          if (data.type === "progress") {
            if (current()) setProgress(data.message);
          } else if (data.type === "result") {
            done();
            resolve(data);
          } else if (data.type === "error") {
            done();
            reject(new Error(data.message));
          }
        };
        w.onerror = () => {
          done();
          reject(
            new Error(
              "Photo analysis could not start. Refresh and try a current Chrome, Edge, Firefox or Safari browser.",
            ),
          );
        };
        try {
          w.postMessage({ photos: inputs });
        } catch (error) {
          done();
          reject(error);
        }
      });
      if (!current()) return;
      const nextImages: Record<string, string> = {};
      for (const face of result.faces) {
        const url = await thumbnail(
          inputs.find((p) => p.id === face.photo_id)!.blob,
          face,
        );
        if (!current()) {
          URL.revokeObjectURL(url);
          return;
        }
        urls.current.push(url);
        nextImages[face.id] = url;
      }
      if (current()) {
        setFaces(result.faces);
        setImages(nextImages);
        setWarnings(result.warnings);
        setAnalyzed(true);
      }
    } catch (e) {
      if (current()) {
        urls.current.forEach(URL.revokeObjectURL);
        urls.current = [];
        setImages({});
        setError(e instanceof Error ? e.message : "Please try again.");
      }
    } finally {
      if (current()) {
        setRunning(false);
        setProgress("");
      }
      controller.abort();
      if (cancel.current === cancelRun) cancel.current = null;
    }
  }
  function choose(slot: "left" | "right", id: string) {
    const face = faces.find((f) => f.id === id);
    if (
      id &&
      (!face?.usable || selection[slot === "left" ? "right" : "left"] === id)
    )
      return;
    setSelection((s) => ({ ...s, [slot]: id }));
    setCharacters((c) => ({
      ...c,
      [slot]: face?.params || null,
    }));
    setReviewed(false);
  }
  const both =
    characters.left && characters.right && selection.left !== selection.right;
  const usableCount = faces.filter((f) => f.usable).length;
  return (
    <section className="photo-analysis" aria-labelledby="analysis-heading">
      <div className="panel-heading">
        <span className="section-number">02</span>
        <div>
          <h2 id="analysis-heading">A face that starts with you</h2>
          <p>Measure your photos, then choose who sits where.</p>
        </div>
      </div>
      <p className="field-help">
        Analysis runs on this device. It estimates visible face proportions and
        nearby hair, skin and top colors. Choose a clear, front-facing photo of
        each person. Separate portraits work too; both people do not need to be
        in the same photo.
      </p>
      <BrandButton
        variant="secondary"
        onClick={analyze}
        disabled={!consent || disabled || running}
        loading={running}
      >
        <ScanFace size={18} />
        {faces.length ? "Analyze photos again" : "Analyze photos"}
      </BrandButton>
      {!consent && (
        <p className="field-help">
          Confirm photo permission above to start analysis.
        </p>
      )}
      {running && (
        <div className="analysis-progress">
          <GenerationStatus label="Reading your photos" detail={progress} />
          <BrandButton variant="text" onClick={() => cancel.current?.()}>
            Cancel analysis
          </BrandButton>
        </div>
      )}
      {error && <ErrorState>{error}</ErrorState>}
      {warnings.map((w, i) => (
        <p className="analysis-warning" key={i}>
          {w}
        </p>
      ))}
      {analyzed && (
        <>
          <div
            className="analysis-result"
            id="face-selection-status"
            role="status"
          >
            <strong>
              {faces.length} {faces.length === 1 ? "face" : "faces"} detected ·{" "}
              {usableCount} usable
            </strong>
            {usableCount < 2 ? (
              <>
                <p>
                  {usableCount === 0
                    ? "No faces are available to select yet. We could not measure clear face proportions from these photos."
                    : "One face is ready to select. Add a clear photo of the other person to continue."}
                </p>
                <p>
                  Use a well-lit, front-facing photo with both eyes and the
                  whole face visible. You can upload one separate portrait per
                  person.
                  {photos.length >= 3 &&
                    " You have 3 photos; remove one above to make room."}
                </p>
                <BrandButton
                  variant="secondary"
                  onClick={onEditPhotos}
                  disabled={disabled || running}
                >
                  Add or replace photos
                </BrandButton>
                <p className="field-help">
                  After changing photos, choose Analyze photos again.
                </p>
              </>
            ) : (
              <p>Choose a different person for each character below.</p>
            )}
          </div>
          <div className="face-candidates">
            {faces.map((f) => (
              <figure
                key={f.id}
                className={
                  !f.usable ? "face-candidate unusable" : "face-candidate"
                }
              >
                <img
                  src={images[f.id]}
                  alt={`Photo ${f.photo_number}, face ${f.face_index + 1}`}
                />
                <figcaption>
                  Photo {f.photo_number} · Face {f.face_index + 1}
                  <span>
                    {f.usable
                      ? "Ready to select"
                      : "Unavailable — use another photo"}
                  </span>
                </figcaption>
                {!f.usable && <p>{f.warnings[0]}</p>}
              </figure>
            ))}
          </div>
          <div className="appearance-review-columns">
            {slots.map((slot) => (
              <fieldset key={slot} disabled={disabled || running}>
                <legend>
                  {slot === "left" ? "Left character" : "Right character"}
                </legend>
                <label className="field">
                  {slot === "left"
                    ? "Left character — reference face"
                    : "Right character — reference face"}
                  <select
                    value={selection[slot]}
                    onChange={(e) => choose(slot, e.target.value)}
                    disabled={usableCount === 0}
                    aria-describedby="face-selection-status"
                  >
                    <option value="">
                      {usableCount ? "Choose a face" : "No usable faces yet"}
                    </option>
                    {faces.map((f) => (
                      <option
                        key={f.id}
                        value={f.id}
                        disabled={
                          !f.usable ||
                          selection[slot === "left" ? "right" : "left"] === f.id
                        }
                      >
                        Photo {f.photo_number} · Face {f.face_index + 1}
                        {!f.usable && " — unavailable (see photo above)"}
                      </option>
                    ))}
                  </select>
                </label>
                {characters[slot] && (
                  <>
                    <div className="selected-face">
                      <img
                        src={images[selection[slot]]}
                        alt={`${slot === "left" ? "Left" : "Right"} character reference`}
                      />
                      <span>
                        <Check size={16} />
                        Photo proportions applied
                      </span>
                    </div>
                    <p className="field-help">
                      Check the colors. Choose hair style, facial hair, glasses,
                      trousers and shoes; these are not detected automatically.
                    </p>
                    {faces
                      .find((f) => f.id === selection[slot])
                      ?.warnings.filter((w) => !w.startsWith("Choose hair"))
                      .map((w) => (
                        <p className="analysis-warning" key={w}>
                          {w}
                        </p>
                      ))}
                    <AppearanceFields
                      value={characters[slot]}
                      onChange={(value) => {
                        setCharacters((c) => ({ ...c, [slot]: value }));
                        setReviewed(false);
                      }}
                    />
                  </>
                )}
              </fieldset>
            ))}
          </div>
          {both && (
            <label className="consent appearance-confirmation">
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
                disabled={disabled || running}
              />
              <span>
                I have checked the left and right people, hair, glasses and
                colors. Use these details for my stylized 3D preview.
              </span>
            </label>
          )}
        </>
      )}
    </section>
  );
}
