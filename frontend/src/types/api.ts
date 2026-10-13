/**
 * Shapes of the data the backend sends.
 *
 * In plain words: these TypeScript types mirror the backend's response schemas
 * (backend/app/schemas). If a field is renamed on the server, the compiler tells
 * us here which screens must change.
 */

export type Outcome = "accepted" | "unknown" | "review_required" | "processing_error";
export type Role = "viewer" | "operator" | "admin";
export type PolicyStatus = "unvalidated" | "experimental" | "calibrated";
export type EmbeddingStatus = "ready" | "stale" | "failed" | "mixed";

// ------------------------------------------------------------- re-identification
export interface Quality {
  usable: boolean;
  flags: string[];
  blocking_reason: string | null;
  metrics: Record<string, number>;
}

export interface Detection {
  index: number;
  /** [x1, y1, x2, y2] in pixels of the uploaded image */
  box: number[];
  /** Detector confidence. NOT an identity-match score. */
  detector_score: number;
  quality: Quality;
}

export interface DetectResponse {
  request_id: string;
  image: { width: number; height: number };
  detector: string;
  detections: Detection[];
  timings_ms: Record<string, number>;
}

export interface Candidate {
  rank: number;
  reference_id: string;
  label: string | null;
  /** Cosine similarity (-1..1): a retrieval score, not a probability. */
  score: number;
  n_images: number | null;
  image_url: string | null;
  /** Which fingerprint produced `score`: the face or the whole body. */
  basis: "face" | "body";
  /** Face similarity to this person's best reference face (null = not compared). */
  face_score: number | null;
  /** Whole-body similarity to this person's best reference image. */
  body_score: number | null;
  /** [x1, y1, x2, y2] of the matched face inside the reference picture (null when no face is on file). */
  face_box: number[] | null;
}

export type FaceStatus = "not_used" | "no_face" | "unusable" | "usable";
export type MatchingMode = "body" | "face_body";

export interface FaceObservation {
  status: FaceStatus;
  /** [x1, y1, x2, y2] of the face in the uploaded image's pixels. */
  box: number[] | null;
  detector_score: number | null;
  face_px: number | null;
  flags: string[];
  message: string | null;
}

/** One supporting cue (hair, skin tone, clothing) of the query next to the closest reference. Never decides anything. */
export interface CueRow {
  cue: string;
  title: string;
  query_rgb: number[];
  query_label: string;
  reference_rgb: number[];
  reference_label: string;
  delta_e: number;
  verdict: "similar" | "different";
}

export interface Decision {
  outcome: Outcome;
  reason_code: string;
  reason: string;
  accepted_reference_id: string | null;
  top1_reference_id: string | null;
  top1_score: number | null;
  top2_score: number | null;
  margin: number | null;
  accept_threshold: number | null;
  min_margin: number | null;
  calibrated_confidence: number | null;
  policy_version: number;
  policy_status: string;
  quality_flags: string[];
  /** body = clothing and build only; face_body = the face decides when a usable face is visible. */
  matching_mode: MatchingMode;
  /** Which evidence `top1_score` and `accept_threshold` belong to. */
  basis: "face" | "body";
  face_status: string | null;
  top1_face_score: number | null;
  top1_body_score: number | null;
  face_threshold: number | null;
  body_threshold: number | null;
}

export interface PersonResult {
  index: number;
  box: number[] | null;
  detector_score: number | null;
  quality: Quality | null;
  decision: Decision;
  candidates: Candidate[];
  crop_url: string | null;
  face: FaceObservation | null;
  cues: CueRow[];
}

export interface PredictResponse {
  request_id: string;
  created_at: string;
  mode: "crop" | "box" | "all";
  image: { width: number; height: number };
  model: { name: string; architecture: string; embedding_dim: number; fingerprint: string; device: string };
  face_model: string | null;
  matching_mode: MatchingMode;
  policy_version: number;
  policy_status: string;
  people: PersonResult[];
  timings_ms: Record<string, number>;
  notes: string[];
}

