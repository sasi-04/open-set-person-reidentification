/**
 * RunStatus: live progress of the current background job.
 *
 * In plain words: polls the backend while a job is queued or running and shows its REAL stage
 * and progress (never a fake timer-driven bar). When the job ends it tells you once - success,
 * failure (with the reason) or cancellation.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleStop } from "lucide-react";
import { useEffect, useRef } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Feedback";
import { Progress } from "@/components/ui/Progress";
import { useToast } from "@/components/ui/Toast";
import { pct } from "@/lib/format";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";

const ACTIVE = ["queued", "running"];
const KIND_TITLE = { evaluation: "Evaluation", calibration: "Calibration", lookalike: "Look-alike experiment", video: "Video analysis" } as const;

export function RunStatus({ runId, canCancel, onFinished }: { runId: string; canCancel: boolean; onFinished: (status: string) => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: keys.run(runId),
    queryFn: () => api.run(runId),
    refetchInterval: (q) => (q.state.data && !ACTIVE.includes(q.state.data.status) ? false : 1500),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelRun(runId),
    onSuccess: () => toast.info("Cancelling… the job stops at the next safe point."),
    onError: (e) => toast.error(describeError(e)),
  });

  const run = query.data;
  const announced = useRef<string | null>(null);
  useEffect(() => {
    if (!run || ACTIVE.includes(run.status) || announced.current === `${run.run_id}:${run.status}`) return;
    announced.current = `${run.run_id}:${run.status}`;
    void queryClient.invalidateQueries({ queryKey: keys.runs });
    void queryClient.invalidateQueries({ queryKey: keys.overview });
    if (run.status === "succeeded") toast.success(`${KIND_TITLE[run.kind]} finished.`);
    if (run.status === "failed") toast.error(`The job failed: ${run.error ?? "unknown error"}`);
    if (run.status === "cancelled") toast.info("The job was cancelled.");
    onFinished(run.status);
  }, [run, queryClient, toast, onFinished]);

  if (!run) return null;
  const active = ACTIVE.includes(run.status);
  return (
    <Card aria-labelledby="status-title" aria-live="polite">
      <CardHeader
        id="status-title"
        title={`${KIND_TITLE[run.kind]} on ${run.dataset}`}
        description={run.stage}
        action={
          <div className="flex items-center gap-2">
            <Badge tone={run.status === "succeeded" ? "ok" : run.status === "failed" ? "bad" : run.status === "cancelled" ? "neutral" : "info"}>{run.status}</Badge>
            {active && (
              <Button size="sm" variant="danger" disabled={!canCancel || run.cancel_requested} loading={cancel.isPending} icon={<CircleStop aria-hidden className="size-3.5" />} onClick={() => cancel.mutate()}>
                {run.cancel_requested ? "Cancelling…" : "Cancel"}
              </Button>
            )}
          </div>
        }
      />
      <CardBody className="space-y-2">
        {active && (
          <>
            <Progress value={run.progress} label={`${run.stage}, ${pct(run.progress, 0)} complete`} />
            <p className="text-xs text-ink-3">{pct(run.progress, 0)} · {run.stage}</p>
          </>
        )}
        {run.status === "failed" && <Notice tone="bad" title="The job failed">{run.error}</Notice>}
        {run.status === "cancelled" && <Notice tone="info">The job was cancelled. No results were stored.</Notice>}
      </CardBody>
    </Card>
  );
}
