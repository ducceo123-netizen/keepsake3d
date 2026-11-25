"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  Camera,
  Check,
  CheckCheck,
  Download,
  Heart,
  ImagePlus,
  LockKeyhole,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  BrandButton,
  ErrorState,
  GenerationStatus,
  StatusBadge,
  Stepper,
  UploaderShell,
} from "@design/primitives";
import {
  activeStates,
  api,
  privateBlob,
  stateMessages,
  type Artifact,
  type Character,
  type Session,
  type Status,
} from "@/lib/api";
import PrivateImage from "./private-image";
import PhotoAnalysis from "./photo-analysis";
import AppearanceFields from "./appearance-fields";
import { designVersion, type AppearanceDraft } from "@/lib/appearance";
const ModelViewer = dynamic(() => import("./model-viewer"), {
  ssr: false,
  loading: () => (
    <div className="viewer-empty" role="status">
      Preparing your viewer…
    </div>
  ),
});
const STORAGE = "keepsake-local-session-v2";
const namePattern = "[A-Za-z \\x2d]{0,12}";
export default function Studio() {
  const [session, setSession] = useState<Session | null>(null),
    sessionRef = useRef<Session | null>(null),
    [status, setStatus] = useState<Status | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(""),
    [names, setNames] = useState(["", ""]),
    [consent, setConsent] = useState(false),
    [loaded, setLoaded] = useState(false),
    [correcting, setCorrecting] = useState(false),
    [corrections, setCorrections] = useState<{
      left: Character;
      right: Character;
    } | null>(null),
    [deleteOpen, setDeleteOpen] = useState(false),
    [dragging, setDragging] = useState(false),
    [pollVersion, setPollVersion] = useState(0);
  const [appearance, setAppearance] = useState<AppearanceDraft | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const restoreFocus = (event: Event) => {
    if (returnFocus.current?.isConnected) {
      event.preventDefault();
      returnFocus.current.focus();
    }
  };
  const input = useRef<HTMLInputElement>(null),
    firstRemovePhoto = useRef<HTMLButtonElement>(null),
    retryKey = useRef<string | null>(null),
    correctionAttempt = useRef<{ fingerprint: string; key: string } | null>(
      null,
    ),
    mounted = useRef(true);
  useEffect(() => {
    retryKey.current = null;
  }, [appearance, names]);
  const saveSession = (s: Session | null) => {
    correctionAttempt.current = null;
    sessionRef.current = s;
    setSession(s);
    if (s) sessionStorage.setItem(STORAGE, JSON.stringify(s));
    else sessionStorage.removeItem(STORAGE);
  };
  const refresh = useCallback(async (s: Session) => {
    const next = await api<Status>(`/api/v1/sessions/${s.id}/status`, s);
    if (mounted.current && sessionRef.current?.id === s.id) setStatus(next);
    return next;
  }, []);
  useEffect(() => {
    mounted.current = true;
    const saved = sessionStorage.getItem(STORAGE);
    if (saved) {
      try {
        const s = JSON.parse(saved) as Session;
        sessionRef.current = s;
        setSession(s);
        refresh(s)
          .catch((err) => {
            setError(err.message);
          })
          .finally(() => setLoaded(true));
      } catch {
        sessionStorage.removeItem(STORAGE);
        setLoaded(true);
      }
    } else setLoaded(true);
    return () => {
      mounted.current = false;
    };
  }, [refresh]);
  useEffect(() => {
    if (!session || !status || !activeStates.has(status.state)) return;
    let stopped = false,
      timer: ReturnType<typeof setTimeout>,
      failures = 0;
    const poll = async () => {
      try {
        await refresh(session);
        failures = 0;
      } catch (err) {
        failures++;
        if (failures >= 3) {
          setError(
            "We lost the connection to your build. Use Refresh status to reconnect.",
          );
          return;
        }
      }
      if (!stopped) timer = setTimeout(poll, 1500);
    };
    timer = setTimeout(poll, 1000);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [session, status?.state, refresh, pollVersion]);
  async function ensureSession() {
    if (sessionRef.current) return sessionRef.current;
    const s = await api<Session>("/api/v1/customization-sessions", null, {
      method: "POST",
      body: JSON.stringify({
        design_id: "better-together",
        design_version: designVersion,
      }),
    });
    saveSession(s);
    return s;
  }
  async function action(label: string, run: () => Promise<void>) {
    if (busy) return;
    setBusy(label);
    setError("");
    try {
      await run();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Please try again.");
    } finally {
      setBusy("");
    }
  }
  async function upload(files: FileList | File[] | null) {
    if (!files?.length) return;
    await action("upload", async () => {
      setAppearance(null);
      if ((status?.photos.length || 0) + files.length > 3)
        throw new Error(
          "Choose up to 3 photos. Remove a photo first to replace it.",
        );
      for (const f of Array.from(files)) {
        if (!["image/jpeg", "image/png", "image/webp"].includes(f.type))
          throw new Error("Please choose a JPEG, PNG, or WebP photo.");
        if (f.size > 10 * 1024 * 1024)
          throw new Error("Each photo needs to be 10 MB or smaller.");
      }
      const s = await ensureSession();
      for (const f of Array.from(files)) {
        const body = new FormData();
        body.append("file", f);
        await api(`/api/v1/sessions/${s.id}/photos`, s, {
          method: "POST",
          body,
        });
        await refresh(s);
      }
    });
    if (input.current) input.current.value = "";
  }
  async function submit() {
    if (!consent || !session || !status?.photos.length || !appearance) return;
    await action("generate", async () => {
      const profile = await api<{ id: string; sha256: string }>(
        `/api/v1/sessions/${session.id}/appearance-profile`,
        session,
        { method: "POST", body: JSON.stringify(appearance) },
      );
      const idempotency = retryKey.current || crypto.randomUUID();
      retryKey.current = idempotency;
      await api(`/api/v1/sessions/${session.id}/submit`, session, {
        method: "POST",
        headers: { "Idempotency-Key": idempotency },
        body: JSON.stringify({
          consent: true,
          names,
          appearance_profile_id: profile.id,
          appearance_profile_sha256: profile.sha256,
        }),
      });
      await refresh(session);
      retryKey.current = null;
    });
  }
  async function sendCorrections(
    characters: Record<string, Partial<Character>>,
  ) {
    if (!session || !status) return;
    const body = JSON.stringify({ characters });
    const fingerprint = JSON.stringify([session.id, status.revision, body]);
    if (correctionAttempt.current?.fingerprint !== fingerprint)
      correctionAttempt.current = { fingerprint, key: crypto.randomUUID() };
    await api(`/api/v1/sessions/${session.id}/corrections`, session, {
      method: "POST",
      headers: { "Idempotency-Key": correctionAttempt.current.key },
      body,
    });
    // Keep the same request key if either acceptance or status reconciliation
    // loses its response. A retry recovers that build instead of enqueuing twice.
    await refresh(session);
    correctionAttempt.current = null;
  }
  async function retryBuild() {
    if (!session || !status?.params) return;
    await action("generate", async () => {
      const characters = status.params!.characters;
      await sendCorrections(characters);
      setPollVersion((v) => v + 1);
    });
  }
  async function approve() {
    if (!session || !status) return;
    await action("approve", async () => {
      await api(`/api/v1/sessions/${session.id}/approve`, session, {
        method: "POST",
        body: JSON.stringify({
          model_revision: status.revision,
          job_checksum: status.checksum,
        }),
      });
      await refresh(session);
    });
  }
  async function applyCorrections() {
    if (!session || !corrections || !status?.params) return;
    await action("correct", async () => {
      const characters = Object.fromEntries(
        (["left", "right"] as const).map((slot) => {
          const previous = status.params!.characters[slot],
            next = corrections[slot];
          const fields: Partial<Character> = Object.fromEntries(
            Object.entries(next).filter(
              ([key, value]) =>
                key !== "face_morphs" &&
                value !== previous[key as keyof Character],
            ),
          );
          const morphs = Object.fromEntries(
            Object.entries(next.face_morphs).filter(
              ([key, value]) => value !== previous.face_morphs[key],
            ),
          );
          if (Object.keys(morphs).length) fields.face_morphs = morphs;
          return [slot, fields];
        }),
      );
      if (
        Object.values(characters).some((fields) => Object.keys(fields).length)
      )
        await sendCorrections(characters);
      setCorrecting(false);
      setAppearance(null);
    });
  }
  async function download(artifact: Artifact) {
    if (!session) return;
    await action(artifact.kind, async () => {
      const blob = await privateBlob(artifact.url, session),
        url = URL.createObjectURL(blob),
        a = document.createElement("a");
      a.href = url;
      a.download =
        artifact.filename ||
        `keepsake-rev-${status?.revision}.${artifact.kind === "provenance" || artifact.kind === "qa" ? "json" : artifact.kind}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  async function deleteSession() {
    await action("delete", async () => {
      if (session)
        await api(`/api/v1/sessions/${session.id}`, session, {
          method: "DELETE",
        });
      saveSession(null);
      setStatus(null);
      setAppearance(null);
      setConsent(false);
      setNames(["", ""]);
      setDeleteOpen(false);
      setCorrecting(false);
    });
  }
  const state = status?.state || "CREATED",
    isRunning = activeStates.has(state),
    isReady = state === "PREVIEW_READY" || state === "CUSTOMER_APPROVED",
    isApproved = state === "CUSTOMER_APPROVED",
    isFailed = state === "FAILED" || state === "MANUAL_REVIEW_REQUIRED",
    isUpload = !isRunning && !isReady && !isFailed;
  const photoCount = status?.photos.length || 0;
  const poster = status?.artifacts.find((a) => a.kind === "png"),
    glb = status?.artifacts.find((a) => a.kind === "glb");
  return (
    <main id="main" className="studio page-width">
      <div className="studio-top">
        <Link className="back-link" href="/">
          The collection
        </Link>
        <StatusBadge>Photo studio · Beta</StatusBadge>
      </div>
      <div className="analysis-result">
        <strong>Try photo-to-3D with Tripo</strong>
        <p>
          Create a complete model directly from one reference photo, without the
          face-selection step.
        </p>
        <Link className="button button--secondary" href="/studio/tripo">
          Open Tripo studio
        </Link>
      </div>
      <Stepper
        step={isApproved ? 2 : isReady || isRunning || isFailed ? 1 : 0}
      />
      <div className="studio-heading">
        <p className="eyebrow">BETTER TOGETHER</p>
        <h1>
          {isApproved ? (
            <>
              A little moment, <em>kept.</em>
            </>
          ) : isReady ? (
            <>
              Hello, <em>you two.</em>
            </>
          ) : isRunning ? (
            <>
              Your story is <em>taking shape.</em>
            </>
          ) : (
            <>
              It starts with <em>the two of you.</em>
            </>
          )}
        </h1>
        <p>
          {isApproved
            ? "Your digital preview is approved. This demo hasn’t placed an order."
            : isReady
              ? "Turn it around. Look a little closer. Make the little details feel like you."
              : isRunning
                ? "We’re creating and checking your actual 3D model files."
                : "Choose a favorite photo, add your names, and explore your keepsake."}
        </p>
      </div>
      {error && (
        <div className="studio-error">
          <ErrorState>{error}</ErrorState>
          {session && (
            <BrandButton
              variant="text"
              onClick={() =>
                action("refresh", async () => {
                  await refresh(session);
                  setPollVersion((v) => v + 1);
                })
              }
            >
              Refresh status
            </BrandButton>
          )}
          {session && !status && (
            <BrandButton
              variant="text"
              onClick={() => {
                saveSession(null);
                setError("");
              }}
            >
              Start a fresh session
            </BrandButton>
          )}
        </div>
      )}
      {!loaded ? (
        <GenerationStatus label="Opening your studio" />
      ) : isUpload ? (
        <div className="upload-layout">
          <section className="upload-panel" aria-labelledby="photo-heading">
            <div className="panel-heading">
              <span className="section-number">01</span>
              <div>
                <h2 id="photo-heading">Your favorite photos</h2>
                <p>A clear face, good light, and a little you.</p>
              </div>
              <span className="photo-counter">{photoCount}/3</span>
            </div>
            <div
              className={dragging ? "drop-area dragging" : "drop-area"}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                upload(e.dataTransfer.files);
              }}
            >
              <UploaderShell>
                <input
                  ref={input}
                  className="file-input"
                  id="photos"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  onChange={(e) => upload(e.target.files)}
                  disabled={!!busy || photoCount >= 3}
                  aria-label="Upload reference photos"
                />
                <BrandButton
                  variant="secondary"
                  onClick={() => input.current?.click()}
                  loading={busy === "upload"}
                  disabled={!!busy || photoCount >= 3}
                >
                  <ImagePlus size={18} />
                  Choose photos
                </BrandButton>
                <span className="upload-help">
                  or drop them here · JPG, PNG, WebP · up to 10 MB each
                </span>
              </UploaderShell>
            </div>
            {photoCount > 0 && session && (
              <div className="uploaded-photos">
                {status!.photos.map((p, i) => (
                  <div className="photo-card" key={p.id}>
                    <PrivateImage
                      url={p.url}
                      session={session}
                      alt={`Your private reference photo ${i + 1}`}
                    />
                    <button
                      ref={i === 0 ? firstRemovePhoto : undefined}
                      aria-label={`Remove photo ${i + 1}`}
                      disabled={!!busy}
                      onClick={() =>
                        action("remove", async () => {
                          setAppearance(null);
                          await api(
                            `/api/v1/sessions/${session.id}/photos/${p.id}`,
                            session,
                            { method: "DELETE" },
                          );
                          await refresh(session);
                        })
                      }
                    >
                      <X size={16} />
                    </button>
                    <span>
                      <Check size={13} />
                      Photo {i + 1}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div className="private-note">
              <LockKeyhole size={16} />
              <p>
                Private to this session. Photo analysis runs on your device;
                photos are not sent to an external AI provider. This temporary
                studio may clear your session when the server restarts.
              </p>
            </div>
            <label className="consent">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span>
                I have permission to use these photos and agree to analysis on
                this device and private server storage until{" "}
                {session
                  ? new Date(session.expires_at).toLocaleString()
                  : "this session expires"}
                , or earlier if I delete this session or the server restarts.
              </span>
            </label>
            {session && photoCount > 0 && (
              <PhotoAnalysis
                key={status!.photos.map((p) => p.id).join(":")}
                photos={status!.photos}
                session={session}
                consent={consent}
                disabled={!!busy}
                onReady={setAppearance}
                onEditPhotos={() => {
                  const target =
                    photoCount >= 3 ? firstRemovePhoto.current : input.current;
                  target?.scrollIntoView({
                    block: "center",
                    behavior: "auto",
                  });
                  target?.focus({ preventScroll: true });
                }}
              />
            )}
            <div className="panel-heading names-heading">
              <span className="section-number">03</span>
              <div>
                <h2>A little personal touch</h2>
                <p>Add your names, if you’d like.</p>
              </div>
              <span className="optional">Optional</span>
            </div>
            <div className="names-grid">
              {["Left character name", "Right character name"].map(
                (label, i) => (
                  <label className="field" key={label}>
                    {label}
                    <input
                      value={names[i]}
                      onChange={(e) =>
                        setNames((n) =>
                          n.map((v, j) => (i === j ? e.target.value : v)),
                        )
                      }
                      placeholder={i === 0 ? "e.g. Alex" : "e.g. Jamie"}
                      maxLength={12}
                      pattern={namePattern}
                      title="Up to 12 letters, spaces, or hyphens"
                    />
                  </label>
                ),
              )}
            </div>
            <p className="field-help">
              Up to 12 letters, spaces, or hyphens. Demo names appear as raised
              labels.
            </p>
            <BrandButton
              className="wide"
              loading={busy === "generate"}
              disabled={
                !!busy ||
                !photoCount ||
                !consent ||
                !appearance ||
                names.some((n) => !/^[A-Za-z -]{0,12}$/.test(n))
              }
              onClick={submit}
            >
              <Sparkles size={18} />
              Create my 3D preview
            </BrandButton>
            <p className="cta-caption">No payment · Preview before approval</p>
          </section>
          <aside className="studio-aside">
            <div className="mini-concept">
              <img
                src="/better-together-concept.png"
                alt="Better Together concept inspiration"
              />
              <span>CONCEPT ART · NOT YOUR GENERATED MODEL</span>
            </div>
            <h2>Two pieces. One story.</h2>
            <p>A small reminder of your favorite person.</p>
            <div className="aside-details">
              <h3>A thoughtful place to start</h3>
              <p>
                <Camera size={18} />
                Clear photos work best
              </p>
              <p>
                <Heart size={18} />
                Names are always optional
              </p>
              <p>
                <ShieldCheck size={18} />
                Your preview is yours to review
              </p>
            </div>
            <div className="demo-note">
              <strong>A stylized keepsake, guided by your photos</strong>
              <p>
                Face proportions and visible colors come from your selected
                photos. You choose hair style and accessories. The sculpted body
                and pose stay fixed; this beta does not promise an exact
                likeness or reproduce the concept artwork.
              </p>
            </div>
          </aside>
        </div>
      ) : isRunning ? (
        <div className="processing-card">
          <GenerationStatus
            label={stateMessages[state] || "Creating your preview"}
            detail="We’re applying your reviewed face proportions and colors, then rendering and checking your model. This can take a few minutes."
          />
          <div className="processing-foot">
            <StatusBadge>Revision {status?.revision}</StatusBadge>
            <span>Photo proportions · Your reviewed details</span>
          </div>
        </div>
      ) : isFailed ? (
        <div className="failure-card">
          <ErrorState>
            {status?.error?.message ||
              "This model needs review before it can be shown. Please try again or start a fresh session."}
          </ErrorState>
          <BrandButton
            onClick={retryBuild}
            loading={busy === "generate"}
            disabled={!!busy}
          >
            Try the build again
          </BrandButton>
          <p>Your photos are still private. No preview has been approved.</p>
        </div>
      ) : isReady && session && status ? (
        <div className="preview-layout">
          <section className="preview-main">
            <ModelViewer
              key={status.revision}
              session={session}
              glbUrl={glb?.url}
              posterUrl={poster?.url}
              revision={status.revision}
            />
            <div className="reference-strip">
              <span>Your reference</span>
              {status.photos.map((p, i) => (
                <PrivateImage
                  key={p.id}
                  url={p.url}
                  session={session}
                  alt={`Private reference ${i + 1}`}
                />
              ))}
              <p>
                Built from the face proportions and colors of your selected
                photos, with the details you reviewed. A stylized
                interpretation.
              </p>
            </div>
            <details className="technical-details">
              <summary>
                Model files & revision details <SlidersHorizontal size={17} />
              </summary>
              <div className="provenance-summary">
                <p>
                  <strong>Design:</strong> better-together · {designVersion}
                </p>
                <p>
                  <strong>Model revision:</strong> {status.revision}
                </p>
                <p>
                  <strong>Build checksum:</strong>{" "}
                  <code>{status.checksum}</code>
                </p>
                <p>
                  The GLB, STL, and rendered image originate from one configured
                  scene. STL contains geometry only. File checks do not
                  establish printability or physical fit.
                </p>
              </div>
              <div className="download-list">
                {status.artifacts.map((a) => (
                  <BrandButton
                    variant="secondary"
                    key={a.url}
                    loading={busy === a.kind}
                    disabled={!!busy}
                    onClick={() => download(a)}
                  >
                    <Download size={16} />
                    {a.kind.toUpperCase()}
                  </BrandButton>
                ))}
              </div>
              {status.qa && (
                <details className="qa-json">
                  <summary>Read geometry QA report</summary>
                  <pre>{JSON.stringify(status.qa, null, 2)}</pre>
                </details>
              )}
            </details>
          </section>
          <aside className="approval-panel">
            <StatusBadge tone={isApproved ? "success" : "warning"}>
              {isApproved
                ? "Preview approved"
                : "Demo model · not print approved"}
            </StatusBadge>
            <h2>
              {isApproved
                ? "A keepsake in the making."
                : "The little details are yours."}
            </h2>
            <p>
              {isApproved
                ? "Your approval is saved against this exact model revision. You can still adjust the details; a new revision will need a new approval."
                : "This is your actual model preview. Take a moment to review it from every angle."}
            </p>
            <dl className="preview-specs">
              <div>
                <dt>Design</dt>
                <dd>Better Together</dd>
              </div>
              <div>
                <dt>Names</dt>
                <dd>
                  {status.params?.characters.left.engraving_text || "No name"} &{" "}
                  {status.params?.characters.right.engraving_text || "No name"}
                </dd>
              </div>
              <div>
                <dt>Revision</dt>
                <dd>{String(status.revision).padStart(2, "0")}</dd>
              </div>
              <div>
                <dt>Model type</dt>
                <dd>Photo-personalized, stylized</dd>
              </div>
            </dl>
            {!isApproved ? (
              <BrandButton
                className="wide"
                loading={busy === "approve"}
                disabled={!!busy}
                onClick={approve}
              >
                <Check size={18} />
                Approve this preview
              </BrandButton>
            ) : (
              <div className="approved-message">
                <CheckCheck size={22} />
                <span>Revision {status.revision} approved</span>
              </div>
            )}
            <BrandButton
              variant="secondary"
              className="wide"
              disabled={!!busy}
              onClick={(event) => {
                returnFocus.current = event.currentTarget;
                setCorrections(status.params?.characters || null);
                setCorrecting(true);
              }}
            >
              <SlidersHorizontal size={17} />
              Adjust the details
            </BrandButton>
            <div className="demo-note">
              <strong>
                {isApproved
                  ? "What happens next?"
                  : "A preview, with perspective"}
              </strong>
              <p>
                {isApproved
                  ? "There’s no checkout or manufacturing in this demo. A professional master model and physical print validation are still needed before a real keepsake can be ordered."
                  : "The final materials and finish haven’t been established. Approving this digital demo is not a print approval or an order."}
              </p>
            </div>
          </aside>
        </div>
      ) : null}
      {session && (
        <div className="session-footer">
          <span>
            <LockKeyhole size={14} />
            Your private session · expires{" "}
            {new Date(session.expires_at).toLocaleString()}
          </span>
          <BrandButton
            variant="text"
            onClick={(event) => {
              returnFocus.current = event.currentTarget;
              setDeleteOpen(true);
            }}
          >
            <Trash2 size={15} />
            Delete session & photos
          </BrandButton>
        </div>
      )}
      <Dialog.Root open={correcting} onOpenChange={setCorrecting}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content
            className="dialog-content correction-dialog"
            onCloseAutoFocus={restoreFocus}
          >
            <Dialog.Title>Make the little details yours</Dialog.Title>
            <Dialog.Description>
              Choose supported demo options. Saving creates a new model
              revision, with a new preview to approve.
            </Dialog.Description>
            {corrections && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  applyCorrections();
                }}
              >
                <div className="correction-columns">
                  {(["left", "right"] as const).map((slot) => (
                    <fieldset key={slot}>
                      <legend>
                        {slot === "left" ? "Left character" : "Right character"}
                      </legend>
                      <AppearanceFields
                        value={corrections[slot]}
                        disabled={!!busy}
                        onChange={(value) =>
                          setCorrections((c) =>
                            c ? { ...c, [slot]: value } : c,
                          )
                        }
                      />
                      <label className="field">
                        Name
                        <input
                          maxLength={12}
                          pattern={namePattern}
                          value={corrections[slot].engraving_text}
                          onChange={(e) =>
                            setCorrections((c) =>
                              c
                                ? {
                                    ...c,
                                    [slot]: {
                                      ...c[slot],
                                      engraving_text: e.target.value,
                                    },
                                  }
                                : c,
                            )
                          }
                        />
                      </label>
                    </fieldset>
                  ))}
                </div>
                <BrandButton
                  type="submit"
                  className="wide"
                  loading={busy === "correct"}
                  disabled={!!busy}
                >
                  Save & create a new preview
                </BrandButton>
                {error && <ErrorState>{error}</ErrorState>}
              </form>
            )}
            <Dialog.Close
              className="dialog-close"
              aria-label="Close corrections"
            >
              <X />
            </Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <Dialog.Root open={deleteOpen} onOpenChange={setDeleteOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content
            className="dialog-content delete-dialog"
            onCloseAutoFocus={restoreFocus}
          >
            <Dialog.Title>Delete this keepsake session?</Dialog.Title>
            <Dialog.Description>
              Your photos, generated files, and preview approval will be removed
              from server storage. You can start again with a fresh session.
            </Dialog.Description>
            <div className="inline">
              <BrandButton
                loading={busy === "delete"}
                disabled={!!busy}
                onClick={deleteSession}
              >
                Delete session & files
              </BrandButton>
              <Dialog.Close asChild>
                <BrandButton variant="secondary">Keep my session</BrandButton>
              </Dialog.Close>
            </div>
            <Dialog.Close
              className="dialog-close"
              aria-label="Close deletion dialog"
            >
              <X />
            </Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </main>
  );
}
