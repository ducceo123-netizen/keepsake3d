"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { ImagePlus, Sparkles, Download } from "lucide-react";
import {
  BrandButton,
  ErrorState,
  GenerationStatus,
  StatusBadge,
} from "@design/primitives";
import {
  api,
  ApiError,
  privateBlob,
  type Session,
  type Photo,
  type Status,
} from "@/lib/api";
import PrivateImage from "./private-image";

const ModelViewer = dynamic(() => import("./model-viewer"), { ssr: false });
const STORAGE = "keepsake-tripo-session-v1";
type Config = {
  available: boolean;
  configured: boolean;
  reason: string | null;
  model: string;
  estimated_credits: number;
  requires_access_code: boolean;
};
type Plan = {
  id: string;
  photo_id: string;
  photo_sha256: string;
  model: string;
  estimated_credits: number;
  expires_at: string;
  options: Record<string, unknown>;
};
type TripoArtifact = {
  id: string;
  kind: string;
  url: string;
  sha256: string;
  size_bytes: number;
};
type TripoStatus = {
  job_id: string | null;
  state: string;
  progress: number;
  model: string;
  estimated_credits: number;
  credits_consumed: number | null;
  error: string | { message: string } | null;
  artifacts: TripoArtifact[];
};
const active = new Set([
  "QUEUED",
  "UPLOADING",
  "SUBMITTING",
  "GENERATING",
  "DOWNLOADING",
  "WAITING_FOR_PROVIDER",
]);
const labels: Record<string, string> = {
  QUEUED: "Your model is queued",
  UPLOADING: "Sending your selected photo to Tripo",
  SUBMITTING: "Starting your Tripo model",
  GENERATING: "Tripo is shaping your model",
  DOWNLOADING: "Checking and saving your model",
  WAITING_FOR_PROVIDER: "Still waiting for Tripo",
  SUBMISSION_UNCERTAIN: "Checking whether Tripo accepted this request",
  FAILED: "Tripo could not finish this model",
};

