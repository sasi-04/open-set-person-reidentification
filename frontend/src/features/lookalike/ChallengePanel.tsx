/**
 * ChallengePanel: the reproducible challenge set and how each model does on it.
 *
 * In plain words: the challenge set is a fixed list of comparisons - different-person pairs chosen
 * BECAUSE the model finds them alike, plus ordinary same-person pairs. Each model is measured on that same
 * list at its own calibrated threshold. Two numbers sit side by side on purpose:
 *   "challenge false-accept rate"  measured only on the hard pairs (high by construction)
 *   "all-pairs false-accept rate"  measured over every different-person pair (the realistic rate)
 * so the first can never be mistaken for the system's real-world error rate.
 */
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardBody, CardHeader, DefinitionList, Stat } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Feedback";
import { AXIS_PROPS, ChartFrame, GRID_PROPS, TooltipBox } from "@/features/evaluation/ChartFrame";
import { count, num, pct } from "@/lib/format";
import type { LabModelOk, LookalikeResult } from "@/types/api";
import { HardGenuineCard } from "./cards";

const SERIES_COLOUR: Record<string, string> = { baseline: "var(--series-1)", improved: "var(--series-2)" };
const DEFINITION_LABELS: [string, string][] = [
  ["source", "Source"], ["impostor_comparisons", "Different-person comparisons"], ["genuine_comparisons", "Same-person comparisons"],
  ["inclusion_criteria", "Inclusion criteria"], ["model_vs_clothing", "Embedding versus clothing"], ["clothing_proxy_rule", "Clothing-colour proxy"], ["splits", "Split definitions"],
];

function okModels(result: LookalikeResult): [string, LabModelOk][] {
  const entries: [string, LabModelOk | { status: string }][] = Object.entries(result.models);
  return entries.filter((e): e is [string, LabModelOk] => e[1].status === "ok");
}

function ThresholdEffects({ result }: { result: LookalikeResult }) {
  const models = okModels(result);
  const longest = Math.max(...models.map(([, m]) => m.challenge.curve.length), 1);
  const [index, setIndex] = useState(0);
  const at = Math.min(index, longest - 1);
  return (
    <div className="space-y-2 rounded-md border border-line p-3">
      <h3 className="text-sm font-semibold">Threshold effects on the challenge set</h3>
      <p className="text-xs text-ink-3">Slide from the strictest threshold (left) to the loosest. Each reading is a measured point of the curve above; nothing is interpolated. For the query-level view with real decisions, use the Threshold sandbox tab.</p>
      <input type="range" min={0} max={longest - 1} step={1} value={at} onChange={(e) => setIndex(Number(e.target.value))} className="w-full accent-[var(--brand)]" aria-label="Threshold position on the curve" />
      <div className="grid gap-2 sm:grid-cols-2">
        {models.map(([name, m]) => {
          const curve = m.challenge.curve;
          const point = curve[Math.min(Math.round((at / Math.max(longest - 1, 1)) * (curve.length - 1)), curve.length - 1)];
          return (
            <p key={name} className="rounded-md bg-surface-2 p-2 text-xs">
              <b className="capitalize">{name}</b> at threshold <b className="tabular">{point ? num(point.threshold) : "—"}</b>: strangers accepted <b className="tabular">{point ? pct(point.far, 1) : "—"}</b> of the hard pairs,
              same-person pairs accepted <b className="tabular">{point ? pct(point.tar, 1) : "—"}</b>.
            </p>
          );
        })}
      </div>
    </div>
  );
}

