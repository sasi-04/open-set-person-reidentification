/** Example backend responses, shaped like the real API (see backend/app/schemas). Used only by tests. */
import type {
  ConfigResponse,
  DemoCaseResult,
  DemoDecision,
  DemoInfo,
  DemoPrepared,
  EvaluationResult,
  GalleryPage,
  IdentitySummary,
  LabFailure,
  LabModelOk,
  LookalikeResult,
  Outcome,
  Overview,
  Policy,
  PredictResponse,
  Readiness,
  RunDetail,
  SandboxInfo,
  SandboxResult,
  SandboxSummary,
  VariantResult,
  VideoLimits,
  VideoResult,
} from "@/types/api";

export const policy = (over: Partial<Policy> = {}): Policy => ({
  version: 1, accept_threshold: 0.7, min_margin: null, margin_action: "review", review_on_quality_flags: true,
  matching_mode: "body", face_accept_threshold: null, face_review_band: null, body_only_action: null, face_models_loaded: true,
  status: "unvalidated", status_explanation: "A starting value nobody has checked. Run calibration before relying on it.",
  calibration_run_id: null, has_confidence_model: false, model_fingerprint: "osnet-abc-flip0", model_matches_current: true,
  note: "", created_by: "system", created_at: "2026-10-12T10:00:00Z", is_active: true, ...over,
});

export const readiness: Readiness = {
  status: "ready",
  components: {
    database: { ok: true },
    embedding_model: { ok: true, architecture: "OSNet-AIN x1.0", fingerprint: "osnet-abc-flip0" },
    detector: { ok: true, name: "fasterrcnn" },
    gallery_index: { version: 1, identities: 0, images: 0 },
    face_models: { ok: true, enabled: true, display_name: "YuNet detector + SFace recogniser", embedding_dim: 128 },
    device: { type: "cpu", name: "CPU" },
    auth: { required: true },
  },
  notes: [],
};

export const config = (over: Partial<ConfigResponse> = {}): ConfigResponse => ({
  policy: policy(),
  limits: { max_upload_mb: 10, max_image_side: 6000, allowed_extensions: [".jpg", ".jpeg", ".png"], max_enroll_files: 20, detector_score_threshold: 0.5 },
  retention: { query_retention_hours: 24, history_retention_days: 30, reference_images: "kept until the identity is deleted" },
  auth: { required: true, roles: ["viewer", "operator", "admin"] },
  model: { embedding: { fingerprint: "osnet-abc-flip0" }, flip_tta: false },
  evaluation_defaults: { bootstrap_samples: 300 },
  ...over,
});

export const identity = (ref: string, over: Partial<IdentitySummary> = {}): IdentitySummary => ({
  reference_id: ref, label: null, n_images: 3, created_at: "2026-10-01T10:00:00Z", updated_at: "2026-10-01T10:00:00Z",
  embedding_status: "ready", thumbnail_url: null, n_faces: 0, ...over,
});

export const galleryPage = (items: IdentitySummary[] = []): GalleryPage => ({
  items, total: items.length, limit: 24, offset: 0,
  summary: {
    identities: items.length, images: items.reduce((n, i) => n + i.n_images, 0), embeddings_ready: items.length * 3, embeddings_stale: 0,
    embeddings_failed: 0, index_version: 2, index_identities: items.length, index_images: items.length * 3, embedding_model: "osnet-abc-flip0",
    faces_usable: 0, faces_without_usable_face: 0, faces_not_analysed: 0, face_model: null,
    strategy: "Individual image embeddings per identity; an identity's score is its best-matching image.",
  },
});

export const overview = (over: Partial<Overview> = {}): Overview => ({
  gallery: { identities: 0, images: 0 },
  inference: {
    requests: 0, people_processed: 0, outcomes: {}, unknown_or_rejected: 0, acceptance_rate: null,
    acceptance_rate_definition: "accepted / decided people", average_latency_ms: null, latency_window: "last 200 requests",
  },
  latest_evaluation: { benchmark_available: false, far: null, recall: null, run_id: null, dataset: null, note: "Not evaluated.", definition: "Test-split FAR and DIR@1." },
  policy: { version: 1, status: "unvalidated", accept_threshold: 0.7, min_margin: null, matching_mode: "body", face_accept_threshold: null, face_matching_active: false },
  readiness: { embedding_model: true, detector: true, face_models: true },
  datasets: [], recent_requests: [], recent_runs: [],
  ...over,
});

