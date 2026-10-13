/**
 * CalibrationApply: put a finished calibration result into effect.
 *
 * In plain words: lists recent calibration runs. A run can be applied only if it reached its
 * target AND was computed for the model that is running now - the buttons say why not
 * otherwise, and the backend re-checks both rules.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { dateTime, num, pct } from "@/lib/format";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";

export function CalibrationApply({ liveFingerprint, canEdit }: { liveFingerprint: string | null; canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: [...keys.runs, "calibration"], queryFn: () => api.runs({ kind: "calibration", limit: 8 }) });

  const apply = useMutation({
    mutationFn: (runId: string) => api.updateThresholds({ from_calibration_run_id: runId, confirm: true, note: "Applied from a calibration run" }),
    onSuccess: (policy) => {
      toast.success(`Calibrated policy v${policy.version} is now active.`);
      for (const key of [keys.config, keys.policyHistory, keys.overview, keys.audit]) void queryClient.invalidateQueries({ queryKey: key });
    },
    onError: (failure) => toast.error(describeError(failure)),
  });

  if (runs.isLoading) return <Skeleton className="h-24 w-full" />;
  if (runs.isError) return <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />;
  const finished = (runs.data?.items ?? []).filter((r) => r.status === "succeeded");
  if (finished.length === 0) {
    return (
      <EmptyState title="No calibration has been run" action={<Link to="/evaluation"><Button variant="primary" size="sm">Open the Evaluation Lab</Button></Link>}>
        Calibration selects a threshold on a held-out calibration split so the rule is based on data, not on a guess.
      </EmptyState>
    );
  }
  return (
    <ul className="divide-y divide-line rounded-md border border-line">
      {finished.map((run) => {
        const h = run.headline as { target_achieved: boolean; threshold: number | null; min_margin: number | null; calibration_far: number | null; calibration_recall: number | null; model_fingerprint: string; is_benchmark: boolean } | null;
        if (!h) return null;
        const matches = liveFingerprint !== null && h.model_fingerprint === liveFingerprint;
        const reason = !h.target_achieved ? "The target was not reached" : !matches ? "Computed for a different model" : !canEdit ? "Requires the admin role" : undefined;
        return (
          <li key={run.run_id} className="flex flex-wrap items-center justify-between gap-3 p-3">
            <div className="min-w-0 space-y-1 text-sm">
              <p className="font-medium">{run.dataset} · {dateTime(run.finished_at)}</p>
              <p className="text-xs text-ink-3">
                threshold {num(h.threshold)} · margin {h.min_margin === null ? "none" : num(h.min_margin)} · calibration FAR {pct(h.calibration_far, 2)} · recall {pct(h.calibration_recall)}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {h.target_achieved ? <Badge tone="ok">Target reached</Badge> : <Badge tone="warn">Target not reached</Badge>}
                {!matches && <Badge tone="warn">Different model</Badge>}
                {!h.is_benchmark && <Badge tone="neutral">Smoke-test data</Badge>}
              </div>
            </div>
            <Button size="sm" variant="primary" disabled={!!reason} title={reason} loading={apply.isPending && apply.variables === run.run_id} onClick={() => apply.mutate(run.run_id)}>
              Apply this calibration
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
