/**
 * VideoStatus: live progress of the current video job.
 *
 * In plain words: shows the job's REAL stage ("Frame 7 of about 30") and progress as reported by the backend,
 * with a Cancel button that really stops processing at the next frame. When it ends it says so once: finished,
 * failed (with the reason) or cancelled (nothing is kept).
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

export function VideoStatus({ jobId, onFinished }: { jobId: string; onFinished: (status: string) => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: keys.videoJob(jobId),
    queryFn: () => api.videoJob(jobId),
    refetchInterval: (q) => (q.state.data && !ACTIVE.includes(q.state.data.status) ? false : 1000),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelVideo(jobId),
    onSuccess: () => toast.info("Cancelling… processing stops after the current frame."),
    onError: (e) => toast.error(describeError(e)),
  });

  const job = query.data;
  const announced = useRef<string | null>(null);
  const sawActive = useRef(false);
  useEffect(() => {
    if (job && ACTIVE.includes(job.status)) sawActive.current = true;
    // Announce an ending only if we watched the job run. Merely opening an old, finished job must not pop up "finished".
    if (!job || ACTIVE.includes(job.status) || !sawActive.current || announced.current === `${job.run_id}:${job.status}`) return;
    announced.current = `${job.run_id}:${job.status}`;
    void queryClient.invalidateQueries({ queryKey: keys.videoJobs });
    void queryClient.invalidateQueries({ queryKey: keys.runs });
    if (job.status === "succeeded") toast.success("Video analysis finished.");
    if (job.status === "failed") toast.error(`The video job failed: ${job.error ?? "unknown error"}`);
    if (job.status === "cancelled") toast.info("The video job was cancelled; nothing was kept.");
    onFinished(job.status);
  }, [job, queryClient, toast, onFinished]);

  if (!job) return null;
  const active = ACTIVE.includes(job.status);
  if (!active && job.status === "succeeded") return null; // the results card takes over
  return (
    <Card aria-labelledby="video-status-title" aria-live="polite">
      <CardHeader
        id="video-status-title"
        title={`Analysing ${job.dataset}`}
        description={job.stage}
        action={
          <div className="flex items-center gap-2">
            <Badge tone={job.status === "failed" ? "bad" : job.status === "cancelled" ? "neutral" : "info"}>{job.status}</Badge>
            {active && (
              <Button size="sm" variant="danger" disabled={job.cancel_requested} loading={cancel.isPending} icon={<CircleStop aria-hidden className="size-3.5" />} onClick={() => cancel.mutate()}>
                {job.cancel_requested ? "Cancelling…" : "Cancel"}
              </Button>
            )}
          </div>
        }
      />
      <CardBody className="space-y-2">
        {active && (<><Progress value={job.progress} label={`${job.stage}, ${pct(job.progress, 0)} complete`} /><p className="text-xs text-ink-3">{pct(job.progress, 0)} · {job.stage}</p></>)}
        {job.status === "failed" && <Notice tone="bad" title="The video job failed">{job.error}</Notice>}
        {job.status === "cancelled" && <Notice tone="info">The job was cancelled. No frames or results were kept, and the uploaded video was deleted.</Notice>}
      </CardBody>
    </Card>
  );
}