export const predictResponse = (outcome: Outcome = "accepted"): PredictResponse => {
  const accepted = outcome === "accepted";
  return {
    request_id: "req123", created_at: "2026-10-12T10:00:00Z", mode: "crop", image: { width: 64, height: 128 },
    model: { name: "osnet_ain_x1_0", architecture: "OSNet-AIN x1.0", embedding_dim: 512, fingerprint: "osnet-abc-flip0", device: "cpu" },
    policy_version: 1, policy_status: "unvalidated", notes: [], timings_ms: { total_ms: 281 },
    people: [{
      index: 0, box: null, detector_score: null, quality: { usable: true, flags: [], blocking_reason: null, metrics: {} }, crop_url: null,
      decision: {
        outcome, reason_code: accepted ? "accepted" : "below_threshold",
        reason: accepted ? "Accepted: 'subject-001' scored 0.813, at or above the threshold 0.700." : "No supported match: the closest candidate 'subject-001' scored 0.640, below the acceptance threshold 0.700.",
        accepted_reference_id: accepted ? "subject-001" : null, top1_reference_id: "subject-001", top1_score: accepted ? 0.813 : 0.64, top2_score: 0.31,
        margin: 0.33, accept_threshold: 0.7, min_margin: null, calibrated_confidence: null, policy_version: 1, policy_status: "unvalidated",
        quality_flags: outcome === "review_required" ? ["blurry"] : [],
        matching_mode: "body", basis: "body", face_status: null, top1_face_score: null, top1_body_score: null, face_threshold: null, body_threshold: null,
      },
      candidates: [
        { rank: 1, reference_id: "subject-001", label: "Lobby test", score: accepted ? 0.813 : 0.64, n_images: 3, image_url: null, basis: "body", face_score: null, body_score: null, face_box: null },
        { rank: 2, reference_id: "subject-002", label: null, score: 0.31, n_images: 2, image_url: null, basis: "body", face_score: null, body_score: null, face_box: null },
      ],
      face: null, cues: [],
    }],
    face_model: null, matching_mode: "body",
  };
};

/** A result produced under the face + body policy: the face decided, the body supports, and colour cues are listed. */
export const faceBodyResponse = (outcome: Outcome = "accepted"): PredictResponse => {
  const base = predictResponse(outcome);
  const accepted = outcome === "accepted";
  const person = base.people[0];
  return {
    ...base, matching_mode: "face_body", face_model: "face-8f2383e4-0ba9fbfa",
    people: [{
      ...person,
      decision: {
        ...person.decision, matching_mode: "face_body", basis: "face", face_status: "usable", top1_score: accepted ? 0.742 : 0.19,
        accept_threshold: 0.363, face_threshold: 0.363, body_threshold: 0.7, top1_face_score: accepted ? 0.742 : 0.19, top1_body_score: 0.91,
        reason: accepted
          ? "Accepted by face: face similarity 0.742 is at or above the face threshold 0.363."
          : "No supported match: a usable face was compared; the closest scored 0.190, below the face threshold 0.363. Body/clothing similarity alone is NOT accepted when a face is available (best body score 0.910).",
      },
      candidates: [{ ...person.candidates[0], basis: "face", score: accepted ? 0.742 : 0.19, face_score: accepted ? 0.742 : 0.19, body_score: 0.91, face_box: [10, 8, 50, 60] }, { ...person.candidates[1], basis: "body", body_score: 0.31, face_score: null }],
      face: { status: "usable", box: [20, 6, 44, 36], detector_score: 0.93, face_px: 64, flags: [], message: "A usable face was found and compared." },
      cues: [
        { cue: "upper_clothing", title: "Upper clothing", query_rgb: [200, 30, 30], query_label: "red", reference_rgb: [205, 35, 32], reference_label: "red", delta_e: 3.1, verdict: "similar" },
        { cue: "hair", title: "Hair colour", query_rgb: [40, 30, 25], query_label: "black", reference_rgb: [110, 80, 50], reference_label: "brown", delta_e: 31.4, verdict: "different" },
      ],
    }],
  };
};

