/**
 * Typed functions for every backend endpoint the interface uses.
 *
 * In plain words: screens call ``api.gallery(...)`` instead of building URLs by hand.
 * Keeping the list in one file means "which endpoints does the UI use?" has a
 * one-glance answer.
 */
import type {
  AuditEntry,
  Checkpoint,
  ConfigResponse,
  DatasetInfo,
  DemoCaseResult,
  DemoInfo,
  DemoPrepared,
  DetectResponse,
  EnrollResponse,
  GalleryPage,
  HistoryDetail,
  HistoryPage,
  IdentityDetail,
  ModelStatus,
  MutationResult,
  Outcome,
  Overview,
  Policy,
  PredictResponse,
  Readiness,
  Role,
  RunDetail,
  RunsPage,
  SandboxInfo,
  SandboxResult,
  VideoLimits,
} from "@/types/api";
import { request, requestBlob } from "./http";

export interface GalleryQuery {
  search?: string;
  sort?: "reference_id" | "created_at" | "updated_at" | "n_images";
  order?: "asc" | "desc";
  embedding_status?: string;
  limit?: number;
  offset?: number;
}

export interface PredictOptions {
  mode: "crop" | "box" | "all";
  box?: number[];
  topK?: number;
}

export interface ThresholdBody {
  accept_threshold?: number;
  min_margin?: number | null;
  margin_action?: "review" | "reject";
  review_on_quality_flags?: boolean;
  /** Omit to keep the current mode. */
  matching_mode?: "body" | "face_body";
  face_accept_threshold?: number;
  face_review_band?: number;
  body_only_action?: "review" | "accept";
  from_calibration_run_id?: string;
  note?: string;
  confirm: boolean;
}

export interface EvaluationBody {
  dataset: string;
  seeds: number[];
  target: { mode: "fixed_recall" | "fixed_far"; target_recall: number; target_far: number; recall_metric: "dir1" | "tar" };
  protocol: {
    gallery_shots: number;
    dev_fraction: number;
    calibration_fraction: number;
    max_identities_per_split: number | null;
    max_images_per_identity: number | null;
    cross_camera: boolean;
  };
  variants?: string[] | null;
  bootstrap_samples: number;
  /** File name of a fine-tuned checkpoint (from /api/evaluation/checkpoints); never a path. */
  finetuned_checkpoint?: string | null;
}

export type CalibrationBody = Pick<EvaluationBody, "dataset" | "target" | "protocol"> & { seed: number; use_margin: boolean };

/** Settings of a Lookalike Failure Lab experiment. */
export interface LookalikeBody extends Pick<EvaluationBody, "dataset" | "target" | "protocol"> {
  seed: number;
  mining_split: "dev" | "calibration" | "test";
  top_pairs: number;
  images_per_pair: number;
  max_genuine_pairs: number;
  max_failures: number;
  use_margin: boolean;
  finetuned_checkpoint?: string | null;
}

/** A trial decision rule for the threshold sandbox. It never changes the live policy. */
export interface SandboxBody {
  split: "calibration" | "test";
  threshold: number;
  min_margin: number | null;
  margin_action: "review" | "reject";
}

export type LabExportFormat = "json" | "md" | "pairs_csv" | "failures_csv" | "summary_csv";