export default function TripoStudio() {
  const [config, setConfig] = useState<Config | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [selected, setSelected] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [status, setStatus] = useState<TripoStatus | null>(null);
  const [transfer, setTransfer] = useState(false),
    [cost, setCost] = useState(false);
  const [accessCode, setAccessCode] = useState("");
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [loaded, setLoaded] = useState(false);
  const [attempted, setAttempted] = useState(false),
    [deleteOpen, setDeleteOpen] = useState(false);
  const alive = useRef(true),
    currentSession = useRef<Session | null>(null),
    input = useRef<HTMLInputElement>(null);
  const attempt = useRef<{ key: string; plan_id: string } | null>(null);
  function forgetSession(sid: string) {
    sessionStorage.removeItem(STORAGE);
    sessionStorage.removeItem(`${STORAGE}:attempt:${sid}`);
    currentSession.current = null;
    attempt.current = null;
    setSession(null);
    setPhotos([]);
    setSelected("");
    setPlan(null);
    setStatus(null);
    setAttempted(false);
    setTransfer(false);
    setCost(false);
    setAccessCode("");
    setDeleteOpen(false);
  }
  const refresh = useCallback(async (s: Session) => {
    const next = await api<TripoStatus>(
      `/api/v1/sessions/${s.id}/tripo/status`,
      s,
    );
    if (alive.current && currentSession.current?.id === s.id) {
      setStatus(next);
      if (next.job_id) setAttempted(true);
    }
    return next;
  }, []);
  useEffect(() => {
    alive.current = true;
    async function load() {
      try {
        const cfg = await api<Config>("/api/v1/tripo/config");
        if (!alive.current) return;
        setConfig(cfg);
        const saved = sessionStorage.getItem(STORAGE);
        if (saved) {
          const s: Session = JSON.parse(saved);
          currentSession.current = s;
          setSession(s);
          const pending = sessionStorage.getItem(`${STORAGE}:attempt:${s.id}`);
          if (pending) {
            attempt.current = JSON.parse(pending);
            setAttempted(true);
          }
          const old = await api<Status>(`/api/v1/sessions/${s.id}/status`, s);
          if (!alive.current) return;
          setPhotos(old.photos);
          setSelected(old.photos[0]?.id || "");
          await refresh(s);
        }
      } catch (e) {
        if (
          alive.current &&
          currentSession.current &&
          e instanceof ApiError &&
          [404, 410].includes(e.status)
        ) {
          forgetSession(currentSession.current.id);
          setError(
            "Your previous studio session has expired or was removed. Upload a new photo to start again. No replacement Tripo generation has been requested.",
          );
          return;
        }
        if (alive.current)
          setError(
            e instanceof Error
              ? e.message
              : "Could not open your Tripo studio.",
          );
      } finally {
        if (alive.current) setLoaded(true);
      }
    }
    void load();
    return () => {
      alive.current = false;
    };
  }, [refresh]);
  useEffect(() => {
    if (!session || !status || !active.has(status.state)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        await refresh(session!);
      } catch {
        if (!cancelled)
          setError(
            "Connection interrupted. Your existing Tripo request is still being checked; no new model was requested.",
          );
      }
      if (!cancelled) timer = setTimeout(poll, 3000);
    }
    timer = setTimeout(poll, 3000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [session, status?.state, refresh]);
  useEffect(() => {
    if (!plan || attempted) return;
    const timer = setTimeout(
      () => {
        setPlan(null);
        setCost(false);
        setError(
          "This cost plan expired. Review the generation cost again before continuing.",
        );
      },
      Math.max(0, new Date(plan.expires_at).getTime() - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [plan, attempted]);
  async function action(name: string, fn: () => Promise<void>) {
    if (busy) return;
    setBusy(name);
    setError("");
    try {
      await fn();
    } catch (e) {
      if (alive.current)
        setError(e instanceof Error ? e.message : "Please try again.");
    } finally {
      if (alive.current) setBusy("");
    }
  }
  async function upload(file?: File) {
    if (!file || attempted || !config?.available) return;
    if (
      !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
      file.size > 10 * 1024 * 1024
    ) {
      setError("Choose a JPG, PNG or WebP image up to 10 MB.");
      return;
    }
    await action("upload", async () => {
      let s = currentSession.current;
      if (!s) {
        s = await api<Session>("/api/v1/customization-sessions", null, {
          method: "POST",
          body: "{}",
        });
        currentSession.current = s;
        setSession(s);
        sessionStorage.setItem(STORAGE, JSON.stringify(s));
      }
      const body = new FormData();
      body.append("file", file);
      await api(`/api/v1/sessions/${s.id}/photos`, s, { method: "POST", body });
      const next = await api<Status>(`/api/v1/sessions/${s.id}/status`, s);
      if (!alive.current) return;
      setPhotos(next.photos);
      setSelected(next.photos.at(-1)?.id || "");
      setPlan(null);
      setTransfer(false);
      setCost(false);
    });
    if (input.current) input.current.value = "";
  }
  async function reviewPlan() {
    if (!session || !selected || attempted) return;
    const photo = photos.find((p) => p.id === selected)!;
    await action("plan", async () => {
      const quote = await api<Plan>(
        `/api/v1/sessions/${session.id}/tripo/plan`,
        session,
        {
          method: "POST",
          body: JSON.stringify({
            photo_id: photo.id,
            photo_sha256: photo.sha256,
          }),
        },
      );
      if (alive.current) {
        setPlan(quote);
        setTransfer(false);
        setCost(false);
      }
    });
  }
  async function submit() {
    if (
      !session ||
      !plan ||
      !transfer ||
      !cost ||
      !accessCode.trim() ||
      attempted ||
      !config?.available
    )
      return;
    if (Date.parse(plan.expires_at) <= Date.now()) {
      setPlan(null);
      setCost(false);
      setError("Review the generation cost again; this plan has expired.");
      return;
    }
    await action("submit", async () => {
      const request = { key: crypto.randomUUID(), plan_id: plan.id };
      attempt.current = request;
      sessionStorage.setItem(
        `${STORAGE}:attempt:${session.id}`,
        JSON.stringify(request),
      );
      setAttempted(true);
      try {
        const next = await api<TripoStatus>(
          `/api/v1/sessions/${session.id}/tripo/submit`,
          session,
          {
            method: "POST",
            headers: { "Idempotency-Key": request.key },
            body: JSON.stringify({
              plan_id: plan.id,
              consent: true,
              cost_accepted: true,
              access_code: accessCode,
            }),
          },
        );
        if (alive.current) {
          setStatus(next);
          setAccessCode("");
        }
      } catch (cause) {
        try {
          const current = await refresh(session);
          if (
            cause instanceof ApiError &&
            [403, 422, 429, 503].includes(cause.status) &&
            current.state === "NOT_STARTED" &&
            !current.job_id
          ) {
            attempt.current = null;
            sessionStorage.removeItem(`${STORAGE}:attempt:${session.id}`);
            setAttempted(false);
            setError(cause.message);
            return;
          }
        } catch {
          /* Keep attempt locked if acceptance is unknown. */
        }
        throw new Error(
          "The response was interrupted or the request was declined. Refresh Tripo status before doing anything else. No second generation has been submitted.",
        );
      }
    });
  }
  async function download(file: TripoArtifact) {
    if (!session) return;
    await action("download", async () => {
      const blob = await privateBlob(file.url, session);
      const bytes = await blob.arrayBuffer();
      const sha = Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
        (b) => b.toString(16).padStart(2, "0"),
      ).join("");
      if (sha !== file.sha256)
        throw new Error(
          "The model checksum did not match. Refresh status and try the download again.",
        );
      const url = URL.createObjectURL(blob),
        link = document.createElement("a");
      link.href = url;
      link.download = "keepsake-tripo-model.glb";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  async function removeSession() {
    if (!session) return;
    await action("delete", async () => {
      try {
        await api(`/api/v1/sessions/${session.id}`, session, {
          method: "DELETE",
        });
      } catch (e) {
        if (!(e instanceof ApiError && [404, 410].includes(e.status))) throw e;
      }
      forgetSession(session.id);
    });
  }
  const model = status?.artifacts.find((a) => a.kind === "glb");
  const poster = status?.artifacts.find((a) =>
    ["png", "preview"].includes(a.kind),
  );
  const jobError =
    typeof status?.error === "string" ? status.error : status?.error?.message;
  return (
    <main id="main" className="studio page-width tripo-studio">
      <div className="studio-top">
        <Link href="/" className="back-link">
          The collection
        </Link>
        <StatusBadge>Tripo 3D · Beta</StatusBadge>
      </div>
      <div className="studio-heading">
        <p className="eyebrow">FROM YOUR PHOTO, INTO 3D</p>
        <h1>
          A new dimension <em>to your memories.</em>
        </h1>
        <p>
          Choose one reference photo. Tripo creates a textured model you can
          turn around and download.
        </p>
      </div>
      {!loaded ? (
        <GenerationStatus label="Opening Tripo studio" />
      ) : (
        <>
          {error && <ErrorState>{error}</ErrorState>}
          {!config?.available && (
            <div className="analysis-result" role="status">
              <strong>Tripo generation is not connected yet</strong>
              <p>
                {config?.reason ||
                  "The studio owner needs to finish connecting Tripo before generation is available."}
              </p>
              <p>
                Your photo will not be sent to Tripo until this is ready and you
                approve a generation.
              </p>
            </div>
          )}
          <div className="tripo-layout">
            <section
              className="upload-panel"
              aria-labelledby="tripo-photo-heading"
            >
              <div className="panel-heading">
                <span className="section-number">01</span>
                <div>
                  <h2 id="tripo-photo-heading">Choose your reference</h2>
                  <p>One image for one model.</p>
                </div>
              </div>
              <p className="field-help">
                A clear view of the whole subject works best. For a couple
                model, use a photo showing both people together. Separate
                portraits are not different views of the same subject.
              </p>
              <div className="tripo-upload">
                <input
                  ref={input}
                  type="file"
                  className="file-input"
                  aria-label="Upload Tripo reference photo"
                  accept="image/jpeg,image/png,image/webp"
                  disabled={
                    !!busy ||
                    attempted ||
                    photos.length >= 3 ||
                    !config?.available
                  }
                  onChange={(e) => void upload(e.target.files?.[0])}
                />
                <BrandButton
                  variant="secondary"
                  onClick={() => input.current?.click()}
                  disabled={
                    !!busy ||
                    attempted ||
                    photos.length >= 3 ||
                    !config?.available
                  }
                >
                  <ImagePlus size={18} />
                  Choose a photo
                </BrandButton>
                <p className="field-help">JPG, PNG or WebP · up to 10 MB</p>
              </div>
              {session && photos.length > 0 && (
                <fieldset
                  className="tripo-photos"
                  disabled={!!busy || attempted}
                >
                  <legend>Reference photo</legend>
                  {photos.map((photo, i) => (
                    <label key={photo.id} className="tripo-photo">
                      <PrivateImage
                        url={photo.url}
                        session={session}
                        alt={`Tripo reference photo ${i + 1}`}
                      />
                      <span>
                        <input
                          type="radio"
                          name="tripo-photo"
                          checked={selected === photo.id}
                          onChange={() => {
                            setSelected(photo.id);
                            setPlan(null);
                            setTransfer(false);
                            setCost(false);
                          }}
                        />
                        Photo {i + 1}
                      </span>
                    </label>
                  ))}
                </fieldset>
              )}
              <p className="field-help">
                No face-selection step is required. Tripo generates the complete
                subject from the selected image; resemblance and hidden details
                can vary.
              </p>
              {!attempted && (
                <BrandButton
                  variant="secondary"
                  onClick={reviewPlan}
                  disabled={!!busy || !selected || !config?.available}
                  loading={busy === "plan"}
                >
                  Review generation cost
                </BrandButton>
              )}
              {plan && !attempted && (
                <div className="tripo-plan">
                  <div className="panel-heading">
                    <span className="section-number">02</span>
                    <h2>Review before creating</h2>
                  </div>
                  <p>
                    <strong>
                      {plan.estimated_credits} Tripo credits estimated
                    </strong>{" "}
                    · one textured GLB model
                  </p>
                  <p className="field-help">
                    Model: {plan.model}. One image-to-model generation, with no
                    paid conversion or automatic retry. Any later generation
                    needs a new approval.
                  </p>
                  <label className="consent">
                    <input
                      type="checkbox"
                      checked={transfer}
                      onChange={(e) => setTransfer(e.target.checked)}
                    />
                    <span>
                      I allow this selected photo to be sent to Tripo for 3D
                      generation and confirm I have permission to use it.
                    </span>
                  </label>
                  <label className="consent">
                    <input
                      type="checkbox"
                      checked={cost}
                      onChange={(e) => setCost(e.target.checked)}
                    />
                    <span>
                      I accept the estimated cost of {plan.estimated_credits}{" "}
                      Tripo credits from the connected account for this
                      generation.
                    </span>
                  </label>
                  <label className="field">
                    Generation access code
                    <input
                      type="password"
                      autoComplete="off"
                      value={accessCode}
                      onChange={(e) => setAccessCode(e.target.value)}
                    />
                  </label>
                  <p className="field-help">
                    Provided by the studio owner to authorize credit use. Do not
                    enter a Tripo API key here.
                  </p>
                  <BrandButton
                    className="wide"
                    onClick={submit}
                    loading={busy === "submit"}
                    disabled={
                      !!busy ||
                      !transfer ||
                      !cost ||
                      !accessCode.trim() ||
                      !config?.available
                    }
                  >
                    <Sparkles size={18} />
                    Create with Tripo
                  </BrandButton>
                </div>
              )}
              {attempted && status?.state !== "READY" && (
                <div className="analysis-result" role="status">
                  <strong>
                    {labels[status?.state || ""] ||
                      "Checking your generation request"}
                  </strong>
                  <p>
                    {active.has(status?.state || "")
                      ? `${Math.max(0, Math.min(100, status?.progress || 0))}% · You can leave this page open while we check the same request.`
                      : "No automatic retry will spend more credits. Check the current request before starting another model."}
                  </p>
                  {jobError && <p>{jobError}</p>}
                </div>
              )}
              {session && (
                <BrandButton
                  variant="text"
                  disabled={!!busy}
                  onClick={() =>
                    action("refresh", async () => {
                      await refresh(session);
                    })
                  }
                >
                  Refresh Tripo status
                </BrandButton>
              )}
            </section>
            <section
              className="tripo-preview"
              aria-labelledby="tripo-preview-heading"
            >
              <h2 id="tripo-preview-heading">Your 3D preview</h2>
              {model && session ? (
                <>
                  <ModelViewer
                    mode="tripo"
                    glbUrl={model.url}
                    posterUrl={poster?.url}
                    session={session}
                    revision={1}
                  />
                  <BrandButton
                    onClick={() => download(model)}
                    disabled={!!busy}
                  >
                    <Download size={18} />
                    Download GLB
                  </BrandButton>
                  <p className="field-help">
                    Tripo credits billed:{" "}
                    {status?.credits_consumed ?? "awaiting provider report"}.
                  </p>
                </>
              ) : (
                <div className="tripo-empty">
                  <Sparkles size={36} />
                  <h3>It starts with your photo</h3>
                  <p>
                    Your generated model will appear here. Rotate it, inspect
                    the details, then save the GLB.
                  </p>
                </div>
              )}
              <p className="field-help">
                This is a generated digital model. The fixed couple pose, heart
                base, name engraving and separate character controls belong to
                the <Link href="/studio">sculpted preview</Link>. Tripo results
                need a separate review before any 3D printing.
              </p>
              <p className="field-help">
                The chosen photo is shared with Tripo only after your approval.
                Deleting this studio session removes local files; it does not
                cancel a remote task or guarantee removal from Tripo.
              </p>
            </section>
          </div>
          {session && (
            <div className="tripo-session">
              <p className="field-help">
                Private studio session · expires{" "}
                {new Date(session.expires_at).toLocaleString()}
              </p>
              {!deleteOpen ? (
                <BrandButton variant="text" onClick={() => setDeleteOpen(true)}>
                  Delete this session
                </BrandButton>
              ) : (
                <div className="analysis-result">
                  <p>
                    Delete this session and its local photos and models? This
                    cannot undo a Tripo generation or its credit charge.
                  </p>
                  <BrandButton
                    variant="secondary"
                    disabled={!!busy}
                    onClick={removeSession}
                  >
                    Confirm session deletion
                  </BrandButton>
                  <BrandButton
                    variant="text"
                    disabled={!!busy}
                    onClick={() => setDeleteOpen(false)}
                  >
                    Keep session
                  </BrandButton>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </main>
  );
}