const seedResult = (far: number, dir1: number) => ({
  variant: "thr", seed: 0, status: "ok",
  selected: { target: {}, target_achieved: true, threshold: 0.81, min_margin: null, calibration: { far: 0.02, dir_at_rank: { "1": 0.9 }, counts: { unknown_accepted: 2, unknown_queries: 100 } }, far_upper_bound_95: 0.06, n_unknown: 100, n_known: 80, sample_size_adequate: true, notes: [] },
  test: { threshold: 0.81, min_margin: null, counts: { known_queries: 80, unknown_queries: 100, known_accepted: 70, known_accepted_correct: 68, known_accepted_wrong_identity: 2, unknown_accepted: far * 100 }, far, tar: 0.88, frr: 0.12, dir_at_rank: { "1": dir1, "5": 0.9 }, precision: 0.9, recall: dir1, f1: 0.86,
    confidence_intervals: { far: { low: far - 0.01, high: far + 0.02, level: 0.95 }, dir1: { low: dir1 - 0.04, high: dir1 + 0.03, level: 0.95 }, tar: { low: 0.8, high: 0.93, level: 0.95 } } },
  curve: { far: [0, 0, 0.02, 0.05, 1], tar: [0, 0.3, 0.8, 0.9, 1], dir1: [0, 0.28, 0.75, 0.84, 0.9], threshold: [null, 0.95, 0.81, 0.7, null] },
  auroc: 0.93, auoscr: 0.81,
  closed_set: { rank1: 0.9, rank5: 0.96, cmc: [0.9, 0.93, 0.95, 0.96, 0.97], mAP: 0.78, queries_used: 80, dropped_same_camera_only: 0 },
  hard_subset: { test: { threshold: 0.81, min_margin: null, counts: { known_queries: 20, unknown_queries: 25, known_accepted: 12, known_accepted_correct: 11, known_accepted_wrong_identity: 1, unknown_accepted: 3 }, far: 0.12, tar: 0.6, frr: 0.4, dir_at_rank: { "1": 0.55 }, precision: 0.78, recall: 0.55, f1: 0.64 } },
  score_histogram: { bin_edges: [0, 0.5, 1], known_correct: [2, 66], known_wrong: [3, 9], unknown: [70, 30] },
});

export const evaluationResult = (): EvaluationResult => {
  const run = seedResult(0.03, 0.85) as unknown as VariantResult["per_seed"][number];
  const summary = (v: number) => ({ mean: v, std: null, n_seeds: 1 });
  const variant = (label: string, key: string): VariantResult => ({
    label, description: `${key} description`, parent: null, status: "ok", reason: null, per_seed: [{ ...run, variant: key }],
    summary: { far: summary(0.03), tar: summary(0.88), dir1: summary(0.85), precision: summary(0.9), f1: summary(0.86), auroc: summary(0.93), auoscr: summary(0.81), rank1: summary(0.9), rank5: summary(0.96), mAP: summary(0.78), hard_far: summary(0.12), hard_dir1: summary(0.55), calibration_far: summary(0.02), calibration_dir1: summary(0.9), threshold: summary(0.81), min_margin: { mean: null, std: null, n_seeds: 0 }, targets_achieved: 1, n_seeds_total: 1 },
  });
  return {
    kind: "evaluation",
    metadata: {
      started_at: "2026-10-12T10:00:00Z", duration_seconds: 42, request: { seeds: [0], target: { mode: "fixed_recall", target_recall: 0.9, target_far: 0.01 } },
      dataset: { name: "market1501", layout: "market1501", kind: "benchmark", description: "", license_note: "", identities: 1501, images: 32000, cameras: 6, available: true, problems: [] },
      is_benchmark: true, model: { architecture: "OSNet-AIN x1.0", weights: "official", fingerprint: "osnet-abc-flip0" },
      protocol: { "0": { calibration: { enrolled_identities: 50, unknown_identities: 50, known_queries: 400, unknown_queries: 500, gallery_images: 150 }, test: { enrolled_identities: 100, unknown_identities: 100, known_queries: 800, unknown_queries: 900, gallery_images: 300 }, hard_subset: { test: { method: "colour-histogram proxy", queries: 40, note: "A proxy." } } } },
      software: { python: "3.14", torch: "2.14", numpy: "2.5" }, operating_target: "DIR@1 (accepted and correct) >= 90.0%, minimise FAR",
    },
    performance: { embedding: { single_crop_ms: { n: 30, mean: 150, p50: 148, p95: 170, p99: 180, min: 140, max: 190 }, batch: { batch_size: 16, ms_per_crop: 140, throughput_crops_per_second: 7.1 } }, retrieval_ms_per_query: 0.04, retrieval_gallery_images: 300, model_load_seconds: 0.6, warmup_seconds: 0.3, peak_memory_mb: 700, device: "cpu", note: "Measured on this machine." },
    variants: { nn_baseline: { ...variant("Nearest neighbour (no rejection)", "nn_baseline"), per_seed: [{ ...run, variant: "nn_baseline", selected: null, curve: undefined }] }, thr: variant("+ Calibrated threshold", "thr") },
    selected_variant: { key: "thr", selected_on: "calibration split", criterion: "lowest calibration FAR among variants that reached the recall target", calibration_far: 0.02, calibration_recall: 0.9 },
    warnings: [],
  };
};

