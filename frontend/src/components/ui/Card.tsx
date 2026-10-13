/**
 * Cards and statistic tiles: the basic content containers.
 */
import clsx from "clsx";
import type { HTMLAttributes, ReactNode } from "react";
import { InfoTip } from "./InfoTip";

export function Card({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  // min-w-0: a card inside a grid may shrink below its content, so wide tables scroll INSIDE the card
  // instead of stretching the page sideways on a phone.
  return <section className={clsx("card min-w-0 rounded-lg border border-line bg-surface shadow-card", className)} {...rest} />;
}

export function CardHeader({ title, description, action, id }: { title: ReactNode; description?: ReactNode; action?: ReactNode; id?: string }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
      <div className="min-w-0">
        <h2 id={id} className="text-[15px] leading-6 font-semibold">
          {title}
        </h2>
        {description && <p className="mt-0.5 text-xs text-ink-3">{description}</p>}
      </div>
      {action}
    </header>
  );
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("px-4 py-4 sm:px-5", className)} {...rest} />;
}

/** A headline number with a plain-language label and (optionally) its measurement definition. */
export function Stat({
  label,
  value,
  hint,
  definition,
  tone,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  definition?: string;
  tone?: "default" | "muted";
  icon?: ReactNode;
}) {
  return (
    <div className="card flex min-w-0 flex-col gap-1 rounded-lg border border-line bg-surface p-4 shadow-card">
      <div className="flex items-center gap-2 text-xs font-medium text-ink-3">
        {icon}
        <span>{label}</span>
        {definition && <InfoTip label={`How "${label}" is measured`}>{definition}</InfoTip>}
      </div>
      {/* "Not evaluated" and similar placeholders are set smaller so they never dominate a tile */}
      <div className={clsx("font-display leading-9 font-semibold", tone === "muted" ? "text-lg text-ink-3" : "text-[26px]")}>{value}</div>
      {hint && <div className="text-xs text-ink-3">{hint}</div>}
    </div>
  );
}

/** A two-column "term: value" list used for metadata panels. */
export function DefinitionList({ items }: { items: { term: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
      {items.map(({ term, value }) => (
        <div key={term} className="contents">
          <dt className="text-ink-3">{term}</dt>
          <dd className="min-w-0 break-words text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
