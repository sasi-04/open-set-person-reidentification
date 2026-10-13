/**
 * Runtime and system health (one tab of the Model & System Settings screen).
 *
 * In plain words: "is everything the matcher needs actually working, and under what limits?" Each
 * line is read from the running backend (readiness, model status, configured limits) - nothing is
 * assumed. A component that failed to load shows the real reason (for example "weights file missing"),
 * because that message is exactly what someone needs to fix it. Settings that are only experimental
 * (a hand-set threshold, flip augmentation) are kept apart from validated ones (a calibrated policy).
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader, DefinitionList } from "@/components/ui/Card";
import { ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { count } from "@/lib/format";
import { api, keys } from "@/services/api";

type Health = "ok" | "warn" | "bad";

function Row({ name, state, detail }: { name: string; state: Health; detail: ReactNode }) {
  const icon = { ok: <CheckCircle2 aria-hidden className="size-4 text-ok" />, warn: <AlertTriangle aria-hidden className="size-4 text-warn" />, bad: <XCircle aria-hidden className="size-4 text-bad" /> }[state];
  const label = { ok: "Working", warn: "Degraded", bad: "Not working" }[state];
  return (
    <li className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5">
      <span className="mt-0.5">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{name} <span className="sr-only">: {label}</span></p>
        <p className="text-xs break-words text-ink-3">{detail}</p>
      </div>
      <Badge tone={state === "ok" ? "ok" : state === "warn" ? "warn" : "bad"}>{label}</Badge>
    </li>
  );
}

export function SystemPanel() {
  const readiness = useQuery({ queryKey: keys.readiness, queryFn: api.readiness, refetchInterval: 15_000, retry: false });
  const config = useQuery({ queryKey: keys.config, queryFn: api.config });
  const video = useQuery({ queryKey: keys.videoLimits, queryFn: api.videoLimits });
  const overview = useQuery({ queryKey: keys.overview, queryFn: api.overview });

  if (readiness.isLoading || config.isLoading) return <Skeleton className="h-72 w-full" />;
  if (readiness.isError || config.isError || !readiness.data || !config.data) {
    return <ErrorState error={readiness.error ?? config.error} onRetry={() => { void readiness.refetch(); void config.refetch(); }} title="System status could not be loaded" />;
  }

  const c = readiness.data.components;
  const embeddingError = c.embedding_model.ok ? null : String(c.embedding_model.error ?? "The embedding model is not loaded.");
  const detectorError = c.detector.ok ? null : String(c.detector.error ?? "The person detector is not loaded.");
  const device = c.device as { type?: string; name?: string; torch?: string };
  const lim = config.data.limits;
  const datasets = overview.data?.datasets ?? [];

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card aria-labelledby="health-title" className="lg:col-span-2">
        <CardHeader id="health-title" title="System health" description="Read live from the backend every 15 seconds." action={<Badge tone={readiness.data.status === "ready" ? "ok" : readiness.data.status === "degraded" ? "warn" : "bad"}>{readiness.data.status.replace("_", " ")}</Badge>} />
        <CardBody>
          <ul className="divide-y divide-line">
            <Row name="Database" state={c.database.ok ? "ok" : "bad"} detail={c.database.ok ? "Answers queries; identities, policies and experiments are stored here." : "The database did not answer."} />
            <Row name="Embedding model" state={c.embedding_model.ok ? "ok" : "bad"} detail={c.embedding_model.ok ? `${String(c.embedding_model.architecture)} · ${String(c.embedding_model.embedding_dim)}-dimension embeddings · weights ${c.embedding_model.weights_verified_against_pinned_hash ? "verified against the pinned checksum" : "custom checkpoint"}` : embeddingError} />
            <Row name="Person detector" state={c.detector.ok ? "ok" : "warn"} detail={c.detector.ok ? `${String(c.detector.display_name ?? c.detector.name)} · minimum confidence ${String(c.detector.score_threshold)}` : `${detectorError} Crop mode still works; Video Explorer needs the detector.`} />
            <Row name="Face models" state={c.face_models?.ok ? "ok" : "warn"} detail={c.face_models?.ok ? `${String(c.face_models.display_name)} · ${String(c.face_models.embedding_dim)}-number face fingerprints · weights verified against the OpenCV model zoo's published SHA-256` : `${String(c.face_models?.error ?? "Not loaded.")} Matching uses the body only until they are loaded.`} />
            <Row name="Gallery index" state="ok" detail={`Version ${c.gallery_index.version}: ${count(c.gallery_index.identities)} identities, ${count(c.gallery_index.images)} reference images in memory.`} />
            <Row name="Inference device" state={device.type && device.type !== "unavailable" ? "ok" : "bad"} detail={device.type ? `${device.type === "cuda" ? `GPU (${device.name ?? "CUDA"})` : "CPU"}${device.torch ? ` · torch ${device.torch}` : ""}. CUDA is optional; everything runs on a CPU.` : "No device was selected."} />
          </ul>
          {(embeddingError || detectorError) && (
            <Notice tone="bad" title="Dependency or weight-loading problem" className="mt-3">
              {[embeddingError && `Embedding model: ${embeddingError}`, detectorError && `Detector: ${detectorError}`].filter(Boolean).join(" ")} Fix it by running <code className="font-mono text-xs">scripts\download_weights.py</code>, then restart the server.
            </Notice>
          )}
          {readiness.data.notes.map((n) => <p key={n} className="mt-2 text-xs text-ink-3">{n}</p>)}
        </CardBody>
      </Card>

      <Card aria-labelledby="runtime-title">
        <CardHeader id="runtime-title" title="Runtime configuration" description="Limits the server enforces. Change them in .env, then restart." />
        <CardBody>
          <DefinitionList items={[
            { term: "Image upload", value: `up to ${lim.max_upload_mb} MB · longest side ${count(lim.max_image_side)} px · ${lim.allowed_extensions.join(", ")}` },
            { term: "Enrollment", value: `up to ${lim.max_enroll_files} images per request` },
            { term: "Video upload", value: video.data ? `up to ${video.data.max_megabytes} MB · ${video.data.max_seconds} s long · ${video.data.max_frames} sampled frames · ${video.data.extensions.join(", ")}` : "—" },
            { term: "Query previews kept", value: config.data.retention.query_retention_hours === 0 ? "Never stored" : `${config.data.retention.query_retention_hours} hours` },
            { term: "History kept", value: `${config.data.retention.history_retention_days} days (scores only, no images)` },
            { term: "Access keys", value: config.data.auth.required ? "Required" : "Off (single-user local demo)" },
            { term: "Flip augmentation", value: config.data.model.flip_tta ? "On (experimental setting)" : "Off" },
          ]} />
        </CardBody>
      </Card>

      <Card aria-labelledby="data-title">
        <CardHeader id="data-title" title="Datasets" description="Evaluation datasets are read from the project's datasets/ folder (never uploaded through the browser)." />
        <CardBody className="space-y-3">
          {datasets.length === 0 ? (
            <Notice tone="info" title="No dataset installed">Place a dataset in <code className="font-mono text-xs">datasets/&lt;name&gt;</code> (for example Market-1501) to enable the Evaluation Lab and the Lookalike Failure Lab. See the README, “Dataset acquisition”.</Notice>
          ) : (
            <ul className="space-y-2.5">
              {datasets.map((d) => (
                <li key={d.name} className="text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-xs font-semibold">datasets/{d.name}</span>
                    {d.kind === "benchmark" ? <Badge tone="ok">Benchmark</Badge> : <Badge tone="warn">Smoke test only</Badge>}
                  </div>
                  <p className="text-xs text-ink-3">{d.available ? `${count(d.identities)} identities · ${count(d.images)} images · layout ${d.layout}` : d.problems.join(" ")}</p>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card aria-labelledby="split-title" className="lg:col-span-2">
        <CardHeader id="split-title" title="Validated versus experimental" />
        <CardBody className="grid gap-3 md:grid-cols-2">
          <div className="rounded-md border border-line p-3">
            <p className="text-sm font-semibold">Validated</p>
            <p className="mt-1 text-xs text-ink-3">A decision policy marked <b>calibrated</b>: its threshold was selected on held-out calibration people for a stated target, and the run that produced it is linked. Pretrained weights are checked against a pinned SHA-256.</p>
          </div>
          <div className="rounded-md border border-line p-3">
            <p className="text-sm font-semibold">Experimental</p>
            <p className="mt-1 text-xs text-ink-3">Anything set by hand (a typed threshold, a margin rule), flip augmentation, a fine-tuned checkpoint that has not been evaluated, and everything in the Threshold sandbox. These never overwrite the validated policy. Change rules on the <Link className="underline" to="/settings?tab=model">Model &amp; thresholds</Link> tab; try values safely in the Evaluation Lab.</p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