export const finishedRun = (over: Partial<RunDetail> = {}): RunDetail => ({
  run_id: "a".repeat(32), kind: "evaluation", status: "succeeded", stage: "Done", progress: 1, dataset: "market1501", dataset_kind: "benchmark",
  created_at: "2026-10-12T10:00:00Z", started_at: "2026-10-12T10:00:01Z", finished_at: "2026-10-12T10:01:00Z",
  headline: { selected_variant: "thr", far: 0.03, recall: 0.85, rank1: 0.9, mAP: 0.78, is_benchmark: true }, error: null,
  config: {}, result: evaluationResult(), cancel_requested: false, ...over,
});

// ------------------------------------------------------------------ Lookalike Failure Lab
const labMeasurement = (far: number, tar: number) => ({
  threshold: 0.8, genuine_pairs: 200, impostor_pairs: 24, true_accepts: Math.round(tar * 200), false_rejects: 200 - Math.round(tar * 200),
  false_accepts: Math.round(far * 24), true_rejects: 24 - Math.round(far * 24), tar, far_on_challenge_set: far, far_on_challenge_set_upper_bound_95: far + 0.1,
  far_all_pairs_reference: 0.0004, all_pairs_compared: 52000,
  note: "The challenge-set FAR is measured on pairs chosen BECAUSE they are hard, so it is much higher than the false-accept rate of normal use.",
  curve: [{ threshold: 0.95, far: 0, tar: 0.3 }, { threshold: 0.8, far, tar }, { threshold: 0.6, far: 0.9, tar: 0.99 }],
  hardest_genuine_pairs: [{ comparison_type: "same_identity" as const, identity: "0007", similarity: 0.41, decision: "false_reject" as const, image_a: "0007/c1_01.jpg", image_b: "0007/c3_02.jpg", camera_a: 1, camera_b: 3 }],
});

