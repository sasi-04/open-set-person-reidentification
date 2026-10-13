/**
 * Loading, empty, error and notice states.
 *
 * In plain words: every screen has to say something sensible when data is loading,
 * missing, or failed. These shared pieces make sure it always does - with a clear
 * message and, where possible, the next step - instead of a blank space.
 */
import clsx from "clsx";
import { AlertTriangle, Info, Loader2, RefreshCcw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { describeError, ApiError } from "@/services/http";
import { Button } from "./Button";

export function Spinner({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={clsx("inline-flex items-center gap-2 text-ink-3", className)}>
      <Loader2 aria-hidden className="size-4 animate-spin" />
      <span>{label}…</span>
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("skeleton", className)} />;
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-line-strong px-6 py-10 text-center">
      {icon && <div className="flex size-11 items-center justify-center rounded-full bg-surface-2 text-ink-3">{icon}</div>}
      <h3 className="text-[15px] font-semibold">{title}</h3>
      {children && <div className="max-w-md text-sm text-ink-3">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "Something went wrong" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const unauthorized = error instanceof ApiError && (error.status === 401 || error.status === 403);
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-lg border border-bad/40 bg-bad-bg p-4 text-sm">
      <div className="flex items-center gap-2 font-semibold text-bad">
        <AlertTriangle aria-hidden className="size-4" />
        {unauthorized ? "Not allowed" : title}
      </div>
      <p className="text-ink-2">{describeError(error)}</p>
      {unauthorized && <p className="text-ink-3">Check your access key and role in Settings.</p>}
      {onRetry && (
        <Button size="sm" icon={<RefreshCcw aria-hidden className="size-3.5" />} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** An inline notice. ``role`` is "alert" for problems and "status" for neutral information. */
export function Notice({ tone = "info", title, children, className }: { tone?: "info" | "warn" | "bad"; title?: string; children?: ReactNode; className?: string }) {
  const styles = { info: "border-info/30 bg-info-bg text-info", warn: "border-warn/30 bg-warn-bg text-warn", bad: "border-bad/30 bg-bad-bg text-bad" }[tone];
  const Icon = tone === "info" ? Info : TriangleAlert;
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={clsx("flex gap-2.5 rounded-md border p-3 text-sm", styles, className)}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 space-y-0.5">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className="text-ink-2">{children}</div>}
      </div>
    </div>
  );
}
