/**
 * Lookalike Failure Lab (screen E): where does the matcher go wrong, and why?
 *
 * In plain words: re-identification fails when two DIFFERENT people look alike. This screen goes looking for
 * those cases on a labelled dataset instead of waiting for them. It lists the pairs of different people the
 * model finds most alike, turns them into a reproducible challenge set, measures the matcher (and, if one
 * exists, a fine-tuned model on the very same examples), lists the real mistakes with the evidence, and lets
 * you explore thresholds. It is a diagnostic tool, not a new learning algorithm: it proves nothing by itself,
 * and it never invents a number - when something cannot run, it says what is missing.
 */
import { useQuery } from "@tanstack/react-query";
import { GitCompareArrows, ListChecks, Search, Target } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/PageHeader";
import { RunHistory } from "@/features/evaluation/RunHistory";
import { RunStatus } from "@/features/evaluation/RunStatus";
import { LabForm } from "@/features/lookalike/LabForm";
import { LabResults } from "@/features/lookalike/LabResults";
import { useSession } from "@/hooks/useSession";
import { can } from "@/lib/present";
import { api, keys } from "@/services/api";
import type { LookalikeResult } from "@/types/api";

const ACTIVE = ["queued", "running"];

const STEPS = [
  { icon: <Search aria-hidden className="size-4" />, title: "1. Mine", text: "List the pairs of different people whose photos the model finds most alike." },
  { icon: <ListChecks aria-hidden className="size-4" />, title: "2. Challenge", text: "Turn them, with ordinary same-person pairs, into a fixed test list and measure the matcher on it." },
  { icon: <GitCompareArrows aria-hidden className="size-4" />, title: "3. Compare", text: "Score the same pairs with a fine-tuned model, if one exists - otherwise say plainly that none was compared." },
  { icon: <Target aria-hidden className="size-4" />, title: "4. Inspect", text: "Open each real mistake: the photos, the measured numbers, and ideas about why - marked as unproven." },
];

export default function LookalikePage() {
  const { role } = useSession();
  const [params] = useSearchParams();
  const datasets = useQuery({ queryKey: keys.datasets, queryFn: api.datasets });
  const readiness = useQuery({ queryKey: keys.readiness, queryFn: api.readiness, retry: false });
  // Any running job (of any kind) blocks a new one: the server runs one at a time.
  const allRuns = useQuery({
    queryKey: keys.runs,
    queryFn: () => api.runs({ limit: 20 }),
    refetchInterval: (q) => (q.state.data?.items.some((r) => ACTIVE.includes(r.status)) ? 3000 : false),
  });
  const labRuns = useQuery({
    queryKey: keys.labRuns,
    queryFn: () => api.labRuns({ limit: 20 }),
    refetchInterval: (q) => (q.state.data?.items.some((r) => ACTIVE.includes(r.status)) ? 3000 : false),
  });

  const [selectedId, setSelectedId] = useState<string | null>(params.get("run"));
  const activeRun = allRuns.data?.items.find((r) => ACTIVE.includes(r.status));
  const newest = labRuns.data?.items[0];
  useEffect(() => {
    if (!selectedId && newest) setSelectedId(newest.run_id);
  }, [selectedId, newest]);

  // The selected experiment keeps refreshing itself while it is active, so its results appear the moment it finishes.
  const detail = useQuery({
    queryKey: keys.run(selectedId ?? ""), queryFn: () => api.labRun(selectedId as string), enabled: !!selectedId,
    refetchInterval: (q) => (q.state.data && ACTIVE.includes(q.state.data.status) ? 1500 : false),
  });
  const onFinished = useCallback(() => { void labRuns.refetch(); void allRuns.refetch(); }, [labRuns, allRuns]);
  const run = detail.data;

  const embedding = readiness.data?.components.embedding_model;
  const modelsReady = readiness.data ? !!embedding?.ok : true; // while the status is loading, do not nag
  const modelsProblem = embedding && !embedding.ok ? String(embedding.error ?? "") || null : null;

  return (
    <>
      <PageHeader
        title="Lookalike Failure Lab"
        description="Find the different people the model confuses, measure how often a matcher would accept them, and inspect the real mistakes. This lab measures the BODY model: its datasets are full-body crops without readable faces."
      />

      <ol className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4" aria-label="How the lab works">
        {STEPS.map((s) => (
          <li key={s.title} className="rounded-lg border border-line bg-surface p-3">
            <p className="flex items-center gap-2 text-sm font-semibold">{s.icon}{s.title}</p>
            <p className="mt-1 text-xs text-ink-3">{s.text}</p>
          </li>
        ))}
      </ol>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card aria-labelledby="lab-form-title">
            <CardHeader id="lab-form-title" title="Run an experiment" description="Thresholds are chosen on calibration people; look-alikes are searched among another group." />
            <CardBody>
              {datasets.isLoading && <Skeleton className="h-64 w-full" />}
              {datasets.isError && <ErrorState error={datasets.error} onRetry={() => void datasets.refetch()} />}
              {datasets.data && (
                <LabForm datasets={datasets.data} modelsReady={modelsReady} modelsProblem={modelsProblem} canRun={can(role, "admin")}
                  busy={!!activeRun} onStarted={(r) => setSelectedId(r.run_id)} />
              )}
            </CardBody>
          </Card>
        </div>

        {/* Below the wide layout the results come FIRST, so a finished experiment is not hidden under the form. */}
        <div className={`min-w-0 space-y-4 ${selectedId || activeRun ? "order-first xl:order-none" : ""}`}>
          {activeRun && <RunStatus runId={activeRun.run_id} canCancel={can(role, "admin")} onFinished={onFinished} />}

          {!selectedId && !activeRun && (
            <EmptyState icon={<GitCompareArrows aria-hidden className="size-5" />} title="No experiment yet">
              Start one on the left. Results, photos, charts and downloadable exports appear here. Nothing on this page is pre-filled or simulated.
            </EmptyState>
          )}
          {selectedId && detail.isLoading && <Skeleton className="h-96 w-full" />}
          {selectedId && detail.isError && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}
          {run && run.status === "succeeded" && run.result?.kind === "lookalike" && <LabResults run={run} result={run.result as LookalikeResult} />}
          {run && run.status === "failed" && <ErrorState error={new Error(run.error ?? "The experiment failed.")} title="This experiment failed" />}

          <Card aria-labelledby="lab-history-title">
            <CardHeader id="lab-history-title" title="Experiment history" description="Newest first." />
            <CardBody>
              {labRuns.isLoading && <Skeleton className="h-24 w-full" />}
              {labRuns.isError && <ErrorState error={labRuns.error} onRetry={() => void labRuns.refetch()} />}
              {labRuns.data && <RunHistory runs={labRuns.data.items} selectedId={selectedId} onSelect={setSelectedId} />}
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}
