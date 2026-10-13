/**
 * IdentityDialog: inspect one enrolled identity, add images, or delete it.
 *
 * In plain words: shows every reference image and its metadata. Adding images works like
 * enrolling. Deleting needs a confirmation that spells out the consequences, and the
 * backend repeats the check (it requires the reference ID back), so a stray click or a
 * hand-made request cannot delete anything.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { EmbeddingBadge, FaceCountBadge } from "@/features/gallery/IdentityCard";
import { AuthImage } from "@/components/ui/AuthImage";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DefinitionList } from "@/components/ui/Card";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { FileDrop } from "@/components/ui/FileDrop";
import { Checkbox } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { useFileLimits } from "@/hooks/useLimits";
import { dateTime } from "@/lib/format";
import { QUALITY_FLAGS, REFERENCE_FACE_STATUS } from "@/lib/present";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";

export function IdentityDialog({ referenceId, onClose, canEdit }: { referenceId: string | null; onClose: () => void; canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const limits = useFileLimits();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [adding, setAdding] = useState(false);
  const [asCrops, setAsCrops] = useState(true);

  const query = useQuery({ queryKey: keys.identity(referenceId ?? ""), queryFn: () => api.identity(referenceId as string), enabled: !!referenceId });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: keys.gallery });
    void queryClient.invalidateQueries({ queryKey: keys.overview });
    if (referenceId) void queryClient.invalidateQueries({ queryKey: keys.identity(referenceId) });
  };

  const addImages = useMutation({
    mutationFn: (files: File[]) => api.addImages(referenceId as string, files, asCrops),
    onSuccess: (response) => {
      const added = response.files.filter((f) => f.status === "enrolled").length;
      const rejected = response.files.filter((f) => f.status === "rejected");
      toast.success(`Added ${added} ${added === 1 ? "image" : "images"} to “${referenceId}”.`);
      rejected.forEach((f) => toast.error(`${f.filename}: ${f.reason}`));
      response.warnings.forEach((w) => toast.info(w));
      setAdding(false);
      refresh();
    },
    onError: (failure) => toast.error(describeError(failure)),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteIdentity(referenceId as string),
    onSuccess: (response) => {
      toast.success(response.message);
      setConfirmDelete(false);
      refresh();
      onClose();
    },
    onError: (failure) => toast.error(describeError(failure)),
  });

  const identity = query.data;
  return (
    <>
      <Dialog
        open={!!referenceId}
        onOpenChange={(open) => !open && onClose()}
        size="lg"
        title={referenceId ? `Identity ${referenceId}` : "Identity"}
        description="Reference images and metadata for this enrolled identity."
        footer={
          <>
            <Button variant="secondary" disabled={!canEdit} title={canEdit ? undefined : "Requires the operator role"} icon={<Plus aria-hidden className="size-4" />} onClick={() => setAdding((v) => !v)}>
              Add images
            </Button>
            <Button variant="danger" disabled={!canEdit} title={canEdit ? undefined : "Requires the operator role"} icon={<Trash2 aria-hidden className="size-4" />} onClick={() => setConfirmDelete(true)}>
              Delete identity
            </Button>
          </>
        }
      >
        {query.isLoading && <div className="space-y-3"><Skeleton className="h-6 w-1/2" /><Skeleton className="h-40 w-full" /></div>}
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {identity && (
          <div className="space-y-5">
            <DefinitionList
              items={[
                { term: "Reference ID", value: <span className="font-mono">{identity.reference_id}</span> },
                { term: "Description", value: identity.label ?? "—" },
                { term: "Enrolled", value: dateTime(identity.created_at) },
                { term: "Last updated", value: dateTime(identity.updated_at) },
                { term: "Reference images", value: identity.n_images },
                { term: "Embedding status", value: <EmbeddingBadge status={identity.embedding_status} /> },
                { term: "Faces on file", value: <FaceCountBadge identity={identity} /> },
                { term: "Authorisation confirmed", value: identity.consent_confirmed ? "Yes (at enrollment)" : "No" },
              ]}
            />
            {identity.embedding_status !== "ready" && (
              <Notice tone="warn" title="Embeddings need rebuilding">
                These images were embedded with a different model, so they are not searched. An operator can press “Rebuild embeddings” on the gallery page.
              </Notice>
            )}
            {adding && (
              <div className="space-y-3 rounded-md border border-line p-3">
                <Checkbox label="Each image is already a tight crop of this person" checked={asCrops} onChange={(e) => setAsCrops(e.target.checked)} />
                <FileDrop multiple limits={limits} compact disabled={addImages.isPending} onFiles={(files) => addImages.mutate(files)} title="Drop more reference images" />
                {addImages.isPending && <p role="status" className="text-sm text-ink-3">Adding images and computing embeddings…</p>}
              </div>
            )}
            {identity.n_faces === 0 && (
              <Notice tone="warn" title="No usable face on file">
                This person can only be matched by clothing and build, which is weaker evidence: a stranger in similar clothes can look alike to the body model. Add a clear, front-facing photo of the face for reliable matching.
              </Notice>
            )}
            <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5" aria-label="Reference images">
              {identity.images.map((image) => {
                const face = REFERENCE_FACE_STATUS[image.face_status] ?? REFERENCE_FACE_STATUS.not_analysed;
                return (
                  <li key={image.image_uid} className="space-y-1">
                    <AuthImage src={image.url} alt={`Reference image of ${identity.reference_id}`} fit="contain" className="aspect-[1/2] w-full rounded-md border border-line bg-surface-2" />
                    <p className="text-[11px] text-ink-3">{image.width}×{image.height}px</p>
                    <span title={image.face_note ?? undefined}><Badge tone={face.tone}>{face.label}</Badge></span>
                    {image.quality_flags.length > 0 && <p className="text-[11px] text-warn">{image.quality_flags.map((f) => QUALITY_FLAGS[f] ?? f).join(", ")}</p>}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </Dialog>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${referenceId}?`}
        confirmLabel="Delete identity"
        loading={remove.isPending}
        requirePhrase={referenceId ?? undefined}
        consequences={<>The identity and all {identity?.n_images ?? ""} of its reference images and embeddings will be permanently deleted, and it will immediately stop being matched. History entries that mention it keep their recorded scores.</>}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
