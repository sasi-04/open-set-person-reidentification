/**
 * ResultsView: the full result of one evaluation run.
 *
 * In plain words: a headline for the configuration that was selected (using calibration data
 * only), then tabs for the ablation table, the ROC curve, the score distributions, retrieval
 * accuracy, the same-clothing subset, speed and the experiment metadata. Everything shown is
 * read from the stored result; missing values are shown as "—", never as zero.
 */
import { Download } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, DefinitionList, Stat } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Feedback";
import { Select } from "@/components/ui/Form";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { count, dateTime, num, pct } from "@/lib/format";
import { api } from "@/services/api";
import { describeError, saveBlob } from "@/services/http";
import type { EvaluationResult, RunDetail, VariantSeedResult } from "@/types/api";
import { AblationTable } from "./AblationTable";
import { CmcChart, LatencyChart, RocChart, ScoreDistributionChart, SeedPicker } from "./charts";
import { ThresholdSandbox } from "./ThresholdSandbox";

function Downloads({ run }: { run: RunDetail }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  async function download(format: "json" | "md" | "html") {
    setBusy(format);
    try {
      saveBlob(await api.reportBlob(run.run_id, format), `reid-report-${run.run_id.slice(0, 8)}.${format}`);
      toast.success(`Report downloaded (${format.toUpperCase()}).`);
    } catch (failure) {
      toast.error(describeError(failure));
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Download the report">
      {(["html", "md", "json"] as const).map((f) => (
        <Button key={f} size="sm" loading={busy === f} icon={<Download aria-hidden className="size-3.5" />} onClick={() => void download(f)}>
          {f === "md" ? "Markdown" : f.toUpperCase()}
        </Button>
      ))}
    </div>
  );
}

export function ResultsView({ run, result }: { run: RunDetail; result: EvaluationResult }) {
  const seeds = result.metadata.request.seeds as number[];
  const [seed, setSeed] = useState(seeds[0]);
  const selectedKey = result.selected_variant.key;
  const [histogramVariant, setHistogramVariant] = useState(selectedKey ?? "thr");
  const chosen = selectedKey ? result.variants[selectedKey] : null;
  const chosenSeed: VariantSeedResult | undefined = chosen?.per_seed.find((r) => r.status === "ok" && r.seed === seed) ?? chosen?.per_seed.find((r) => r.status === "ok");
  const target = result.metadata.request.target as { mode: string; target_recall: number; target_far: number };

  const histogramRun = result.variants[histogramVariant]?.per_seed.find((r) => r.status === "ok" && r.seed === seed);
  const selectableVariants = Object.entries(result.variants).filter(([, v]) => v.per_seed.some((r) => r.status === "ok"));

  const protocolOfSeed = result.metadata.protocol[String(seed)] ?? Object.values(result.metadata.protocol)[0];
  const perf = result.performance;

  return (
    <div className="space-y-4">
      {result.warnings.map((w) => <Notice key={w} tone="warn" title="Not a benchmark result">{w}</Notice>)}

      <Card aria-labelledby="headline-title">
        <CardHeader
          id="headline-title"
          title="Selected configuration"
          description={`${result.metadata.dataset.name} · ${result.metadata.operating_target} · ${dateTime(result.metadata.started_at)} · ${Math.round(result.metadata.duration_seconds)} s`}
          action={<Downloads run={run} />}
        />
        <CardBody className="space-y-4">
          {!chosen || !chosenSeed ? (
            <Notice tone="warn" title="No configuration reached the requested operating point">
              {result.selected_variant.reason} The ablation table below shows what each variant achieved. Nothing was tuned on the test split to hide this.
            </Notice>
          ) : (
            <>
              <p className="text-sm">
                <b>{chosen.label}</b> was selected on the <b>calibration split</b> ({result.selected_variant.criterion}). Its frozen rule was then applied to the held-out test split:
              </p>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
                <Stat label="Recall (DIR@1)" value={pct(chosenSeed.test.dir_at_rank["1"])} hint="Enrolled people accepted and correct" definition="Accepted AND correctly identified ÷ all enrolled-person queries, on the test split." />
                <Stat label="False accepts (FAR)" value={pct(chosenSeed.test.far, 2)} hint={`${chosenSeed.test.counts.unknown_accepted} of ${chosenSeed.test.counts.unknown_queries} strangers`} definition="Strangers for whom the system named an enrolled person ÷ all stranger queries." />
                <Stat label="Rank-1" value={pct(chosenSeed.closed_set.rank1)} hint="Closed-set retrieval" />
                <Stat label="mAP" value={pct(chosenSeed.closed_set.mAP)} hint="Mean average precision" />
                <Stat label="AUOSCR" value={num(chosenSeed.auoscr ?? null)} hint="Open-set rejection + identification" definition="Area under DIR@1 versus FAR as the threshold sweeps; 1.0 is perfect." />
              </div>
              <p className="text-xs text-ink-3">
                Chosen on calibration data: threshold <b>{num(chosenSeed.selected?.threshold ?? null)}</b>, margin <b>{chosenSeed.selected?.min_margin === null ? "none" : num(chosenSeed.selected?.min_margin ?? null)}</b>.
                Calibration FAR was {pct(chosenSeed.selected?.calibration.far ?? null, 2)} (95% upper bound {pct(chosenSeed.selected?.far_upper_bound_95 ?? null, 2)}) from {chosenSeed.selected?.n_unknown} stranger queries
                {chosenSeed.selected && !chosenSeed.selected.sample_size_adequate && " — too few to resolve this FAR target"}. Test FAR can differ: that difference is the honest generalisation gap.
              </p>
            </>
          )}
          <SeedPicker seeds={seeds} value={seed} onChange={setSeed} />
        </CardBody>
      </Card>

      <Card aria-labelledby="detail-title">
        <CardHeader id="detail-title" title="Results in detail" description="Switch between views. Every chart has a data table underneath. The Threshold sandbox lets you try other thresholds safely." />
        <CardBody>
          <Tabs tabs={[
            { id: "ablation", label: "Ablation", content: (
              <div className="space-y-3">
                <p className="text-sm text-ink-2">Each row adds one ingredient to its parent and is measured the same way on the same held-out people.</p>
                <AblationTable result={result} />
              </div>) },
            { id: "roc", label: "ROC / FAR vs TAR", content: (
              <div className="space-y-5">
                <RocChart result={result} seed={seed} targetRecall={target.mode === "fixed_recall" ? target.target_recall : undefined} targetFar={target.mode === "fixed_far" ? target.target_far : undefined} />
                <FarSweepTable result={result} seed={seed} />
              </div>) },
            { id: "scores", label: "Score distribution", content: (
              <div className="space-y-3">
                <label className="flex max-w-sm flex-col gap-1.5 text-sm font-medium">Variant
                  <Select value={histogramVariant} onChange={(e) => setHistogramVariant(e.target.value)}>
                    {selectableVariants.map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </Select>
                </label>
                {histogramRun ? <ScoreDistributionChart histogram={histogramRun.score_histogram} threshold={histogramRun.selected?.threshold} scale={histogramRun.score_scale} /> : <p className="text-sm text-ink-3">No data for this variant.</p>}
                {histogramRun?.confidence_model && <ConfidenceQuality run={histogramRun} />}
              </div>) },
            ...(result.sandbox_available ? [{ id: "sandbox", label: "Threshold sandbox", content: <ThresholdSandbox runId={run.run_id} /> }] : []),
            { id: "cmc", label: "Retrieval (CMC, mAP)", content: <CmcChart result={result} seed={seed} /> },
            { id: "hard", label: "Same-clothing subset", content: <HardSubset result={result} seed={seed} /> },
            { id: "speed", label: "Speed & memory", content: (
              <div className="space-y-4">
                {perf.embedding?.single_crop_ms && <LatencyChart stats={perf.embedding.single_crop_ms} />}
                <DefinitionList items={[
                  { term: "Device", value: perf.device },
                  { term: "Batch throughput", value: perf.embedding ? `${perf.embedding.batch.throughput_crops_per_second} crops/s (batch of ${perf.embedding.batch.batch_size}, ${perf.embedding.batch.ms_per_crop} ms per crop)` : "—" },
                  { term: "Retrieval", value: `${perf.retrieval_ms_per_query} ms per query against ${count(perf.retrieval_gallery_images)} gallery images` },
                  { term: "Model load (one-off)", value: `${perf.model_load_seconds} s` },
                  { term: "Warm-up (one-off)", value: `${perf.warmup_seconds} s` },
                  { term: "Peak process memory", value: perf.peak_memory_mb !== null ? `${perf.peak_memory_mb} MB` : "—" },
                ]} />
                <p className="text-xs text-ink-3">{perf.note} Detection time is not part of this benchmark; it is reported per request in the inference history.</p>
              </div>) },
            { id: "meta", label: "Experiment metadata", content: (
              <div className="space-y-3">
                <DefinitionList items={[
                  { term: "Run", value: <span className="font-mono text-xs">{run.run_id}</span> },
                  { term: "Dataset", value: `${result.metadata.dataset.name} (${result.metadata.dataset.kind.replace("_", " ")})` },
                  { term: "Seeds", value: seeds.join(", ") },
                  { term: "Model", value: `${String(result.metadata.model.architecture)} · ${String(result.metadata.model.weights)}` },
                  { term: "Model fingerprint", value: <span className="font-mono text-xs break-all">{String(result.metadata.model.fingerprint)}</span> },
                  { term: "Calibration split", value: `${protocolOfSeed.calibration.enrolled_identities} enrolled + ${protocolOfSeed.calibration.unknown_identities} unknown people; ${protocolOfSeed.calibration.known_queries} known / ${protocolOfSeed.calibration.unknown_queries} unknown queries` },
                  { term: "Test split", value: `${protocolOfSeed.test.enrolled_identities} enrolled + ${protocolOfSeed.test.unknown_identities} unknown people; ${protocolOfSeed.test.known_queries} known / ${protocolOfSeed.test.unknown_queries} unknown queries` },
                  { term: "Software", value: `Python ${String(result.metadata.software.python)} · torch ${String(result.metadata.software.torch)} · numpy ${String(result.metadata.software.numpy)}` },
                ]} />
                <details className="text-xs"><summary className="cursor-pointer font-medium">Full request configuration (JSON)</summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-surface-2 p-3 whitespace-pre-wrap">{JSON.stringify(result.metadata.request, null, 2)}</pre></details>
              </div>) },
          ]} />
        </CardBody>
      </Card>
    </div>
  );
}

function FarSweepTable({ result, seed }: { result: EvaluationResult; seed: number }) {
  const rows = Object.entries(result.variants).flatMap(([key, v]) => {
    const run = v.per_seed.find((r) => r.status === "ok" && r.seed === seed);
    return run?.curve_operating_points?.map((p) => ({ key, label: v.label, ...p })) ?? [];
  });
  if (!rows.length) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold">Recall at fixed false-accept rates</h3>
      <p className="mb-2 text-xs text-ink-3">Read off the test-split ROC at each FAR (step function, no interpolation). These sweep the threshold on test data, so they describe what the scores allow - they are not pre-registered operating points.</p>
      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full min-w-[32rem] text-left text-xs">
          <caption className="sr-only">Recall at fixed FAR values</caption>
          <thead className="bg-surface-2 text-ink-3"><tr>{["Variant", "FAR limit", "TAR", "DIR@1", "Achieved FAR"].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line tabular">
            {rows.map((r, i) => <tr key={`${r.key}-${i}`}><td className="px-3 py-1.5">{r.label}</td><td className="px-3 py-1.5">≤ {pct(r.target_far, 1)}</td><td className="px-3 py-1.5">{pct(r.recall)}</td><td className="px-3 py-1.5">{pct(r.dir1)}</td><td className="px-3 py-1.5">{pct(r.achieved_far, 2)}</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HardSubset({ result, seed }: { result: EvaluationResult; seed: number }) {
  const protocol = result.metadata.protocol[String(seed)] ?? Object.values(result.metadata.protocol)[0];
  const method = protocol.hard_subset as { test?: { method?: string; note?: string; queries?: number } } | undefined;
  const rows = Object.entries(result.variants).flatMap(([key, v]) => {
    const run = v.per_seed.find((r) => r.status === "ok" && r.seed === seed);
    return run && key !== "nn_baseline" ? [{ key, label: v.label, run }] : [];
  });
  return (
    <div className="space-y-4">
      <Notice tone="info" title="How the same-clothing subset was chosen">
        {method?.test?.method ?? "Colour-histogram proxy"}: the queries whose torso/leg colours are closest to ANOTHER enrolled person ({method?.test?.queries ?? "?"} queries on test). {method?.test?.note} It was fixed from the images alone, before any scores or outcomes were looked at.
      </Notice>
      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <caption className="sr-only">Same frozen rule on all queries versus the look-alike subset</caption>
          <thead className="bg-surface-2 text-xs text-ink-3"><tr>{["Variant", "FAR · all", "FAR · look-alikes", "DIR@1 · all", "DIR@1 · look-alikes", "Recall needed on look-alikes*"].map((h) => <th key={h} scope="col" className="px-3 py-2.5 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line tabular">
            {rows.map(({ key, label, run }) => {
              const aware = run.hard_subset.hard_aware_calibration;
              return (
                <tr key={key}>
                  <td className="px-3 py-2.5 font-medium">{label}</td>
                  <td className="px-3 py-2.5">{pct(run.test.far, 2)}</td>
                  <td className="px-3 py-2.5 font-semibold">{pct(run.hard_subset.test.far, 2)}</td>
                  <td className="px-3 py-2.5">{pct(run.test.dir_at_rank["1"])}</td>
                  <td className="px-3 py-2.5">{pct(run.hard_subset.test.dir_at_rank["1"])}</td>
                  <td className="px-3 py-2.5 text-xs">{aware?.test ? `${pct(aware.test.dir_at_rank["1"])} at FAR ${pct(aware.test.far, 2)}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">The same threshold is used for both columns. *Last column: if the threshold is instead re-selected on the calibration look-alikes to meet the same target, this is the recall and FAR that result on test look-alikes - the price of holding the target against look-alikes.</p>
    </div>
  );
}

function ConfidenceQuality({ run }: { run: VariantSeedResult }) {
  const q = run.confidence_model!.quality_on_test;
  return (
    <Notice tone="info" title="Calibrated confidence: how trustworthy is it?">
      {run.confidence_model!.meaning} On the test split: expected calibration error <b>{pct(q.ece, 1)}</b>, Brier score <b>{num(q.brier)}</b> ({q.n} queries). Lower is better; it holds only for the known:unknown mix of the calibration split.
      <Badge tone="neutral" className="ml-2">fitted on calibration only</Badge>
    </Notice>
  );
}
