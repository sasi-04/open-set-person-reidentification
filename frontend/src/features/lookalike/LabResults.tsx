/**
 * LabResults: everything one Lookalike Failure Lab experiment found, in six tabs.
 *
 *   Look-alike pairs     the different people the model finds most alike (photos side by side)
 *   Challenge set        the reproducible test list, each model's numbers, the curve, threshold effects
 *   Mistakes             real false accepts / rejections, with measured facts and unproven hypotheses
 *   Baseline vs improved the two models on identical examples - or why no comparison exists
 *   Threshold sandbox    try other thresholds on the stored query results (never changes the policy)
 *   Method & limits      definitions, limitations, reproducibility
 *
 * Everything is read from the stored result. Where something is missing (no improved model, no
 * benchmark) the screen says so; it never fills the gap with a made-up number.
 */
import { Download } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, DefinitionList, Stat } from "@/components/ui/Card";
import { EmptyState, Notice } from "@/components/ui/Feedback";
import { Select } from "@/components/ui/Form";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { ThresholdSandbox } from "@/features/evaluation/ThresholdSandbox";
import { count, dateTime, num, pct } from "@/lib/format";
import { api, type LabExportFormat } from "@/services/api";
import { describeError, saveBlob } from "@/services/http";
import type { FailureCategory, LabModelOk, LabModelUnavailable, LookalikeResult, RunDetail } from "@/types/api";
import { ChallengePanel } from "./ChallengePanel";
import { FailureCard, PairCard } from "./cards";

const PAGE = 6;
const EXPORTS: { format: LabExportFormat; label: string; file: string }[] = [
  { format: "json", label: "Full record (JSON)", file: "json" },
  { format: "pairs_csv", label: "Pairs (CSV)", file: "pairs.csv" },
  { format: "failures_csv", label: "Mistakes (CSV)", file: "failures.csv" },
  { format: "summary_csv", label: "Summary (CSV)", file: "summary.csv" },
  { format: "md", label: "Report (Markdown)", file: "md" },
];

function ExportBar({ run }: { run: RunDetail }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  async function download(format: LabExportFormat, file: string) {
    setBusy(format);
    try {
      saveBlob(await api.labExport(run.run_id, format), `lookalike-${run.run_id.slice(0, 8)}.${file}`);
      toast.success("Export downloaded.");
    } catch (failure) {
      toast.error(describeError(failure));
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Export this experiment">
      {EXPORTS.map((e) => (
        <Button key={e.format} size="sm" loading={busy === e.format} icon={<Download aria-hidden className="size-3.5" />} onClick={() => void download(e.format, e.file)}>{e.label}</Button>
      ))}
    </div>
  );
}

function More({ shown, total, onMore }: { shown: number; total: number; onMore: () => void }) {
  if (shown >= total) return null;
  return <div className="mt-3 text-center"><Button size="sm" onClick={onMore}>Show {Math.min(PAGE, total - shown)} more ({shown} of {total} shown)</Button></div>;
}

function PairsPanel({ run, result }: { run: RunDetail; result: LookalikeResult }) {
  const [filter, setFilter] = useState<"all" | "accepted" | "clothing">("all");
  const [shown, setShown] = useState(PAGE);
  const thresholds: Record<string, number> = Object.fromEntries(
    Object.entries(result.models).flatMap(([name, m]): [string, number][] => (m.status === "ok" ? [[name, (m as LabModelOk).rule.threshold]] : [])),
  );
  const all = result.challenge_set.identity_pairs;
  const pairs = all.filter((p) => (filter === "accepted" ? p.by_model.baseline.decision === "false_accept" : filter === "clothing" ? p.similar_clothing_proxy : true));
  const wrongly = all.filter((p) => p.by_model.baseline.decision === "false_accept").length;
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-2">
        The {count(all.length)} pairs of <b>different</b> people that the baseline model finds most alike, searched among the <b>{String(result.metadata.request.mining_split)}</b> people.
        {" "}<b>{wrongly}</b> of them score above the calibrated threshold, which means a matcher using that threshold would treat the two as the same person.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex max-w-full min-w-0 flex-wrap items-center gap-2 text-sm font-medium">Show
          <Select className="!w-auto max-w-full min-w-0" value={filter} onChange={(e) => { setFilter(e.target.value as typeof filter); setShown(PAGE); }}>
            <option value="all">all pairs</option>
            <option value="accepted">only pairs the matcher would accept (false accepts)</option>
            <option value="clothing">only pairs with similar clothing colours</option>
          </Select>
        </label>
        <span className="text-xs text-ink-3">{pairs.length} shown</span>
      </div>
      {pairs.length === 0 ? <EmptyState title="No pairs match this filter" /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{pairs.slice(0, shown).map((p) => <PairCard key={p.rank} runId={run.run_id} pair={p} thresholds={thresholds} />)}</div>
          <More shown={shown} total={pairs.length} onMore={() => setShown((n) => n + PAGE)} />
        </>
      )}
    </div>
  );
}

