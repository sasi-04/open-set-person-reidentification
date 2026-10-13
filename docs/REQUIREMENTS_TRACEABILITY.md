# Requirements traceability

Every requirement of the PS-1 challenge and of the build briefs, where it is satisfied, and what proves it. **Section C is the current brief (OpenID Vision); sections A and B are the earlier build brief, kept because the work they describe is still in the product.**
**Status words:** **Done** - implemented and tested · **Done, unbenchmarked** - implemented and tested, but its *measured performance* needs the public dataset you have to supply ·
**Partly** - some of it is done (the gap is stated) · **Not done** - deliberately out of scope (stated).

## A. The PS-1 challenge text

| # | Requirement | Status | Where | Evidence |
|---|---|---|---|---|
| 1 | Re-identify against an **open set** where many identities look near-identical | Done, unbenchmarked | [decision engine](../backend/app/cv/open_set/decision_engine.py), [hard subset](../backend/app/evaluation/hard_subset.py) | `test_decision_engine.py` (24), `test_evaluation_pipeline.py` |
| 2 | **Minimise false-accept rate at a fixed recall** under low inter-class variance | Done, unbenchmarked | [`calibration.py`](../backend/app/evaluation/calibration.py) mode `fixed_recall` (default) | `test_unreachable_target_is_reported_not_hidden`, `test_fixed_far_selection_respects_the_target…`; Lab + CLI |
| 3a | **Deep metric learning**, hard-negative mining, margin formulation | Done (no checkpoint trained) | [`training/triplet.py`](../backend/app/training/triplet.py), [`finetune.py`](../backend/app/training/finetune.py), `scripts/finetune_triplet.py`, margin in [`policy.py`](../backend/app/cv/open_set/policy.py) | `test_batch_hard_loss_picks_the_hardest_positive_and_hardest_negative`, `test_finetune_trains_only_the_chosen_layers…` |
| 3b | **Open-set recognition**, discriminative embeddings | Done | OSNet-AIN embeddings + decision engine | real-model tests in `test_training_and_model.py` |
| 3c | **Calibration of similarity scores into confidences** | Done, unbenchmarked | [`confidence.py`](../backend/app/cv/open_set/confidence.py) (+ ECE/Brier in `metrics.py`) | `test_confidence_model.py` (5), `test_calibrated_confidence_model_is_only_used_for_the_model_it_was_fitted_on` |
| 4a | **Real-time** inference | **Partly** | measured 0.5 s idle / 1.2 s busy per query on a 2-core CPU ([PERFORMANCE.md](PERFORMANCE.md)); *interactive, not video-rate; no claim of real-time* | `scripts/benchmark_latency.py` |
| 4b | Embeddings from **one compact backbone** | Done | OSNet-AIN x1.0, 2.17 M parameters | `test_every_registered_model_has_a_pinned_hash_and_one_embedding_size` |
| 4c | **No fixed identity count** | Done | no classifier head; gallery = index of embeddings; enroll/delete need no retraining | gallery tests (`test_api_gallery.py`, 23) |
| 5a | Matching algorithm | Done | `cv/` | - |
| 5b | **ROC / FAR-vs-TAR analysis** on a **public benchmark** | **Pipeline done; benchmark run pending your dataset** | [`metrics.py`](../backend/app/evaluation/metrics.py), Evaluation Lab | `test_metrics.py` (23, hand-computed) |
| 5c | **Curated low-variance (same-clothing) subset** | Done (proxy + manual hook), unbenchmarked | `hard_subset.py`, `scripts/prepare_dataset.py template` | `test_evaluation_pipeline.py` |
| 5d | **Ablations isolating each component** | Done, unbenchmarked | [`ablation.py`](../backend/app/evaluation/ablation.py) (6 variants) | `test_full_run_produces_all_variants_and_selects_on_calibration` |

## B. Build brief

### 3.1 Detection and preprocessing

| Requirement | Status | Evidence |
|---|---|---|
| File upload, format and size validation | Done | `test_imaging_quality.py` (23), `test_api_reid.py::test_non_image_upload…`, `…oversized…` |
| Detect people; boxes; crops with sensible aspect ratio; resize/normalise | Done | `detector.py`, `geometry.py`, `extractor._to_tensor`; `test_wide_crop_is_padded_not_stretched` |
| Reject/flag unusable crops | Done | `quality.py`; `test_tiny_person_is_a_processing_error…`, `test_blurry_input_goes_to_review…` |
| Multiple people in one image | Done | `test_several_people_are_each_matched_and_decided_separately` |
| Show boxes with detector confidence, kept separate from identity confidence | Done | `DetectionPreview.tsx`, `DecisionSummary.tsx`; `test_detect_endpoint_returns_boxes_and_keeps_detector_score_separate`, `reid.test.tsx` |
| Useful error when no person is detected | Done | `test_no_person_detected_is_a_clear_error`, UI test |
| Record preprocessing and inference latency | Done | per-stage `timings_ms`; `test_response_reports_per_stage_timings` |
| Video-file workflow | **Not done** (optional in the brief) | stated in README §20 |

