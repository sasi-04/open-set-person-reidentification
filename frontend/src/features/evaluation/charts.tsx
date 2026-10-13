/**
 * The evaluation charts. Every chart plots MEASURED values from a run's result JSON - nothing
 * is smoothed, extrapolated or invented, and missing values are skipped, not drawn as zero.
 */
import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Segmented } from "@/components/ui/Form";
import { num, pct } from "@/lib/format";
import type { EvaluationResult, LatencyStats, ScoreHistogram, VariantResult, VariantSeedResult } from "@/types/api";
import { AXIS_PROPS, ChartFrame, GRID_PROPS, QUERY_KIND_COLOUR, TooltipBox, VARIANT_COLOUR } from "./ChartFrame";

type Metric = "dir1" | "tar";
const METRIC_LABEL: Record<Metric, string> = { dir1: "Recall: accepted and correct (DIR@1)", tar: "Recall: accepted, any identity (TAR)" };

function firstOk(variant: VariantResult, seed: number): VariantSeedResult | undefined {
  return variant.per_seed.find((r) => r.status === "ok" && r.seed === seed);
}

// ----------------------------------------------------------------------------------------------
// ROC: false accepts against recall
// ----------------------------------------------------------------------------------------------
export function RocChart({ result, seed, targetRecall, targetFar }: { result: EvaluationResult; seed: number; targetRecall?: number; targetFar?: number }) {
  const [metric, setMetric] = useState<Metric>("dir1");
  const [logAxis, setLogAxis] = useState(false);

  const series = useMemo(
    () =>
      Object.entries(result.variants).flatMap(([key, variant]) => {
        const run = firstOk(variant, seed);
        if (!run?.curve) return []; // the nearest-neighbour baseline has no curve: it is a single point at FAR = 100%
        const points = run.curve.far.map((far, i) => ({ far, y: run.curve![metric][i] })).filter((p) => (logAxis ? p.far > 0 : true));
        return [{ key, label: variant.label, points, mark: { far: run.test.far, y: metric === "dir1" ? run.test.dir_at_rank["1"] : run.test.tar } }];
      }),
    [result, seed, metric, logAxis],
  );

  const tableRows = series.flatMap((s) => s.points.filter((_, i) => i % Math.max(1, Math.floor(s.points.length / 25)) === 0).map((p) => [s.label, pct(p.far, 2), pct(p.y)]));

  return (
    <ChartFrame
      title="False accepts versus recall (ROC)"
      description={
        metric === "dir1"
          ? "Recall = enrolled people accepted AND correctly identified (DIR@1). Plotted against FAR this is the open-set classification rate (OSCR) curve; the area under it is AUOSCR."
          : METRIC_LABEL[metric]
      }
      help="Each point is one possible threshold on the TEST split. Further left = fewer strangers wrongly accepted (FAR); higher = more enrolled people correctly accepted. Dots mark the threshold that was chosen on the calibration split and frozen before the test split was scored."
      legend={series.map((s) => ({ label: s.label, colour: VARIANT_COLOUR[s.key] }))}
      table={{ columns: ["Variant", "FAR", "Recall"], rows: tableRows, caption: "Sampled points of each ROC curve" }}
      footer={
        <span>
          Curves sweep the threshold on test data to show what the scores allow; the dots are the pre-selected operating points.
          {logAxis && " Points with FAR = 0 cannot be drawn on a logarithmic axis."}
        </span>
      }
    >
      <div className="mb-2 flex flex-wrap gap-4 text-xs">
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={logAxis} onChange={(e) => setLogAxis(e.target.checked)} /> Log FAR axis</label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={metric === "tar"} onChange={(e) => setMetric(e.target.checked ? "tar" : "dir1")} /> Count any identity as accepted (TAR)
        </label>
      </div>
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis {...AXIS_PROPS} type="number" dataKey="far" scale={logAxis ? "log" : "linear"} domain={logAxis ? [0.001, 1] : [0, 1]} allowDataOverflow
              tickFormatter={(v: number) => pct(v, logAxis && v < 0.01 ? 1 : 0)} label={{ value: "False Accept Rate (FAR)", position: "insideBottom", offset: -12, fill: "var(--ink-3)", fontSize: 11 }} />
            <YAxis {...AXIS_PROPS} type="number" domain={[0, 1]} tickFormatter={(v: number) => pct(v, 0)} width={44} />
            <Tooltip
              cursor={{ stroke: "var(--axis)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const point = payload[0].payload as { far: number; y: number };
                return <TooltipBox title={`FAR ${pct(point.far, 2)}`} rows={[{ label: payload[0].name ? String(payload[0].name) : "Recall", value: pct(point.y), colour: payload[0].color }]} />;
              }}
            />
            {targetRecall !== undefined && <ReferenceLine y={targetRecall} stroke="var(--ink-3)" strokeWidth={1} label={{ value: `target recall ${pct(targetRecall, 0)}`, fill: "var(--ink-3)", fontSize: 10, position: "insideBottomRight" }} />}
            {targetFar !== undefined && targetFar > 0 && <ReferenceLine x={targetFar} stroke="var(--ink-3)" strokeWidth={1} label={{ value: `target FAR ${pct(targetFar)}`, fill: "var(--ink-3)", fontSize: 10, position: "insideTopRight" }} />}
            {series.map((s) => (
              <Line key={s.key} data={s.points} dataKey="y" name={s.label} type="stepAfter" stroke={VARIANT_COLOUR[s.key]} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            ))}
            {series.map((s) =>
              s.mark.far !== null && s.mark.y !== null && (!logAxis || s.mark.far > 0) ? (
                <ReferenceDot key={`${s.key}-dot`} x={s.mark.far} y={s.mark.y} r={5} fill={VARIANT_COLOUR[s.key]} stroke="var(--surface)" strokeWidth={2} ifOverflow="hidden" />
              ) : null,
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// ----------------------------------------------------------------------------------------------
// Score distribution: where the low-inter-class-variance problem shows up
// ----------------------------------------------------------------------------------------------
export function ScoreDistributionChart({ histogram, threshold, scale = "cosine similarity" }: { histogram: ScoreHistogram; threshold?: number | null; scale?: string }) {
  const [metric, setMetric] = useState<"share" | "count">("share");
  const totals = {
    known_correct: histogram.known_correct.reduce((a, b) => a + b, 0),
    known_wrong: histogram.known_wrong.reduce((a, b) => a + b, 0),
    unknown: histogram.unknown.reduce((a, b) => a + b, 0),
  };
  const data = histogram.known_correct.map((_, i) => {
    const centre = (histogram.bin_edges[i] + histogram.bin_edges[i + 1]) / 2;
    const row = { x: centre, lo: histogram.bin_edges[i], hi: histogram.bin_edges[i + 1] } as Record<string, number>;
    for (const kind of ["known_correct", "known_wrong", "unknown"] as const) {
      const n = histogram[kind][i];
      row[`${kind}_n`] = n;
      row[kind] = metric === "share" ? (totals[kind] ? (n / totals[kind]) * 100 : 0) : n;
    }
    return row;
  });
  const legend = [
    { label: `Enrolled, correct (${totals.known_correct})`, colour: QUERY_KIND_COLOUR.known_correct },
    { label: `Strangers (${totals.unknown})`, colour: QUERY_KIND_COLOUR.unknown },
    { label: `Enrolled, wrong person (${totals.known_wrong})`, colour: QUERY_KIND_COLOUR.known_wrong },
  ];
  return (
    <ChartFrame
      title="Score distribution of the best candidate"
      description={`Top-1 ${scale} for each kind of query. The more the orange and blue areas overlap, the harder it is to reject strangers without turning enrolled people away.`}
      help="This is the low inter-class variance problem made visible: strangers who look like enrolled people score high, and overlap with the correct matches."
      legend={legend}
      table={{ columns: ["Score range", "Enrolled, correct", "Strangers", "Enrolled, wrong"], caption: "Query counts per score bin",
        rows: data.map((d) => [`${num(d.lo, 2)}–${num(d.hi, 2)}`, d.known_correct_n, d.unknown_n, d.known_wrong_n]) }}
    >
      <div className="mb-2 text-xs">
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={metric === "count"} onChange={(e) => setMetric(e.target.checked ? "count" : "share")} /> Show query counts instead of share of each group</label>
      </div>
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis {...AXIS_PROPS} dataKey="x" type="number" domain={[histogram.bin_edges[0], histogram.bin_edges[histogram.bin_edges.length - 1]]} tickFormatter={(v: number) => num(v, 1)}
              label={{ value: `Top-1 ${scale}`, position: "insideBottom", offset: -12, fill: "var(--ink-3)", fontSize: 11 }} />
            <YAxis {...AXIS_PROPS} width={44} tickFormatter={(v: number) => (metric === "share" ? `${Math.round(v)}%` : String(v))} />
            <Tooltip
              cursor={{ stroke: "var(--axis)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as Record<string, number>;
                return <TooltipBox title={`Score ${num(d.lo, 2)}–${num(d.hi, 2)}`} rows={[
                  { label: "Enrolled, correct", value: String(d.known_correct_n), colour: QUERY_KIND_COLOUR.known_correct },
                  { label: "Strangers", value: String(d.unknown_n), colour: QUERY_KIND_COLOUR.unknown },
                  { label: "Enrolled, wrong", value: String(d.known_wrong_n), colour: QUERY_KIND_COLOUR.known_wrong },
                ]} />;
              }}
            />
            {(["known_correct", "unknown", "known_wrong"] as const).map((kind) => (
              <Area key={kind} dataKey={kind} type="stepAfter" stroke={QUERY_KIND_COLOUR[kind]} strokeWidth={2} fill={QUERY_KIND_COLOUR[kind]} fillOpacity={0.12} isAnimationActive={false} />
            ))}
            {threshold !== null && threshold !== undefined && (
              <ReferenceLine x={threshold} stroke="var(--ink)" strokeWidth={1.5} label={{ value: `threshold ${num(threshold, 2)}`, fill: "var(--ink)", fontSize: 11, position: "insideTopRight" }} />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// ----------------------------------------------------------------------------------------------
// CMC: closed-set retrieval
// ----------------------------------------------------------------------------------------------
export function CmcChart({ result, seed }: { result: EvaluationResult; seed: number }) {
  const lines = Object.entries(result.variants).flatMap(([key, variant]) => {
    const run = firstOk(variant, seed);
    // Variants that share the same embeddings share the same CMC; draw each distinct source once.
    return run && run.closed_set.cmc.length ? [{ key, label: variant.label, cmc: run.closed_set.cmc }] : [];
  });
  const unique = lines.filter((l, i) => lines.findIndex((o) => JSON.stringify(o.cmc) === JSON.stringify(l.cmc)) === i);
  const ranks = unique[0]?.cmc.length ?? 0;
  const data = Array.from({ length: ranks }, (_, i) => ({ rank: i + 1, ...Object.fromEntries(unique.map((l) => [l.key, l.cmc[i]])) }));
  return (
    <ChartFrame
      title="Closed-set retrieval (CMC)"
      description="Share of enrolled-person queries whose true identity is among the top-k candidates. Thresholds are ignored: this asks whether retrieval works at all."
      legend={unique.map((l) => ({ label: l.key === "nn_baseline" ? "Base embeddings" : l.label, colour: VARIANT_COLOUR[l.key] }))}
      table={{ columns: ["Rank", ...unique.map((l) => (l.key === "nn_baseline" ? "Base embeddings" : l.label))], caption: "Rank-k accuracy", rows: data.map((d) => [d.rank, ...unique.map((l) => pct(d[l.key as keyof typeof d] as number))]) }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis {...AXIS_PROPS} dataKey="rank" type="number" domain={[1, ranks]} allowDecimals={false} label={{ value: "Rank k", position: "insideBottom", offset: -12, fill: "var(--ink-3)", fontSize: 11 }} />
          <YAxis {...AXIS_PROPS} domain={[0, 1]} tickFormatter={(v: number) => pct(v, 0)} width={44} />
          <Tooltip cursor={{ stroke: "var(--axis)" }} content={({ active, payload, label }) => active && payload?.length ? (
            <TooltipBox title={`Rank ${label}`} rows={payload.map((p) => ({ label: String(p.name), value: pct(p.value as number), colour: p.color }))} />) : null} />
          {unique.map((l) => <Line key={l.key} dataKey={l.key} name={l.key === "nn_baseline" ? "Base embeddings" : l.label} stroke={VARIANT_COLOUR[l.key]} strokeWidth={2} dot={{ r: 3, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

// ----------------------------------------------------------------------------------------------
// Latency
// ----------------------------------------------------------------------------------------------
export function LatencyChart({ stats }: { stats: LatencyStats }) {
  const data = [
    { name: "Median (p50)", ms: stats.p50 ?? 0 },
    { name: "p95", ms: stats.p95 ?? 0 },
    { name: "p99", ms: stats.p99 ?? 0 },
  ];
  return (
    <ChartFrame
      title="Embedding latency, one crop at a time"
      description={`Steady state after warm-up, ${stats.n} measurements on this machine. Lower is better.`}
      table={{ columns: ["Percentile", "Milliseconds"], caption: "Embedding latency percentiles", rows: [...data.map((d) => [d.name, num(d.ms, 1)]), ["Mean", num(stats.mean ?? null, 1)], ["Min", num(stats.min ?? null, 1)], ["Max", num(stats.max ?? null, 1)]] }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis {...AXIS_PROPS} dataKey="name" />
          <YAxis {...AXIS_PROPS} width={52} unit=" ms" />
          <Tooltip cursor={{ fill: "var(--surface-2)" }} content={({ active, payload }) => active && payload?.length ? <TooltipBox title={String(payload[0].payload.name)} rows={[{ label: "Latency", value: `${num(payload[0].value as number, 1)} ms`, colour: "var(--series-1)" }]} /> : null} />
          <Bar dataKey="ms" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={56} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** Small control used by the results view to pick a seed when several were run. */
export function SeedPicker({ seeds, value, onChange }: { seeds: number[]; value: number; onChange: (seed: number) => void }) {
  if (seeds.length < 2) return null;
  return (
    <Segmented label="Seed shown in the charts" value={String(value)} onChange={(v) => onChange(Number(v))} options={seeds.map((s) => ({ value: String(s), label: `Seed ${s}` }))} />
  );
}
