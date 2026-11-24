import type { Metadata } from "next";
export const metadata: Metadata = { title: "Design system — Keepsake 3D" };
import {
  BrandButton,
  ErrorState,
  GenerationStatus,
  StatusBadge,
  Stepper,
  UploaderShell,
} from "@design/primitives";
export default function Gallery() {
  return (
    <main id="main" className="page-width gallery">
      <p className="eyebrow">The foundations</p>
      <h1>Soft Keepsake Editorial</h1>
      <p>A shared language for a thoughtful, photo-first experience.</p>
      <section>
        <h2>Color & type</h2>
        <div className="swatches">
          {[
            "canvas",
            "surface",
            "primary",
            "heading",
            "blush",
            "success",
            "warning",
            "error",
          ].map((s) => (
            <div key={s}>
              <span style={{ background: `var(--ks-${s})` }} />
              {s}
            </div>
          ))}
        </div>
        <h2>
          Two pieces. <em>One story.</em>
        </h2>
        <p>Fraunces for feelings. DM Sans for everything else.</p>
      </section>
      <section>
        <h2>Buttons & fields</h2>
        <div className="inline">
          <BrandButton>Create your keepsake</BrandButton>
          <BrandButton variant="secondary">Use a sample</BrandButton>
          <BrandButton loading>Creating</BrandButton>
          <BrandButton disabled>Unavailable</BrandButton>
        </div>
        <label className="field">
          Optional engraving
          <input placeholder="Alex" maxLength={12} />
        </label>
      </section>
      <section>
        <h2>Progress & status</h2>
        <Stepper step={1} />
        <div className="inline">
          <StatusBadge>Concept image</StatusBadge>
          <StatusBadge tone="warning">Demo model</StatusBadge>
          <StatusBadge tone="success">Preview approved</StatusBadge>
        </div>
      </section>
      <section>
        <h2>Upload & feedback</h2>
        <UploaderShell>
          <span>Keyboard-accessible file input in the studio</span>
        </UploaderShell>
        <ErrorState>
          That photo couldn’t be read. Please choose a PNG, JPEG, or WebP image.
        </ErrorState>
      </section>
      <section>
        <h2>Generation & viewer shell</h2>
        <GenerationStatus
          label="Making your little moment"
          detail="Example processing state. Actual jobs show their current stage without a fabricated percentage."
        />
        <div className="viewer-empty">
          <span>3D model preview</span>
          <p>Model loads here when its revision is ready.</p>
        </div>
      </section>
      <section>
        <h2>Preview approval</h2>
        <div className="notice">
          <div>
            <strong>Take a moment to make it yours.</strong>
            <p>
              Review the current model revision before approving. Digital
              preview approval is separate from manufacturing approval.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
