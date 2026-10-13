/**
 * LabForm: set up one Lookalike Failure Lab experiment.
 *
 * In plain words: choose a labelled dataset, say which group of people to search for look-alikes, say what
 * recall the operating threshold must keep, and press Run. If something needed is missing - no dataset,
 * models that did not load, another job already running - the form says exactly what and why instead of
 * offering a button that cannot work. The "improved model" menu only lists checkpoints that really exist;
 * with none, the experiment runs the baseline alone and says so.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitCompareArrows } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Feedback";
import { Field, Segmented, Select, TextInput } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { api, keys, type LookalikeBody } from "@/services/api";
import { describeError } from "@/services/http";
import type { DatasetInfo, RunDetail } from "@/types/api";

function whole(text: string, low: number, high: number): { value: number | null; error: string | null } {
  if (text.trim() === "") return { value: null, error: "Enter a number." };
  const value = Number(text);
  if (!Number.isInteger(value)) return { value: null, error: "Enter a whole number." };
  if (value < low || value > high) return { value: null, error: `Between ${low} and ${high}.` };
  return { value, error: null };
}

export function LabForm({ datasets, modelsReady, modelsProblem, canRun, busy, onStarted }: {
  datasets: DatasetInfo[];
  modelsReady: boolean;
  modelsProblem: string | null;
  canRun: boolean;
  busy: boolean;
  onStarted: (run: RunDetail) => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const usable = datasets.filter((d) => d.available);
  const checkpoints = useQuery({ queryKey: keys.checkpoints, queryFn: api.checkpoints });

  const [dataset, setDataset] = useState(usable[0]?.name ?? "");
  const [split, setSplit] = useState<"dev" | "calibration" | "test">("test");
  const [recallPct, setRecallPct] = useState("90");
  const [topPairs, setTopPairs] = useState("30");
  const [perPair, setPerPair] = useState("3");
  const [maxPeople, setMaxPeople] = useState("150");
  const [seed, setSeed] = useState("0");
  const [checkpoint, setCheckpoint] = useState("");

  const recall = whole(recallPct, 1, 100);
  const pairs = whole(topPairs, 5, 200);
  const images = whole(perPair, 1, 10);
  const people = maxPeople.trim() === "" ? { value: null, error: null } : whole(maxPeople, 10, 2000);
  const seedN = whole(seed, 0, 10_000);
  const chosen = datasets.find((d) => d.name === dataset);
  const picked = checkpoints.data?.find((c) => c.name === checkpoint);
  const valid = !!dataset && !recall.error && !pairs.error && !images.error && !people.error && !seedN.error;

  function pickCheckpoint(name: string) {
    setCheckpoint(name);
    const c = checkpoints.data?.find((x) => x.name === name);
    if (c?.seed !== null && c?.seed !== undefined) setSeed(String(c.seed)); // valid only for the people it was trained against
    if (c?.dataset && usable.some((d) => d.name === c.dataset)) setDataset(c.dataset);
    if (name && split === "dev") setSplit("test"); // a fine-tuned model is never compared on its own training people
  }

  const start = useMutation({
    mutationFn: () => {
      const body: LookalikeBody = {
        dataset, seed: seedN.value ?? 0, mining_split: split, top_pairs: pairs.value ?? 30, images_per_pair: images.value ?? 3,
        max_genuine_pairs: 4000, max_failures: 40, use_margin: true, finetuned_checkpoint: checkpoint || null,
        target: { mode: "fixed_recall", target_recall: (recall.value ?? 90) / 100, target_far: 0.01, recall_metric: "dir1" },
        protocol: { gallery_shots: 3, dev_fraction: 0.4, calibration_fraction: 0.2, max_identities_per_split: people.value, max_images_per_identity: 12, cross_camera: true },
      };
      return api.startLab(body);
    },
    onSuccess: (run) => {
      toast.success("Experiment started. Progress appears on the right.");
      void queryClient.invalidateQueries({ queryKey: keys.runs });
      void queryClient.invalidateQueries({ queryKey: keys.labRuns });
      onStarted(run);
    },
    onError: (e) => toast.error(describeError(e)),
  });

  if (usable.length === 0) {
    return (
      <Notice tone="warn" title="Not runnable yet: no labelled dataset is installed">
        The lab needs identity-labelled photos to find look-alikes in. Download Market-1501 for research use and unpack it into <code className="font-mono text-xs">datasets/market1501</code>
        (README, “Dataset acquisition”). To check that the lab itself works, run <code className="font-mono text-xs">python scripts/make_smoke_dataset.py</code>: its results are labelled as a smoke test, not a benchmark.
        {datasets.filter((d) => !d.available).map((d) => <span key={d.name} className="mt-1 block">{d.name}: {d.problems.join(" ")}</span>)}
      </Notice>
    );
  }

  const blocked = !canRun || !valid || busy || !modelsReady;
  return (
    <form onSubmit={(e) => e.preventDefault()} className="space-y-4" aria-label="Look-alike experiment configuration" noValidate>
      {!modelsReady && <Notice tone="bad" title="Not runnable: the embedding model is not loaded">{modelsProblem ?? "The model weights could not be loaded."} Fix it on <Link className="underline" to="/settings?tab=system">Model &amp; System</Link>.</Notice>}

      <Field label="Dataset">
        <Select value={dataset} onChange={(e) => setDataset(e.target.value)}>
          {usable.map((d) => <option key={d.name} value={d.name}>{d.name} — {d.identities} people, {d.images} images{d.kind !== "benchmark" ? " (smoke test)" : ""}</option>)}
        </Select>
      </Field>
      {chosen && chosen.kind !== "benchmark" && <Notice tone="warn" title="Smoke-test dataset">These results only show that the lab runs. They are not benchmark results and must not be quoted as performance.</Notice>}
      {chosen?.license_note && <p className="text-xs text-ink-3">{chosen.license_note}</p>}

      <Segmented<"dev" | "calibration" | "test"> label="Search for look-alikes among…" value={split} onChange={setSplit} options={[
        { value: "test", label: "Test people", hint: "Final diagnosis. The threshold is still chosen on calibration people." },
        { value: "calibration", label: "Calibration people", hint: "The people the threshold was chosen on." },
        { value: "dev", label: "Development people", hint: "The pool for training hard negatives; no improved model is compared here." },
      ]} />

      <Field label="Recall the threshold must keep (%)" hint="The threshold is chosen on calibration people so that this share of enrolled people is accepted AND correctly named, with as few strangers let in as possible." error={recall.error}>
        <TextInput type="number" min={1} max={100} step={1} value={recallPct} onChange={(e) => setRecallPct(e.target.value)} />
      </Field>

      <div className="space-y-2">
        <Field label="Improved model (optional)" hint="Compare the official weights with a fine-tuned checkpoint on the very same pairs. A checkpoint is refused automatically if it was trained on any person being evaluated.">
          <Select value={checkpoint} onChange={(e) => pickCheckpoint(e.target.value)} disabled={checkpoints.isLoading}>
            <option value="">None: baseline only</option>
            {checkpoints.data?.map((c) => <option key={c.name} value={c.name}>{c.name} (dataset {c.dataset ?? "?"}, seed {c.seed ?? "?"}, {c.trained_people ?? "?"} people)</option>)}
          </Select>
        </Field>
        {checkpoints.data && checkpoints.data.length === 0 && (
          <p className="flex flex-wrap items-center gap-2 text-xs text-ink-3"><Badge tone="neutral">None trained</Badge> No fine-tuned checkpoint exists, so the lab cannot compare an improved model. Create one with <code className="font-mono">scripts/finetune_triplet.py</code>.</p>
        )}
        {picked && <Notice tone="warn" title="Not yet validated">Trained on {picked.trained_people ?? "?"} development people. Whether it is better is decided only by this experiment.</Notice>}
      </div>

      <details className="rounded-md border border-line p-3">
        <summary className="cursor-pointer text-sm font-medium select-none">Challenge-set size and speed</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="Look-alike pairs of people" hint="How many of the most alike pairs to list and test." error={pairs.error}><TextInput type="number" min={5} max={200} value={topPairs} onChange={(e) => setTopPairs(e.target.value)} /></Field>
          <Field label="Photo pairs per look-alike pair" error={images.error}><TextInput type="number" min={1} max={10} value={perPair} onChange={(e) => setPerPair(e.target.value)} /></Field>
          <Field label="Max people per split" hint="Blank = all. Smaller is faster on a CPU." error={people.error}><TextInput type="number" min={10} value={maxPeople} onChange={(e) => setMaxPeople(e.target.value)} placeholder="all" /></Field>
          <Field label="Random seed" hint="Same data, seed and settings reproduce the experiment." error={seedN.error}><TextInput type="number" min={0} value={seed} onChange={(e) => setSeed(e.target.value)} /></Field>
        </div>
      </details>

      {!canRun && <Notice tone="info">Running experiments needs the admin role.</Notice>}
      {busy && <Notice tone="info">Another job is already running. Wait for it to finish or cancel it.</Notice>}
      <Button variant="primary" disabled={blocked} loading={start.isPending} icon={<GitCompareArrows aria-hidden className="size-4" />} onClick={() => start.mutate()}>
        Run look-alike experiment
      </Button>
      <p className="text-xs text-ink-3">Embedding runs on the CPU at roughly 0.2 s per new image; results are cached, so repeating an experiment is fast. Use “Max people per split” for a quick first run.</p>
    </form>
  );
}
