/**
 * Comparison: the example's verdict, side by side.
 *
 * In plain words: a small table with one row per question an interviewer would ask - "were known people recognised?",
 * "were strangers wrongly let in?", "what about strangers dressed like an enrolled person?" - and two columns: the system
 * (face + body) and a clothes-only matcher. Each cell is a count taken from the server's own verdicts, with a tick or a cross.
 */
import { CheckCircle2, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { Notice } from "@/components/ui/Feedback";
import type { DemoCase, DemoCaseResult } from "@/types/api";
import { conclusion, ofTotal, tally, type Tally } from "./summary";

interface Metric { id: string; label: ReactNode; total: (t: Tally) => number; shown: (t: Tally) => number; good: (t: Tally) => boolean }

const METRICS: Metric[] = [
  { id: "known", label: "Known people recognised", total: (t) => t.known.total, shown: (t) => t.known.matched, good: (t) => t.known.matched === t.known.total },
  { id: "strangers", label: "Strangers wrongly accepted", total: (t) => t.strangers.total, shown: (t) => t.strangers.falseAccepted, good: (t) => t.strangers.falseAccepted === 0 },
  { id: "lookalikes", label: <>… of them dressed in the same clothes as an enrolled person</>, total: (t) => t.lookalikes.total, shown: (t) => t.lookalikes.falseAccepted, good: (t) => t.lookalikes.falseAccepted === 0 },
  { id: "noface", label: "Known people with no usable face sent to a person", total: (t) => t.noFace.total, shown: (t) => t.noFace.sentToReview, good: (t) => t.noFace.sentToReview === t.noFace.total },
  { id: "right", label: "Photos decided exactly right", total: (t) => t.analysed, shown: (t) => t.right, good: (t) => t.right === t.analysed },
];

function Figure({ metric, t }: { metric: Metric; t: Tally }) {
  const good = metric.good(t);
  return (
    <span className={`inline-flex items-center gap-1.5 font-display text-base font-semibold sm:gap-2 sm:text-xl ${good ? "text-ok" : "text-bad"}`}>
      {good ? <CheckCircle2 aria-hidden className="size-4 shrink-0 sm:size-5" /> : <XCircle aria-hidden className="size-4 shrink-0 sm:size-5" />}
      {ofTotal(metric.shown(t), metric.total(t))}
      <span className="sr-only">{good ? " (good)" : " (not good)"}</span>
    </span>
  );
}

export function Comparison({ cases, results }: { cases: DemoCase[]; results: Record<string, DemoCaseResult | undefined> }) {
  const faceBody = tally(cases, results, "face_body");
  const clothes = tally(cases, results, "clothes_only");
  const metrics = METRICS.filter((m) => m.total(faceBody) > 0);
  const summary = conclusion(cases.length, faceBody, clothes);
  return (
    <div className="space-y-3">
      {summary && <Notice tone="info" title="What the example shows">{summary}</Notice>}
      <div className="relative overflow-x-auto rounded-md border border-line">
        <table className="w-full table-fixed border-collapse text-left text-sm">
          <caption className="sr-only">The same {cases.length} photos judged by the system (face and body) and by a clothes-only matcher</caption>
          <thead className="bg-surface-2 text-xs text-ink-3">
            <tr>
              <th scope="col" className="w-[44%] px-3 py-2 font-medium">Question</th>
              <th scope="col" className="w-[28%] px-2 py-2 font-medium sm:px-3">Face + body <span className="block font-normal">(this system)</span></th>
              <th scope="col" className="w-[28%] px-2 py-2 font-medium sm:px-3">Clothes only <span className="block font-normal">(weaker matcher)</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {metrics.map((m) => (
              <tr key={m.id}>
                <th scope="row" className="px-3 py-2.5 text-sm font-normal text-ink-2">{m.label}</th>
                <td className="px-2 py-2.5 sm:px-3"><Figure metric={m} t={faceBody} /></td>
                <td className="px-2 py-2.5 sm:px-3"><Figure metric={m} t={clothes} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
