import {
  correctionOptions,
  correctionLabels,
  morphLabels,
} from "@/lib/appearance";
import type { Character } from "@/lib/api";

export default function AppearanceFields({
  value,
  onChange,
  disabled = false,
}: {
  value: Character;
  onChange: (value: Character) => void;
  disabled?: boolean;
}) {
  return (
    <>
      <div className="appearance-fields">
        {Object.entries(correctionOptions).map(([key, options]) => (
          <label className="field" key={key}>
            {correctionLabels[key]}
            <select
              disabled={disabled}
              value={String(value[key as keyof Character])}
              onChange={(e) => onChange({ ...value, [key]: e.target.value })}
            >
              {options.map((o) => (
                <option key={o} value={o}>
                  {o.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase())}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <details className="face-adjustments">
        <summary>Fine-tune face proportions</summary>
        <p>
          These controls shape a stylized face. Depth and brow details start
          from the sculpted default.
        </p>
        {Object.entries(morphLabels).map(([key, label]) => (
          <label className="morph-field" key={key}>
            <span>
              {label}
              <output>{Math.round((value.face_morphs[key] || 0) * 100)}</output>
            </span>
            <input
              type="range"
              min={-1}
              max={1}
              step={0.05}
              disabled={disabled}
              value={value.face_morphs[key] || 0}
              onChange={(e) =>
                onChange({
                  ...value,
                  face_morphs: {
                    ...value.face_morphs,
                    [key]: Number(e.target.value),
                  },
                })
              }
            />
          </label>
        ))}
      </details>
    </>
  );
}