export const api = {
  // ---------------------------------------------------------------- status
  readiness: () => request<Readiness>("/api/readiness", { acceptStatus: [503] }),
  me: () => request<{ role: Role; auth_required: boolean }>("/api/auth/me"),
  overview: () => request<Overview>("/api/overview"),

  // ---------------------------------------------------------------- re-identification
  detect(image: File) {
    const form = new FormData();
    form.append("image", image);
    return request<DetectResponse>("/api/reid/detect", { method: "POST", form });
  },
  predict(image: File, options: PredictOptions) {
    const form = new FormData();
    form.append("image", image);
    form.append("mode", options.mode);
    if (options.box) form.append("box", options.box.join(","));
    form.append("top_k", String(options.topK ?? 5));
    return request<PredictResponse>("/api/reid/predict", { method: "POST", form });
  },
  history: (query: { limit?: number; offset?: number; outcome?: Outcome | "" }) =>
    request<HistoryPage>("/api/reid/history", { query }),
  historyItem: (requestId: string) => request<HistoryDetail>(`/api/reid/history/${requestId}`),

  // ---------------------------------------------------------------- gallery
  gallery: (query: GalleryQuery) => request<GalleryPage>("/api/gallery", { query: { ...query } }),
  identity: (referenceId: string) => request<IdentityDetail>(`/api/gallery/${encodeURIComponent(referenceId)}`),
  enroll(body: { referenceId: string; label?: string; files: File[]; imagesAreCrops: boolean; consent: boolean }) {
    const form = new FormData();
    form.append("reference_id", body.referenceId);
    if (body.label) form.append("label", body.label);
    form.append("consent_confirmed", String(body.consent));
    form.append("images_are_crops", String(body.imagesAreCrops));
    body.files.forEach((f) => form.append("images", f));
    return request<EnrollResponse>("/api/gallery/enroll", { method: "POST", form });
  },
  addImages(referenceId: string, files: File[], imagesAreCrops: boolean) {
    const form = new FormData();
    form.append("images_are_crops", String(imagesAreCrops));
    files.forEach((f) => form.append("images", f));
    return request<EnrollResponse>(`/api/gallery/${encodeURIComponent(referenceId)}/images`, { method: "POST", form });
  },
  deleteIdentity: (referenceId: string) =>
    request<MutationResult>(`/api/gallery/${encodeURIComponent(referenceId)}`, {
      method: "DELETE",
      query: { confirm: referenceId },
    }),
  rebuildGallery: () => request<MutationResult>("/api/gallery/rebuild", { method: "POST" }),
  analyseFaces: () => request<MutationResult>("/api/gallery/analyse-faces", { method: "POST" }),
  resetGallery: () => request<MutationResult>("/api/gallery/reset", { method: "POST", json: { confirm: "RESET DEMO GALLERY" } }),
  imageBlob: (url: string) => requestBlob(url),

  // ---------------------------------------------------------------- configuration
  config: () => request<ConfigResponse>("/api/config"),
  modelStatus: () => request<ModelStatus>("/api/model/status"),
  policyHistory: () => request<Policy[]>("/api/config/history"),
  updateThresholds: (body: ThresholdBody) => request<Policy>("/api/config/thresholds", { method: "POST", json: body }),
  audit: () => request<AuditEntry[]>("/api/audit"),
  cleanup: () => request<Record<string, number>>("/api/maintenance/cleanup", { method: "POST" }),

  // ---------------------------------------------------------------- evaluation
  datasets: () => request<DatasetInfo[]>("/api/evaluation/datasets"),
  checkpoints: () => request<Checkpoint[]>("/api/evaluation/checkpoints"),
  runs: (query: { kind?: string; limit?: number; offset?: number } = {}) => request<RunsPage>("/api/evaluation/runs", { query }),
  run: (runId: string) => request<RunDetail>(`/api/evaluation/runs/${runId}`),
  startEvaluation: (body: EvaluationBody) => request<RunDetail>("/api/evaluation/run", { method: "POST", json: body }),
  startCalibration: (body: CalibrationBody) => request<RunDetail>("/api/evaluation/calibrate", { method: "POST", json: body }),
  cancelRun: (runId: string) => request<RunDetail>(`/api/evaluation/runs/${runId}/cancel`, { method: "POST" }),
  reportBlob: (runId: string, format: "json" | "md" | "html") =>
    requestBlob(`/api/evaluation/runs/${runId}/report`, { format }),

  // ---------------------------------------------------------------- threshold sandbox
  sandboxInfo: (runId: string) => request<SandboxInfo>(`/api/evaluation/runs/${runId}/sandbox`),
  sandbox: (runId: string, body: SandboxBody) => request<SandboxResult>(`/api/evaluation/runs/${runId}/sandbox`, { method: "POST", json: body }),

  // ---------------------------------------------------------------- Lookalike Failure Lab
  labRuns: (query: { limit?: number; offset?: number } = {}) => request<RunsPage>("/api/lookalike/runs", { query }),
  labRun: (runId: string) => request<RunDetail>(`/api/lookalike/runs/${runId}`),
  startLab: (body: LookalikeBody) => request<RunDetail>("/api/lookalike/run", { method: "POST", json: body }),
  labExport: (runId: string, format: LabExportFormat) => requestBlob(`/api/lookalike/runs/${runId}/export`, { format }),
  /** URL (for AuthImage) of a dataset photo the experiment recorded. */
  labImageUrl: (runId: string, ref: string) => `/api/lookalike/runs/${runId}/image?ref=${encodeURIComponent(ref)}`,

  // ---------------------------------------------------------------- Video Explorer
  videoLimits: () => request<VideoLimits>("/api/video/limits"),
  analyzeVideo(video: File, options: { everySeconds: number; maxFrames: number }) {
    const form = new FormData();
    form.append("video", video);
    form.append("every_seconds", String(options.everySeconds));
    form.append("max_frames", String(options.maxFrames));
    return request<RunDetail>("/api/video/analyze", { method: "POST", form, timeoutMs: 10 * 60_000 }); // a big upload can take a while
  },
  videoJobs: (query: { limit?: number; offset?: number } = {}) => request<RunsPage>("/api/video/jobs", { query }),
  videoJob: (jobId: string) => request<RunDetail>(`/api/video/jobs/${jobId}`),
  cancelVideo: (jobId: string) => request<RunDetail>(`/api/video/jobs/${jobId}/cancel`, { method: "POST" }),
  deleteVideo: (jobId: string) => request<null>(`/api/video/jobs/${jobId}`, { method: "DELETE" }),
  videoFrameUrl: (jobId: string, index: number) => `/api/video/jobs/${jobId}/frames/${index}`,
  videoExport: (jobId: string, format: "json" | "frames_csv") => requestBlob(`/api/video/jobs/${jobId}/export`, { format }),

  // ---------------------------------------------------------------- built-in example (open-set analysis)
  demo: () => request<DemoInfo>("/api/demo"),
  /** Builds the private, in-memory example gallery. Saves nothing and never touches the real gallery. */
  demoPrepare: () => request<DemoPrepared>("/api/demo/prepare", { method: "POST", timeoutMs: 120_000 }),
  demoCase: (caseId: string) => request<DemoCaseResult>(`/api/demo/cases/${encodeURIComponent(caseId)}`, { method: "POST", timeoutMs: 120_000 }),
  demoForget: () => request<{ ok: boolean }>("/api/demo/sandbox", { method: "DELETE" }),

  // ---------------------------------------------------------------- decision records
  decisionRecord: (requestId: string, format: "json" | "csv") => requestBlob(`/api/reid/history/${requestId}/export`, { format }),
};

/** Query keys in one place so a screen can invalidate exactly what a mutation changed. */
export const keys = {
  readiness: ["readiness"] as const,
  me: ["me"] as const,
  overview: ["overview"] as const,
  config: ["config"] as const,
  modelStatus: ["model-status"] as const,
  policyHistory: ["policy-history"] as const,
  audit: ["audit"] as const,
  gallery: ["gallery"] as const,
  identity: (id: string) => ["identity", id] as const,
  history: ["history"] as const,
  historyItem: (id: string) => ["history", id] as const,
  datasets: ["datasets"] as const,
  checkpoints: ["checkpoints"] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["run", id] as const,
  labRuns: ["lab-runs"] as const,
  sandboxInfo: (id: string) => ["sandbox-info", id] as const,
  videoLimits: ["video-limits"] as const,
  videoJobs: ["video-jobs"] as const,
  videoJob: (id: string) => ["video-job", id] as const,
  demo: ["demo"] as const,
  demoRun: ["demo-run"] as const,
};
