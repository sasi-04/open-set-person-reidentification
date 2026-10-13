/**
 * Dialogs.
 *
 * In plain words: built on Radix UI's Dialog primitive, which provides what is hard to
 * get right by hand - focus is trapped inside while open, Escape closes it, focus
 * returns to the button that opened it, and screen readers are told it is a modal.
 * ``ConfirmDialog`` is the standard pattern for destructive actions: it says exactly
 * what will happen and can require typing a phrase before the red button works.
 */
import * as RadixDialog from "@radix-ui/react-dialog";
import clsx from "clsx";
import { X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Notice } from "./Feedback";
import { TextInput } from "./Form";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const width = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-3xl", xl: "max-w-5xl" }[size];
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-[var(--overlay)]" />
        <RadixDialog.Content
          className={clsx(
            "animate-fade-in fixed top-1/2 left-1/2 z-50 flex max-h-[min(92dvh,52rem)] w-[calc(100vw-1.5rem)] -translate-x-1/2 -translate-y-1/2 flex-col",
            "rounded-lg border border-line bg-surface shadow-pop",
            width,
          )}
        >
          <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <RadixDialog.Title className="font-display text-base font-semibold">{title}</RadixDialog.Title>
              <RadixDialog.Description className={clsx("mt-0.5 text-sm text-ink-3", !description && "sr-only")}>
                {description ?? title}
              </RadixDialog.Description>
            </div>
            <RadixDialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="Close dialog" className="-mr-2 size-8 !px-0">
                <X aria-hidden className="size-4" />
              </Button>
            </RadixDialog.Close>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  consequences,
  confirmLabel,
  onConfirm,
  loading = false,
  requirePhrase,
  tone = "danger",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  consequences: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  loading?: boolean;
  /** When set, the person must type this exact text before the confirm button is enabled. */
  requirePhrase?: string;
  tone?: "danger" | "primary";
}) {
  const [typed, setTyped] = useState("");
  const ready = !requirePhrase || typed === requirePhrase;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setTyped("");
        onOpenChange(next);
      }}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
            Cancel
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} loading={loading} disabled={!ready} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <Notice tone={tone === "danger" ? "warn" : "info"} title={tone === "danger" ? "This cannot be undone" : "Please confirm"}>
          {consequences}
        </Notice>
        {requirePhrase && (
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">
              Type <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-xs">{requirePhrase}</code> to confirm
            </span>
            <TextInput value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} />
          </label>
        )}
      </div>
    </Dialog>
  );
}
