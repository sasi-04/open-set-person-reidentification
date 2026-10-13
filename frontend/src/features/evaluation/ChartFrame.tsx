/**
 * ChartFrame: title, legend, plot area and a "data table" twin.
 *
 * In plain words: every chart sits in the same frame. The legend is HTML (so it is readable
 * by screen readers), the plot is sized to include its axis labels, and the exact numbers
 * behind the picture are always available as a table - a tooltip is never the only way to
 * read a value.
 */
import type { ReactNode } from "react";
import { InfoTip } from "@/components/ui/InfoTip";

/** One colour per entity, in a fixed order that never changes when other series are hidden. */
export const VARIANT_COLOUR: Record<string, string> = {
  nn_baseline: "var(--ink-3)",
  thr: "var(--series-1)",
  thr_margin: "var(--series-2)",
  thr_confidence: "var(--series-3)",
  thr_margin_flip: "var(--series-4)",
  thr_margin_finetuned: "var(--series-5)",
};

/** The three kinds of query in the score-distribution chart. */
export const QUERY_KIND_COLOUR = {
  known_correct: "var(--series-1)",
  unknown: "var(--series-2)",
  known_wrong: "var(--series-3)",
} as const;

export interface LegendItem {
  label: string;
  colour: string;
  shape?: "line" | "square";
}

export function ChartLegend({ items }: { items: LegendItem[] }) {
  if (items.length < 2) return null; // a single series is named by the chart title
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="Legend">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span aria-hidden className={item.shape === "square" ? "size-2.5 rounded-sm" : "h-0.5 w-4 rounded"} style={{ background: item.colour }} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export function ChartFrame({
  title,
  description,
  help,
  legend,
  children,
  table,
  footer,
}: {
  title: string;
  description?: string;
  help?: string;
  legend?: LegendItem[];
  children: ReactNode;
  table?: { columns: string[]; rows: (string | number)[][]; caption: string };
  footer?: ReactNode;
}) {
  return (
    <figure className="min-w-0">
      <figcaption className="mb-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold">{title}</h3>
          {help && <InfoTip label={`About ${title}`}>{help}</InfoTip>}
        </div>
        {description && <p className="text-xs text-ink-3">{description}</p>}
      </figcaption>
      {legend && <ChartLegend items={legend} />}
      <div className="h-[300px] w-full min-w-0">{children}</div>
      {footer && <div className="mt-2 text-xs text-ink-3">{footer}</div>}
      {table && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer font-medium text-ink-2 select-none">View data as a table</summary>
          <div className="mt-2 max-h-64 overflow-auto rounded-md border border-line">
            <table className="w-full text-left">
              <caption className="sr-only">{table.caption}</caption>
              <thead className="sticky top-0 bg-surface-2 text-ink-3">
                <tr>{table.columns.map((c) => <th key={c} scope="col" className="px-2.5 py-1.5 font-medium">{c}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line tabular">
                {table.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j} className="px-2.5 py-1.5">{cell}</td>)}</tr>)}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  );
}

/** Tooltip body shared by all charts. */
export function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; colour?: string }[] }) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-pop">
      <p className="mb-1 font-semibold text-ink">{title}</p>
      {rows.map((row) => (
        <p key={row.label} className="flex items-center gap-2 text-ink-2">
          {row.colour && <span aria-hidden className="size-2 rounded-full" style={{ background: row.colour }} />}
          <span>{row.label}</span>
          <span className="ml-auto pl-3 font-medium text-ink tabular">{row.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Axis styling shared by all charts: small muted text, hairline solid rules. */
export const AXIS_PROPS = {
  stroke: "var(--axis)",
  tick: { fill: "var(--ink-3)", fontSize: 11 },
  tickLine: false as const,
};
export const GRID_PROPS = { stroke: "var(--grid)", strokeDasharray: undefined, vertical: false as const };
