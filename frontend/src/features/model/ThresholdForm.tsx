/**
 * ThresholdForm: change the live decision rules.
 *
 * In plain words: this really changes backend behaviour - saving creates a NEW policy
 * version and the very next query uses it. So the form validates ranges, shows what
 * changed, and asks for confirmation that spells out the consequence. A manually typed
 * value is stored as "experimental": only a calibration run can make a policy "calibrated".
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Notice } from "@/components/ui/Feedback";
import { Checkbox, Field, Select, TextInput } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";
import type { Policy } from "@/types/api";

interface FormState {
  mode: "body" | "face_body";
  faceThreshold: string;
  faceBand: string;
  bodyOnly: "review" | "accept";
  threshold: string;
  useMargin: boolean;
  margin: string;
  marginAction: "review" | "reject";
  reviewOnQuality: boolean;
  note: string;
}

function fromPolicy(policy: Policy): FormState {
  return {
    mode: policy.matching_mode ?? "body",
    faceThreshold: (policy.face_accept_threshold ?? 0.465).toFixed(3),
    faceBand: (policy.face_review_band ?? 0.1).toFixed(3),
    bodyOnly: policy.body_only_action ?? "review",
    threshold: policy.accept_threshold.toFixed(3),
    useMargin: policy.min_margin !== null,
    margin: (policy.min_margin ?? 0.05).toFixed(3),
    marginAction: policy.margin_action,
    reviewOnQuality: policy.review_on_quality_flags,
    note: "",
  };
}

function parseRange(text: string, low: number, high: number): { value: number | null; error: string | null } {
  if (text.trim() === "") return { value: null, error: "Enter a number." };
  const value = Number(text);
  if (!Number.isFinite(value)) return { value: null, error: "Enter a valid number." };
  if (value < low || value > high) return { value: null, error: `Must be between ${low} and ${high}.` };
  return { value, error: null };
}

export function ThresholdForm({ policy, canEdit }: { policy: Policy; canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => fromPolicy(policy));
  const [confirming, setConfirming] = useState(false);

  // When a new policy version becomes active (after saving, or applying a calibration), show its values.
  useEffect(() => setForm(fromPolicy(policy)), [policy.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const threshold = parseRange(form.threshold, 0, 1);
  const margin = form.useMargin ? parseRange(form.margin, 0, 1) : { value: null, error: null };
  const withFace = form.mode === "face_body";
  const faceThreshold = withFace ? parseRange(form.faceThreshold, 0.01, 0.99) : { value: null, error: null };
  const faceBand = withFace ? parseRange(form.faceBand, 0, 0.5) : { value: null, error: null };
  const valid = !threshold.error && !margin.error && !faceThreshold.error && !faceBand.error;

  const base = fromPolicy(policy);
  const dirty =
    form.threshold !== base.threshold || form.useMargin !== base.useMargin || (form.useMargin && form.margin !== base.margin) ||
    form.marginAction !== base.marginAction || form.reviewOnQuality !== base.reviewOnQuality || form.mode !== base.mode ||
    (withFace && (form.faceThreshold !== base.faceThreshold || form.faceBand !== base.faceBand || form.bodyOnly !== base.bodyOnly));

  const save = useMutation({
    mutationFn: () =>
      api.updateThresholds({
        accept_threshold: threshold.value as number,
        min_margin: form.useMargin ? (margin.value as number) : null,
        margin_action: form.marginAction,
        review_on_quality_flags: form.reviewOnQuality,
        matching_mode: form.mode,
        ...(withFace ? { face_accept_threshold: faceThreshold.value as number, face_review_band: faceBand.value as number, body_only_action: form.bodyOnly } : {}),
        note: form.note.trim(),
        confirm: true,
      }),
    onSuccess: (created) => {
      toast.success(`Policy v${created.version} is now active (experimental). The next query uses it.`);
      setConfirming(false);
      for (const key of [keys.config, keys.policyHistory, keys.overview, keys.audit]) void queryClient.invalidateQueries({ queryKey: key });
    },
    onError: (failure) => {
      setConfirming(false);
      toast.error(describeError(failure));
    },
  });

  return (
    <form
      onSubmit={(event) => { event.preventDefault(); if (valid && dirty) setConfirming(true); }}
      className="space-y-4" noValidate aria-label="Decision policy"
    >
      {!canEdit && <Notice tone="info" title="Read-only">Changing the policy needs the admin role.</Notice>}
      <div className="space-y-3 rounded-md border border-line p-3">
        <Field label="Matching mode" hint="What the system compares. Face + body is the recommended mode: a face that does not match can never be overruled by similar clothing.">
          <Select value={form.mode} disabled={!canEdit} onChange={(e) => setForm({ ...form, mode: e.target.value as "body" | "face_body" })}>
            <option value="face_body">Face + body (recommended)</option>
            <option value="body">Body only (original PS-1 baseline: clothing and build)</option>
          </Select>
        </Field>
        {withFace && !policy.face_models_loaded && (
          <Notice tone="warn" title="Face models are not loaded">
            Until they are downloaded (<code className="font-mono text-xs">scripts\download_weights.py</code>) and the server is restarted, this policy still matches on the body only.
          </Notice>
        )}
        {withFace && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Face threshold" hint="Minimum face similarity (0–1) for a MATCH. Higher = stricter. 0.465 keeps strangers to about 1 in 100,000 comparisons in the LFW measurement; the model card's own value is 0.363." error={faceThreshold.error}>
              <TextInput type="number" inputMode="decimal" min={0.01} max={0.99} step={0.005} value={form.faceThreshold} disabled={!canEdit} onChange={(e) => setForm({ ...form, faceThreshold: e.target.value })} />
            </Field>
            <Field label="Face review band" hint="A face score this far BELOW the threshold goes to a person instead of UNKNOWN." error={faceBand.error}>
              <TextInput type="number" inputMode="decimal" min={0} max={0.5} step={0.01} value={form.faceBand} disabled={!canEdit} onChange={(e) => setForm({ ...form, faceBand: e.target.value })} />
            </Field>
            <Field label="No usable face: clothing and build alone" hint="When there is no usable face, a strong body match is..." className="sm:col-span-2">
              <Select value={form.bodyOnly} disabled={!canEdit} onChange={(e) => setForm({ ...form, bodyOnly: e.target.value as "review" | "accept" })}>
                <option value="review">Sent to a person for review (recommended)</option>
                <option value="accept">Accepted as a MATCH (the original behaviour)</option>
              </Select>
            </Field>
          </div>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Acceptance threshold" hint={withFace ? "Body similarity (0–1) that counts as 'clothing and build agree'." : "Minimum top-1 cosine similarity (0–1) to accept."} error={threshold.error}>
          <TextInput type="number" inputMode="decimal" min={0} max={1} step={0.005} value={form.threshold} disabled={!canEdit} onChange={(e) => setForm({ ...form, threshold: e.target.value })} />
        </Field>
        <Field label="If the margin rule fails" hint="What to do with a near-tie." >
          <Select value={form.marginAction} disabled={!canEdit || !form.useMargin} onChange={(e) => setForm({ ...form, marginAction: e.target.value as "review" | "reject" })}>
            <option value="review">Send to human review</option>
            <option value="reject">Reject as unknown</option>
          </Select>
        </Field>
      </div>
      <Checkbox label="Require a minimum margin between the top two candidates" hint="Optional. Guards against near-ties between look-alikes." checked={form.useMargin} disabled={!canEdit} onChange={(e) => setForm({ ...form, useMargin: e.target.checked })} />
      {form.useMargin && (
        <Field label="Minimum margin (top-1 − top-2)" hint="0–1. Typical values are small, such as 0.02–0.10." error={margin.error} className="sm:max-w-xs">
          <TextInput type="number" inputMode="decimal" min={0} max={1} step={0.005} value={form.margin} disabled={!canEdit} onChange={(e) => setForm({ ...form, margin: e.target.value })} />
        </Field>
      )}
      <Checkbox label="Send poor-quality crops to review" hint="Blurry, tiny or cut-off crops are not auto-accepted or auto-rejected." checked={form.reviewOnQuality} disabled={!canEdit} onChange={(e) => setForm({ ...form, reviewOnQuality: e.target.checked })} />
      <Field label="Note (optional)" hint="Why you are changing it. Kept in the version history.">
        <TextInput value={form.note} maxLength={400} disabled={!canEdit} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" disabled={!canEdit || !valid || !dirty} icon={<Save aria-hidden className="size-4" />}>Save settings</Button>
        <Button disabled={!dirty || save.isPending} icon={<RotateCcw aria-hidden className="size-4" />} onClick={() => setForm(fromPolicy(policy))}>Cancel changes</Button>
      </div>
      <ConfirmDialog
        open={confirming} onOpenChange={setConfirming} tone="primary" title="Apply these decision rules?" confirmLabel="Apply to live decisions"
        loading={save.isPending} onConfirm={() => save.mutate()}
        consequences={<>A new policy version <b>v{policy.version + 1}</b> will become active immediately: <b>{withFace ? `face + body matching (face threshold ${faceThreshold.value})` : "body-only matching"}</b>, body threshold <b>{threshold.value}</b>{form.useMargin ? <>, minimum margin <b>{margin.value}</b></> : ", no margin rule"}. It will be marked <b>experimental</b> because it was not selected on calibration data. The previous version stays in the history.</>}
      />
    </form>
  );
}