export const lookalikeResult = (improved = false): LookalikeResult => {
  const ok = (label: string, far: number, tar: number): LabModelOk => ({
    status: "ok", label, embedding_source: "plain",
    calibration: { target: {}, target_achieved: true, threshold: 0.8, min_margin: 0.05, calibration: {} as never, far_upper_bound_95: 0.05, n_unknown: 120, n_known: 90, sample_size_adequate: true, notes: [] },
    rule: { threshold: 0.8, min_margin: 0.05, margin_action: "review" },
    test_query_level: { threshold: 0.8, min_margin: 0.05, counts: { known_queries: 90, unknown_queries: 120, known_accepted: 70, known_accepted_correct: 68, known_accepted_wrong_identity: 2, unknown_accepted: 3 }, far: 0.025, tar: 0.78, frr: 0.22, dir_at_rank: { "1": 0.76 }, precision: 0.9, recall: 0.76, f1: 0.82, far_upper_bound_95: 0.06 },
    challenge: labMeasurement(far, tar), model: { fingerprint: "osnet-abc-flip0" },
  });
  const failure = (id: string, category: "incorrect_acceptance" | "genuine_rejected"): LabFailure => ({
    id, category, category_label: category === "incorrect_acceptance" ? "Stranger accepted as an enrolled person" : "Enrolled person not accepted",
    query: { ref: "0101/c2_03.jpg", identity: "0101", camera: 2, is_known: category === "genuine_rejected" }, matched: { identity: "0042", ref: "0042/c1_01.jpg", camera: 1 },
    observed: { outcome: category === "incorrect_acceptance" ? "accepted" : "unknown", top1_score: 0.82, threshold: 0.8, score_minus_threshold: 0.02, margin: 0.01, min_margin: null,
      true_identity_rank: category === "genuine_rejected" ? 2 : null, true_identity_score: category === "genuine_rejected" ? 0.7 : null, quality_flags: [], sharpness: 80, clothing_colour_similarity: 0.95 },
    possible_causes: [{ cause: "threshold_too_permissive", text: "The threshold may be too permissive for this operating point.", evidence: "similarity 0.820 is only 0.020 above the threshold 0.800.", status: "hypothesis - not proven" }],
  });
  return {
    kind: "lookalike",
    metadata: {
      experiment_id: "b".repeat(32), started_at: "2026-10-12T10:00:00Z", duration_seconds: 31,
      request: { dataset: "market1501", seed: 0, mining_split: "test" }, is_benchmark: true, operating_target: "DIR@1 (accepted and correct) >= 90.0%, minimise FAR",
      dataset: { name: "market1501", layout: "market1501", kind: "benchmark", description: "", license_note: "", identities: 1501, images: 32000, cameras: 6, available: true, problems: [] },
      protocol: {}, software: { python: "3.14", torch: "2.14", numpy: "2.5" }, reproducibility: "Same dataset files, same seed and the same settings give the same splits, pairs and numbers.",
    },
    challenge_set: {
      definition: { source: "dataset 'market1501', split 'test', seed 0", impostor_comparisons: "different-person photo pairs", genuine_comparisons: "same-person photo pairs from different cameras",
        inclusion_criteria: "The impostor side is selected BY the baseline model's similarity.", model_vs_clothing: "'Similar' for mining means similar EMBEDDINGS; clothing is measured separately.",
        clothing_proxy_rule: "top 25% colour similarity", splits: "people are divided into dev / calibration / test" },
      counts: { identity_pairs: 2, impostor_comparisons: 24, genuine_comparisons: 200, all_pairs_compared: 52000 },
      identity_pairs: [
        { rank: 1, comparison_type: "different_identities", split: "test", identity_a: "0042", identity_b: "0101", similarity: 0.91, image_a: "0042/c1_01.jpg", image_b: "0101/c2_03.jpg", camera_a: 1, camera_b: 2,
          clothing_colour_similarity: 0.96, similar_clothing_proxy: true, comparisons_in_challenge_set: 3, by_model: { baseline: { similarity: 0.91, decision: "false_accept" }, ...(improved ? { improved: { similarity: 0.7, decision: "correct_reject" as const } } : {}) } },
        { rank: 2, comparison_type: "different_identities", split: "test", identity_a: "0050", identity_b: "0060", similarity: 0.7, image_a: "0050/c1_01.jpg", image_b: "0060/c2_01.jpg", camera_a: 1, camera_b: 2,
          clothing_colour_similarity: 0.5, similar_clothing_proxy: false, comparisons_in_challenge_set: 3, by_model: { baseline: { similarity: 0.7, decision: "correct_reject" }, ...(improved ? { improved: { similarity: 0.5, decision: "correct_reject" as const } } : {}) } },
      ],
    },
    models: {
      baseline: ok("Baseline (official pretrained weights)", 0.5, 0.9),
      improved: improved ? ok("Improved (fine-tuned checkpoint)", 0.2, 0.88) : { status: "unavailable", reason: "No fine-tuned checkpoint was selected. None is shipped with this project; scripts/finetune_triplet.py trains one on the development people." },
    },
    comparison: improved ? [
      { model: "baseline", label: "Baseline", threshold: 0.8, test_far: 0.025, test_recall_dir1: 0.76, test_unknown_accepted: 3, test_unknown_queries: 120, challenge_far: 0.5, challenge_tar: 0.9, challenge_false_accepts: 12, challenge_impostor_pairs: 24, single_crop_ms_p50: 150 },
      { model: "improved", label: "Improved", threshold: 0.75, test_far: 0.01, test_recall_dir1: 0.8, test_unknown_accepted: 1, test_unknown_queries: 120, challenge_far: 0.2, challenge_tar: 0.88, challenge_false_accepts: 5, challenge_impostor_pairs: 24, single_crop_ms_p50: 151 },
    ] : null,
    failures: { baseline: { counts: { incorrect_acceptance: 3, wrong_identity_accepted: 0, genuine_rejected: 20, queries: 210, genuine_sent_to_review: 4, strangers_sent_to_review: 6 },
      listed: [failure("IN-001", "incorrect_acceptance"), failure("GE-001", "genuine_rejected")], rule: { threshold: 0.8, min_margin: 0.05, margin_action: "review" },
      note: "'observed' holds recorded measurements. 'possible_causes' are hypotheses worded from those measurements; they have not been tested and must not be read as the proven reason." } },
    sandbox_available: true,
    limitations: ["Results are measurements on one sample of people.", "The challenge set is selected by the baseline model."],
    warnings: [],
  };
};

export const labRun = (over: Partial<RunDetail> = {}, improved = false): RunDetail => ({
  run_id: "b".repeat(32), kind: "lookalike", status: "succeeded", stage: "Done", progress: 1, dataset: "market1501", dataset_kind: "benchmark",
  created_at: "2026-10-12T10:00:00Z", started_at: "2026-10-12T10:00:01Z", finished_at: "2026-10-12T10:01:00Z",
  headline: { mining_split: "test", target_achieved: true, threshold: 0.8, challenge_far: 0.5, all_pairs_far: 0.0004, challenge_tar: 0.9, improved_status: improved ? "ok" : "unavailable", is_benchmark: true },
  error: null, config: {}, result: lookalikeResult(improved), cancel_requested: false, ...over,
});

export const sandboxInfo = (): SandboxInfo => ({
  run_id: "b".repeat(32), kind: "lookalike", dataset: "market1501",
  reference: { variant: "baseline", label: "Baseline (official pretrained weights)", threshold: 0.8, min_margin: 0.05, margin_action: "review", target_achieved: true, chosen_on: "calibration split, seed 0" },
  embedding_source: "plain", model_fingerprint: "osnet-abc-flip0", splits: { calibration: 210, test: 210 }, score_range: { min: 0.1, max: 0.97 }, is_benchmark: true, writes_policy: false,
  explanation: "A fixed table of the per-query results of this run. Trying a different threshold only re-counts that table - no model is re-run and the active decision policy is never changed.",
});