const CATEGORY_FILTERS: { value: "all" | FailureCategory; label: string }[] = [
  { value: "all", label: "all mistakes" },
  { value: "incorrect_acceptance", label: "strangers accepted" },
  { value: "wrong_identity_accepted", label: "enrolled people given the wrong name" },
  { value: "genuine_rejected", label: "enrolled people not accepted" },
];

function FailuresPanel({ run, result }: { run: RunDetail; result: LookalikeResult }) {
  const models = Object.keys(result.failures);
  const [model, setModel] = useState(models[0]);
  const [category, setCategory] = useState<"all" | FailureCategory>("all");
  const [shown, setShown] = useState(PAGE);
  const block = result.failures[model];
  const list = block.listed.filter((f) => category === "all" || f.category === category);
  const c = block.counts;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Strangers accepted" value={count(c.incorrect_acceptance)} hint={`of ${count(result.models.baseline.test_query_level.counts.unknown_queries)} stranger queries`} definition="A person who is not enrolled was accepted as an enrolled person." />
        <Stat label="Wrong name given" value={count(c.wrong_identity_accepted)} hint="enrolled, but a different person named" definition="An enrolled person was accepted, but as a different enrolled person." />
        <Stat label="Enrolled, not accepted" value={count(c.genuine_rejected)} hint={`${count(c.genuine_sent_to_review)} sent to REVIEW`} definition="An enrolled person was not accepted: UNKNOWN (below the threshold) or REVIEW (ambiguous)." />
        <Stat label="Queries checked" value={count(c.queries)} hint="on the test people" />
      </div>
      <Notice tone="info" title="Observed versus possible">{block.note}</Notice>
      <div className="flex flex-wrap items-center gap-3">
        {models.length > 1 && (
          <label className="flex max-w-full min-w-0 flex-wrap items-center gap-2 text-sm font-medium">Model
            <Select className="!w-auto max-w-full min-w-0" value={model} onChange={(e) => { setModel(e.target.value); setShown(PAGE); }}>{models.map((m) => <option key={m} value={m}>{m === "baseline" ? "Baseline" : "Improved"}</option>)}</Select>
          </label>
        )}
        <label className="flex max-w-full min-w-0 flex-wrap items-center gap-2 text-sm font-medium">Show
          <Select className="!w-auto max-w-full min-w-0" value={category} onChange={(e) => { setCategory(e.target.value as typeof category); setShown(PAGE); }}>{CATEGORY_FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</Select>
        </label>
        <span className="text-xs text-ink-3">{list.length} listed (the most instructive first; counts above cover all)</span>
      </div>
      {list.length === 0 ? (
        <EmptyState title={c.incorrect_acceptance + c.wrong_identity_accepted + c.genuine_rejected === 0 ? "No mistakes on these people" : "Nothing in this category"}>
          {c.incorrect_acceptance + c.wrong_identity_accepted + c.genuine_rejected === 0 ? "At this threshold every query was handled correctly. That describes this sample only." : "Try another category."}
        </EmptyState>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{list.slice(0, shown).map((f) => <FailureCard key={f.id} runId={run.run_id} failure={f} />)}</div>
          <More shown={shown} total={list.length} onMore={() => setShown((n) => n + PAGE)} />
        </>
      )}
    </div>
  );
}

