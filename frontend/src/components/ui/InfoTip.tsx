/**
 * InfoTip: a small "i" button that reveals an explanation.
 *
 * In plain words: used to show how a number is measured. It is a real button, so it
 * works with the keyboard (Tab to focus, Enter/Space to toggle, Escape to close) and
 * the text is linked to it with aria-describedby for screen readers.
 */
import { Info } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        // Click opens (a tap on a touch screen has no hover). It closes on Escape, on moving away, or on
        // blur. It must NOT toggle: a mouse hover already opened it, and the click would shut it again.
        onClick={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="inline-flex size-4 items-center justify-center rounded-full text-ink-3 hover:text-ink"
      >
        <Info aria-hidden className="size-3.5" />
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute top-full left-1/2 z-30 mt-1.5 w-60 -translate-x-1/2 rounded-md border border-line bg-surface p-2.5 text-left text-xs font-normal text-ink-2 shadow-pop"
        >
          {children}
        </span>
      )}
    </span>
  );
}