const sandboxSummary = (threshold: number, falseAccepts: number, falseRejects: number): SandboxSummary => ({
  rule: { threshold, min_margin: 0.05, margin_action: "review" },
  metrics: { threshold, min_margin: 0.05, counts: { known_queries: 90, unknown_queries: 120, known_accepted: 90 - falseRejects, known_accepted_correct: 88 - falseRejects, known_accepted_wrong_identity: 2, unknown_accepted: falseAccepts },
    far: falseAccepts / 120, tar: 0.8, frr: 0.2, dir_at_rank: { "1": (88 - falseRejects) / 90 }, precision: 0.9, recall: 0.8, f1: 0.85, far_upper_bound_95: 0.08 },
  confusion: { true_accepts: 88 - falseRejects, wrong_identity_accepts: 2, false_accepts: falseAccepts, false_rejects: falseRejects, true_rejects: 120 - falseAccepts, known_sent_to_review: 3, unknown_sent_to_review: 5,
    definitions: { true_accepts: "enrolled person, accepted, and the right person was named", false_accepts: "stranger (not enrolled), accepted as someone" } },
  outcome_counts: { accepted: 80, review_required: 8, unknown: 122 },
});

export const sandboxResult = (threshold = 0.8, split: "calibration" | "test" = "calibration"): SandboxResult => ({
  run_id: "b".repeat(32), split, n_queries: 210, trial: sandboxSummary(threshold, threshold < 0.8 ? 9 : 3, threshold < 0.8 ? 5 : 20), calibrated_rule: sandboxSummary(0.8, 3, 20),
  decisions_changed: threshold === 0.8 ? 0 : 12,
  changed_examples: threshold === 0.8 ? [] : [{ ref: "0101/c2_03.jpg", query_identity: "0101", is_known: false, top1_identity: "0042", top1_correct: false, top1_score: 0.74, margin: 0.2, calibrated_rule: "unknown", trial_rule: "accepted" }],
  writes_policy: false, is_benchmark: true,
  warning: split === "test" ? "You are looking at the TEST split. Moving the threshold while watching these numbers and then keeping the best-looking value would be tuning on the test set." : null,
});

// ---------------------------------------------------------------------------- Video Explorer
export const videoLimits = (over: Partial<VideoLimits> = {}): VideoLimits => ({
  max_megabytes: 100, max_seconds: 180, max_frames: 120, max_frame_side: 3840, extensions: [".mp4", ".mov", ".avi", ".mkv", ".webm"],
  detector_ready: true, embedding_ready: true, frame_previews_kept_hours: 24,
  scope: "Frame-by-frame re-identification of a prerecorded clip. It is not multi-object tracking.", ...over,
});

export const videoResult = (): VideoResult => {
  const person = (outcome: Outcome, id: string | null, score: number) => ({
    index: 0, box: [10, 10, 60, 150], detector_score: 0.97, usable: true, quality_flags: [], blocking_reason: null, outcome,
    reason_code: outcome, reason: outcome === "accepted" ? `Accepted: '${id}' scored ${score}.` : `No supported match: the closest candidate scored ${score}.`,
    accepted_reference_id: outcome === "accepted" ? id : null, top1_reference_id: id, top1_score: score, top2_score: 0.2, margin: 0.4,
  });
  const frame = (index: number, time: number, people: ReturnType<typeof person>[]) => ({
    index, frame_number: index * 10, time_seconds: time, width: 320, height: 240, thumbnail: `f000${index}.jpg`, people,
    timings_ms: { decode_ms: 5, detect_ms: 400, embed_ms: 150, match_ms: 1, processing_ms: 551 },
  });
  return {
    kind: "video",
    metadata: {
      original_name: "lobby.avi", video: { width: 320, height: 240, fps: 10, frame_count: 30, duration_seconds: 3, container: "avi" },
      sampling: { every_seconds: 1, max_frames: 30, every_n_frames: 10, assumed_fps: null, frames_processed: 3 },
      policy: { version: 1, status: "unvalidated", accept_threshold: 0.7, min_margin: null }, model: { name: "osnet_ain_x1_0", fingerprint: "osnet-abc-flip0", device: "cpu" },
      detector: "fasterrcnn", thumbnails_kept: true, retention_hours: 24, generated_at: "2026-10-12T10:00:00Z",
    },
    frames: [frame(0, 0, [person("accepted", "p-red", 0.91)]), frame(1, 1, [person("unknown", "p-red", 0.3)]), frame(2, 2, [])],
    summary: {
      frames_processed: 3, people_detected: 2, outcomes: { accepted: 1, unknown: 1 },
      identities_seen: [{ reference_id: "p-red", label: "Red test", frames: 1, first_seen_seconds: 0, last_seen_seconds: 0, best_score: 0.91 }],
      latency_ms: { processing_per_frame: { n: 3, p50: 551, p95: 560 }, note: "detection + embedding + matching for one frame, measured." }, wall_seconds: 2, frames_per_second_processed: 1.5,
    },
    notes: [
      "Each sampled frame is judged on its own. A person is NOT followed from frame to frame, nothing is tracked through occlusion, and no identity is carried between frames - this is frame-by-frame re-identification, not multi-object tracking.",
      "The active decision policy is 'unvalidated': its threshold has not been calibrated on held-out data.",
    ],
  };
};

