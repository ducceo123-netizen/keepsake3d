"use client";
import { useEffect, useRef, useState } from "react";
import {
  Expand,
  RotateCcw,
  Move,
  ZoomIn,
  ZoomOut,
  X,
  MoveHorizontal,
  Image as ImageIcon,
} from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { BrandButton, ErrorState } from "@design/primitives";
import { usePrivateBlob } from "./private-image";
import type { Session } from "@/lib/api";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
type View = "Perspective" | "Front" | "Side" | "Back";
function Scene({
  url,
  view,
  zoom,
  reset,
  separated,
  onError,
  onReady,
}: {
  url: string;
  view: View;
  zoom: number;
  reset: number;
  separated: boolean;
  onError: (message: string) => void;
  onReady: () => void;
}) {
  const assemblies = useRef<
    Array<{ node: THREE.Object3D; position: THREE.Vector3; direction: number }>
  >([]);
  const host = useRef<HTMLDivElement>(null),
    control = useRef<{
      camera: THREE.PerspectiveCamera;
      orbit: OrbitControls;
      render: () => void;
    } | null>(null);
  useEffect(() => {
    if (!host.current) return;
    let disposed = false;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onError(
        "Interactive 3D is unavailable on this device. You can still download the model file.",
      );
      return;
    }
    const element = host.current;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.setClearColor(0, 0);
    element.appendChild(renderer.domElement);
    renderer.domElement.setAttribute(
      "aria-label",
      "Interactive 3D demo model. Drag to rotate; use the view and zoom buttons for keyboard controls.",
    );
    renderer.domElement.setAttribute("role", "img");
    const style = getComputedStyle(document.documentElement),
      white = new THREE.Color(style.getPropertyValue("--ks-white").trim()),
      ground = new THREE.Color(style.getPropertyValue("--ks-muted").trim());
    const scene = new THREE.Scene(),
      camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
    camera.position.set(3, 2.2, 4.4);
    const orbit = new OrbitControls(camera, renderer.domElement);
    orbit.target.set(0, 0, 0);
    orbit.enablePan = false;
    orbit.enableZoom = false;
    orbit.minDistance = 2;
    orbit.maxDistance = 8;
    orbit.enableDamping = false;
    scene.add(new THREE.HemisphereLight(white, ground, 2.4));
    const key = new THREE.DirectionalLight(white, 3);
    key.position.set(3, 5, 4);
    scene.add(key);
    const fill = new THREE.DirectionalLight(white, 1);
    fill.position.set(-4, 2, -3);
    scene.add(fill);
    const render = () => {
      if (!disposed) renderer.render(scene, camera);
    };
    control.current = { camera, orbit, render };
    orbit.addEventListener("change", render);
    const resize = () => {
      const width = element.clientWidth,
        height = element.clientHeight;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.zoom = Math.min(1, camera.aspect);
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    const disposeModel = (root: THREE.Object3D) =>
      root.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose();
          const materials = Array.isArray(obj.material)
            ? obj.material
            : [obj.material];
          materials.forEach((mat) => {
            for (const value of Object.values(mat))
              if (value instanceof THREE.Texture) value.dispose();
            mat.dispose();
          });
        }
      });
    new GLTFLoader().load(
      url,
      (gltf) => {
        if (disposed) {
          disposeModel(gltf.scene);
          return;
        }
        const bounds = new THREE.Box3().setFromObject(gltf.scene);
        const size = bounds.getSize(new THREE.Vector3());
        const center = bounds.getCenter(new THREE.Vector3());
        const scale = 2.6 / Math.max(size.x, size.y, size.z);
        gltf.scene.position.copy(center).multiplyScalar(-scale);
        gltf.scene.scale.setScalar(scale);
        scene.add(gltf.scene);
        assemblies.current = ["ASSEMBLY_LEFT", "ASSEMBLY_RIGHT"].flatMap(
          (name, i) => {
            const node = gltf.scene.getObjectByName(name);
            return node
              ? [
                  {
                    node,
                    position: node.position.clone(),
                    direction: i === 0 ? -1 : 1,
                  },
                ]
              : [];
          },
        );
        if (separated)
          for (const item of assemblies.current)
            item.node.position.x += item.direction * 0.55;
        render();
        onReady();
      },
      undefined,
      () => {
        if (!disposed)
          onError(
            "The interactive model could not be loaded. You can retry the viewer or download the model file.",
          );
      },
    );
    return () => {
      disposed = true;
      control.current = null;
      observer.disconnect();
      orbit.dispose();
      disposeModel(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
    // callbacks are stable state setters in the viewer
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);
  useEffect(() => {
    const c = control.current;
    if (!c) return;
    const positions: Record<View, [number, number, number]> = {
      Perspective: [3, 2.2, 4.4],
      Front: [0, 1, 5.4],
      Side: [5.4, 1, 0],
      Back: [0, 1, -5.4],
    };
    c.camera.position.set(...positions[view]);
    c.camera.position.multiplyScalar(zoom);
    c.orbit.target.set(0, 0, 0);
    c.orbit.update();
    c.render();
  }, [view, zoom, reset]);
  useEffect(() => {
    for (const item of assemblies.current) {
      item.node.position.copy(item.position);
      if (separated) item.node.position.x += item.direction * 0.55;
    }
    control.current?.render();
  }, [separated]);
  return <div className="three-canvas" ref={host} />;
}
export default function ModelViewer({
  glbUrl,
  posterUrl,
  session,
  revision,
  mode = "sculpted",
}: {
  glbUrl?: string;
  posterUrl?: string;
  session: Session;
  revision: number;
  mode?: "sculpted" | "tripo";
}) {
  const returnFocus = useRef<HTMLElement | null>(null);
  const [retry, setRetry] = useState(0);
  const model = usePrivateBlob(glbUrl, session, retry),
    poster = usePrivateBlob(posterUrl, session);
  const [view, setView] = useState<View>("Perspective"),
    [zoom, setZoom] = useState(1),
    [reset, setReset] = useState(0),
    [error, setError] = useState(""),
    [ready, setReady] = useState(false),
    [showPoster, setShowPoster] = useState(false),
    [fullscreen, setFullscreen] = useState(false),
    [separated, setSeparated] = useState(false);
  useEffect(() => {
    setError("");
    setReady(false);
    setShowPoster(false);
  }, [glbUrl]);
  const controls = (
    <>
      <div className="view-tabs" aria-label="Camera views">
        {(["Perspective", "Front", "Side", "Back"] as View[]).map((v) => (
          <button
            key={v}
            onClick={() => {
              setView(v);
              setShowPoster(false);
            }}
            aria-pressed={view === v && !showPoster}
          >
            {v === "Perspective" ? "3/4 view" : v}
          </button>
        ))}
      </div>
      <div className="viewer-tools">
        <button
          onClick={() => setZoom((z) => Math.max(0.55, z - 0.15))}
          aria-label="Zoom in"
        >
          <ZoomIn size={18} />
        </button>
        <button
          onClick={() => setZoom((z) => Math.min(1.4, z + 0.15))}
          aria-label="Zoom out"
        >
          <ZoomOut size={18} />
        </button>
        <button
          onClick={() => {
            setView("Perspective");
            setZoom(1);
            setReset((r) => r + 1);
            setSeparated(false);
            setShowPoster(false);
          }}
          aria-label="Reset model view"
        >
          <RotateCcw size={18} />
        </button>
        {mode === "sculpted" && (
          <button
            onClick={() => {
              setSeparated((v) => !v);
              setShowPoster(false);
            }}
            disabled={!ready}
            aria-label="Show separated halves"
            aria-pressed={separated}
          >
            <MoveHorizontal size={18} />
          </button>
        )}
        {posterUrl && (
          <button
            onClick={() => setShowPoster((p) => !p)}
            aria-label="Toggle rendered image"
            aria-pressed={showPoster}
          >
            <ImageIcon size={18} />
          </button>
        )}
      </div>
    </>
  );
  const content = (
    <>
      <div className="model-stage">
        <div className="viewer-topline">
          <span>3D MODEL PREVIEW</span>
          <span>Revision {String(revision).padStart(2, "0")}</span>
        </div>
        {poster.url && (!ready || error || showPoster) && (
          <img
            className="model-poster"
            src={poster.url}
            alt={`Rendered ${mode === "tripo" ? "Tripo" : "procedural demo"} model, revision ${revision}`}
          />
        )}
        <div
          style={{
            visibility: error || showPoster ? "hidden" : "visible",
            height: "100%",
          }}
        >
          {model.url && (
            <Scene
              url={model.url}
              view={view}
              zoom={zoom}
              reset={reset}
              separated={separated}
              onError={setError}
              onReady={() => setReady(true)}
            />
          )}
        </div>
        {!ready && !error && !model.error && !showPoster && (
          <div className="viewer-loading" role="status">
            Loading your model…
          </div>
        )}
        <div className="viewer-bottomline">
          <span>
            <Move size={14} />
            Drag to rotate · use zoom controls
          </span>
          <span>
            {mode === "tripo"
              ? "Tripo generated model"
              : separated
                ? "Separated · fit unverified"
                : "Procedural demo"}
          </span>
        </div>
      </div>
      <div className="viewer-controls">{controls}</div>
    </>
  );
  return (
    <div className="model-viewer">
      {!fullscreen && content}
      {(error || model.error) && (
        <p className="viewer-fallback" role="status">
          {error || model.error}{" "}
          <BrandButton
            variant="text"
            onClick={() => {
              setError("");
              setReady(false);
              setRetry((v) => v + 1);
            }}
          >
            Retry interactive model
          </BrandButton>
        </p>
      )}
      <div className="viewer-caption">
        <span>The preview and downloads share this model revision.</span>
        <BrandButton
          variant="text"
          onClick={(event) => {
            returnFocus.current = event.currentTarget;
            setFullscreen(true);
          }}
        >
          <Expand size={16} />
          Expand
        </BrandButton>
      </div>
      <Dialog.Root open={fullscreen} onOpenChange={setFullscreen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content
            className="dialog-content model-dialog"
            onCloseAutoFocus={(event) => {
              if (returnFocus.current?.isConnected) {
                event.preventDefault();
                returnFocus.current.focus();
              }
            }}
          >
            <Dialog.Title>Your keepsake, a little closer</Dialog.Title>
            <Dialog.Description>
              Digital demo model · revision {revision}. Not approved for
              manufacturing.
            </Dialog.Description>
            {fullscreen && content}
            <Dialog.Close
              className="dialog-close"
              aria-label="Close full-screen preview"
            >
              <X />
            </Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
