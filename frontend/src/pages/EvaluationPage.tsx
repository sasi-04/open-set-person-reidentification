/**
 * Evaluation Lab: configure experiments, watch them run, read the results.
 *
 *   top      experiment form + live status of the current job
 *   below    the selected run's results (ablation, ROC, score distributions, ...)
 *   bottom   run history
 */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/PageHeader";
import { CalibrationView } from "@/features/evaluation/CalibrationView";
import { ResultsView } from "@/features/evaluation/ResultsView";
import { RunForm } from "@/features/evaluation/RunForm";
import { RunHistory } from "@/features/evaluation/RunHistory";
import { RunStatus } from "@/features/evaluation/RunStatus";
import { useSession } from "@/hooks/useSession";
import { can } from "@/lib/present";
import { api, keys } from "@/services/api";
import type { CalibrationResult, EvaluationResult } from "@/types/api";
import { FlaskConical } from "lucide-react";

const ACTIVE = ["queued", "running"];

export default function EvaluationPage() {
  const { role } = useSession();
  const datasets = useQuery({ queryKey: keys.datasets, queryFn: api.datasets });
  const runs = useQuery({
    queryKey: keys.runs,
    queryFn: () => api.runs({ limit: 20 }),
    refetchInterval: (q) => (q.state.data?.items.some((r) => ACTIVE.includes(r.status)) ? 3000 : false),
  });

  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(params.get("run")); // ?run=<id> opens a specific experiment
  const activeRun = runs.data?.items.find((r) => ACTIVE.includes(r.status));
  const newestRun = runs.data?.items[0];

  // Show the newest run by default (even a failed one, so its reason stays visible after the progress
  // card disappears), until the person picks another run from the history.
  useEffect(() => {
    if (!selectedId && newestRun) setSelectedId(newestRun.run_id);
  }, [selectedId, newestRun]);

  // The selected run keeps refreshing itself while it is active, so its results appear the moment it finishes.
  const detail = useQuery({
    queryKey: keys.run(selectedId ?? ""), queryFn: () => api.run(selectedId as string), enabled: !!selectedId,
    refetchInterval: (q) => (q.state.data && ACTIVE.includes(q.state.data.status) ? 1500 : false),
  });
  const onFinished = useCallback((status: string) => { void runs.refetch(); if (status !== "succeeded") return; }, [runs]);
  const run = detail.data;

  return (
    <>
      <PageHeader
        title="Evaluation Lab"
        description="Measure how often strangers are wrongly accepted against how many enrolled people are correctly accepted, on people the system was never tuned on. ROC, fixed-recall operating point, ablations, a threshold sandbox and downloadable reports. These experiments measure the BODY model (full-body datasets have no readable faces); the face stage is measured separately - see docs/FACE_AND_BODY_MATCHING.md."
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card aria-labelledby="form-title">
            <CardHeader id="form-title" title="Run an experiment" description="Thresholds are chosen on calibration people and tested on different people." />
            <CardBody>
              {datasets.isLoading && <Skeleton className="h-64 w-full" />}
              {datasets.isError && <ErrorState error={datasets.error} onRetry={() => void datasets.refetch()} />}
              {datasets.data && <RunForm datasets={datasets.data} canRun={can(role, "admin")} busy={!!activeRun} onStarted={(r) => setSelectedId(r.run_id)} />}
            </CardBody>
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          {activeRun && <RunStatus runId={activeRun.run_id} canCancel={can(role, "admin")} onFinished={onFinished} />}

          {!selectedId && !activeRun && (
            <EmptyState icon={<FlaskConical aria-hidden className="size-5" />} title="No results yet">
              Start an evaluation or a calibration on the left. Results, charts and downloadable reports appear here. Nothing on this page is pre-filled or simulated.
            </EmptyState>
          )}
          {selectedId && detail.isLoading && <Skeleton className="h-96 w-full" />}
          {selectedId && detail.isError && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}
          {run && run.status === "succeeded" && run.result?.kind === "evaluation" && <ResultsView run={run} result={run.result as EvaluationResult} />}
          {run && run.status === "succeeded" && run.result?.kind === "calibration" && <CalibrationView run={run} result={run.result as CalibrationResult} />}
          {run && run.status === "succeeded" && run.result?.kind === "lookalike" && (
            <Notice tone="info" title="This is a look-alike experiment">
              Its pairs, failures and comparison are in the <Link className="font-medium underline" to={`/lookalike?run=${run.run_id}`}>Lookalike Failure Lab</Link>.
              Its threshold sandbox is there too.
            </Notice>
          )}
          {run && run.status === "failed" && <ErrorState error={new Error(run.error ?? "The job failed.")} title="This run failed" />}

          <Card aria-labelledby="runs-title">
            <CardHeader id="runs-title" title="Run history" description="Newest first." />
            <CardBody>
              {runs.isLoading && <Skeleton className="h-24 w-full" />}
              {runs.isError && <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />}
              {runs.data && <RunHistory runs={runs.data.items} selectedId={selectedId} onSelect={setSelectedId} />}
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}
