/**
 * ScoreBar: a similarity score drawn against the acceptance threshold.
 *
 * In plain words: the filled part is the similarity (0 to 1) and the vertical tick is the
 * threshold. If the fill stops short of the tick, the match was not accepted. It is a
 * meter for screen readers, and its text always states the numbers.
 */
import clsx from "clsx";

/**
 * ``tone`` overrides the fill colour when "above the threshold" does not mean "good" - for example a
 * look-alike pair of DIFFERENT people that scores above the threshold is a false accept, shown red.
 */
export function ScoreBar({ score, threshold, accepted, tone }: { score: number; threshold: number | null; accepted?: boolean; tone?: "ok" | "bad" | "neutral" }) {
  const filled = Math.min(Math.max(score, 0), 1) * 100;
  const passes = threshold !== null && score >= threshold;
  const fill = tone ? { ok: "bg-ok", bad: "bg-bad", neutral: "bg-ink-3" }[tone] : accepted || passes ? "bg-ok" : "bg-ink-3";
  return (
    <div
      role="meter"
      aria-label="Similarity score"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={Number(score.toFixed(3))}
      aria-valuetext={`Similarity ${score.toFixed(3)}${threshold !== null ? `, threshold ${threshold.toFixed(3)}` : ""}`}
      className="relative h-2 w-full rounded-full bg-surface-2"
    >
      <div className={clsx("h-full rounded-full", fill)} style={{ width: `${filled}%` }} />
      {threshold !== null && (
        <span aria-hidden title={`Threshold ${threshold.toFixed(3)}`} className="absolute -top-1 h-4 w-0.5 rounded bg-ink" style={{ left: `calc(${threshold * 100}% - 1px)` }} />
      )}
    </div>
  );
}
