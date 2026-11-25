import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertCircle, Check, LoaderCircle, UploadCloud } from "lucide-react";
export function BrandButton({
  children,
  variant = "primary",
  loading = false,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "text";
  loading?: boolean;
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={`button button--${variant} ${className}`}
      aria-busy={loading}
    >
      {loading && <LoaderCircle size={18} className="spin" />}
      {children}
    </button>
  );
}
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "error";
}) {
  return (
    <span className={`badge badge--${tone}`}>
      {tone === "success" && <Check size={14} />} {children}
    </span>
  );
}
export function ErrorState({ children }: { children: ReactNode }) {
  return (
    <div className="notice notice--error" role="alert">
      <AlertCircle size={20} />
      <div>{children}</div>
    </div>
  );
}
export function GenerationStatus({
  label,
  detail,
}: {
  label: string;
  detail?: string;
}) {
  return (
    <div className="generation" role="status" aria-live="polite">
      <span className="generation-icon">
        <LoaderCircle className="spin" size={28} />
      </span>
      <h2>{label}</h2>
      <p>
        {detail ||
          "Your preview is taking shape. You can keep this page open while we work."}
      </p>
      <div className="indeterminate" aria-hidden="true" />
    </div>
  );
}
export function Stepper({ step }: { step: number }) {
  return (
    <ol className="stepper" aria-label="Personalization steps">
      {["Your photos", "3D preview", "Confirm"].map((label, i) => (
        <li
          key={label}
          aria-current={step === i ? "step" : undefined}
          className={step >= i ? "active" : ""}
        >
          <span>{step > i ? <Check size={16} /> : i + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}
export function UploaderShell({ children }: { children?: ReactNode }) {
  return (
    <div className="upload-shell">
      <UploadCloud size={30} />
      <strong>A favorite photo. A lovely beginning.</strong>
      <p>
        Choose 1–3 clear photos. Separate portraits of each person work too.
      </p>
      {children}
    </div>
  );
}
