/**
 * AblationTable: every variant, same metrics, same test split.
 *
 * In plain words: each row differs from its "parent" by exactly one ingredient, so you can see what
 * that ingredient bought. Numbers are on the held-out TEST split, using rules chosen on the
 * CALIBRATION split. With one seed the 95% bootstrap interval (over people) is shown; with several,
 * mean ± standard deviation across seeds.
 */
import clsx from "clsx";
import { Badge } from "@/components/ui/Badge";
import { InfoTip } from "@/components/ui/InfoTip";
import { num, pct } from "@/lib/format";
import type { EvaluationResult, Stat } from "@/types/api";

function stat(s: Stat | undefined, asPercent = true, digits = 1): string {
  if (!s || s.mean === null) return "—";
  const text = asPercent ? pct(s.mean, digits) : num(s.mean, 3);
  return s.std === null ? text : `${text} ± ${asPercent ? pct(s.std, digits) : num(s.std, 3)}`;
}

function ci(interval: { low: number; high: number } | null | undefined): string {
  return interval ? `${pct(interval.low)}–${pct(interval.high)}` : "";
}

export function AblationTable({ result }: { result: EvaluationResult }) {
  const single = result.metadata.request.seeds.length === 1;
  const selected = result.selected_variant.key;
  const columns: [string, string][] = [
    ["Recall (DIR@1)", "Enrolled people accepted AND correctly named ÷ all enrolled people."],
    ["False accepts (FAR)", "Strangers wrongly accepted ÷ all strangers."],
    ["TAR", "Enrolled people accepted under any identity ÷ all enrolled people."],
    ["Rank-1", "Closed-set: the true person is the top candidate. Ignores thresholds."],
    ["mAP", "Mean average precision over ranked gallery images."],
    ["AUOSCR", "Area under the open-set classification curve (DIR@1 vs FAR). 1.0 is perfect."],
    ["F1", "Harmonic mean of precision and recall for correctly naming accepted people."],
  ];
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full min-w-[56rem] text-left text-sm">
        <caption className="sr-only">Ablation comparison of every variant on the held-out test split</caption>
        <thead className="border-b border-line bg-surface-2 text-xs text-ink-3">
          <tr>
            <th scope="col" className="px-3 py-2.5 font-medium">Variant</th>
            {columns.map(([name, help]) => (
              <th key={name} scope="col" className="px-3 py-2.5 font-medium whitespace-nowrap">
                <span className="inline-flex items-center gap-1">{name}<InfoTip label={`About ${name}`}>{help}</InfoTip></span>
              </th>
            ))}
            <th scope="col" className="px-3 py-2.5 font-medium">Rule (threshold · margin)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line tabular">
          {Object.entries(result.variants).map(([key, variant]) => {
            const s = variant.summary;
            const first = variant.per_seed.find((r) => r.status === "ok");
            const intervals = first?.test.confidence_intervals;
            const isSelected = key === selected;
            return (
              <tr key={key} className={clsx(isSelected && "bg-ok-bg/40")}>
                <th scope="row" className="max-w-[16rem] px-3 py-2.5 align-top font-medium">
                  <div className="flex flex-wrap items-center gap-1.5">{variant.label}{isSelected && <Badge tone="ok">Selected</Badge>}</div>
                  <p className="mt-0.5 text-xs font-normal text-ink-3">{variant.status !== "ok" ? (variant.reason ?? variant.status) : variant.description}</p>
                </th>
                {!s || !first ? (
                  <td colSpan={8} className="px-3 py-2.5 text-ink-3">Not available</td>
                ) : (
                  <>
                    <td className="px-3 py-2.5 align-top">{single ? <>{pct(first.test.dir_at_rank["1"])}<Ci text={ci(intervals?.dir1)} /></> : stat(s.dir1)}</td>
                    <td className="px-3 py-2.5 align-top">{single ? <>{pct(first.test.far, 2)}<Ci text={ci(intervals?.far)} /></> : stat(s.far, true, 2)}</td>
                    <td className="px-3 py-2.5 align-top">{single ? <>{pct(first.test.tar)}<Ci text={ci(intervals?.tar)} /></> : stat(s.tar)}</td>
                    <td className="px-3 py-2.5 align-top">{stat(s.rank1)}</td>
                    <td className="px-3 py-2.5 align-top">{stat(s.mAP)}</td>
                    <td className="px-3 py-2.5 align-top">{key === "nn_baseline" ? "—" : stat(s.auoscr, false)}</td>
                    <td className="px-3 py-2.5 align-top">{single ? pct(first.test.f1) : stat(s.f1)}</td>
                    <td className="px-3 py-2.5 align-top text-xs">
                      {key === "nn_baseline" ? "accept every query" : (
                        <>
                          {num(s.threshold.mean)} · {s.min_margin.mean === null ? "no margin" : num(s.min_margin.mean)}
                          <div className="mt-0.5">{s.targets_achieved === s.n_seeds_total ? <Badge tone="ok">Target met on calibration</Badge> : <Badge tone="warn">Target not met ({s.targets_achieved}/{s.n_seeds_total})</Badge>}</div>
                        </>
                      )}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Ci({ text }: { text: string }) {
  return text ? <div className="text-[11px] font-normal text-ink-3">95% CI {text}</div> : null;
}
