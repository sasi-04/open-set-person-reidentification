/**
 * Model & thresholds: what is running, and the rules that turn scores into decisions.
 *
 * In plain words: this is the "validated settings" half of the Model & System screen. It shows the
 * loaded models with their weight provenance and checksum, the ACTIVE decision policy and how far it
 * can be trusted (unvalidated / experimental / calibrated), and the versioned history of every change.
 * Changing a rule needs explicit confirmation and creates a new auditable version; nothing here is
 * ever edited in place.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge, PolicyBadge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader, DefinitionList } from "@/components/ui/Card";
import { ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { CalibrationApply } from "@/features/model/CalibrationApply";
import { ThresholdForm } from "@/features/model/ThresholdForm";
import { useSession } from "@/hooks/useSession";
import { dateTime, num } from "@/lib/format";
import { can } from "@/lib/present";
import { api, keys } from "@/services/api";

const str = (value: unknown): string => (value === undefined || value === null || value === "" ? "—" : String(value));

/** The thresholds that decide whether a face is good enough to use, in words. */
function usableRules(rules: unknown): string {
  const r = (rules ?? {}) as Record<string, number>;
  if (!r.min_face_px) return "—";
  return `at least ${r.min_face_px} px wide, detector confidence ≥ ${r.min_detector_confidence}, not turned more than ${r.max_turn_ratio} of its width, sharp enough`;
}

