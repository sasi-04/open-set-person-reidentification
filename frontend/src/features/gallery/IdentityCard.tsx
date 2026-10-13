/** Gallery entries, as a grid card or a list row. Both are one button that opens the details. */
import clsx from "clsx";
import { Badge } from "@/components/ui/Badge";
import { AuthImage } from "@/components/ui/AuthImage";
import { shortDate } from "@/lib/format";
import type { EmbeddingStatus, IdentitySummary } from "@/types/api";
import { CheckCircle2, RefreshCcw, ScanFace, TriangleAlert } from "lucide-react";

export function EmbeddingBadge({ status }: { status: EmbeddingStatus }) {
  if (status === "ready") return <Badge tone="ok" icon={<CheckCircle2 aria-hidden className="size-3.5" />}>Embeddings ready</Badge>;
  if (status === "failed") return <Badge tone="bad" icon={<TriangleAlert aria-hidden className="size-3.5" />}>Embedding failed</Badge>;
  return <Badge tone="warn" icon={<RefreshCcw aria-hidden className="size-3.5" />}>{status === "stale" ? "Needs rebuild" : "Partly stale"}</Badge>;
}

/** How many of a person's reference photos have a usable face on file - the thing face matching relies on. */
export function FaceCountBadge({ identity }: { identity: IdentitySummary }) {
  if (identity.n_faces > 0) {
    return <Badge tone="ok" icon={<ScanFace aria-hidden className="size-3.5" />}>{identity.n_faces} of {identity.n_images} with a face</Badge>;
  }
  return <Badge tone="warn" icon={<ScanFace aria-hidden className="size-3.5" />}>No face on file</Badge>;
}

export function IdentityCard({ identity, view, onOpen }: { identity: IdentitySummary; view: "grid" | "list"; onOpen: () => void }) {
  const images = `${identity.n_images} ${identity.n_images === 1 ? "image" : "images"}`;
  if (view === "list") {
    return (
      <button type="button" onClick={onOpen} aria-label={`Open ${identity.reference_id}, ${images}`} className="flex w-full items-center gap-3 rounded-md border border-line bg-surface p-2.5 text-left hover:bg-surface-2">
        <AuthImage src={identity.thumbnail_url} alt="" className="h-14 w-7 shrink-0 rounded" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-sm font-semibold">{identity.reference_id}</p>
          <p className="truncate text-xs text-ink-3">{identity.label ?? "No description"}</p>
        </div>
        <span className="hidden text-xs text-ink-3 sm:block">{images}</span>
        <span className="hidden text-xs text-ink-3 md:block">{shortDate(identity.created_at)}</span>
        <span className="hidden lg:block"><FaceCountBadge identity={identity} /></span>
        <EmbeddingBadge status={identity.embedding_status} />
      </button>
    );
  }
  return (
    <button type="button" onClick={onOpen} aria-label={`Open ${identity.reference_id}, ${images}`} className={clsx("flex w-full min-w-0 flex-col overflow-hidden rounded-lg border border-line bg-surface text-left shadow-card transition-shadow hover:shadow-pop")}>
      <AuthImage src={identity.thumbnail_url} alt="" className="aspect-[3/4] w-full" />
      <div className="space-y-1.5 p-3">
        <p className="truncate font-mono text-sm font-semibold">{identity.reference_id}</p>
        <p className="truncate text-xs text-ink-3">{identity.label ?? "No description"}</p>
        <div className="flex items-center justify-between text-xs text-ink-3">
          <span>{images}</span>
          <span>{shortDate(identity.created_at)}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <EmbeddingBadge status={identity.embedding_status} />
          <FaceCountBadge identity={identity} />
        </div>
      </div>
    </button>
  );
}
