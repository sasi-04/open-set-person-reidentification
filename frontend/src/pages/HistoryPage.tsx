/**
 * Decision history: past Match Studio requests with their outcomes (opened from Match Studio).
 *
 * Wide screens get a table; phones get one card per request (a six-column table does not
 * fit in 360px). Records hold scores and decisions - never raw images or embeddings.
 */
import { useQuery } from "@tanstack/react-query";
import { History as HistoryIcon, RefreshCcw, ScanSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { OutcomeBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Select } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/PageHeader";
import { HistoryDetailDialog } from "@/features/history/HistoryDetailDialog";
import { dateTime, ms, num } from "@/lib/format";
import { api, keys } from "@/services/api";
import type { HistoryItem, Outcome } from "@/types/api";

const PAGE_SIZE = 15;

function Outcomes({ item }: { item: HistoryItem }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {(Object.entries(item.outcomes) as [Outcome, number][]).map(([outcome, n]) => (
        <span key={outcome} className="inline-flex items-center gap-1"><OutcomeBadge outcome={outcome} short />{n > 1 && <span className="text-xs text-ink-3">×{n}</span>}</span>
      ))}
    </div>
  );
}

export default function HistoryPage() {
  const [outcome, setOutcome] = useState<Outcome | "">("");
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const query = useQuery({
    queryKey: [...keys.history, { outcome, page }],
    queryFn: () => api.history({ outcome, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    placeholderData: (previous) => previous,
  });
  const data = query.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="Decision history"
        description="Every Match Studio request with its decision, scores and timings. Raw images and embeddings are not stored here."
        actions={
          <>
            <Link to="/match"><Button icon={<ScanSearch aria-hidden className="size-4" />}>Back to Match Studio</Button></Link>
            <Button icon={<RefreshCcw aria-hidden className="size-4" />} loading={query.isFetching && !query.isLoading} onClick={() => void query.refetch()}>Refresh</Button>
          </>
        }
      />
      <Card className="mb-4 flex flex-wrap items-center gap-3 p-3">
        <label htmlFor="outcome-filter" className="text-sm font-medium">Outcome</label>
        <Select id="outcome-filter" className="max-w-xs" value={outcome} onChange={(e) => { setOutcome(e.target.value as Outcome | ""); setPage(0); }}>
          <option value="">All outcomes</option>
          <option value="accepted">Match</option>
          <option value="unknown">Unknown (no supported match)</option>
          <option value="review_required">Review</option>
          <option value="processing_error">Processing error</option>
        </Select>
        {data && <span className="text-sm text-ink-3">{data.total} {data.total === 1 ? "request" : "requests"}</span>}
      </Card>

      {query.isLoading && <div className="space-y-2" aria-busy="true" aria-label="Loading history">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-14" />)}</div>}
      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} title="History could not be loaded" />}
      {data && data.items.length === 0 && (
        <EmptyState icon={<HistoryIcon aria-hidden className="size-5" />} title={outcome ? "No requests with this outcome" : "No requests yet"}>
          {outcome ? "Try another outcome filter." : "Run a query in Match Studio and it will be listed here."}
        </EmptyState>
      )}
      {data && data.items.length > 0 && (
        <div className={query.isFetching && !query.isLoading ? "opacity-60" : undefined}>
          {/* wide screens: table */}
          <Card className="hidden overflow-x-auto md:block">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Re-identification requests, newest first</caption>
              <thead className="border-b border-line bg-surface-2 text-xs text-ink-3">
                <tr>{["When", "People", "Outcomes", "Best similarity", "Policy", "Time", ""].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((item) => (
                  <tr key={item.request_id} className="hover:bg-surface-2/60">
                    <td className="px-4 py-2.5 whitespace-nowrap">{dateTime(item.created_at)}</td>
                    <td className="px-4 py-2.5 tabular">{item.n_people}</td>
                    <td className="px-4 py-2.5"><Outcomes item={item} /></td>
                    <td className="px-4 py-2.5 tabular">{num(item.best_score)}</td>
                    <td className="px-4 py-2.5 tabular">v{item.policy_version}</td>
                    <td className="px-4 py-2.5 tabular whitespace-nowrap">{ms(item.total_ms)}</td>
                    <td className="px-4 py-2.5 text-right"><Button size="sm" onClick={() => setOpen(item.request_id)} aria-label={`View details of request ${item.request_id}`}>Details</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {/* phones: cards */}
          <ul className="space-y-2 md:hidden">
            {data.items.map((item) => (
              <li key={item.request_id}>
                <button type="button" onClick={() => setOpen(item.request_id)} aria-label={`View details of request ${item.request_id}`} className="w-full space-y-1.5 rounded-lg border border-line bg-surface p-3 text-left shadow-card">
                  <div className="flex items-center justify-between gap-2 text-xs text-ink-3"><span>{dateTime(item.created_at)}</span><span>{ms(item.total_ms)}</span></div>
                  <Outcomes item={item} />
                  <p className="text-xs text-ink-3">{item.n_people} {item.n_people === 1 ? "person" : "people"} · best similarity {num(item.best_score)} · policy v{item.policy_version}</p>
                </button>
              </li>
            ))}
          </ul>
          <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-3 text-sm">
            <span className="text-ink-3">Page {page + 1} of {pages}</span>
            <div className="flex gap-2">
              <Button size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </nav>
        </div>
      )}
      <HistoryDetailDialog requestId={open} onClose={() => setOpen(null)} />
    </>
  );
}
