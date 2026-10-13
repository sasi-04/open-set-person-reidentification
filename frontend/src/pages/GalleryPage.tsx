/**
 * Identity Gallery: browse, enroll, inspect, delete.
 *
 * In plain words: a searchable, sortable, paged list of enrolled identities, shown as a
 * grid or a list. Clicking one opens its details. Enrolling, rebuilding embeddings and
 * resetting are separate buttons, enabled only for roles that may use them (the backend
 * enforces this again). The page address can carry ?ref=<id> so other screens can link
 * straight to one identity.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutGrid, List, RefreshCcw, ScanFace, Search, Trash, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { EmptyState, ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { Select, TextInput } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { EnrollDialog } from "@/features/gallery/EnrollDialog";
import { IdentityCard } from "@/features/gallery/IdentityCard";
import { IdentityDialog } from "@/features/gallery/IdentityDialog";
import { useSession } from "@/hooks/useSession";
import { count } from "@/lib/format";
import { can } from "@/lib/present";
import { api, keys, type GalleryQuery } from "@/services/api";
import { describeError } from "@/services/http";

const PAGE_SIZE = 24;

export default function GalleryPage() {
  const { role } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();

  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState<NonNullable<GalleryQuery["sort"]>>("reference_id");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [status, setStatus] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [page, setPage] = useState(0);
  const [enrolling, setEnrolling] = useState(false);
  const [resetting, setResetting] = useState(false);

  // Wait for a pause in typing before asking the server, and go back to the first page.
  useEffect(() => {
    const timer = window.setTimeout(() => { setDebounced(search); setPage(0); }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const query = useQuery({
    queryKey: [...keys.gallery, { debounced, sort, order, status, page }],
    queryFn: () => api.gallery({ search: debounced, sort, order, embedding_status: status || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    placeholderData: (previous) => previous, // keep the old list visible (dimmed) instead of flashing a skeleton
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: keys.gallery });
    void queryClient.invalidateQueries({ queryKey: keys.overview });
  };
  const rebuild = useMutation({
    mutationFn: api.rebuildGallery,
    onSuccess: (r) => { toast.success(r.message); refresh(); },
    onError: (e) => toast.error(describeError(e)),
  });
  const analyse = useMutation({
    mutationFn: api.analyseFaces,
    onSuccess: (r) => { toast.success(r.message); refresh(); },
    onError: (e) => toast.error(describeError(e)),
  });
  const reset = useMutation({
    mutationFn: api.resetGallery,
    onSuccess: (r) => { toast.success(r.message); setResetting(false); refresh(); },
    onError: (e) => toast.error(describeError(e)),
  });

  const operator = can(role, "operator");
  const admin = can(role, "admin");
  const selectedRef = params.get("ref");
  const data = query.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const filtering = !!debounced || !!status;

  return (
    <>
      <PageHeader
        title="Identity gallery"
        description="People enrolled for matching. Use only authorised identities and pseudonymous reference IDs."
        actions={
          <>
            <Button variant="primary" disabled={!operator} title={operator ? undefined : "Requires the operator role"} icon={<UserPlus aria-hidden className="size-4" />} onClick={() => setEnrolling(true)}>
              Enroll identity
            </Button>
            <Button disabled={!operator} loading={rebuild.isPending} title={operator ? "Re-embed every reference image with the current model" : "Requires the operator role"} icon={<RefreshCcw aria-hidden className="size-4" />} onClick={() => rebuild.mutate()}>
              Rebuild embeddings
            </Button>
            <Button disabled={!operator} loading={analyse.isPending} title={operator ? "Find and fingerprint the faces in reference photos that have none on file yet" : "Requires the operator role"} icon={<ScanFace aria-hidden className="size-4" />} onClick={() => analyse.mutate()}>
              Analyse faces
            </Button>
            <Button variant="danger" disabled={!admin} title={admin ? undefined : "Requires the admin role"} icon={<Trash aria-hidden className="size-4" />} onClick={() => setResetting(true)}>
              Reset demo gallery
            </Button>
          </>
        }
      />

      {data && (
        <dl className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Identities", count(data.summary.identities)],
            ["Reference images", count(data.summary.images)],
            ["Embeddings ready", `${count(data.summary.embeddings_ready)} / ${count(data.summary.images)}`],
            ["Usable faces on file", `${count(data.summary.faces_usable ?? 0)} / ${count(data.summary.images)}`],
          ].map(([term, value]) => (
            <div key={term} className="rounded-lg border border-line bg-surface p-3 shadow-card">
              <dt className="text-xs text-ink-3">{term}</dt>
              <dd className="font-display text-lg font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {data && data.summary.embeddings_stale > 0 && (
        <Notice tone="warn" title={`${data.summary.embeddings_stale} embeddings were made by a different model`} className="mb-4">
          They are excluded from matching until rebuilt. Press “Rebuild embeddings”.
        </Notice>
      )}
      {data && (data.summary.faces_not_analysed ?? 0) > 0 && data.summary.face_model && (
        <Notice tone="info" title={`${data.summary.faces_not_analysed} reference photo(s) have not had their face analysed`} className="mb-4">
          They are matched by body only until analysed. An operator can press “Analyse faces”.
        </Notice>
      )}
      {data && (
        <p className="mb-4 text-xs text-ink-3">Gallery strategy: {data.summary.strategy} Search index v{data.summary.index_version} · {count(data.summary.index_images)} images.</p>
      )}

      <Card className="mb-4 p-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_180px_130px_170px_auto]">
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <TextInput aria-label="Search identities" placeholder="Search reference ID or description" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Sort by" value={sort} onChange={(e) => { setSort(e.target.value as typeof sort); setPage(0); }}>
            <option value="reference_id">Sort: Reference ID</option>
            <option value="created_at">Sort: Enrollment date</option>
            <option value="updated_at">Sort: Last updated</option>
            <option value="n_images">Sort: Image count</option>
          </Select>
          <Select aria-label="Sort order" value={order} onChange={(e) => { setOrder(e.target.value as "asc" | "desc"); setPage(0); }}>
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </Select>
          <Select aria-label="Filter by embedding status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>
            <option value="">All embedding states</option>
            <option value="ready">Ready</option>
            <option value="stale">Needs rebuild</option>
            <option value="failed">Failed</option>
          </Select>
          <div role="group" aria-label="View" className="flex gap-1">
            <Button variant={view === "grid" ? "dark" : "secondary"} aria-pressed={view === "grid"} aria-label="Grid view" className="!px-3" onClick={() => setView("grid")}><LayoutGrid aria-hidden className="size-4" /></Button>
            <Button variant={view === "list" ? "dark" : "secondary"} aria-pressed={view === "list"} aria-label="List view" className="!px-3" onClick={() => setView("list")}><List aria-hidden className="size-4" /></Button>
          </div>
        </div>
      </Card>

      {query.isLoading && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6" aria-busy="true" aria-label="Loading gallery">
          {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="aspect-[3/4]" />)}
        </div>
      )}
      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} title="The gallery could not be loaded" />}
      {data && data.total === 0 && (
        <EmptyState icon={<Users aria-hidden className="size-5" />} title={filtering ? "No identities match" : "The gallery is empty"}
          action={!filtering && operator ? <Button variant="primary" onClick={() => setEnrolling(true)}>Enroll the first identity</Button> : undefined}>
          {filtering ? "Try a different search or clear the filters." : "No one is enrolled yet. Until you enroll an authorised identity, every query is reported as unknown."}
        </EmptyState>
      )}
      {data && data.total > 0 && (
        <div className={query.isFetching && !query.isLoading ? "opacity-60 transition-opacity" : "transition-opacity"} aria-busy={query.isFetching}>
          <ul className={view === "grid" ? "grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6" : "space-y-2"}>
            {data.items.map((identity) => (
              <li key={identity.reference_id} className="min-w-0">
                <IdentityCard identity={identity} view={view} onOpen={() => setParams({ ref: identity.reference_id })} />
              </li>
            ))}
          </ul>
          <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-3 text-sm">
            <span className="text-ink-3">Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total)} of {data.total}</span>
            <div className="flex items-center gap-2">
              <Button size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <span className="text-xs text-ink-3">Page {page + 1} of {pages}</span>
              <Button size="sm" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </nav>
        </div>
      )}

      <EnrollDialog open={enrolling} onOpenChange={setEnrolling} />
      <IdentityDialog referenceId={selectedRef} canEdit={operator} onClose={() => setParams({})} />
      <ConfirmDialog
        open={resetting}
        onOpenChange={setResetting}
        title="Reset the demonstration gallery?"
        confirmLabel="Delete everything"
        requirePhrase="RESET DEMO GALLERY"
        loading={reset.isPending}
        consequences={<>Every enrolled identity, reference image and embedding will be permanently deleted. Inference history is kept but will refer to identities that no longer exist.</>}
        onConfirm={() => reset.mutate()}
      />
    </>
  );
}