export function ModelPanel() {
  const { role } = useSession();
  const config = useQuery({ queryKey: keys.config, queryFn: api.config });
  const status = useQuery({ queryKey: keys.modelStatus, queryFn: api.modelStatus, refetchInterval: 20_000 });
  const history = useQuery({ queryKey: keys.policyHistory, queryFn: api.policyHistory });

  if (config.isLoading || status.isLoading) return <Skeleton className="h-64 w-full" />;
  if (config.isError || status.isError || !config.data || !status.data) {
    return <ErrorState error={config.error ?? status.error} onRetry={() => { void config.refetch(); void status.refetch(); }} />;
  }

  const policy = config.data.policy;
  const emb = status.data.embedding;
  const det = status.data.detector;
  const face = status.data.face;
  const liveFingerprint = typeof emb.fingerprint === "string" ? emb.fingerprint : null;
  const admin = can(role, "admin");

  return (
    <>
      <p className="mb-4 max-w-3xl text-sm text-ink-3">The loaded models, and the versioned rules that turn similarity scores into MATCH, UNKNOWN or REVIEW decisions. These are the <b className="text-ink-2">validated settings</b>: a rule only becomes “calibrated” through a calibration run on held-out people.</p>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <Card aria-labelledby="emb-title">
            <CardHeader id="emb-title" title="Embedding model" description="One compact backbone turns each person crop into a fixed-length vector." />
            <CardBody>
              {!emb.ready ? <Notice tone="bad" title="Not loaded">{str(emb.error)}</Notice> : (
                <DefinitionList items={[
                  { term: "Architecture", value: str(emb.architecture) },
                  { term: "Checkpoint", value: str(emb.weights) },
                  { term: "Integrity", value: emb.weights_verified_against_pinned_hash ? "Verified against the pinned SHA-256" : "Custom checkpoint (hash reported, not pinned)" },
                  { term: "SHA-256", value: <span className="font-mono text-xs break-all">{str(emb.weights_sha256)}</span> },
                  { term: "Embedding dimension", value: str(emb.embedding_dim) },
                  { term: "Input size", value: Array.isArray(emb.input_size) ? `${emb.input_size[0]}×${emb.input_size[1]} px` : "—" },
                  { term: "Parameters", value: typeof emb.parameters === "number" ? `${(emb.parameters / 1e6).toFixed(2)} M` : "—" },
                  { term: "Device", value: str(emb.device) },
                  { term: "Flip augmentation", value: emb.flip_tta ? "On" : "Off" },
                  { term: "Initialisation", value: `Loaded in ${str(emb.load_seconds)} s; warm-up ${str(emb.warmup_seconds)} s (one-off, excluded from request latency)` },
                  { term: "Weights licence", value: str(emb.weights_license) },
                  { term: "Trained on", value: str(emb.training_data) },
                  { term: "Source", value: <span className="break-all">{str(emb.weights_source)}</span> },
                ]} />
              )}
            </CardBody>
          </Card>
          <Card aria-labelledby="face-title">
            <CardHeader id="face-title" title="Face models" description="A face detector and a face recogniser. When a usable face is visible, the face decides." action={face?.ready ? <Badge tone="ok">Loaded</Badge> : <Badge tone="warn">Not loaded</Badge>} />
            <CardBody>
              {!face?.ready ? <Notice tone="warn" title="Face models are not loaded">{str(face?.error ?? "Run scripts\\download_weights.py and restart the server.")} Matching uses the body only until they are.</Notice> : (
                <DefinitionList items={[
                  { term: "Models", value: str(face.display_name) },
                  { term: "Fingerprint size", value: `${str(face.embedding_dim)} numbers per face` },
                  { term: "Integrity", value: face.weights_verified_against_pinned_hash ? "Verified against the SHA-256 published by the OpenCV model zoo" : "Not verified" },
                  { term: "Enrolled faces", value: `${face.enrolled_faces} reference faces from ${face.identities_with_a_face} people` },
                  { term: "A face is usable when", value: usableRules(face.usable_face_rules) },
                  { term: "Licences", value: "YuNet: MIT · SFace: Apache-2.0" },
                ]} />
              )}
            </CardBody>
          </Card>
          <Card aria-labelledby="det-title">
            <CardHeader id="det-title" title="Person detector" />
            <CardBody>
              {!det.ready ? <Notice tone="warn" title="Not loaded">{str(det.error)}</Notice> : (
                <DefinitionList items={[
                  { term: "Model", value: str(det.display_name) }, { term: "Device", value: str(det.device) },
                  { term: "Minimum confidence", value: str(det.score_threshold) }, { term: "Weights", value: str(det.weights_source) },
                  { term: "Search index", value: `version ${status.data.gallery_index.version} · ${status.data.gallery_index.identities} identities · ${status.data.gallery_index.images} images` },
                ]} />
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-4">
          <Card aria-labelledby="policy-title">
            <CardHeader id="policy-title" title="Active decision policy" description={`Version ${policy.version}, set by ${policy.created_by} on ${dateTime(policy.created_at)}`} action={<PolicyBadge status={policy.status} />} />
            <CardBody className="space-y-4">
              <Notice tone={policy.status === "calibrated" ? "info" : "warn"} title={policy.status === "calibrated" ? "Calibrated" : policy.status === "experimental" ? "Experimental threshold" : "Unvalidated starting value"}>
                {policy.status_explanation}
              </Notice>
              <DefinitionList items={[
                { term: "Matching mode", value: policy.matching_mode === "face_body" ? <>Face + body{!policy.face_models_loaded && <span className="ml-1 font-medium text-warn"> (face models not loaded: body only for now)</span>}</> : "Body only (clothing and build)" },
                ...(policy.matching_mode === "face_body" ? [
                  { term: "Face threshold", value: <span className="tabular">{num(policy.face_accept_threshold)} (review band {num(policy.face_review_band, 2)} below it)</span> },
                  { term: "Without a usable face", value: policy.body_only_action === "accept" ? "A strong body match is accepted" : "A strong body match goes to a person for review" },
                ] : []),
                { term: policy.matching_mode === "face_body" ? "Body threshold" : "Threshold", value: <span className="tabular">{num(policy.accept_threshold)}</span> },
                { term: "Minimum margin", value: policy.min_margin === null ? "Not used" : <span className="tabular">{num(policy.min_margin)} (then: {policy.margin_action})</span> },
                { term: "Quality review", value: policy.review_on_quality_flags ? "Poor-quality crops go to review" : "Off" },
                { term: "Calibration run", value: policy.calibration_run_id ? <span className="font-mono text-xs">{policy.calibration_run_id.slice(0, 12)}…</span> : "None" },
                { term: "Confidence model", value: policy.has_confidence_model ? "Fitted on the calibration split" : "None" },
                { term: "Set for model", value: policy.model_fingerprint ? <>{policy.model_fingerprint}{policy.model_matches_current === false && <span className="ml-1 font-medium text-warn"> (not the model running now)</span>}</> : "—" },
                { term: "Note", value: policy.note || "—" },
              ]} />
            </CardBody>
          </Card>

          <Card aria-labelledby="edit-title">
            <CardHeader id="edit-title" title="Experimental: set the rules by hand" description="A hand-set value creates a new version marked “experimental”, never “calibrated”. It takes effect on the next query and is audited." action={<Badge tone="info">Experimental</Badge>} />
            <CardBody><ThresholdForm policy={policy} canEdit={admin} /></CardBody>
          </Card>

          <Card aria-labelledby="cal-title">
            <CardHeader id="cal-title" title="Validated: apply a calibration result" description="Thresholds selected on a held-out calibration split. Start one in the Evaluation Lab." action={<span className="flex items-center gap-2"><Badge tone="ok">Validated</Badge><Link to="/evaluation" className="text-sm font-medium underline">Evaluation Lab</Link></span>} />
            <CardBody><CalibrationApply liveFingerprint={liveFingerprint} canEdit={admin} /></CardBody>
          </Card>
        </div>
      </div>

      <Card className="mt-4" aria-labelledby="hist-title">
        <CardHeader id="hist-title" title="Policy version history" description="Newest first. Older versions are never edited." />
        <CardBody className="overflow-x-auto">
          {history.isLoading && <Skeleton className="h-24 w-full" />}
          {history.isError && <ErrorState error={history.error} onRetry={() => void history.refetch()} />}
          {history.data && (
            <table className="w-full min-w-[40rem] text-left text-sm">
              <caption className="sr-only">Decision policy versions</caption>
              <thead className="text-xs text-ink-3"><tr>{["Version", "Status", "Mode", "Threshold", "Margin", "By", "When", "Note"].map((h) => <th key={h} scope="col" className="py-2 pr-4 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {history.data.map((p) => (
                  <tr key={p.version} className={p.is_active ? "bg-surface-2/60" : undefined}>
                    <td className="py-2 pr-4 tabular">v{p.version}{p.is_active && <span className="ml-1.5 text-xs font-medium text-ok">active</span>}</td>
                    <td className="py-2 pr-4"><PolicyBadge status={p.status} /></td>
                    <td className="py-2 pr-4 whitespace-nowrap">{p.matching_mode === "face_body" ? `Face + body (face ${num(p.face_accept_threshold)})` : "Body only"}</td>
                    <td className="py-2 pr-4 tabular">{num(p.accept_threshold)}</td>
                    <td className="py-2 pr-4 tabular">{p.min_margin === null ? "—" : num(p.min_margin)}</td>
                    <td className="py-2 pr-4 capitalize">{p.created_by}</td>
                    <td className="py-2 pr-4 whitespace-nowrap">{dateTime(p.created_at)}</td>
                    <td className="py-2 text-ink-3">{p.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </>
  );
}