export interface HistoryItem {
  request_id: string;
  created_at: string;
  mode: string;
  n_people: number;
  outcomes: Record<string, number>;
  top_outcome: Outcome;
  best_score: number | null;
  policy_version: number;
  model_name: string;
  total_ms: number;
}

export interface HistoryPage {
  items: HistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface HistoryDetail {
  request_id: string;
  created_at: string;
  mode: string;
  image: { width: number; height: number };
  model_name: string;
  policy_version: number;
  people: PersonResult[];
  timings_ms: Record<string, number>;
}

// ----------------------------------------------------------------------- gallery
export interface GalleryImage {
  image_uid: string;
  width: number;
  height: number;
  created_at: string;
  embedding_status: EmbeddingStatus;
  quality_flags: string[];
  url: string;
  /** ready = usable face on file; weak = a face was found but is unusable; no_face; stale; failed; not_analysed. */
  face_status: "ready" | "weak" | "no_face" | "stale" | "failed" | "not_analysed";
  face_note: string | null;
  face_box: number[] | null;
}

export interface IdentitySummary {
  reference_id: string;
  label: string | null;
  n_images: number;
  created_at: string;
  updated_at: string;
  embedding_status: EmbeddingStatus;
  thumbnail_url: string | null;
  /** Reference images with a usable face on file. */
  n_faces: number;
}

export interface IdentityDetail extends IdentitySummary {
  consent_confirmed: boolean;
  images: GalleryImage[];
}

export interface GallerySummary {
  identities: number;
  images: number;
  embeddings_ready: number;
  embeddings_stale: number;
  embeddings_failed: number;
  index_version: number;
  index_identities: number;
  index_images: number;
  embedding_model: string | null;
  faces_usable: number;
  faces_without_usable_face: number;
  faces_not_analysed: number;
  face_model: string | null;
  strategy: string;
}

export interface GalleryPage {
  items: IdentitySummary[];
  total: number;
  limit: number;
  offset: number;
  summary: GallerySummary;
}

export interface EnrollResponse {
  identity: IdentityDetail;
  files: { filename: string; status: "enrolled" | "rejected"; reason: string | null; image_uid: string | null; face_status: string | null; face_note: string | null }[];
  warnings: string[];
}

export interface MutationResult {
  ok: boolean;
  message: string;
  detail: Record<string, unknown>;
}

// ----------------------------------------------------------- configuration / model
export interface Policy {
  version: number;
  accept_threshold: number;
  min_margin: number | null;
  margin_action: "review" | "reject";
  review_on_quality_flags: boolean;
  /** body = the PS-1 baseline (clothing and build); face_body = face first, body as support. */
  matching_mode: MatchingMode;
  face_accept_threshold: number | null;
  face_review_band: number | null;
  body_only_action: "review" | "accept" | null;
  /** False: face_body falls back to body evidence until the face models are downloaded. */
  face_models_loaded: boolean;
  status: PolicyStatus;
  status_explanation: string;
  calibration_run_id: string | null;
  has_confidence_model: boolean;
  model_fingerprint: string | null;
  model_matches_current: boolean | null;
  note: string;
  created_by: string;
  created_at: string;
  is_active: boolean;
}

export interface ConfigResponse {
  policy: Policy;
  limits: {
    max_upload_mb: number;
    max_image_side: number;
    allowed_extensions: string[];
    max_enroll_files: number;
    detector_score_threshold: number;
  };
  retention: { query_retention_hours: number; history_retention_days: number; reference_images: string };
  auth: { required: boolean; roles: string[] };
  model: { embedding: Record<string, unknown>; face?: FaceModelStatus; flip_tta: boolean };
  evaluation_defaults: { bootstrap_samples: number };
}

export type FaceModelStatus = Record<string, unknown> & {
  ready: boolean;
  enabled: boolean;
  error?: string;
  enrolled_faces: number;
  identities_with_a_face: number;
};

export interface ModelStatus {
  embedding: Record<string, unknown> & { ready: boolean; error?: string };
  detector: Record<string, unknown> & { ready: boolean; error?: string };
  device: Record<string, unknown>;
  gallery_index: { version: number; identities: number; images: number };
  face: FaceModelStatus;
}

export interface Readiness {
  status: "ready" | "degraded" | "not_ready";
  components: {
    database: { ok: boolean };
    embedding_model: { ok: boolean; error?: string } & Record<string, unknown>;
    detector: { ok: boolean; error?: string } & Record<string, unknown>;
    gallery_index: { version: number; identities: number; images: number };
    face_models: { ok: boolean; enabled: boolean; error?: string } & Record<string, unknown>;
    device: Record<string, unknown>;
    auth: { required: boolean };
  };
  notes: string[];
}

export interface AuditEntry {
  at: string;
  role: string;
  action: string;
  subject: string | null;
  detail: Record<string, unknown>;
}

// -------------------------------------------------------------------- evaluation
export interface DatasetInfo {
  name: string;
  layout: string;
  kind: "benchmark" | "smoke_test" | string;
  description: string;
  license_note: string;
  identities: number;
  images: number;
  cameras: number;
  available: boolean;
  problems: string[];
}

export interface Checkpoint {
  name: string;
  dataset: string | null;
  /** The protocol seed it was trained for: evaluate it with this seed only. */
  seed: number | null;
  trained_people: number | null;
  training_images: number | null;
  /** Always false until an evaluation on held-out people has been run. */
  validated: boolean;
  size_mb: number;
  modified: string;
}

/** evaluation + calibration: Evaluation Lab. lookalike: Lookalike Failure Lab. video: Video Explorer. */
export type RunKind = "evaluation" | "calibration" | "lookalike" | "video";

export interface RunSummary {
  run_id: string;
  kind: RunKind;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  stage: string;
  progress: number;
  dataset: string;
  dataset_kind: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  headline: Record<string, unknown> | null;
  error: string | null;
}

export interface RunDetail extends RunSummary {
  config: Record<string, unknown>;
  result: EvaluationResult | CalibrationResult | LookalikeResult | VideoResult | null;
  cancel_requested: boolean;
}

export interface RunsPage {
  items: RunSummary[];
  total: number;
}

/** A metric with its mean and standard deviation across seeds (null when undefined). */
export interface Stat {
  mean: number | null;
  std: number | null;
  n_seeds: number;
}

export interface OperatingPoint {
  threshold: number;
  min_margin: number | null;
  /** One-sided 95% upper confidence bound of the FAR (only where the backend computed it). */
  far_upper_bound_95?: number | null;
  counts: {
    known_queries: number;
    unknown_queries: number;
    known_accepted: number;
    known_accepted_correct: number;
    known_accepted_wrong_identity: number;
    unknown_accepted: number;
  };
  far: number | null;
  tar: number | null;
  frr: number | null;
  dir_at_rank: Record<string, number | null>;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  confidence_intervals?: Record<string, { low: number; high: number; level: number } | null> | null;
}

export interface SelectedPoint {
  target: Record<string, unknown>;
  target_achieved: boolean;
  threshold: number | null;
  min_margin: number | null;
  calibration: OperatingPoint;
  far_upper_bound_95: number | null;
  n_unknown: number;
  n_known: number;
  sample_size_adequate: boolean;
  notes: string[];
}

export interface Curve {
  far: number[];
  tar: number[];
  dir1: number[];
  threshold: (number | null)[];
}

export interface ScoreHistogram {
  bin_edges: number[];
  known_correct: number[];
  known_wrong: number[];
  unknown: number[];
}

export interface VariantSeedResult {
  variant: string;
  seed: number;
  status: string;
  reason?: string;
  selected: SelectedPoint | null;
  test: OperatingPoint;
  curve?: Curve;
  auroc?: number;
  auoscr?: number;
  curve_operating_points?: { target_far: number; recall: number; achieved_far: number; threshold: number | null; dir1: number }[];
  closed_set: { rank1: number | null; rank5: number | null; cmc: number[]; mAP: number | null; queries_used: number; dropped_same_camera_only: number };
  hard_subset: {
    test: OperatingPoint;
    hard_aware_calibration?: { selected: SelectedPoint; test: OperatingPoint | null; note: string };
  };
  score_histogram: ScoreHistogram;
  score_scale?: string;
  confidence_model?: { quality_on_test: { ece: number; brier: number; n: number; bins: { bin_low: number; bin_high: number; n: number; mean_predicted: number; observed_rate: number }[] }; meaning: string };
}

/** Headline metrics of one variant, averaged over seeds (see backend/app/evaluation/ablation.py). */
export interface VariantSummary {
  far: Stat;
  tar: Stat;
  dir1: Stat;
  precision: Stat;
  f1: Stat;
  auroc: Stat;
  auoscr: Stat;
  rank1: Stat;
  rank5: Stat;
  mAP: Stat;
  hard_far: Stat;
  hard_dir1: Stat;
  calibration_far: Stat;
  calibration_dir1: Stat;
  threshold: Stat;
  min_margin: Stat;
  /** In how many seeds the requested operating point was reached on the calibration split. */
  targets_achieved: number;
  n_seeds_total: number;
}

export interface VariantResult {
  label: string;
  description: string;
  parent: string | null;
  status: string;
  reason: string | null;
  per_seed: VariantSeedResult[];
  summary: VariantSummary | null;
}

export interface LatencyStats {
  n: number;
  mean?: number;
  p50?: number;
  p95?: number;
  p99?: number;
  min?: number;
  max?: number;
}

export interface EvaluationResult {
  kind: "evaluation";
  metadata: {
    started_at: string;
    duration_seconds: number;
    request: Record<string, unknown> & { seeds: number[] };
    dataset: DatasetInfo;
    is_benchmark: boolean;
    model: Record<string, unknown>;
    protocol: Record<string, { calibration: Record<string, number>; test: Record<string, number>; hard_subset?: Record<string, unknown> }>;
    software: Record<string, unknown>;
    operating_target: string;
  };
  performance: {
    embedding?: { single_crop_ms: LatencyStats; batch: { batch_size: number; ms_per_crop: number; throughput_crops_per_second: number } };
    retrieval_ms_per_query: number;
    retrieval_gallery_images: number;
    model_load_seconds: number;
    warmup_seconds: number;
    peak_memory_mb: number | null;
    device: string;
    note: string;
  };
  variants: Record<string, VariantResult>;
  selected_variant: { key: string | null; selected_on: string; criterion?: string; reason?: string; calibration_far?: number; calibration_recall?: number };
  /** True when the run kept the per-query table that the threshold sandbox needs. */
  sandbox_available?: boolean;
  warnings: string[];
}

export interface CalibrationResult {
  kind: "calibration";
  metadata: { dataset: DatasetInfo; is_benchmark: boolean; split_used: string; operating_target: string; started_at: string };
  proposed_policy: { accept_threshold: number | null; min_margin: number | null; margin_action: string; status: PolicyStatus };
  selected: SelectedPoint;
  score_histogram: ScoreHistogram;
  confidence_model: Record<string, unknown> | null;
  model_fingerprint: string;
  warnings: string[];
}

// ------------------------------------------------------------ Lookalike Failure Lab
/** What the matcher did with one pair of photos: a different-person pair it accepted is a false accept. */
export type PairDecision = "false_accept" | "correct_reject";

export interface LabPair {
  rank: number;
  comparison_type: "different_identities";
  split: string;
  identity_a: string;
  identity_b: string;
  /** Similarity of the most alike pair of photos of these two people (baseline model). */
  similarity: number;
  by_model: Record<string, { similarity: number; decision: PairDecision }>;
  image_a: string;
  image_b: string;
  camera_a: number | null;
  camera_b: number | null;
  /** Clothing-colour similarity (a label-free proxy) - independent of the model similarity above. */
  clothing_colour_similarity: number;
  similar_clothing_proxy: boolean;
  comparisons_in_challenge_set: number;
}

export interface HardGenuinePair {
  comparison_type: "same_identity";
  identity: string;
  similarity: number;
  decision: "false_reject" | "correct_accept";
  image_a: string;
  image_b: string;
  camera_a: number | null;
  camera_b: number | null;
}

export interface PairCurvePoint {
  threshold: number;
  far: number;
  tar: number;
}

export interface ChallengeMeasurement {
  threshold: number;
  genuine_pairs: number;
  impostor_pairs: number;
  true_accepts: number;
  false_rejects: number;
  false_accepts: number;
  true_rejects: number;
  tar: number | null;
  far_on_challenge_set: number | null;
  far_on_challenge_set_upper_bound_95: number | null;
  far_all_pairs_reference: number | null;
  all_pairs_compared: number;
  note: string;
  curve: PairCurvePoint[];
  hardest_genuine_pairs: HardGenuinePair[];
}

export interface LabModelOk {
  status: "ok";
  label: string;
  embedding_source: string;
  calibration: SelectedPoint;
  rule: { threshold: number; min_margin: number | null; margin_action: string };
  test_query_level: OperatingPoint;
  challenge: ChallengeMeasurement;
  model?: Record<string, unknown>;
  latency?: { single_crop_ms?: LatencyStats; batch?: { batch_size: number; ms_per_crop: number; throughput_crops_per_second: number } };
}

export interface LabModelUnavailable {
  status: "unavailable";
  reason: string;
}

export type FailureCategory = "incorrect_acceptance" | "wrong_identity_accepted" | "genuine_rejected";

export interface PossibleCause {
  cause: string;
  text: string;
  evidence: string;
  /** Always "hypothesis - not proven": these are ideas to check, never conclusions. */
  status: string;
}

export interface LabFailure {
  id: string;
  category: FailureCategory;
  category_label: string;
  query: { ref: string; identity: string; camera: number | null; is_known: boolean };
  matched: { identity: string; ref: string | null; camera: number | null };
  observed: {
    outcome: Outcome;
    top1_score: number;
    threshold: number;
    score_minus_threshold: number;
    margin: number | null;
    min_margin: number | null;
    true_identity_rank: number | null;
    true_identity_score: number | null;
    quality_flags: string[];
    sharpness: number;
    clothing_colour_similarity: number | null;
  };
  possible_causes: PossibleCause[];
}

export interface LabFailures {
  counts: Record<"incorrect_acceptance" | "wrong_identity_accepted" | "genuine_rejected" | "queries" | "genuine_sent_to_review" | "strangers_sent_to_review", number>;
  listed: LabFailure[];
  rule: { threshold: number; min_margin: number | null; margin_action: string };
  note: string;
}

export interface LabComparisonRow {
  model: string;
  label: string;
  threshold: number;
  test_far: number | null;
  test_recall_dir1: number | null;
  test_unknown_accepted: number;
  test_unknown_queries: number;
  challenge_far: number | null;
  challenge_tar: number | null;
  challenge_false_accepts: number;
  challenge_impostor_pairs: number;
  single_crop_ms_p50: number | null;
}

export interface LookalikeResult {
  kind: "lookalike";
  metadata: {
    experiment_id: string;
    started_at: string;
    duration_seconds: number;
    request: Record<string, unknown> & { mining_split: string; seed: number };
    dataset: DatasetInfo;
    is_benchmark: boolean;
    operating_target: string;
    protocol: Record<string, unknown>;
    software: Record<string, unknown>;
    reproducibility: string;
  };
  challenge_set: {
    definition: Record<string, string | number>;
    counts: { identity_pairs: number; impostor_comparisons: number; genuine_comparisons: number; all_pairs_compared: number };
    identity_pairs: LabPair[];
  };
  models: { baseline: LabModelOk; improved: LabModelOk | LabModelUnavailable };
  comparison: LabComparisonRow[] | null;
  failures: Record<string, LabFailures>;
  /** True when the threshold sandbox can be opened for this run (the table itself is served separately). */
  sandbox_available: boolean;
  limitations: string[];
  warnings: string[];
}

// ----------------------------------------------------------------- threshold sandbox
export interface SandboxInfo {
  run_id: string;
  kind: RunKind;
  dataset: string;
  reference: { variant: string; label: string; threshold: number; min_margin: number | null; margin_action: string; target_achieved: boolean; chosen_on: string };
  embedding_source: string;
  model_fingerprint: string | null;
  splits: Record<string, number>;
  score_range: { min: number; max: number };
  is_benchmark: boolean;
  writes_policy: false;
  explanation: string;
}

export interface SandboxSummary {
  rule: { threshold: number; min_margin: number | null; margin_action: string };
  metrics: OperatingPoint;
  confusion: {
    true_accepts: number;
    wrong_identity_accepts: number;
    false_accepts: number;
    false_rejects: number;
    true_rejects: number;
    known_sent_to_review: number;
    unknown_sent_to_review: number;
    definitions: Record<string, string>;
  };
  outcome_counts: Record<string, number>;
}

export interface SandboxChange {
  ref: string;
  query_identity: string;
  is_known: boolean;
  top1_identity: string;
  top1_correct: boolean;
  top1_score: number;
  margin: number | null;
  calibrated_rule: string;
  trial_rule: string;
}

export interface SandboxResult {
  run_id: string;
  split: "calibration" | "test";
  n_queries: number;
  trial: SandboxSummary;
  calibrated_rule: SandboxSummary;
  decisions_changed: number;
  changed_examples: SandboxChange[];
  writes_policy: false;
  warning: string | null;
  is_benchmark: boolean;
}

// ---------------------------------------------------------------------- Video Explorer
export interface VideoPerson {
  index: number;
  box: number[];
  detector_score: number;
  usable: boolean;
  quality_flags: string[];
  blocking_reason: string | null;
  outcome: Outcome;
  reason_code: string;
  reason: string;
  accepted_reference_id?: string | null;
  top1_reference_id?: string | null;
  top1_score?: number | null;
  top2_score?: number | null;
  margin?: number | null;
  calibrated_confidence?: number | null;
  /** Present when face matching was on: what the face analysis saw, and which evidence decided. */
  face_status?: string;
  face_box?: number[] | null;
  face_flags?: string[];
  basis?: "face" | "body";
  top1_face_score?: number | null;
  top1_body_score?: number | null;
  accept_threshold?: number;
}

export interface VideoFrame {
  index: number;
  frame_number: number;
  time_seconds: number;
  width: number;
  height: number;
  /** null when previews are not stored (retention 0) or have expired. */
  thumbnail: string | null;
  people: VideoPerson[];
  timings_ms: { decode_ms: number; detect_ms: number; embed_ms: number; face_ms?: number; match_ms: number; processing_ms: number };
}

export interface VideoResult {
  kind: "video";
  metadata: {
    original_name: string;
    video: { width: number; height: number; fps: number; frame_count: number | null; duration_seconds: number | null; container: string };
    sampling: { every_seconds: number; max_frames: number; every_n_frames: number; assumed_fps: number | null; frames_processed: number };
    policy: { version: number; status: PolicyStatus; accept_threshold: number; min_margin: number | null; matching_mode?: MatchingMode; face_accept_threshold?: number | null };
    model: { name: string; fingerprint: string; device: string };
    face_model?: string | null;
    detector: string | null;
    thumbnails_kept: boolean;
    retention_hours: number;
    generated_at: string;
  };
  frames: VideoFrame[];
  summary: {
    frames_processed: number;
    people_detected: number;
    outcomes: Record<string, number>;
    identities_seen: { reference_id: string; label: string | null; frames: number; first_seen_seconds: number; last_seen_seconds: number; best_score: number }[];
    latency_ms: { processing_per_frame: LatencyStats; note: string };
    wall_seconds: number;
    frames_per_second_processed: number | null;
  };
  notes: string[];
}

export interface VideoLimits {
  max_megabytes: number;
  max_seconds: number;
  max_frames: number;
  max_frame_side: number;
  extensions: string[];
  detector_ready: boolean;
  embedding_ready: boolean;
  frame_previews_kept_hours: number;
  scope: string;
}

// ----------------------------------------------------------------------- overview
export interface Overview {
  gallery: { identities: number; images: number };
  inference: {
    requests: number;
    people_processed: number;
    outcomes: Record<string, number>;
    unknown_or_rejected: number;
    acceptance_rate: number | null;
    acceptance_rate_definition: string;
    average_latency_ms: number | null;
    latency_window: string;
  };
  latest_evaluation: {
    benchmark_available: boolean;
    far: number | null;
    recall: number | null;
    run_id: string | null;
    dataset: string | null;
    note: string | null;
    definition: string;
  };
  policy: {
    version: number; status: PolicyStatus; accept_threshold: number; min_margin: number | null;
    matching_mode?: MatchingMode; face_accept_threshold?: number | null; face_matching_active?: boolean;
  };
  readiness: { embedding_model: boolean; detector: boolean; face_models?: boolean };
  datasets: DatasetInfo[];
  recent_requests: { request_id: string; created_at: string; n_people: number; total_ms: number; outcomes: Outcome[] }[];
  recent_runs: RunSummary[];
}

// ----------------------------------------------------------------------- built-in example (open-set analysis)
export interface DemoRules {
  matching_mode: string;
  face_threshold: number;
  face_review_band: number;
  body_threshold: number;
  policy_version: number;
  policy_status: string;
  face_models_loaded: boolean;
}
export interface DemoGroup { id: string; title: string; blurb: string }
export interface DemoPhoto { name: string; url: string; face_status: string | null; face_note: string | null }
export interface DemoPerson { id: string; label: string; note: string; photos: DemoPhoto[]; n_faces: number }
export interface DemoExpect { kind: "match" | "unknown" | "review"; person: string | null; person_label: string | null; text: string }
export interface DemoCase { id: string; group: string; title: string; story: string; image_url: string; expect: DemoExpect }
export interface DemoInfo {
  available: boolean;
  reason: string | null;
  title: string;
  intro: string;
  groups: DemoGroup[];
  people: DemoPerson[];
  cases: DemoCase[];
  rules: DemoRules | null;
  disclaimer: string;
}
export interface DemoPrepared { people: DemoPerson[]; rules: DemoRules; built_ms: number }
/** Was this decision right? (`review` = sent to a person; `cautious` = not accepted although a person should have looked.) */
export type DemoVerdict = "correct" | "review" | "cautious" | "false_accept" | "wrong_person" | "missed" | "risky";
export interface DemoCandidate { person: string; label: string; score: number; basis: string; face_score: number | null; body_score: number | null }
export interface DemoDecision {
  outcome: Outcome;
  accepted_person: string | null;
  accepted_label: string | null;
  top1_person: string | null;
  top1_label: string | null;
  top1_score: number | null;
  /** Face similarity to the closest enrolled face (null = no usable face was compared). */
  face_score: number | null;
  /** Clothing-and-build similarity to the closest enrolled person. */
  body_score: number | null;
  basis: string;
  threshold: number | null;
  reason: string;
  verdict: DemoVerdict;
  candidates: DemoCandidate[];
}
export interface DemoCaseResult {
  case_id: string;
  face: FaceObservation | null;
  face_body: DemoDecision;
  clothes_only: DemoDecision;
  timings_ms: Record<string, number>;
}