/**
 * Video Explorer (screen D): re-identify people in sampled frames of a prerecorded video.
 *
 * In plain words: upload a clip, choose how often to sample it, and the system asks the same question it asks
 * of a single photo - "who is this, if anyone?" - for every sampled frame, with the same detector, the same
 * model, the same gallery and the same decision rules. Each frame is judged on its own. This is NOT a
 * multi-object tracker: nobody is followed from frame to frame or through occlusion, and the screen says so.
 */
import { useQuery } from "@tanstack/react-query";
import { Film } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/PageHeader";
import { VideoResults } from "@/features/video/VideoResults";
import { VideoStatus } from "@/features/video/VideoStatus";
import { VideoUpload } from "@/features/video/VideoUpload";
import { useSession } from "@/hooks/useSession";
import { dateTime, pct } from "@/lib/format";
import { can } from "@/lib/present";
import { api, keys } from "@/services/api";
import type { VideoResult } from "@/types/api";

const ACTIVE = ["queued", "running"];
const TONE = { succeeded: "ok", failed: "bad", cancelled: "neutral", running: "info", queued: "info" } as const;

export default function VideoPage() {
  const { role } = useSession();
  const [params] = useSearchParams();
  const limits = useQuery({ queryKey: keys.videoLimits, queryFn: api.videoLimits });
  const jobs = useQuery({
    queryKey: keys.videoJobs,
    queryFn: () => api.videoJobs({ limit: 20 }),
    refetchInterval: (q) => (q.state.data?.items.some((j) => ACTIVE.includes(j.status)) ? 2000 : false),
  });
  // A job of any kind blocks a new video: the server runs one at a time.
  const allRuns = useQuery({
    queryKey: keys.runs,
    queryFn: () => api.runs({ limit: 20 }),
    refetchInterval: (q) => (q.state.data?.items.some((r) => ACTIVE.includes(r.status)) ? 3000 : false),
  });

  const [selectedId, setSelectedId] = useState<string | null>(params.get("job"));
  const activeJob = jobs.data?.items.find((j) => ACTIVE.includes(j.status));
  const busy = !!activeJob || !!allRuns.data?.items.some((r) => ACTIVE.includes(r.status));
  const newest = jobs.data?.items[0];
  useEffect(() => {
    if (!selectedId && newest) setSelectedId(newest.run_id);
  }, [selectedId, newest]);

  // The selected job keeps refreshing itself while it is active, so its results appear the moment it finishes.
  const detail = useQuery({
    queryKey: keys.videoJob(selectedId ?? ""), queryFn: () => api.videoJob(selectedId as string), enabled: !!selectedId, retry: false,
    refetchInterval: (q) => (q.state.data && ACTIVE.includes(q.state.data.status) ? 1000 : false),
  });
  const job = detail.data;
  const onFinished = useCallback(() => { void jobs.refetch(); void allRuns.refetch(); }, [jobs, allRuns]);
  const onDeleted = useCallback(() => { setSelectedId(null); void jobs.refetch(); }, [jobs]);

  return (
    <>
      <PageHeader title="Video Explorer" description="Re-identify the people in sampled frames of a prerecorded video, and see the decision for every frame and every person." />
      {/* Once a result is on screen it repeats this statement itself, so the page-level notice is only for the empty state. */}
      {!selectedId && <Notice tone="info" title="Scope" className="mb-4">This analyses sampled frames one at a time. It is not a multi-object tracker: a person is never followed between frames or through occlusion, and no live camera is used.</Notice>}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card aria-labelledby="video-form-title">
            <CardHeader id="video-form-title" title="Analyse a video" description="Authorised, controlled test footage only." />
            <CardBody>
              {limits.isLoading && <Skeleton className="h-64 w-full" />}
              {limits.isError && <ErrorState error={limits.error} onRetry={() => void limits.refetch()} />}
              {limits.data && <VideoUpload limits={limits.data} canRun={can(role, "viewer")} busy={busy} onStarted={(r) => setSelectedId(r.run_id)} />}
            </CardBody>
          </Card>

          <Card aria-labelledby="video-jobs-title">
            <CardHeader id="video-jobs-title" title="Past analyses" description="Newest first. Previews expire; decisions stay until you delete them." />
            <CardBody>
              {jobs.isLoading && <Skeleton className="h-20 w-full" />}
              {jobs.isError && <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />}
              {jobs.data && jobs.data.items.length === 0 && <p className="text-sm text-ink-3">No video has been analysed yet.</p>}
              {jobs.data && jobs.data.items.length > 0 && (
                <ul className="divide-y divide-line rounded-md border border-line">
                  {jobs.data.items.map((j) => {
                    const h = j.headline as { frames_processed?: number; people_detected?: number } | null;
                    return (
                      <li key={j.run_id} className="flex flex-wrap items-center justify-between gap-2 p-2.5" aria-current={j.run_id === selectedId ? "true" : undefined}>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{j.dataset}</p>
                          <p className="text-xs text-ink-3">{dateTime(j.created_at)}{h?.frames_processed != null && ` · ${h.frames_processed} frames, ${h.people_detected} people`}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge tone={TONE[j.status]}>{j.status === "running" ? `running ${pct(j.progress, 0)}` : j.status}</Badge>
                          <Button size="sm" variant={j.run_id === selectedId ? "dark" : "secondary"} onClick={() => setSelectedId(j.run_id)}>{j.run_id === selectedId ? "Viewing" : "View"}</Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Below the wide layout the results come FIRST, so a finished analysis is not hidden under the upload form. */}
        <div className={`min-w-0 space-y-4 ${selectedId ? "order-first xl:order-none" : ""}`}>
          {/* The status card follows the job you are looking at (and announces how it ended); a different running job is shown too. */}
          {selectedId && <VideoStatus jobId={selectedId} onFinished={onFinished} />}
          {activeJob && activeJob.run_id !== selectedId && <VideoStatus jobId={activeJob.run_id} onFinished={onFinished} />}
          {!selectedId && !activeJob && (
            <EmptyState icon={<Film aria-hidden className="size-5" />} title="No video analysed yet">
              Choose a clip on the left. Every sampled frame, every detected person and every decision appears here - nothing is simulated.
            </EmptyState>
          )}
          {selectedId && detail.isLoading && <Skeleton className="h-96 w-full" />}
          {selectedId && detail.isError && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}
          {job && job.status === "succeeded" && job.result?.kind === "video" && <VideoResults job={job} result={job.result as VideoResult} onDeleted={onDeleted} />}
        </div>
      </div>
    </>
  );
}