### 3.2 Feature extraction

| Requirement | Status | Evidence |
|---|---|---|
| Compact pretrained ReID model; CPU and CUDA; automatic device choice | Done (CUDA path untested - no GPU) | `core/device.py`, `extractor.py` |
| Load once; eval mode; no gradients; normalised; validated dim/values | Done | `OSNetExtractor.load/_validate`; `test_real_model_produces_512_dim_unit_length_deterministic_embeddings` |
| Handle missing / incompatible / corrupted weights gracefully | Done | `test_missing_weights_file_gives_an_actionable_message`, `test_corrupted_weights_are_rejected_by_checksum`, `test_weights_that_do_not_fit_the_architecture_are_rejected`, `test_server_starts_but_reports_not_ready_when_the_model_is_missing` |
| Init and inference timing; config in one place; swappable backbone | Done | `info()`; `registry.py` |
| No silent downloads; document source and licence | Done | `scripts/download_weights.py`, README §8, THIRD_PARTY_NOTICES |
| Real embeddings only (no random vectors in the inference path) | Done | the only fakes live in `tests/` and are labelled |

### 3.3 Low inter-class variance

| Requirement | Status | Evidence |
|---|---|---|
| L2-normalised embeddings; cosine retrieval | Done | `ranking.py`; `test_cosine_similarity_known_values` |
| top-1 / top-2 margin, consistently defined | Done | `decision_engine.py`; `test_ambiguous_margin_triggers_review_by_default` |
| Threshold rejection | Done | `test_top_candidate_is_not_automatically_accepted` |
| Calibration on a separate validation split | Done | `test_calibration_run_never_embeds_a_test_image` |
| Hard-negative analysis | Done | hard subset + score-distribution chart |
| Optional metric-learning fine-tuning | Done (not trained) | see A.3a |
| Ablation framework | Done | see A.5d |
| Clearly separate "implemented" from "actually trained" | Done | README §1 table |

### 3.4 Open-set decision engine

| Requirement | Status | Evidence |
|---|---|---|
| Dedicated, UI-independent, testable module | Done | `cv/open_set/` (no web, DB or image imports) |
| Top-k, configurable threshold, optional margin, explicit unknown, review outcome, ranked list | Done | `test_decision_engine.py` |
| Explanations agree with the scores; policy version recorded | Done | `test_explanation_matches_the_underlying_scores`, `test_decision_records_the_policy_that_made_it` |
| Retrieval score, detection confidence, calibrated score kept distinct | Done | `test_retrieval_score_and_calibrated_confidence_are_separate_fields` |
| Configurable via an authorised interface; changes alter real decisions | Done | `test_changing_the_threshold_changes_the_live_decision`, `test_roles_are_enforced…` |
| No unvalidated default presented as optimal; calibration workflow; report when the target is missed | Done | status labels; `test_an_unreachable_target_cannot_be_applied_as_calibrated` |
| Never auto-enroll rejected queries or merge unknowns | Done | no such code path; README §1 |
| Invalid thresholds rejected; deterministic ranking | Done | `test_invalid_thresholds_are_rejected`, `test_ranking_is_deterministic…` |

### 3.5 Gallery

| Requirement | Status | Evidence |
|---|---|---|
| Enroll with one or more images, pseudonymous ID; add images; view; inspect; delete with confirmation; rebuild; size/status; reset | Done | `test_api_gallery.py` (23) and `pages.test.tsx` gallery tests |
| Documented, consistent gallery strategy (individual embeddings, best image per person) | Done | README §3, ARCHITECTURE decision 3, one shared function |
| Parameterised DB access, validation, access control | Done (access control optional) | ORM only; `test_invalid_reference_ids_are_rejected`; roles are implemented and tested but **switched off by default** for the single-user local demo (`REID_AUTH_REQUIRED=false`) |

### 4 Evaluation

