/**
 * ThresholdSandbox: "what would change if I moved the dial?" - safely.
 *
 * In plain words: a finished run keeps a fixed table of its per-query results (who each query really
 * was, who the matcher picked, how alike they looked). Here you try any threshold or margin rule on that
 * SAME table and watch the real counts change - strangers let in, enrolled people turned away, decisions
 * that flip - next to the run's own calibrated rule. The counting is done by the backend with the same
 * decision rule the live system uses; this screen only draws the answer.
 *
 * Two promises, both visible on screen:
 *   * it never changes the active decision policy (there is no "apply" button here on purpose);
 *   * on the TEST split it warns that choosing a threshold because it looks good there is tuning on the
 *     test set. Real thresholds are chosen on the calibration split by a calibration run.
 */
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { RotateCcw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, OutcomeBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { Checkbox, Segmented, Select, TextInput } from "@/components/ui/Form";
import { useDebounced } from "@/hooks/useDebounced";
import { count, num, pct } from "@/lib/format";
import { api, keys, type SandboxBody } from "@/services/api";
import type { Outcome, SandboxResult, SandboxSummary } from "@/types/api";

const OUTCOME_OF: Record<string, Outcome> = { accepted: "accepted", review_required: "review_required", unknown: "unknown" };

function Tile({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: "bad" | "ok" | "warn" }) {
  return (
    <div className="rounded-md border border-line bg-surface-2/50 p-3">
      <p className="text-xs text-ink-3">{label}</p>
      <p className={clsx("font-display text-xl font-semibold tabular", tone === "bad" && "text-bad", tone === "ok" && "text-ok", tone === "warn" && "text-warn")}>{value}</p>
      <p className="text-xs text-ink-3">{hint}</p>
    </div>
  );
}

function delta(trial: number | null, base: number | null, digits = 1): string {
  if (trial === null || base === null) return "—";
  const d = (trial - base) * 100;
  if (Math.abs(d) < 0.05) return "no change";
  return `${d > 0 ? "+" : "−"}${Math.abs(d).toFixed(digits)} points`;
}

function Comparison({ trial, base }: { trial: SandboxSummary; base: SandboxSummary }) {
  const t = trial.metrics, b = base.metrics;
  const rows: [string, string, string, string][] = [
    ["False accepts (FAR)", `${pct(b.far, 2)}  (${b.counts.unknown_accepted} of ${b.counts.unknown_queries})`, `${pct(t.far, 2)}  (${t.counts.unknown_accepted} of ${t.counts.unknown_queries})`, delta(t.far, b.far, 2)],
    ["Recall (DIR@1)", pct(b.dir_at_rank["1"]), pct(t.dir_at_rank["1"]), delta(t.dir_at_rank["1"], b.dir_at_rank["1"])],
    ["Enrolled people turned away", String(base.confusion.false_rejects), String(trial.confusion.false_rejects), String(trial.confusion.false_rejects - base.confusion.false_rejects)],
    ["Enrolled people given the wrong name", String(base.confusion.wrong_identity_accepts), String(trial.confusion.wrong_identity_accepts), String(trial.confusion.wrong_identity_accepts - base.confusion.wrong_identity_accepts)],
    ["Sent to REVIEW (enrolled / strangers)", `${base.confusion.known_sent_to_review} / ${base.confusion.unknown_sent_to_review}`, `${trial.confusion.known_sent_to_review} / ${trial.confusion.unknown_sent_to_review}`, "—"],
  ];
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full min-w-[34rem] text-left text-sm">
        <caption className="sr-only">Trial rule compared with the calibrated rule on the same queries</caption>
        <thead className="bg-surface-2 text-xs text-ink-3"><tr>{["Measure", "Calibrated rule", "Your trial rule", "Change"].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line tabular">
          {rows.map(([name, a, c, d]) => (
            <tr key={name}><th scope="row" className="px-3 py-2 font-medium">{name}</th><td className="px-3 py-2">{a}</td><td className="px-3 py-2 font-semibold">{c}</td><td className="px-3 py-2 text-ink-3">{d}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ThresholdSandbox({ runId }: { runId: string }) {
  const info = useQuery({ queryKey: keys.sandboxInfo(runId), queryFn: () => api.sandboxInfo(runId), retry: false });

  const reference = info.data?.reference;
  const [split, setSplit] = useState<"calibration" | "test">("calibration");
  const [threshold, setThresholdValue] = useState<number | null>(null);
  const [thresholdText, setThresholdText] = useState(""); // what is typed in the box, which may be half-finished ("0.")
  const [useMargin, setUseMargin] = useState(false);
  const [margin, setMarginValue] = useState(0.05);
  const [marginText, setMarginText] = useState("0.05");
  const [action, setAction] = useState<"review" | "reject">("review");

  const setThreshold = (value: number) => { setThresholdValue(value); setThresholdText(value.toFixed(3)); };
  const setMargin = (value: number) => { setMarginValue(value); setMarginText(String(value)); };
  /** Typing updates the number only while the text is a complete, valid value; the box keeps whatever you typed. */
  function typed(text: string, apply: (value: number) => void, set: (text: string) => void) {
    set(text);
    const value = Number(text);
    if (text.trim() !== "" && Number.isFinite(value)) apply(Math.min(1, Math.max(0, value)));
  }

  // Start from the run's own calibrated rule, so the first thing you see is "no change".
  useEffect(() => {
    if (!reference) return;
    setThreshold(reference.threshold);
    setUseMargin(reference.min_margin !== null);
    setMargin(reference.min_margin ?? 0.05);
    setAction(reference.margin_action === "reject" ? "reject" : "review");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the setters are stable re-creations of the same two state updates
  }, [reference]);

  const body: SandboxBody | null = threshold === null ? null : { split, threshold, min_margin: useMargin ? margin : null, margin_action: action };
  const settled = useDebounced(body, 250);
  const result = useQuery<SandboxResult>({
    queryKey: ["sandbox", runId, settled],
    queryFn: () => api.sandbox(runId, settled as SandboxBody),
    enabled: !!settled && !!info.data,
    placeholderData: (previous) => previous,
    retry: false,
  });

  if (info.isLoading) return <Skeleton className="h-64 w-full" />;
  if (info.isError || !info.data || !reference) {
    return <Notice tone="info" title="No threshold sandbox for this run">{info.error instanceof Error ? info.error.message : "Only finished evaluation and look-alike runs keep the per-query scores the sandbox needs."}</Notice>;
  }

  const range = info.data.score_range;
  const low = Math.max(0, Math.floor((range.min - 0.02) * 100) / 100);
  const high = Math.min(1, Math.ceil((range.max + 0.02) * 100) / 100);
  const data = result.data;
  const same = threshold === reference.threshold && (useMargin ? margin : null) === reference.min_margin && action === (reference.margin_action === "reject" ? "reject" : "review");

  return (
    <div className="space-y-4">
      <Notice tone="info" title="A safe place to explore - it changes nothing outside this page">
        {info.data.explanation} To change the real threshold, run a calibration and apply it in <Link className="underline" to="/settings?tab=model">Model &amp; System Settings</Link>. {!info.data.is_benchmark && "This run used a smoke-test dataset, so the numbers only demonstrate the tool."}
      </Notice>

      <div className="space-y-4">
        <div className="grid gap-x-8 gap-y-4 rounded-lg border border-line p-4 md:grid-cols-2">
          <div className="min-w-0 space-y-4">
          <Segmented<"calibration" | "test"> label="Which people to count" value={split} onChange={setSplit}
            options={[{ value: "calibration", label: "Calibration people", hint: `${count(info.data.splits.calibration)} queries - the right place to choose a threshold` },
              { value: "test", label: "Test people", hint: `${count(info.data.splits.test)} queries - for understanding only` }]} />

          <div className="space-y-2">
            <label htmlFor="sandbox-threshold" className="flex items-center justify-between text-sm font-medium">
              <span>Acceptance threshold</span>
              <span className="font-mono tabular">{threshold === null ? "—" : threshold.toFixed(3)}</span>
            </label>
            <input id="sandbox-threshold" type="range" min={low} max={high} step={0.005} value={threshold ?? reference.threshold}
              onChange={(e) => setThreshold(Number(e.target.value))} className="w-full accent-[var(--brand)]" aria-describedby="sandbox-threshold-help" />
            <div className="flex items-center justify-between gap-2 text-xs text-ink-3" id="sandbox-threshold-help">
              <span>{low.toFixed(2)} (loosest)</span>
              <label className="flex items-center gap-2">exact value
                <TextInput type="text" inputMode="decimal" className="!min-h-8 !w-24 !px-2 !text-xs" value={thresholdText}
                  onChange={(e) => typed(e.target.value, setThresholdValue, setThresholdText)} onBlur={() => threshold !== null && setThresholdText(threshold.toFixed(3))} aria-label="Exact threshold" />
              </label>
              <span>{high.toFixed(2)} (strictest)</span>
            </div>
            <p className="text-xs text-ink-3">The run's own calibrated threshold is <b className="text-ink-2">{reference.threshold.toFixed(3)}</b> ({reference.label}, {reference.chosen_on}).</p>
          </div>
          </div>

          <div className="min-w-0 space-y-4">
          <div className="space-y-2">
            <Checkbox label="Require a lead over the runner-up (margin rule)" hint="A near-tie between two enrolled people is not a confident match."
              checked={useMargin} onChange={(e) => setUseMargin(e.target.checked)} />
            {useMargin && (
              <div className="grid grid-cols-2 gap-3 pl-8">
                <label className="flex flex-col gap-1 text-xs font-medium">Minimum margin
                  <TextInput type="text" inputMode="decimal" value={marginText} onChange={(e) => typed(e.target.value, setMarginValue, setMarginText)} onBlur={() => setMarginText(String(margin))} />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium">If the lead is too small
                  <Select value={action} onChange={(e) => setAction(e.target.value === "reject" ? "reject" : "review")}>
                    <option value="review">send to REVIEW</option>
                    <option value="reject">treat as UNKNOWN</option>
                  </Select>
                </label>
              </div>
            )}
          </div>

          <Button icon={<RotateCcw aria-hidden className="size-4" />} disabled={same} onClick={() => { setThreshold(reference.threshold); setUseMargin(reference.min_margin !== null); setMargin(reference.min_margin ?? 0.05); setAction(reference.margin_action === "reject" ? "reject" : "review"); }}>
            Back to the calibrated rule
          </Button>
          </div>
        </div>

        <div className="min-w-0 space-y-4" aria-live="polite" aria-busy={result.isFetching}>
          {result.isError && <ErrorState error={result.error} onRetry={() => void result.refetch()} title="The sandbox could not be computed" />}
          {data?.warning && <Notice tone="warn" title="Exploration only">{data.warning}</Notice>}
          {!data && !result.isError && <Skeleton className="h-64 w-full" />}
          {data && (
            <div className={clsx("space-y-4", result.isFetching && "opacity-70")}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge tone="info" icon={<ShieldCheck aria-hidden className="size-3.5" />}>Read-only sandbox</Badge>
                <span className="text-ink-3">{count(data.n_queries)} queries · {data.decisions_changed === 0 ? "no decision differs from the calibrated rule" : `${count(data.decisions_changed)} decisions differ from the calibrated rule`}</span>
              </div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Tile label="Strangers let in" value={String(data.trial.confusion.false_accepts)} hint={`FAR ${pct(data.trial.metrics.far, 2)}${data.trial.metrics.far_upper_bound_95 != null ? ` (95% bound ${pct(data.trial.metrics.far_upper_bound_95, 1)})` : ""}`} tone={data.trial.confusion.false_accepts > 0 ? "bad" : "ok"} />
                <Tile label="Enrolled, correctly accepted" value={String(data.trial.confusion.true_accepts)} hint={`recall ${pct(data.trial.metrics.dir_at_rank["1"])}`} tone="ok" />
                <Tile label="Enrolled, turned away" value={String(data.trial.confusion.false_rejects)} hint="not accepted: UNKNOWN or REVIEW" tone={data.trial.confusion.false_rejects > 0 ? "warn" : undefined} />
                <Tile label="Strangers rejected" value={String(data.trial.confusion.true_rejects)} hint="correctly not accepted" />
              </div>
              <Comparison trial={data.trial} base={data.calibrated_rule} />
              <details className="text-xs text-ink-3">
                <summary className="cursor-pointer font-medium text-ink-2">What these counts mean</summary>
                <ul className="mt-2 list-disc space-y-1 pl-5">{Object.values(data.trial.confusion.definitions).map((d) => <li key={d}>{d}</li>)}</ul>
              </details>

              <div>
                <h3 className="text-sm font-semibold">Decisions that change</h3>
                <p className="mb-2 text-xs text-ink-3">Compared with the calibrated rule. Strangers who now get in are listed first.</p>
                {data.changed_examples.length === 0 ? (
                  <p className="rounded-md border border-dashed border-line-strong p-3 text-sm text-ink-3">Nothing changes at this setting.</p>
                ) : (
                  <div className="overflow-x-auto rounded-md border border-line">
                    <table className="w-full min-w-[36rem] text-left text-xs">
                      <caption className="sr-only">Queries whose decision differs from the calibrated rule</caption>
                      <thead className="bg-surface-2 text-ink-3"><tr>{["Query", "Really is", "Matcher picked", "Similarity", "Margin", "Calibrated rule", "Your rule"].map((h) => <th key={h} scope="col" className="px-2.5 py-2 font-medium">{h}</th>)}</tr></thead>
                      <tbody className="divide-y divide-line tabular">
                        {data.changed_examples.map((c) => (
                          <tr key={c.ref}>
                            <td className="px-2.5 py-2 font-mono break-all">{c.ref}</td>
                            <td className="px-2.5 py-2">{c.is_known ? `enrolled ${c.query_identity}` : <span className="font-medium">stranger</span>}</td>
                            <td className="px-2.5 py-2">{c.top1_identity}{c.is_known && !c.top1_correct && <span className="text-bad"> (wrong person)</span>}</td>
                            <td className="px-2.5 py-2">{num(c.top1_score)}</td>
                            <td className="px-2.5 py-2">{c.margin === null ? "—" : num(c.margin)}</td>
                            <td className="px-2.5 py-2"><OutcomeBadge outcome={OUTCOME_OF[c.calibrated_rule] ?? "unknown"} short /></td>
                            <td className="px-2.5 py-2"><OutcomeBadge outcome={OUTCOME_OF[c.trial_rule] ?? "unknown"} short /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
