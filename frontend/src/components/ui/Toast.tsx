/**
 * Toast notifications.
 *
 * In plain words: short messages in the corner. A toast is only shown AFTER the backend
 * has confirmed (or refused) an action - never optimistically. They live in an
 * aria-live region so screen-reader users hear them too, and errors stay longer.
 */
import clsx from "clsx";
import { CheckCircle2, TriangleAlert, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type Kind = "success" | "error" | "info";
interface ToastItem {
  id: number;
  kind: Kind;
  message: string;
}
interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (kind: Kind, message: string) => {
      const id = nextId.current++;
      setItems((all) => [...all.slice(-3), { id, kind, message }]);
      window.setTimeout(() => dismiss(id), kind === "error" ? 9000 : 5000);
    },
    [dismiss],
  );
  const api = useMemo<ToastApi>(
    () => ({ success: (m) => push("success", m), error: (m) => push("error", m), info: (m) => push("info", m) }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div aria-live="polite" aria-atomic="false" className="pointer-events-none fixed right-3 bottom-3 left-3 z-[60] flex flex-col items-end gap-2 sm:left-auto sm:w-[26rem]">
        {items.map((toast) => (
          <div
            key={toast.id}
            role={toast.kind === "error" ? "alert" : "status"}
            className={clsx(
              "animate-fade-in pointer-events-auto flex w-full items-start gap-2.5 rounded-md border bg-surface p-3 text-sm shadow-pop",
              toast.kind === "error" ? "border-bad/50" : "border-line",
            )}
          >
            {toast.kind === "error" ? (
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-bad" />
            ) : (
              <CheckCircle2 aria-hidden className={clsx("mt-0.5 size-4 shrink-0", toast.kind === "success" ? "text-ok" : "text-info")} />
            )}
            <p className="min-w-0 flex-1 break-words">{toast.message}</p>
            <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(toast.id)} className="rounded p-0.5 text-ink-3 hover:text-ink">
              <X aria-hidden className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used inside <ToastProvider>");
  return api;
}