| Requirement | Status | Evidence |
|---|---|---|
| ROC, FAR, FRR, TAR, TAR at fixed FAR, DIR@k, Rank-k, mAP, OSCR, P/R/F1, latency percentiles, throughput, peak memory | Done | `metrics.py`, `performance.py`; `test_metrics.py` |
| Metrics defined with denominators; query-level (not pairwise) FAR | Done | [METRICS.md](METRICS.md); `test_unknown_query_is_falsely_accepted_when_any_identity_is_named` |
| Identity-disjoint dev/calibration/test; gallery vs known vs unknown separated; no tuning on test | Done | `protocol.py`; `test_splits_are_identity_disjoint`, `test_leakage_is_detected` |
| Configurable fixed-recall analysis; report achieved FAR/threshold; admit failure | Done | `calibration.py`; unreachable-target tests |
| Hard-negative subset with documented selection, no outcome-based selection, manual annotation route | Done | `hard_subset.py`, EVALUATION §4 |
| Ablations with identical metrics; multiple seeds; confidence intervals; recorded configuration | Done | `ablation.py`, `cluster_bootstrap_ci`, result metadata; `test_runs_are_reproducible_with_fixed_seeds` |
| No fabricated results; honest empty state when no dataset | Done | `test_no_datasets_is_an_empty_list_not_an_error`, `pages.test.tsx` ("No dataset is installed") |
| **Results on a public benchmark** | **Needs your data** | README §9 |

### 5 Interface

| Requirement | Status | Evidence |
|---|---|---|
| Restrained enterprise look; tokens; graphite default with a light theme | Done | [DESIGN.md](DESIGN.md); contrast computed for every pair |
| Shell: 7-item sidebar; top bar with module title, readiness, device, theme, role (role only when access keys are on); collapsible/mobile nav | Done | `components/layout/`; `responsive navigation` tests |
| Command Center (was Overview) with real values, definitions, empty states, quick actions | Done | `CommandCenterPage.tsx`; `pages.test.tsx` + `labs.test.tsx` Command Center tests; `test_overview_shows_real_numbers_and_honest_empty_states` |
| Match Studio (was Re-ID workspace): upload (drag/browse/validate/replace), controls, detection preview with selection, decision summary, ranked candidates, query-vs-reference comparison, exports | Done | `MatchStudioPage.tsx` + `features/reid/`; 11 component + 7 screen tests. *No "Cancel" button: the server cannot cancel a running inference, so none is shown* |
| Gallery: grid/list, search, sort, filter, pagination, details, add images, delete with confirm, states | Done | `GalleryPage.tsx`; tests |
| Evaluation Lab: dataset/split/model-checkpoint/variant/target controls, run, calibrate, real progress, ROC, FAR-vs-TAR, Rank-1/mAP, OSCR, latency chart, ablation table, report download, metadata, history | Done | `features/evaluation/`; tests. Charts have tooltips, legends, data tables |
| Model & thresholds (now a tab of Model & System Settings): model facts, device, thresholds, status, validation, confirmation, versioned/audited, apply calibration | Done | `features/model/ModelPanel.tsx`; 4 tests |
| Every visible button does something real; loading/success/error/disabled states; no success toast before confirmation | Done | audited by tests that assert the request is sent *before* the toast ("toast appears only AFTER the backend answered") |

### 6 API (adapted to the architecture; extra routes: `/api/overview`, `/api/auth/me`, `/api/evaluation/checkpoints`, `/api/audit`, `/api/maintenance/cleanup`)

| Requirement | Status | Evidence |
|---|---|---|
| All listed endpoints, Pydantic schemas, structured errors, request IDs, CORS limits, pagination, background jobs with real status/cancel/failure | Done | OpenAPI at `/api/docs`; `test_api_*` (98 tests) |
| Logging without sensitive data; timeouts and resource limits | **Partly** | size/dimension/concurrency limits and a 2-minute client timeout; **no server-side per-request kill** |

### 7 Security and privacy · 8 Performance

| Requirement | Status | Evidence |
|---|---|---|
| Authorised images only; no scraping/cameras/tracking; faces only for enrolled, consenting people (see the face section below); uploads outside public folder; type+MIME+dimension+size checks; safe names; no traversal | Done | [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md); `test_path_traversal_through_image_uid_is_impossible`, `test_script_disguised_as_image_is_rejected_by_content_sniffing` |
| Retention policy + cleanup; no raw images/embeddings in logs; access control; neutral wording for rejections | Done | `maintenance_service.py`; `test_stored_query_crop_is_available_then_removed_by_retention`, `test_query_images_are_not_stored_when_retention_is_zero` |
| Load once; batching; reusable gallery embeddings; cache invalidation; efficient top-k; CPU fallback; profiling; load/warm-up reported separately | Done | `GalleryIndex` versions; [PERFORMANCE.md](PERFORMANCE.md) |
| No unsupported performance claims | Done | every number measured; one earlier claim retracted in PERFORMANCE.md |

### 10 Responsive and accessible · 11 Tests · 12 Documentation

