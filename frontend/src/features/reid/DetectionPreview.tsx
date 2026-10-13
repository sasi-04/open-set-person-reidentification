/**
 * DetectionPreview: the uploaded image with the detected people drawn on it.
 *
 * In plain words: each detected person is an actual <button> placed over the picture at
 * the detector's real box coordinates, so people can be selected with a mouse, a finger
 * or the keyboard. The number shown on a box is the DETECTOR's confidence that it is a
 * person - it is labelled as such, and is unrelated to who the person might be.
 */
import clsx from "clsx";
import type { Tone } from "@/lib/present";

export interface BoxOverlay {
  key: number;
  box: number[]; // [x1, y1, x2, y2] in image pixels
  label: string;
  ariaLabel: string;
  selected: boolean;
  tone?: Tone | "pending";
  onSelect?: () => void;
}

const TONE_COLOUR: Record<string, string> = {
  ok: "var(--ok)",
  warn: "var(--warn)",
  neutral: "var(--neutral)",
  bad: "var(--bad)",
  info: "var(--info)",
  brand: "var(--brand)",
  pending: "var(--info)",
};

export function DetectionPreview({
  src,
  alt,
  size,
  overlays,
  busy,
}: {
  src: string;
  alt: string;
  size: { width: number; height: number } | null;
  overlays: BoxOverlay[];
  busy?: boolean;
}) {
  return (
    <div className="relative mx-auto w-fit max-w-full overflow-hidden rounded-md bg-surface-2">
      <img src={src} alt={alt} className="block max-h-[min(68dvh,640px)] w-auto max-w-full" draggable={false} />
      {size &&
        overlays.map((overlay) => {
          const [x1, y1, x2, y2] = overlay.box;
          const colour = TONE_COLOUR[overlay.tone ?? "pending"];
          return (
            <button
              key={overlay.key}
              type="button"
              aria-label={overlay.ariaLabel}
              aria-pressed={overlay.selected}
              onClick={overlay.onSelect}
              disabled={!overlay.onSelect}
              style={{
                left: `${(x1 / size.width) * 100}%`,
                top: `${(y1 / size.height) * 100}%`,
                width: `${((x2 - x1) / size.width) * 100}%`,
                height: `${((y2 - y1) / size.height) * 100}%`,
                borderColor: colour,
                boxShadow: overlay.selected ? `0 0 0 2px var(--surface), 0 0 0 4px ${colour}` : undefined,
              }}
              className={clsx("absolute rounded-sm border-2 text-left transition-shadow", overlay.selected ? "bg-white/10" : "bg-transparent hover:bg-white/10")}
            >
              <span style={{ background: colour }} className="absolute top-0 left-0 max-w-full truncate rounded-br px-1.5 py-px text-[10px] leading-4 font-semibold text-white">
                {overlay.label}
              </span>
            </button>
          );
        })}
      {busy && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30" role="status" aria-label="Processing">
          <div className="size-8 animate-spin rounded-full border-2 border-white/40 border-t-white" />
        </div>
      )}
    </div>
  );
}
