/** A real progress bar: the value comes from the backend job, it is never animated on a timer. */
import clsx from "clsx";

export function Progress({ value, label, className }: { value: number; label: string; className?: string }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className={clsx("w-full", className)}>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div className="h-full rounded-full bg-brand transition-[width] duration-300" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