| Requirement | Status | Evidence |
|---|---|---|
| Works 360-1440 px; no horizontal overflow; touch targets; focus; semantics; contrast; reduced motion | Done | scripted real-browser audit: 7 screens × 5 widths plus all 7 evaluation-result tabs × 5 widths, no overflow ([DESIGN.md §5](DESIGN.md)); computed contrast; ARIA tests |
| Automated responsive tests | **Partly** | the audit is a script run by hand (jsdom has no layout), not part of the test runner |
| CV, decision-engine, evaluation, API and frontend tests as listed | Done | see below |
| README (23 sections), `.env.example`, `.gitignore`, sample commands | Done | README; git-ignore verified (nothing sensitive or large would be committed) |

## C. The OpenID Vision brief (current)

Same status words. "Not benchmarked" below always means: the capability is built and tested, but **no real-benchmark number has been produced** because the dataset has to be supplied by you.

### §3-4 Audit, architecture · §5 The engine

| Requirement | Status | Where / evidence |
|---|---|---|
| Inspect the repository first; preserve working code; no secrets printed | Done | the existing system was audited and extended, not replaced; see the handover |
| Layers: input, features, storage, matching, evaluation, application; the frontend never invents decisions | Done | [ARCHITECTURE.md](ARCHITECTURE.md); the interface only draws backend answers (sandbox, lab, video included) |
| Real person detector (boxes, scores, crops, invalid boxes rejected, several people, user picks one) | Done | `cv/detection`, `cv/geometry`; `test_several_people_are_each_matched_and_decided_separately`, `test_box_mode_matches_only_the_selected_person`, `test_bad_box_is_rejected` |
| One compact pretrained ReID backbone with provenance, cached, CPU, optional CUDA, validated I/O, timings | Done (CUDA untested here) | OSNet-AIN x1.0 (2.17 M parameters), SHA-256 pinned; `test_real_model_is_verified_and_reports_its_provenance` |
| ONNX / TensorRT | **Not done** (optional per the brief) | none claimed |
| Enrollment: unique IDs, several references, previews, add later, details, remove, rebuild when the model changes, empty gallery never matches | Done | `test_api_gallery.py` (23); `test_empty_gallery_gives_unknown_not_an_error`, `test_changing_the_model_marks_embeddings_stale_until_rebuilt` |
| Matching: validate → compare → aggregate → rank → decide → explain, with MATCH / UNKNOWN / REVIEW; quality, missing model or bad embedding is an error/review, not "unknown" | Done | `decision_engine.py`; `test_top_candidate_is_not_automatically_accepted`, `test_blurry_input_goes_to_review_instead_of_a_confident_answer`, `test_a_broken_embedding_is_a_processing_error_for_that_person_not_an_unknown` |
| Scores are never called probabilities; no unexplained universal threshold | Done | UI copy; threshold status badge *unvalidated / experimental / calibrated* |
| Calibrated threshold: validation data → target recall → measured FAR → independent test; warn when uncalibrated; test labels cannot influence it | Done, not benchmarked | `calibration.py`; `test_calibration_run_never_embeds_a_test_image`, `test_the_threshold_is_chosen_on_calibration_people_so_the_mined_split_cannot_change_it` |
| Threshold sandbox on a fixed evaluation set that cannot overwrite the production policy | Done | `evaluation/sandbox.py`; `test_sandbox.py` (17), `test_trying_thresholds_changes_the_counts_but_never_the_active_policy` |

### §6 Lookalike Failure Lab

| Requirement | Status | Where / evidence |
|---|---|---|
| Difficult-negative discovery with pair IDs, similarity, split, images, genuine-vs-impostor type, the matcher's decision; no test-label leakage | Done, not benchmarked | `lookalike.py` (`scan_identity_pairs`, `top_identity_pairs`); `test_pair_scan_equals_a_brute_force_double_loop`, `test_listed_pairs_are_different_people_ranked_most_alike_first_with_their_decision` |
| Reproducible challenge set with provenance, labels, split definitions, generation strategy, inclusion criteria and counts; "similar embeddings" kept distinct from "similar clothing" | Done | `result.challenge_set.definition/counts`; `test_a_run_has_every_section_and_labels_what_it_is`; per-pair clothing-colour proxy |
| Baseline vs improved on the same held-out examples; no invented improvement | **Partly** | comparison machinery done and tested (`test_a_clean_checkpoint_is_compared_on_the_very_same_pairs…`, leakage refusal, dev-split refusal); **no fine-tuned checkpoint has been trained**, so the screen says "no comparison" |
| Failure explanation: observed error vs hypothesised cause kept apart | Done | `inspect_failures`, `explain_failure`; `test_every_hypothesis_is_labelled_unproven_and_tied_to_a_number`, `test_failures_have_observed_facts_and_unproven_hypotheses_and_counts_cover_all` |
| Export: experiment ID, model, dataset/split, thresholds, metrics, latency, examples, limitations, reproducibility; CSV and JSON | Done (PDF **not done**, optional) | `lookalike_export.py`; `test_every_export_format_is_downloadable_and_parseable`; spreadsheet-formula guard |

