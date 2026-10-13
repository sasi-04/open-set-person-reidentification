/**
 * ScoreStrip: where each example photo landed on a similarity scale.
 *
 * In plain words: every photo gets a similarity number between 0 (nothing alike) and 1 (identical) against the closest
 * enrolled person. This draws one dot per photo, a row per kind of photo, with a vertical line at the threshold. If the
 * dots of "known people" sit to the right of the line and every stranger sits to the left, the number separates them
 * cleanly. If strangers sit on the same side as known people, it cannot - which is what happens with clothing.
 * The shaded band just left of the face line is the "ask a person" zone. It only draws numbers the server measured.
 */
import clsx from "clsx";
import { InfoTip } from "@/components/ui/InfoTip";
import { GROUP_DOT } from "./present";
import { plain } from "./summary";

export interface StripDot { id: string; score: number; title: string }
export interface StripRow { id: string; label: string; dots: StripDot[] }

const TICKS = [0, 0.25, 0.5, 0.75, 1];
const place = (score: number) => `${Math.min(1, Math.max(0, score)) * 100}%`;

export function ScoreStrip({ title, explain, rows, threshold, thresholdLabel, reviewBand }: {
  title: string;
  explain: string;
  rows: StripRow[];
  threshold: number | null;
  thresholdLabel: string;
  /** Width of the "ask a person" zone just below the threshold (face only). */
  reviewBand?: number;
}) {
  const summary = rows.map((r) => `${r.label}: ${r.dots.length ? r.dots.map((d) => d.score.toFixed(2)).join(", ") : "no score"}`).join("; ");
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
        {title}
        <InfoTip label={`About: ${title}`}>{explain}</InfoTip>
      </figcaption>
      <div
        role="img"
        aria-label={`${title}. ${summary}.${threshold === null ? "" : ` ${thresholdLabel} ${plain(threshold)}.`}`}
        className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 sm:grid-cols-[10.5rem_minmax(0,1fr)]"
      >
        <div className="pt-6">
          {rows.map((row) => <div key={row.id} className="flex h-8 items-center text-xs leading-tight text-ink-2">{row.label}</div>)}
        </div>
        <div className="relative px-2 pt-6">
          {rows.map((row) => (
            <div key={row.id} className="relative h-8 border-b border-line">
              {reviewBand && threshold !== null && (
                <div aria-hidden className="absolute inset-y-0 bg-warn-bg" style={{ left: place(threshold - reviewBand), width: `${Math.min(reviewBand, threshold) * 100}%` }} />
              )}
              {row.dots.map((dot) => (
                <span
                  key={dot.id}
                  title={`${dot.title}: ${dot.score.toFixed(3)}`}
                  className={clsx("absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface", GROUP_DOT[row.id] ?? "bg-ink-3")}
                  style={{ left: place(dot.score) }}
                />
              ))}
              {row.dots.length === 0 && <span className="absolute inset-y-0 left-2 flex items-center text-[11px] text-ink-3">no similarity to plot</span>}
            </div>
          ))}
          <div aria-hidden className="relative h-6">
            {TICKS.map((t) => <span key={t} className="absolute top-1 -translate-x-1/2 text-[11px] text-ink-3" style={{ left: place(t) }}>{t}</span>)}
          </div>
          {threshold !== null && (
            <div aria-hidden className="pointer-events-none absolute top-5 bottom-6 left-2 right-2">
              <div className="absolute inset-y-0 border-l-2 border-dashed border-ink" style={{ left: place(threshold) }}>
                <span className="absolute -top-0.5 left-1 -translate-y-full text-[11px] font-medium whitespace-nowrap text-ink">{thresholdLabel} {plain(threshold)}</span>
              </div>
            </div>
          )}
        </div>
      </div>
      {reviewBand && threshold !== null && (
        <p className="mt-1 flex items-center gap-1.5 text-[11px] text-ink-3 sm:pl-[11.5rem]">
          <span aria-hidden className="inline-block h-2.5 w-4 shrink-0 rounded-sm bg-warn-bg ring-1 ring-warn/30" />the &ldquo;ask a person&rdquo; zone just below the line
        </p>
      )}
    </figure>
  );
}
