/** One past request in detail: each person's decision, candidates, and (during retention) the stored crop. */
import { useQuery } from "@tanstack/react-query";
import { AuthImage } from "@/components/ui/AuthImage";
import { OutcomeBadge } from "@/components/ui/Badge";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { dateTime, ms, num } from "@/lib/format";
import { api, keys } from "@/services/api";

export function HistoryDetailDialog({ requestId, onClose }: { requestId: string | null; onClose: () => void }) {
  const query = useQuery({ queryKey: keys.historyItem(requestId ?? ""), queryFn: () => api.historyItem(requestId as string), enabled: !!requestId });
  const data = query.data;
  return (
    <Dialog open={!!requestId} onOpenChange={(open) => !open && onClose()} size="lg" title="Request details" description={requestId ? `Request ${requestId}` : undefined}>
      {query.isLoading && <Skeleton className="h-40 w-full" />}
      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {data && (
        <div className="space-y-4">
          <p className="text-sm text-ink-3">
            {dateTime(data.created_at)} · mode <b className="text-ink">{data.mode}</b> · model {data.model_name} · policy v{data.policy_version} · {ms(data.timings_ms.total_ms)} · image {data.image.width}×{data.image.height}px
          </p>
          <p className="text-xs text-ink-3">Query images are deleted after the retention window; scores and decisions remain.</p>
          {data.people.map((person) => (
            <section key={person.index} aria-label={`Person ${person.index + 1}`} className="space-y-2 rounded-md border border-line p-3">
              <div className="flex gap-3">
                {person.crop_url ? <AuthImage src={person.crop_url} alt={`Query crop, person ${person.index + 1}`} fit="contain" className="h-28 w-14 shrink-0 rounded bg-surface-2" /> : (
                  <div className="flex h-28 w-14 shrink-0 items-center justify-center rounded bg-surface-2 p-1 text-center text-[10px] text-ink-3">Image removed</div>
                )}
                <div className="min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold">Person {person.index + 1}</span>
                    <OutcomeBadge outcome={person.decision.outcome} />
                  </div>
                  <p className="text-sm">{person.decision.reason}</p>
                  <p className="text-xs text-ink-3">
                    similarity {num(person.decision.top1_score)} · threshold {num(person.decision.accept_threshold)} · margin {num(person.decision.margin)}
                    {person.detector_score !== null && ` · detector ${num(person.detector_score, 2)}`}
                  </p>
                </div>
              </div>
              {person.candidates.length > 0 && (
                <ol className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="Candidates">
                  {person.candidates.map((c) => (
                    <li key={c.reference_id}>#{c.rank} <span className="font-mono">{c.reference_id}</span> {num(c.score)}</li>
                  ))}
                </ol>
              )}
            </section>
          ))}
        </div>
      )}
    </Dialog>
  );
}