### §7-8 Datasets, evaluation

| Requirement | Status | Where / evidence |
|---|---|---|
| Public benchmark adapter, layout documented, identity-aware splits, cross-camera protocol, curated low-variance subset (documented method, counts) | Done, not benchmarked | `evaluation/datasets.py`, `protocol.py`, `hard_subset.py`; **Market-1501 has not been run** (you supply it) |
| No synthetic result presented as a benchmark | Done | `kind: smoke_test` labelling in results, exports and UI; `test_smoke_datasets_are_never_presented_as_benchmarks` |
| TA/FA/FR/TR, TAR/FAR, precision/recall, ROC, AUC, FAR at fixed recall, latency, metadata; precise denominators | Done | `metrics.py`, [METRICS.md](METRICS.md); hand-computed tests (`test_metrics.py`, 23) |
| Ablations with real contributions; machine-readable results; visual comparison | Done, not benchmarked | six variants; `test_full_run_produces_all_variants_and_selects_on_calibration`; hard-negative mining / margin-loss *training* variants need a trained checkpoint (**not available**) |

### §9-11 Interface, screens, interaction contract

| Requirement | Status | Where / evidence |
|---|---|---|
| Graphite + restrained crimson workstation look; original logo (sidebar, header, favicon, loading screen, empty states, reports); not an official ZED product | Done | [DESIGN.md](DESIGN.md); `Brand.tsx`, `favicon.svg`, `report.py`; test `names the product, carries the tagline and says it is not an official Zed Digital product` |
| Responsive desktop → phone, no horizontal overflow | Done | scripted browser audit: 10 routes at 360 / 390 / 768 / 1024 / 1440 px and every lab tab, no overflow ([DESIGN.md §5](DESIGN.md)) |
| **A** Command Center - real state, first-run guidance; since 2026-10-13 also the **home page**: the essentials first and a built-in open-set example | Done | `CommandCenterPage.tsx`, `features/home/Essentials.tsx`, `features/demo/`; `pages.test.tsx`, `labs.test.tsx`, `demo.test.tsx` (see the next section) |
| **B** Identity Gallery - add, upload, preview, search, filter/sort, details, remove with confirmation, rebuild, errors | Done | `GalleryPage.tsx`; gallery tests |
| **C** Match Studio - upload, validate, detect, select, match, ranked candidates, thresholds, MATCH/UNKNOWN/REVIEW, explanation, time, retry, export record, query-vs-reference | Done | `MatchStudioPage.tsx`; `reid.test.tsx`; `test_a_decision_record_can_be_downloaded_as_json_and_csv` |
| **D** Video Explorer - upload/validate, sampling, progress, cancel, sampled frames, detections, per-frame decisions, timestamps, latency, errors; **not labelled as tracking** | Done | `VideoPage.tsx`, `video_service.py`; 47 API tests incl. real AVI files; 10 UI tests |
| **E** Lookalike Failure Lab - dataset/model selection, challenge set, difficult pairs, baseline/improved runs, metric comparison, false accepts/rejects, threshold effects, export; "not runnable" states | Done (improved model: see §6) | `LookalikePage.tsx` + `features/lookalike/`; 15 UI tests |
| **F** Evaluation Lab - ROC, FAR-vs-TAR, fixed-recall point, **threshold sandbox**, metric cards, ablations, dataset metadata, history, latency, exports | Done | `EvaluationPage.tsx`, `ThresholdSandbox.tsx`; 5 sandbox UI tests |
| **G** Model & System Settings - model, provenance, version, dimensions, device, readiness, thresholds, calibration status, dataset paths (relative), runtime config, health, loading errors; experimental vs validated; destructive actions confirmed | Done | `SettingsPage.tsx`, `SystemPanel.tsx`, `ModelPanel.tsx`; 3 UI tests |
| No dead buttons, fake loading, `alert()`, or links to nowhere; validation, loading, disabled, success, error, empty states, confirmations, retry, keyboard access, labels, focus, tooltips | Done | every control on the new screens is exercised by a UI test that asserts the request that is sent; navigation links are asserted individually. **Not** an exhaustive automated crawl |

### §12-15 Backend, privacy, performance, tests

