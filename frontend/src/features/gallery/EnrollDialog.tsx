/**
 * EnrollDialog: add a new authorised identity to the gallery.
 *
 * In plain words: choose a pseudonymous reference ID, tick that the person is authorised,
 * add one or more images, submit. The backend answers file by file, so a bad image is
 * reported without losing the good ones. The dialog shows that answer (and any
 * "possible duplicate person" warnings) before closing.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Notice } from "@/components/ui/Feedback";
import { FileDrop } from "@/components/ui/FileDrop";
import { Checkbox, Field, TextInput } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { useFileLimits } from "@/hooks/useLimits";
import { fileSize } from "@/lib/format";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";
import type { EnrollResponse } from "@/types/api";

const REFERENCE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$/;

export function EnrollDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const limits = useFileLimits();

  const [referenceId, setReferenceId] = useState("");
  const [label, setLabel] = useState("");
  const [consent, setConsent] = useState(false);
  const [asCrops, setAsCrops] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [touched, setTouched] = useState(false);
  const [outcome, setOutcome] = useState<EnrollResponse | null>(null);

  const previews = useMemo(() => files.map((file) => ({ file, url: URL.createObjectURL(file) })), [files]);
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);

  function close(next: boolean) {
    if (!next) {
      setReferenceId(""); setLabel(""); setConsent(false); setFiles([]); setTouched(false); setOutcome(null);
    }
    onOpenChange(next);
  }

  const mutation = useMutation({
    mutationFn: () => api.enroll({ referenceId: referenceId.trim(), label: label.trim() || undefined, files, imagesAreCrops: asCrops, consent }),
    onSuccess: (response) => {
      setOutcome(response);
      const enrolled = response.files.filter((f) => f.status === "enrolled").length;
      toast.success(`Enrolled “${response.identity.reference_id}” with ${enrolled} ${enrolled === 1 ? "image" : "images"}.`);
      void queryClient.invalidateQueries({ queryKey: keys.gallery });
      void queryClient.invalidateQueries({ queryKey: keys.overview });
    },
    onError: (failure) => toast.error(describeError(failure)),
  });

  const idError = touched && !REFERENCE_ID.test(referenceId.trim()) ? "Use 2–64 letters, digits, '.', '_' or '-', starting with a letter or digit." : null;
  const valid = REFERENCE_ID.test(referenceId.trim()) && consent && files.length > 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (valid) mutation.mutate();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      size="lg"
      title="Enroll an authorised identity"
      description="Only enroll people who have agreed to be in this test gallery."
      footer={
        outcome ? (
          <Button variant="primary" onClick={() => close(false)}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={() => close(false)} disabled={mutation.isPending}>Cancel</Button>
            <Button variant="primary" type="submit" form="enroll-form" loading={mutation.isPending} disabled={!valid}>Enroll identity</Button>
          </>
        )
      }
    >
      {outcome ? (
        <div className="space-y-3">
          <Notice tone="info" title={`“${outcome.identity.reference_id}” now has ${outcome.identity.n_images} reference ${outcome.identity.n_images === 1 ? "image" : "images"}`}>
            Body and face fingerprints were computed and the search index was refreshed.
          </Notice>
          {outcome.warnings.map((warning) => (
            <Notice key={warning} tone="warn" title={/usable face/i.test(warning) ? "No usable face to match on" : "Possible duplicate person"}>{warning}</Notice>
          ))}
          <ul className="divide-y divide-line rounded-md border border-line text-sm">
            {outcome.files.map((file, index) => (
              <li key={`${file.filename}-${index}`} className="flex items-start gap-2.5 px-3 py-2">
                {file.status === "enrolled" ? <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-ok" /> : <XCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-bad" />}
                <div className="min-w-0">
                  <p className="truncate font-medium">{file.filename}</p>
                  <p className="text-xs text-ink-3">
                    {file.status === "enrolled" ? "Enrolled" : `Not enrolled: ${file.reason}`}
                    {file.status === "enrolled" && file.face_status && file.face_status !== "not_analysed" && (
                      <> · {file.face_status === "ready" ? "usable face on file" : file.face_note ?? "no usable face"}</>
                    )}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <form id="enroll-form" onSubmit={submit} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Reference ID" hint="A pseudonymous label, e.g. subject-017. Not a real name or ID number." error={idError}>
              <TextInput value={referenceId} onChange={(e) => setReferenceId(e.target.value)} onBlur={() => setTouched(true)} autoComplete="off" spellCheck={false} maxLength={64} required />
            </Field>
            <Field label="Description (optional)" hint="Shown in the gallery. Keep it non-sensitive.">
              <TextInput value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} />
            </Field>
          </div>

          <FileDrop multiple limits={limits} onFiles={(added) => setFiles((current) => [...current, ...added].slice(0, 20))} title="Drag reference images here" compact />
          {previews.length > 0 && (
            <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5" aria-label="Chosen images">
              {previews.map(({ file, url }, index) => (
                <li key={`${file.name}-${index}`} className="relative overflow-hidden rounded-md border border-line">
                  <img src={url} alt={file.name} className="h-24 w-full object-cover" />
                  <p className="truncate bg-surface px-1.5 py-1 text-[11px] text-ink-3" title={`${file.name} · ${fileSize(file.size)}`}>{file.name}</p>
                  <button type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((c) => c.filter((_, i) => i !== index))} className="absolute top-1 right-1 rounded-full bg-black/60 p-1 text-white hover:bg-black/80">
                    <X aria-hidden className="size-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <Checkbox
            label="Each image is already a tight crop of this one person"
            hint="Untick to let the detector find and crop the person. Photos showing several people are refused so the wrong person is never enrolled. Include at least one clear, front-facing photo of the face: it is what face matching relies on."
            checked={asCrops}
            onChange={(e) => setAsCrops(e.target.checked)}
          />
          <Checkbox
            label="I confirm this person is authorised to be enrolled in this test gallery"
            hint="Required. A fingerprint of their face and body is stored (biometric data) until you delete them. Do not enroll anyone without their permission."
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
        </form>
      )}
    </Dialog>
  );
}