export const videoJob = (over: Partial<RunDetail> = {}): RunDetail => ({
  run_id: "c".repeat(32), kind: "video", status: "succeeded", stage: "Done", progress: 1, dataset: "lobby.avi", dataset_kind: "video",
  created_at: "2026-10-12T10:00:00Z", started_at: "2026-10-12T10:00:01Z", finished_at: "2026-10-12T10:00:30Z",
  headline: { frames_processed: 3, people_detected: 2, outcomes: { accepted: 1, unknown: 1 }, is_benchmark: false }, error: null,
  config: {}, result: videoResult(), cancel_requested: false, ...over,
});

// ---------------------------------------------------------------------------- built-in example (open-set analysis)
export const demoInfo = (over: Partial<DemoInfo> = {}): DemoInfo => ({
  available: true, reason: null, title: "Open-set example",
  intro: "An open-set system must do two things at once: recognise the people it knows, and refuse everyone else.",
  groups: [
    { id: "known", title: "Known people, seen again", blurb: "The same person in different clothes. The right answer is MATCH with the right person." },
    { id: "no_face", title: "Known person, but no usable face", blurb: "Clothes alone are weak evidence, so the safe answer is REVIEW." },
    { id: "stranger", title: "Strangers (never enrolled)", blurb: "Nobody in the gallery is this person. The right answer is UNKNOWN." },
    { id: "lookalike", title: "Strangers in the SAME clothes as an enrolled person", blurb: "The hard case: a clothes-only matcher is fooled; the face is not." },
  ],
  people: [
    { id: "person1", label: "Example person 1", note: "Two portraits.", n_faces: 0, photos: [{ name: "p1a.jpg", url: "/api/demo/files/faces/enroll/p1a.jpg", face_status: null, face_note: null }] },
    { id: "person2", label: "Example person 2", note: "Two portraits.", n_faces: 0, photos: [{ name: "p2a.jpg", url: "/api/demo/files/faces/enroll/p2a.jpg", face_status: null, face_note: null }] },
    { id: "person3", label: "Example person 3", note: "A street photo with the head blurred.", n_faces: 0, photos: [{ name: "p3a.jpg", url: "/api/demo/files/p3a.jpg", face_status: null, face_note: null }] },
  ],
  cases: [
    { id: "known-1", group: "known", title: "Example person 1 in a NASA jacket", story: "Different clothes and place.", image_url: "/api/demo/files/q/known-1.jpg", expect: { kind: "match", person: "person1", person_label: "Example person 1", text: "Enrolled: Example person 1. The right answer is MATCH Example person 1." } },
    { id: "known-2", group: "known", title: "Example person 2 in flight", story: "Nothing like either enrolled photo.", image_url: "/api/demo/files/q/known-2.jpg", expect: { kind: "match", person: "person2", person_label: "Example person 2", text: "Enrolled: Example person 2. The right answer is MATCH Example person 2." } },
    { id: "noface-1", group: "no_face", title: "Example person 3 again - head blurred", story: "The clothes match strongly but there is no face.", image_url: "/api/demo/files/q/noface-1.jpg", expect: { kind: "review", person: "person3", person_label: "Example person 3", text: "Example person 3 is enrolled, but there is no usable face." } },
    { id: "stranger-1", group: "stranger", title: "A stranger in a cockpit", story: "Never enrolled.", image_url: "/api/demo/files/q/stranger-1.jpg", expect: { kind: "unknown", person: null, person_label: null, text: "Not enrolled - a stranger. The right answer is UNKNOWN." } },
    { id: "same-1", group: "lookalike", title: "A stranger in the same orange flight suit (1)", story: "Dressed like the enrolled people.", image_url: "/api/demo/files/q/same-1.jpg", expect: { kind: "unknown", person: null, person_label: null, text: "Not enrolled - a stranger. The right answer is UNKNOWN." } },
    { id: "same-2", group: "lookalike", title: "A stranger in the same orange flight suit (2)", story: "Another stranger, same suit.", image_url: "/api/demo/files/q/same-2.jpg", expect: { kind: "unknown", person: null, person_label: null, text: "Not enrolled - a stranger. The right answer is UNKNOWN." } },
  ],
  rules: { matching_mode: "face_body", face_threshold: 0.465, face_review_band: 0.1, body_threshold: 0.7, policy_version: 1, policy_status: "unvalidated", face_models_loaded: true },
  disclaimer: "A small demonstration with public-domain photographs, not a benchmark. Nothing from this example is saved.",
  ...over,
});