| Requirement | Status | Where / evidence |
|---|---|---|
| Modular typed routes: health, readiness, enrollment, listing, deletion, matching, **video**, evaluation, thresholds, experiment results, exports; validation, status codes, central errors, limits, safe paths, CORS, model cache, structured logging, persistent experiments, API docs | Done | `/api/docs`; `test_api_*` |
| Database migrations | **Not done** (SQLite `create_all`; stated as a limitation) | README §20 |
| Embeddings from incompatible models cannot be compared silently | Done | fingerprint per embedding; `test_changing_the_model_marks_embeddings_stale_until_rebuilt`; `check_embedding` |
| Privacy: authorised data, validated uploads, size and video-length limits, no leaked paths/secrets, deletion, auditable changes, retention documented, warning that matches can be wrong. NOTE: the original brief excluded face recognition; the user asked for it explicitly on 2026-10-13, so it was added as a switchable mode with biometric-data safeguards (SECURITY_AND_PRIVACY.md §4a) | Done | [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) (§3a video); `test_files_that_are_not_videos_are_refused_by_their_content_not_their_name`, `test_the_upload_is_deleted_and_previews_are_served_only_for_real_frames` |
| Measured performance on the available hardware; benchmark script; no real-time promise | Done (CUDA optional, untested; ONNX/TensorRT not done) | [PERFORMANCE.md](PERFORMANCE.md); `scripts/benchmark_latency.py` |
| The 20 required test topics | Done | 1 known match `test_enrolled_person_is_accepted_with_real_scores` · 2 unknown `test_a_stranger_is_rejected_even_though_a_nearest_neighbour_exists` · 3 empty gallery `test_empty_gallery_gives_unknown_not_an_error` · 4 invalid image `test_non_image_upload_is_unsupported_media` · 5 corrupted `test_truncated_image_is_rejected`, `test_a_corrupted_video_is_refused_and_leaves_nothing_behind` · 6-8 invalid / wrong-dimension / zero-norm embedding `test_embedding_validation.py` · 9 several references `test_identity_score_is_the_best_of_its_images`, `test_index_search_returns_ranked_identities_with_best_reference_image` · 10 threshold boundary `test_score_at_or_above_threshold_is_accepted`, `test_the_threshold_boundary_is_inclusive_like_the_live_engine` · 11 ambiguity `test_ambiguous_twins_trigger_review_when_a_margin_rule_is_set` · 12 calibration `test_calibration_uses_only_the_calibration_split_and_can_be_applied` · 13 test isolation `test_calibration_run_never_embeds_a_test_image` · 14 metrics `test_metrics.py` · 15 API validation `test_invalid_policy_values_are_rejected` and others · 16 model-loading failure `test_missing_weights_file_gives_an_actionable_message`, `test_corrupted_weights_are_rejected_by_checksum` · 17 CPU inference `test_real_model_is_verified_and_reports_its_provenance` · 18 deletion `test_delete_requires_confirmation_and_removes_the_files` · 19 video errors `test_api_lab_and_video.py` · 20 persistence and model-version compatibility `test_changing_the_model_marks_embeddings_stale_until_rebuilt`, `test_a_damaged_stored_reference_is_set_aside…` |
| Integration test of the whole workflow | Done | enrol → upload → detect → embed → compare → decide → record → display: `test_api_reid.py` (API) + `pages.test.tsx` (UI against a pretend server) + the real-model end-to-end runs below |

## Face + body matching (added 2026-10-13 at the user's request)

The original brief excluded face recognition; the user then asked for it explicitly ("it only watches dress ... it needs face, hair, skin tone, body structure ... like mobile biometrics").
It was added as a **switchable mode with biometric-data safeguards**, and the earlier "no faces" statements in the documentation were corrected. Honest scope: this is 2-D photo matching, not a phone's depth-sensing Face ID.