function CurveChart({ result }: { result: LookalikeResult }) {
  const models = okModels(result);
  const series = useMemo(() => models.map(([name, m]) => ({ name, curve: m.challenge.curve, mark: { far: m.challenge.far_on_challenge_set, tar: m.challenge.tar } })), [models]);
  return (
    <ChartFrame
      title="Same-person pairs accepted versus hard strangers accepted"
      description="Each point is one possible threshold on the challenge pairs. Up and to the left is better. The dot marks each model's calibrated threshold."
      help="Hard strangers are different people the baseline model finds alike, so this curve is a stress test, not the everyday ROC (that is in the Evaluation Lab)."
      legend={series.map((s) => ({ label: s.name === "baseline" ? "Baseline" : "Improved", colour: SERIES_COLOUR[s.name] }))}
      table={{ columns: ["Model", "Threshold", "Hard strangers accepted", "Same-person pairs accepted"], caption: "Challenge-set curve points",
        rows: series.flatMap((s) => s.curve.filter((_, i) => i % Math.max(1, Math.floor(s.curve.length / 20)) === 0).map((p) => [s.name, num(p.threshold), pct(p.far, 1), pct(p.tar, 1)])) }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis {...AXIS_PROPS} type="number" dataKey="far" domain={[0, 1]} tickFormatter={(v: number) => pct(v, 0)} label={{ value: "Hard strangers accepted", position: "insideBottom", offset: -12, fill: "var(--ink-3)", fontSize: 11 }} />
          <YAxis {...AXIS_PROPS} type="number" domain={[0, 1]} tickFormatter={(v: number) => pct(v, 0)} width={44} />
          <Tooltip cursor={{ stroke: "var(--axis)" }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as { far: number; tar: number; threshold: number };
            return <TooltipBox title={`Threshold ${num(p.threshold)}`} rows={[{ label: "Hard strangers accepted", value: pct(p.far, 1) }, { label: "Same-person pairs accepted", value: pct(p.tar, 1), colour: payload[0].color }]} />;
          }} />
          {series.map((s) => <Line key={s.name} data={s.curve} dataKey="tar" name={s.name} type="stepAfter" stroke={SERIES_COLOUR[s.name]} strokeWidth={2} dot={false} isAnimationActive={false} />)}
          {series.map((s) => s.mark.far !== null && s.mark.tar !== null ? <ReferenceDot key={`${s.name}-d`} x={s.mark.far} y={s.mark.tar} r={5} fill={SERIES_COLOUR[s.name]} stroke="var(--surface)" strokeWidth={2} ifOverflow="hidden" /> : null)}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export function ChallengePanel({ run, result }: { run: { run_id: string }; result: LookalikeResult }) {
  const def = result.challenge_set.definition;
  const counts = result.challenge_set.counts;
  const models = okModels(result);
  const baseline = result.models.baseline;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Look-alike pairs of people" value={count(counts.identity_pairs)} hint="most alike different people" />
        <Stat label="Different-person comparisons" value={count(counts.impostor_comparisons)} hint="photo pairs a matcher could confuse" definition="Photo pairs of two different people, chosen because the baseline model finds them alike." />
        <Stat label="Same-person comparisons" value={count(counts.genuine_comparisons)} hint="from different cameras" definition="Photo pairs of the same person taken by different cameras: what a matcher must connect." />
        <Stat label="All different-person pairs" value={count(counts.all_pairs_compared)} hint="denominator of the realistic rate" definition="Every different-person photo pair in the searched group, used for the all-pairs false-accept rate." />
      </div>

      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <caption className="sr-only">Each model measured on the same challenge set at its own calibrated threshold</caption>
          <thead className="bg-surface-2 text-xs text-ink-3"><tr>{["Model", "Threshold", "Hard strangers accepted", "All-pairs strangers accepted", "Same-person pairs accepted", "Test: strangers let in", "Test: recall"].map((h) => <th key={h} scope="col" className="px-3 py-2.5 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line tabular">
            {models.map(([name, m]) => (
              <tr key={name}>
                <th scope="row" className="px-3 py-2.5 font-medium">{m.label}</th>
                <td className="px-3 py-2.5">{num(m.rule.threshold)}</td>
                <td className="px-3 py-2.5 font-semibold">{pct(m.challenge.far_on_challenge_set, 1)} <span className="font-normal text-ink-3">({m.challenge.false_accepts} of {m.challenge.impostor_pairs})</span></td>
                <td className="px-3 py-2.5">{pct(m.challenge.far_all_pairs_reference, 3)}</td>
                <td className="px-3 py-2.5">{pct(m.challenge.tar, 1)} <span className="text-ink-3">({m.challenge.true_accepts} of {m.challenge.genuine_pairs})</span></td>
                <td className="px-3 py-2.5">{pct(m.test_query_level.far, 2)} <span className="text-ink-3">({m.test_query_level.counts.unknown_accepted} of {m.test_query_level.counts.unknown_queries})</span></td>
                <td className="px-3 py-2.5">{pct(m.test_query_level.dir_at_rank["1"])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Notice tone="info" title="Read the two stranger columns together">{baseline.challenge.note}</Notice>

      <CurveChart result={result} />
      <ThresholdEffects result={result} />

      <Card aria-labelledby="def-title">
        <CardHeader id="def-title" title="How this challenge set was built" description="Everything needed to rebuild it exactly." />
        <CardBody>
          <DefinitionList items={DEFINITION_LABELS.filter(([key]) => def[key] !== undefined).map(([key, label]) => ({ term: label, value: String(def[key]) }))} />
          <p className="mt-3 text-xs text-ink-3">Dataset: <b>{result.metadata.dataset.name}</b> ({result.metadata.dataset.kind.replace("_", " ")}) · seed {result.metadata.request.seed} · {result.metadata.reproducibility}</p>
        </CardBody>
      </Card>

      <div>
        <h3 className="text-sm font-semibold">The other side: same-person pairs the model finds least alike</h3>
        <p className="mb-2 text-xs text-ink-3">These are the genuine pairs a matcher would turn away first (baseline model).</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {baseline.challenge.hardest_genuine_pairs.slice(0, 6).map((p, i) => <HardGenuineCard key={i} runId={run.run_id} pair={p} threshold={baseline.rule.threshold} />)}
        </div>
        {baseline.challenge.hardest_genuine_pairs.length === 0 && <p className="text-sm text-ink-3">No same-person pairs from different cameras exist in this group.</p>}
      </div>
    </div>
  );
}