export const demoPrepared = (): DemoPrepared => {
  const info = demoInfo();
  return {
    people: info.people.map((p) => ({ ...p, n_faces: p.id === "person3" ? 0 : 1, photos: p.photos.map((ph) => ({ ...ph, face_status: p.id === "person3" ? "no_face" : "ready" })) })),
    rules: info.rules!, built_ms: 3100,
  };
};

export const demoDecision = (over: Partial<DemoDecision> = {}): DemoDecision => ({
  outcome: "unknown", accepted_person: null, accepted_label: null, top1_person: "person1", top1_label: "Example person 1", top1_score: 0.15,
  face_score: null, body_score: null, basis: "body", threshold: 0.7, reason: "No supported match.", verdict: "correct", candidates: [], ...over,
});

/** A realistic answer for each example photo: the system gets all six right; a clothes-only matcher fails in both directions. */
export const DEMO_ANSWERS: Record<string, Pick<DemoCaseResult, "face_body" | "clothes_only">> = {
  "known-1": {
    face_body: demoDecision({ outcome: "accepted", accepted_person: "person1", accepted_label: "Example person 1", top1_score: 0.62, face_score: 0.62, body_score: 0.31, basis: "face", threshold: 0.465, reason: "Accepted by face." }),
    clothes_only: demoDecision({ outcome: "unknown", top1_score: 0.44, body_score: 0.44, verdict: "missed", reason: "Below the clothes threshold." }),
  },
  "known-2": {
    face_body: demoDecision({ outcome: "accepted", accepted_person: "person2", accepted_label: "Example person 2", top1_person: "person2", top1_label: "Example person 2", top1_score: 0.55, face_score: 0.55, body_score: 0.38, basis: "face", threshold: 0.465 }),
    clothes_only: demoDecision({ outcome: "unknown", top1_score: 0.38, body_score: 0.38, verdict: "missed" }),
  },
  "noface-1": {
    face_body: demoDecision({ outcome: "review_required", top1_person: "person3", top1_label: "Example person 3", top1_score: 0.91, body_score: 0.91, reason: "No face. Clothes alone are not enough: a person should confirm." }),
    clothes_only: demoDecision({ outcome: "accepted", accepted_person: "person3", accepted_label: "Example person 3", top1_person: "person3", top1_label: "Example person 3", top1_score: 0.91, body_score: 0.91, verdict: "risky" }),
  },
  "stranger-1": {
    face_body: demoDecision({ top1_score: 0.12, face_score: 0.12, body_score: 0.2, basis: "face", threshold: 0.465 }),
    clothes_only: demoDecision({ top1_score: 0.25, body_score: 0.25 }),
  },
  "same-1": {
    face_body: demoDecision({ top1_score: 0.15, face_score: 0.15, body_score: 0.79, basis: "face", threshold: 0.465, reason: "Clothing similarity alone is NOT accepted when a face is available." }),
    clothes_only: demoDecision({ outcome: "accepted", accepted_person: "person1", accepted_label: "Example person 1", top1_score: 0.79, body_score: 0.79, verdict: "false_accept" }),
  },
  "same-2": {
    face_body: demoDecision({ top1_score: 0.18, face_score: 0.18, body_score: 0.81, basis: "face", threshold: 0.465 }),
    clothes_only: demoDecision({ outcome: "accepted", accepted_person: "person1", accepted_label: "Example person 1", top1_score: 0.81, body_score: 0.81, verdict: "false_accept" }),
  },
};

export const demoCaseResult = (caseId: string): DemoCaseResult => ({
  case_id: caseId,
  face: { status: caseId === "noface-1" ? "no_face" : "usable", box: caseId === "noface-1" ? null : [10, 10, 60, 70], detector_score: 0.9, face_px: 50, flags: [], message: null },
  timings_ms: { total_ms: 300 },
  ...DEMO_ANSWERS[caseId],
});