| Requirement (user's words, interpreted) | Status | Where / evidence |
|---|---|---|
| A different person in the same clothes must not be accepted | Done | the face decides when a usable face is visible: `cv/open_set/multicue.py`; `test_SAME_CLOTHES_DIFFERENT_FACE_is_not_a_match`, `test_SAME_CLOTHES_a_stranger_is_unknown`, `test_the_body_only_policy_would_have_accepted_that_stranger`; end to end on real photos `scripts/verify_face_vs_body.py` (clothing-only accepted 48 of 60 strangers; face + body 0 of 60) |
| Analyse the face, hair, skin tone, clothing colour and body structure | Done (face and body decide; hair, skin tone and clothing colours are shown as supporting cues) | face fingerprint (YuNet + SFace) `cv/face/engine.py`; body fingerprint (OSNet); colour cues `cv/face/appearance.py` - **display only, never part of the decision** (uncalibrated; lighting and clothes change) - `test_colours_are_named_and_compared`, `test_skin_and_hair_need_a_face_and_are_skipped_otherwise` |
| Accurate face matching | Done and **measured**, with limits | LFW 10-fold accuracy 98.93 % ± 0.35, a face found in 7,701 of 7,701 pictures (`docs/results/face_lfw.json`, `scripts/evaluate_face_lfw.py`); threshold chosen by a fixed rule on 4.5 M stranger pairs ([FACE_AND_BODY_MATCHING.md](FACE_AND_BODY_MATCHING.md) §4) |
| "Like mobile biometrics" | **Not claimed** | no depth sensor, no liveness check, stated on every relevant screen and document |
| Open-set behaviour kept (strangers are UNKNOWN, uncertain cases go to a person) | Done | UNKNOWN / REVIEW rules in `multicue.py`; unit tests `TestFaceDecides`, `TestBodyOnlyFallback`, `TestMixedGallery` |
| A face that cannot be used is reported, not guessed | Done | usable-face checks (size, confidence, turn, sharpness): `cv/face/engine.py`; `test_a_tiny_face_in_the_query_is_unusable_and_explained`, `test_a_tiny_face_is_stored_as_weak_and_not_used` |
| Works for photos AND video | Done | one shared decision function `services/matching.py`; real clip `demo/samples/clip_faces.avi` → MATCH / UNKNOWN / MATCH |
| Existing galleries keep working | Done | `add_missing_columns` upgrades the database in place; faces of older photos are analysed at start-up or with *Analyse faces*; `test_new_columns_are_added_to_an_existing_database_without_losing_rows`, `test_faces_are_added_to_identities_enrolled_before_face_matching` |
| Works (and says so) without the face models; can be switched off | Done | `test_a_face_policy_without_face_models_matches_on_the_body_and_says_so`, `test_switching_face_matching_off_in_the_settings` |
| Consent and deletion for biometric data | Done | enrolment text; deletion removes face records `test_deleting_an_identity_removes_its_faces`; [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) §4a |
| Understandable by people who did not write the code | Done | in-app **How it works** page; [JURY_GUIDE.md](JURY_GUIDE.md); the demo pack (`demo/`: PDF guide, 15-slide deck, runnable scenarios with real outputs) |

## Home page and built-in open-set example (added 2026-10-13 at the user's request)

The user asked that the home page show "the project's highlighted things as a demo", because an interviewer only looks at what they need to analyse: the essentials (enroll people, match photos) and the open-set analysis, without navigating around or preparing photos.

| Requirement (user's words, interpreted) | Status | Where / evidence |
|---|---|---|
| The essentials first on the home page: enroll people, match photos | Done | `features/home/Essentials.tsx` (three cards that tick themselves from real data; hint to enroll before matching); `demo.test.tsx` *leads with enroll / match / open-set analysis...*, *shows what is enrolled...*, *warns that matching a photo is pointless until someone is enrolled* |
| An example demo that shows the open-set analysis, on the home page, with no setup | Done | `features/demo/OpenSetExample.tsx`; backend `GET /api/demo`, `POST /api/demo/prepare`, `POST /api/demo/cases/{id}` (`services/demo_service.py`, `demo/samples/demo_manifest.json`); `demo.test.tsx` *runs the example photo by photo and lays out the comparison* |
| Known people, strangers **and strangers in the same clothes** | Done | 13 public-domain photos in four groups; three same-suit strangers added to `demo/prepare_faces.py` (licences checked by the script; credits in `demo/samples/SOURCES.md`) |
| Face + body shown against clothes-only on the same photos | Done | both decisions come from the real `decide_person` (`test_a_stranger_in_the_same_clothes_is_the_open_set_failure_clothes_alone_cannot_avoid`, `test_a_known_person_in_new_clothes_is_matched_by_the_face_and_missed_by_clothes`) |
| Results readable at a glance | Done | comparison table with n-of-m and tick / cross, two score plots with the threshold line, a conclusion sentence written from the counts, a "move the face line" slider, every photo with both answers and the reason (`Comparison.tsx`, `Analysis.tsx`, `summary.ts`; `summary.test.ts`) |
| Never touches the user's data | Done | private in-memory gallery; `test_the_real_gallery_history_and_audit_trail_are_untouched`, `test_the_example_people_are_not_findable_by_a_real_query`, `test_only_files_named_in_the_manifest_are_served`, `test_path_traversal_is_impossible` |
| Honest about what it proves | Done | the card, the jury guide and [OPEN_SET_EXAMPLE.md](OPEN_SET_EXAMPLE.md) say it is a 13-photo demonstration, not a benchmark; portraits are outside the body model's design; thresholds unvalidated |
| Reproducible from the command line | Done | `demo/run_open_set_example.py` → `docs/results/open_set_example.json` (live run, real models: face + body 13 of 13; clothes-only 4 of 13, 3 of 3 same-suit strangers accepted) |
| The manual and the presentation show it | Done | user manual chapter "Try the example first" (3 pages, real screenshots); jury deck slide 9; JURY_GUIDE §5 demo script starts with the example |

## Test results

Last full run on the development machine (Windows 10, Python 3.14.4, Node 24.21, 2-core CPU), 2026-10-13:

| Suite | Result |
|---|---|
| Backend `pytest` | **427 passed** (339 before face matching + **54 in `test_face_matching.py`** + **34 in `test_demo.py`** (the built-in example): decision rules 27, enrolment 6, matching 9, fallback 3, upgrading old galleries 3, database upgrade 1, colour cues 3, padding 2) - api_basics 19 · api_config_and_jobs 33 · api_gallery 23 · **api_lab_and_video 47** · api_reid 24 · confidence 5 · decision_engine 24 · **embedding_validation 21** · evaluation_pipeline 23 · imaging_quality 23 · **lookalike 25** · metrics 23 · ranking_and_index 9 · **sandbox 17** · training_and_model 23 (incl. 5 real-model tests) |
| Frontend `vitest` | **157 passed** (114 before + **16 in `face.test.tsx`** + **27 for the home-page example**: `demo.test.tsx` 15, `summary.test.ts` 12) - pages 43 · **labs 39** · **demo 15** · **demo summary 12** · reid components 11 · ui components 9 · lib 6 · http client 6 |
| TypeScript `tsc --noEmit` (strict) | no errors |
| Production build | succeeds |
| Real-model end-to-end (live server, real detector + OSNet, public-domain street photo) | enrolled person accepted at similarity 0.957 (and 0.937 on the mirrored photo); a different photo's four people → three `unknown` (0.64 / 0.57 / 0.55), one `review required` (cut off by the frame, 0.45); identical scores on two separate runs |
| Real-model end-to-end, Video Explorer (live server, real detector + OSNet, real AVI cut from street photos) | enrolled person MATCH at 0.938 and 0.951, the five people in a different scene all UNKNOWN (0.47-0.61 < 0.70), upload deleted afterwards, 0.74-1.68 s processing per frame (same photo for both match frames: it proves the pipeline and the decisions, not accuracy) |
| Real-model end-to-end, Lookalike Failure Lab (smoke-test set, 800 images) | ran in 73 s; raised both warnings (smoke test; target not reached); 24 hard comparisons all accepted, all-pairs rate 38 % (the cartoon people cannot be separated - the *correct* result for such data); sandbox, five exports and image serving verified; path traversal returned 404 |
| Real-model end-to-end, face + body (live server, real YuNet + SFace + OSNet) | 12 of 12 demo scenarios behave as intended (`demo/run_demo.py --lab`): the same person in different clothes and up to 12 years later → MATCH (face 0.57 - 0.73); strangers → UNKNOWN (face 0.21 - 0.26); no usable face → REVIEW; video MATCH / UNKNOWN / MATCH; same eight photos: clothing-only 3 right, face + body 8 right |
| Real-model end-to-end, built-in example (live server, real YuNet + SFace + OSNet; `demo/run_open_set_example.py`) | 13 public-domain photos: face + body right on **13 of 13** (5 known people matched, 2 no-face photos to REVIEW, 6 strangers UNKNOWN including 3 in the same suit); clothes-only right on 4 of 13 (0 of 5 known people recognised, **3 of 3 same-suit strangers accepted**). Face scores: known ≥ 0.57, strangers ≤ 0.26; clothes scores: same-suit strangers 0.78-0.81 against known people at 0.50-0.62. Whole run 5-14 s on 2 CPU cores. Report: `docs/results/open_set_example.json` |
| Real-browser checks (new screens) | graphite theme, brand and the seven-screen navigation; mistake cards on a phone; a Match Studio query with the real model and the decision-record export; sandbox moved to 0.95 → 124 changed decisions and no apply button; responsive audit clean at 360 / 390 / 768 / 1024 / 1440 px |
| UI-driven check (real browser) | enroll with consent gate → accepted match → (default threshold) a stranger wrongly accepted → calibrate → apply → stranger rejected - see [EVALUATION.md §7](EVALUATION.md) |

**What the tests do *not* show:** accuracy on real benchmark data (not run), whether any fine-tuned model is better (none has been trained), tracking of any kind (not implemented), behaviour on a GPU, behaviour under concurrent load, or any security audit beyond the listed checks.
Backend API tests substitute deterministic fakes for the neural networks; they test plumbing, rules and safety, not model quality.
