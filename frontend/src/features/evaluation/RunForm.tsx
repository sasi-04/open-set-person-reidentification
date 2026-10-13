/**
 * RunForm: configure and launch an experiment.
 *
 * In plain words: pick a dataset, say what you want to hold fixed (a recall to keep, or a
 * false-accept limit), and press either "Run evaluation" (the whole study with ablations on
 * a held-out test split) or "Calibrate threshold" (only chooses a threshold on the
 * calibration split - the test split is never read). Both start a background job whose real
 * progress is shown below the form.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Feedback";
import { Checkbox, Field, Segmented, Select, TextInput } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { api, keys, type EvaluationBody } from "@/services/api";
import { describeError } from "@/services/http";
import type { DatasetInfo, RunDetail } from "@/types/api";

const VARIANT_CHOICES = [
  { key: "nn_baseline", label: "Nearest neighbour (no rejection)", on: true },
  { key: "thr", label: "+ Calibrated threshold", on: true },
  { key: "thr_margin", label: "+ Top-1/top-2 margin rule", on: true },
  { key: "thr_confidence", label: "+ Calibrated confidence", on: true },
  { key: "thr_margin_flip", label: "+ Flip test-time augmentation", on: true },
];

function number(text: string, low: number, high: number, integer = false): { value: number | null; error: string | null } {
  if (text.trim() === "") return { value: null, error: "Enter a number." };
  const value = Number(text);
  if (!Number.isFinite(value) || (integer && !Number.isInteger(value))) return { value: null, error: integer ? "Enter a whole number." : "Enter a number." };
  if (value < low || value > high) return { value: null, error: `Between ${low} and ${high}.` };
  return { value, error: null };
}

export function RunForm({ datasets, canRun, busy, onStarted }: { datasets: DatasetInfo[]; canRun: boolean; busy: boolean; onStarted: (run: RunDetail) => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const usable = datasets.filter((d) => d.available);

  const [dataset, setDataset] = useState(usable[0]?.name ?? "");
  const [mode, setMode] = useState<"fixed_recall" | "fixed_far">("fixed_recall");
  const [recallPct, setRecallPct] = useState("90");
  const [farPct, setFarPct] = useState("1");
  const [metric, setMetric] = useState<"dir1" | "tar">("dir1");
  const [seeds, setSeeds] = useState<number[]>([0]);
  const [maxIdentities, setMaxIdentities] = useState("");
  const [maxImages, setMaxImages] = useState("12");
  const [shots, setShots] = useState("3");
  const [crossCamera, setCrossCamera] = useState(true);
  const [bootstrap, setBootstrap] = useState("200");
  const [useMargin, setUseMargin] = useState(true);
  const [variants, setVariants] = useState<string[]>(VARIANT_CHOICES.filter((v) => v.on).map((v) => v.key));
  const [devPct, setDevPct] = useState("40");
  const [calPct, setCalPct] = useState("20");
  const [checkpoint, setCheckpoint] = useState("");

  const checkpoints = useQuery({ queryKey: keys.checkpoints, queryFn: api.checkpoints });
  const chosenCheckpoint = checkpoints.data?.find((c) => c.name === checkpoint);

  const recall = number(recallPct, 1, 100);
  const far = number(farPct, 0, 50);
  const identities = maxIdentities.trim() === "" ? { value: null, error: null } : number(maxIdentities, 10, 2000, true);
  const images = number(maxImages, 4, 200, true);
  const shotsN = number(shots, 1, 10, true);
  const boot = number(bootstrap, 0, 2000, true);
  const dev = number(devPct, 0, 80);
  const cal = number(calPct, 5, 80);
  const splitError = !dev.error && !cal.error && (dev.value ?? 0) + (cal.value ?? 0) > 90 ? "Development + calibration must leave at least 10% for the test split." : null;
  const valid = !!dataset && !(mode === "fixed_recall" ? recall.error : far.error) && !identities.error && !images.error && !shotsN.error && !boot.error
    && !dev.error && !cal.error && !splitError && seeds.length > 0 && variants.length > 0;
  const chosen = datasets.find((d) => d.name === dataset);

  /** A fine-tuned checkpoint is only valid for the seed (= the held-out people) it was trained for. */
  function pickCheckpoint(name: string) {
    setCheckpoint(name);
    const picked = checkpoints.data?.find((c) => c.name === name);
    if (picked?.seed !== null && picked?.seed !== undefined) setSeeds([picked.seed]);
    if (picked?.dataset && usable.some((d) => d.name === picked.dataset)) setDataset(picked.dataset);
  }

  function body(): EvaluationBody {
    return {
      dataset, seeds, bootstrap_samples: boot.value ?? 200, variants,
      finetuned_checkpoint: checkpoint || null,
      target: { mode, target_recall: (recall.value ?? 90) / 100, target_far: (far.value ?? 1) / 100, recall_metric: metric },
      protocol: { gallery_shots: shotsN.value ?? 3, dev_fraction: (dev.value ?? 40) / 100, calibration_fraction: (cal.value ?? 20) / 100, max_identities_per_split: identities.value, max_images_per_identity: images.value, cross_camera: crossCamera },
    };
  }

  const started = (run: RunDetail, what: string) => {
    toast.success(`${what} started. Progress appears below.`);
    void queryClient.invalidateQueries({ queryKey: keys.runs });
    onStarted(run);
  };
  const evaluate = useMutation({ mutationFn: () => api.startEvaluation(body()), onSuccess: (r) => started(r, "Evaluation"), onError: (e) => toast.error(describeError(e)) });
  const calibrate = useMutation({
    mutationFn: () => { const { dataset: d, target, protocol } = body(); return api.startCalibration({ dataset: d, target, protocol, seed: seeds[0] ?? 0, use_margin: useMargin }); },
    onSuccess: (r) => started(r, "Calibration"), onError: (e) => toast.error(describeError(e)),
  });

  if (usable.length === 0) {
    return (
      <Notice tone="warn" title="No dataset is installed">
        Evaluations need an identity-labelled dataset in <code className="font-mono text-xs">datasets/</code>. Download Market-1501 for research use, then unpack it into <code className="font-mono text-xs">datasets/market1501</code>
        (see the README, “Dataset acquisition”). For a pipeline check only, run <code className="font-mono text-xs">python scripts/make_smoke_dataset.py</code>.
        {datasets.filter((d) => !d.available).map((d) => <span key={d.name} className="mt-1 block">{d.name}: {d.problems.join(" ")}</span>)}
      </Notice>
    );
  }

  return (
    <form onSubmit={(e) => e.preventDefault()} className="space-y-4" aria-label="Experiment configuration" noValidate>
      <Field label="Dataset">
        <Select value={dataset} onChange={(e) => setDataset(e.target.value)}>
          {usable.map((d) => <option key={d.name} value={d.name}>{d.name} — {d.identities} people, {d.images} images{d.kind !== "benchmark" ? " (smoke test)" : ""}</option>)}
        </Select>
      </Field>
      {chosen && chosen.kind !== "benchmark" && <Notice tone="warn" title="Smoke-test dataset">Results only check that the pipeline runs. They are not benchmark results and the dashboard will not count them.</Notice>}
      {chosen?.license_note && <p className="text-xs text-ink-3">{chosen.license_note}</p>}

      <Segmented label="Operating point" value={mode} onChange={setMode} options={[
        { value: "fixed_recall", label: "Fixed recall → minimise false accepts", hint: "The PS-1 objective" },
        { value: "fixed_far", label: "Fixed false-accept limit → maximise recall" },
      ]} />
      {mode === "fixed_recall" ? (
        <Field label="Recall to keep (%)" hint="Share of enrolled people who must be accepted and correctly named." error={recall.error}>
          <TextInput type="number" min={1} max={100} step={1} value={recallPct} onChange={(e) => setRecallPct(e.target.value)} />
        </Field>
      ) : (
        <Field label="Largest acceptable false-accept rate (%)" hint="Share of strangers allowed to be wrongly accepted." error={far.error}>
          <TextInput type="number" min={0} max={50} step={0.1} value={farPct} onChange={(e) => setFarPct(e.target.value)} />
        </Field>
      )}
      <Field label="Recall means" hint="“Accepted and correct” is stricter and more honest.">
        <Select value={metric} onChange={(e) => setMetric(e.target.value as "dir1" | "tar")}>
          <option value="dir1">Accepted AND correctly identified (DIR@1)</option>
          <option value="tar">Accepted, any identity (TAR)</option>
        </Select>
      </Field>

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Random seeds</legend>
        <div className="flex flex-wrap gap-4">
          {[0, 1, 2].map((s) => (
            <Checkbox key={s} label={`Seed ${s}`} checked={seeds.includes(s)} onChange={(e) => setSeeds((cur) => (e.target.checked ? [...cur, s].sort() : cur.filter((x) => x !== s)))} />
          ))}
        </div>
        <p className="mt-1 text-xs text-ink-3">Each seed re-draws which people are enrolled. More seeds show how stable the result is.</p>
      </fieldset>

      <details className="rounded-md border border-line p-3">
        <summary className="cursor-pointer text-sm font-medium select-none">Protocol and variants</summary>
        <div className="mt-3 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Max people per split" hint="Blank = all. Smaller is faster on a CPU." error={identities.error}><TextInput type="number" min={10} value={maxIdentities} onChange={(e) => setMaxIdentities(e.target.value)} placeholder="all" /></Field>
            <Field label="Max images per person" error={images.error}><TextInput type="number" min={4} value={maxImages} onChange={(e) => setMaxImages(e.target.value)} /></Field>
            <Field label="Gallery images per enrolled person" error={shotsN.error}><TextInput type="number" min={1} max={10} value={shots} onChange={(e) => setShots(e.target.value)} /></Field>
            <Field label="Bootstrap resamples" hint="For 95% intervals. 0 turns them off." error={boot.error}><TextInput type="number" min={0} value={bootstrap} onChange={(e) => setBootstrap(e.target.value)} /></Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Development people (%)" hint="Set aside for fine-tuning and hard-negative mining; never scored." error={dev.error ?? splitError}><TextInput type="number" min={0} max={80} value={devPct} onChange={(e) => setDevPct(e.target.value)} /></Field>
            <Field label="Calibration people (%)" hint="Used ONLY to choose thresholds. The rest is the test split." error={cal.error}><TextInput type="number" min={5} max={80} value={calPct} onChange={(e) => setCalPct(e.target.value)} /></Field>
          </div>
          <Checkbox label="Cross-camera matching only" hint="A query ignores gallery photos of the same person from the same camera (Market-1501 convention)." checked={crossCamera} onChange={(e) => setCrossCamera(e.target.checked)} />
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium">Variants to compare</legend>
            <div className="space-y-2">
              {VARIANT_CHOICES.map((v) => (
                <Checkbox key={v.key} label={v.label} checked={variants.includes(v.key)} onChange={(e) => setVariants((cur) => (e.target.checked ? [...cur, v.key] : cur.filter((x) => x !== v.key)))} />
              ))}
            </div>
          </fieldset>
          <div className="space-y-2">
            <Field label="Fine-tuned backbone (optional)" hint="Adds the “triplet fine-tuned backbone” variant. A checkpoint is only valid for the held-out people it was trained against, so the seed is set for you.">
              <Select value={checkpoint} onChange={(e) => pickCheckpoint(e.target.value)} disabled={checkpoints.isLoading}>
                <option value="">None: pretrained weights only</option>
                {checkpoints.data?.map((c) => (
                  <option key={c.name} value={c.name}>{c.name} (dataset {c.dataset ?? "?"}, seed {c.seed ?? "?"}, {c.trained_people ?? "?"} people)</option>
                ))}
              </Select>
            </Field>
            {checkpoints.data && checkpoints.data.length === 0 && (
              <p className="flex items-center gap-2 text-xs text-ink-3"><Badge tone="neutral">None trained</Badge> No fine-tuned checkpoint exists yet. Create one with scripts/finetune_triplet.py (README, “Metric-learning fine-tuning”).</p>
            )}
            {chosenCheckpoint && (
              <Notice tone="warn" title="Not yet validated">
                Trained on {chosenCheckpoint.trained_people ?? "?"} development people. Whether it is better is decided only by this evaluation; if any of its training people appear in the calibration or test split, it is refused automatically.
              </Notice>
            )}
          </div>
          <Checkbox label="Calibration: also search a margin rule" hint="Used by “Calibrate threshold”." checked={useMargin} onChange={(e) => setUseMargin(e.target.checked)} />
        </div>
      </details>

      {!canRun && <Notice tone="info">Running experiments needs the admin role.</Notice>}
      {busy && <Notice tone="info">A job is already running. Wait for it to finish or cancel it.</Notice>}
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={!canRun || !valid || busy} loading={evaluate.isPending} icon={<FlaskConical aria-hidden className="size-4" />} onClick={() => evaluate.mutate()}>Run evaluation</Button>
        <Button disabled={!canRun || !valid || busy} loading={calibrate.isPending} icon={<SlidersHorizontal aria-hidden className="size-4" />} onClick={() => calibrate.mutate()}
          title="Selects a threshold on the calibration split only; never reads the test split">
          Calibrate threshold
        </Button>
      </div>
      <p className="text-xs text-ink-3">Embedding runs on the CPU at roughly 0.2 s per new image; results are cached, so repeating a run is fast. Use “Max people per split” for a quick first run.</p>
    </form>
  );
}
