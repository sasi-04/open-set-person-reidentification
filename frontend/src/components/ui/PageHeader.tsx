import type { ReactNode } from "react";

/** The heading block at the top of each operational screen (kept compact: this is a tool, not a landing page). */
export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl leading-7 sm:text-2xl sm:leading-8">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-3">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