function ComparisonPanel({ result }: { result: LookalikeResult }) {
  const improved = result.models.improved as LabModelOk | LabModelUnavailable;
  if (improved.status !== "ok" || !result.comparison) {
    return (
      <div className="space-y-3">
        <Notice tone="warn" title="No improved-model comparison in this experiment">{(improved as LabModelUnavailable).reason}</Notice>
        <p className="text-sm text-ink-2">Nothing is shown here because nothing was measured: this project makes no claim that metric-learning fine-tuning improves results until a checkpoint has been trained on the development people and evaluated like this on held-out people.</p>
        <p className="text-xs text-ink-3">To create one: <code className="font-mono">python scripts/finetune_triplet.py</code> (README, “Metric-learning fine-tuning”), then run this experiment again and pick the checkpoint.</p>
      </div>
    );
  }
  const [base, tuned] = result.comparison;
  const rows: [string, string, string, string][] = [
    ["Threshold (chosen on calibration people)", num(base.threshold), num(tuned.threshold), "differs per model"],
    ["Test: strangers let in", `${pct(base.test_far, 2)} (${base.test_unknown_accepted} of ${base.test_unknown_queries})`, `${pct(tuned.test_far, 2)} (${tuned.test_unknown_accepted} of ${tuned.test_unknown_queries})`, "—"],
    ["Test: recall (DIR@1)", pct(base.test_recall_dir1), pct(tuned.test_recall_dir1), "—"],
    ["Challenge: hard strangers accepted", `${pct(base.challenge_far, 1)} (${base.challenge_false_accepts} of ${base.challenge_impostor_pairs})`, `${pct(tuned.challenge_far, 1)} (${tuned.challenge_false_accepts} of ${tuned.challenge_impostor_pairs})`, "same pairs for both"],
    ["Challenge: same-person pairs accepted", pct(base.challenge_tar), pct(tuned.challenge_tar), "same pairs for both"],
    ["Speed: one crop, median", base.single_crop_ms_p50 === null ? "—" : `${base.single_crop_ms_p50} ms`, tuned.single_crop_ms_p50 === null ? "—" : `${tuned.single_crop_ms_p50} ms`, "measured on this machine"],
  ];
  return (
    <div className="space-y-3">
      <Notice tone="info" title="Same examples, each model at its own calibrated threshold">The two models are scored on identical challenge pairs and identical test queries. The hard strangers were chosen with the baseline model, so the comparison is a fair stress test but not a random sample.</Notice>
      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full min-w-[34rem] text-left text-sm">
          <caption className="sr-only">Baseline and improved model compared on the same examples</caption>
          <thead className="bg-surface-2 text-xs text-ink-3"><tr>{["Measure", "Baseline", "Improved", "Note"].map((h) => <th key={h} scope="col" className="px-3 py-2.5 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line tabular">{rows.map(([m, a, b, n]) => <tr key={m}><th scope="row" className="px-3 py-2.5 font-medium">{m}</th><td className="px-3 py-2.5">{a}</td><td className="px-3 py-2.5 font-semibold">{b}</td><td className="px-3 py-2.5 text-xs text-ink-3">{n}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">Differences of a few examples are within sampling noise. Check the counts before reading anything into a percentage.</p>
    </div>
  );
}

function MethodPanel({ result, run }: { result: LookalikeResult; run: RunDetail }) {
  const m = result.metadata;
  const baseline = result.models.baseline;
  return (
    <div className="space-y-4">
      <Card aria-labelledby="lim-title">
        <CardHeader id="lim-title" title="Limitations of this experiment" />
        <CardBody><ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">{result.limitations.map((l) => <li key={l}>{l}</li>)}</ul></CardBody>
      </Card>
      <Card aria-labelledby="repro-title">
        <CardHeader id="repro-title" title="Reproducibility" description="Enough to repeat the experiment exactly." />
        <CardBody>
          <DefinitionList items={[
            { term: "Experiment ID", value: <span className="font-mono text-xs">{run.run_id}</span> },
            { term: "Dataset", value: `${m.dataset.name} (${m.dataset.kind.replace("_", " ")}, ${m.dataset.layout} layout, ${count(m.dataset.identities)} people, ${count(m.dataset.images)} images)` },
            { term: "Seed and split", value: `seed ${m.request.seed}; searched the ${m.request.mining_split} people` },
            { term: "Operating target", value: m.operating_target },
            { term: "Baseline model", value: <span className="font-mono text-xs break-all">{String((baseline.model as Record<string, unknown> | undefined)?.fingerprint ?? "—")}</span> },
            { term: "Software", value: `Python ${String(m.software.python)} · torch ${String(m.software.torch)} · numpy ${String(m.software.numpy)}` },
            { term: "Duration", value: `${Math.round(m.duration_seconds)} s, started ${dateTime(m.started_at)}` },
          ]} />
          <details className="mt-3 text-xs"><summary className="cursor-pointer font-medium">Full request (JSON)</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-surface-2 p-3 whitespace-pre-wrap">{JSON.stringify(m.request, null, 2)}</pre></details>
        </CardBody>
      </Card>
    </div>
  );
}

export function LabResults({ run, result }: { run: RunDetail; result: LookalikeResult }) {
  const baseline = result.models.baseline;
  return (
    <div className="space-y-4">
      {result.warnings.map((w) => <Notice key={w} tone="warn" title="Read this first">{w}</Notice>)}

      <Card aria-labelledby="lab-headline">
        <CardHeader
          id="lab-headline"
          title="What this experiment found"
          description={`${result.metadata.dataset.name} · searched ${String(result.metadata.request.mining_split)} people · ${result.metadata.operating_target} · ${dateTime(result.metadata.started_at)}`}
          action={<ExportBar run={run} />}
        />
        <CardBody className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Hard strangers accepted" value={pct(baseline.challenge.far_on_challenge_set, 1)} hint={`${baseline.challenge.false_accepts} of ${baseline.challenge.impostor_pairs} look-alike comparisons`} definition="Of the different-person pairs chosen because the model finds them alike, the share the baseline matcher would accept. High by construction." />
            <Stat label="Strangers accepted, all pairs" value={pct(baseline.challenge.far_all_pairs_reference, 3)} hint={`of ${count(baseline.challenge.all_pairs_compared)} different-person pairs`} definition="The same question asked of EVERY different-person pair: the realistic rate." />
            <Stat label="Test: strangers let in" value={pct(baseline.test_query_level.far, 2)} hint={`${baseline.test_query_level.counts.unknown_accepted} of ${baseline.test_query_level.counts.unknown_queries} stranger queries`} definition="Query-level false-accept rate on the test people at the calibrated threshold." />
            <Stat label="Test: recall" value={pct(baseline.test_query_level.dir_at_rank["1"])} hint="enrolled people accepted and correct" definition="DIR@1: accepted AND correctly named, divided by all enrolled-person queries." />
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
            <Badge tone={baseline.calibration.target_achieved ? "ok" : "warn"}>{baseline.calibration.target_achieved ? "Calibration target reached" : "Calibration target NOT reached"}</Badge>
            <span>threshold {num(baseline.rule.threshold)} chosen on {count(baseline.calibration.n_known)} enrolled and {count(baseline.calibration.n_unknown)} stranger calibration queries</span>
            <Badge tone={result.metadata.is_benchmark ? "ok" : "warn"}>{result.metadata.is_benchmark ? "Benchmark dataset" : "Smoke test, not a benchmark"}</Badge>
            <Badge tone={result.models.improved.status === "ok" ? "info" : "neutral"}>{result.models.improved.status === "ok" ? "Improved model compared" : "Baseline only"}</Badge>
          </div>
        </CardBody>
      </Card>

      <Card aria-labelledby="lab-detail">
        <CardHeader id="lab-detail" title="Explore the results" description="Every number is read from the stored experiment." />
        <CardBody>
          <Tabs tabs={[
            { id: "pairs", label: "Look-alike pairs", content: <PairsPanel run={run} result={result} /> },
            { id: "challenge", label: "Challenge set", content: <ChallengePanel run={run} result={result} /> },
            { id: "failures", label: "Mistakes", content: <FailuresPanel run={run} result={result} /> },
            { id: "compare", label: "Baseline vs improved", content: <ComparisonPanel result={result} /> },
            ...(result.sandbox_available ? [{ id: "sandbox", label: "Threshold sandbox", content: <ThresholdSandbox runId={run.run_id} /> }] : []),
            { id: "method", label: "Method & limits", content: <MethodPanel result={result} run={run} /> },
          ]} />
        </CardBody>
      </Card>
    </div>
  );
}
