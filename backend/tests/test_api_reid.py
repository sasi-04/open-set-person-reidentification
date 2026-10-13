"""Re-identification through the real HTTP API: decisions, rejection of strangers, quality, history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select

from app.db.models import InferenceResult
from app.services import maintenance_service
from tests.fakes import BLUE, GREEN, RED, YELLOW, crop_png, detection, scene_png


def enrol_three(env):
    env.enroll("red-person", RED, n=3)
    env.enroll("green-person", GREEN, n=3)
    env.enroll("blue-person", BLUE, n=3)


def person(response):
    return response.json()["people"][0]


# ------------------------------------------------------------------- the core behaviour
def test_empty_gallery_gives_unknown_not_an_error(env):
    result = person(env.predict(crop_png(RED)))
    assert result["decision"]["outcome"] == "unknown"
    assert result["decision"]["reason_code"] == "empty_gallery"
    assert result["candidates"] == []


def test_enrolled_person_is_accepted_with_real_scores(env):
    enrol_three(env)
    body = env.predict(crop_png(RED, seed=99)).json()
    decision = body["people"][0]["decision"]
    assert decision["outcome"] == "accepted" and decision["accepted_reference_id"] == "red-person"
    assert decision["top1_score"] >= decision["accept_threshold"]
    assert decision["reason"].startswith("Accepted")
    assert [c["rank"] for c in body["people"][0]["candidates"]] == [1, 2, 3]
    assert body["people"][0]["candidates"][0]["reference_id"] == "red-person"


def test_a_stranger_is_rejected_even_though_a_nearest_neighbour_exists(env):
    enrol_three(env)
    result = person(env.predict(crop_png(YELLOW)))
    decision = result["decision"]
    assert decision["outcome"] == "unknown" and decision["accepted_reference_id"] is None
    assert decision["top1_reference_id"] is not None  # a nearest neighbour exists...
    assert decision["top1_score"] < decision["accept_threshold"]  # ...but it is NOT supported by the evidence
    assert len(result["candidates"]) == 3  # alternatives stay visible


def test_changing_the_threshold_changes_the_live_decision(env):
    enrol_three(env)
    query = crop_png(RED, seed=5)
    assert person(env.predict(query))["decision"]["outcome"] == "accepted"
    top_score = person(env.predict(query))["decision"]["top1_score"]

    env.post("/api/config/thresholds", json={"accept_threshold": min(top_score + 0.001, 1.0), "confirm": True})
    stricter = env.predict(query).json()
    assert stricter["people"][0]["decision"]["outcome"] == "unknown"
    assert stricter["policy_version"] == 2 and stricter["policy_status"] == "experimental"


def test_every_decision_records_the_policy_that_made_it(env):
    enrol_three(env)
    decision = person(env.predict(crop_png(RED)))["decision"]
    assert decision["policy_version"] == 1 and decision["policy_status"] == "unvalidated"
    assert decision["accept_threshold"] == 0.70


def test_ambiguous_twins_trigger_review_when_a_margin_rule_is_set(env):
    env.enroll("twin-a", RED, n=2)
    env.enroll("twin-b", (222, 32, 30), n=2)  # almost the same colour as twin-a
    env.post("/api/config/thresholds", json={"accept_threshold": 0.5, "min_margin": 0.30, "confirm": True})
    decision = person(env.predict(crop_png(RED, seed=3)))["decision"]
    assert decision["outcome"] == "review_required" and decision["reason_code"] == "ambiguous_margin"
    assert decision["margin"] is not None and decision["margin"] < 0.30
    assert decision["accepted_reference_id"] is None


def test_blurry_input_goes_to_review_instead_of_a_confident_answer(env):
    enrol_three(env)
    flat = crop_png(RED, noise=0.0)  # a perfectly flat image has no sharpness
    decision = person(env.predict(flat))["decision"]
    assert decision["outcome"] == "review_required" and "blurry" in decision["quality_flags"]


def test_tiny_person_is_a_processing_error_without_an_embedding(env):
    enrol_three(env)
    env.detector.boxes = []
    response = env.predict(scene_png(RED), mode="box", box="100,100,108,112")
    result = person(response)
    assert result["decision"]["outcome"] == "processing_error"
    assert result["decision"]["top1_score"] is None and result["candidates"] == []
    assert "too small" in result["decision"]["reason"]


# ------------------------------------------------------------------ detection workflow
def test_detect_endpoint_returns_boxes_and_keeps_detector_score_separate(env):
    env.detector.boxes = [detection(80, 40, 220, 360, 0.93)]
    body = env.post("/api/reid/detect", role="viewer", files={"image": ("s.png", scene_png(RED), "image/png")}).json()
    assert body["detections"][0]["detector_score"] == 0.93
    assert body["detections"][0]["box"] == [80.0, 40.0, 220.0, 360.0]
    assert "similarity" not in str(body)  # detection says nothing about identity


def test_several_people_are_each_matched_and_decided_separately(env):
    enrol_three(env)
    env.detector.boxes = [detection(10, 10, 110, 300, 0.97), detection(150, 20, 280, 330, 0.88)]
    body = env.predict(scene_png(RED), mode="all").json()
    assert len(body["people"]) == 2
    assert [p["detector_score"] for p in body["people"]] == [0.97, 0.88]
    assert all(p["decision"]["policy_version"] == 1 for p in body["people"])


def test_no_person_detected_is_a_clear_error(env):
    env.detector.boxes = []
    response = env.predict(scene_png(RED), mode="all")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "no_person_detected" and "crop" in error["message"]


def test_box_mode_matches_only_the_selected_person(env):
    enrol_three(env)
    response = env.predict(scene_png(GREEN), mode="box", box="80,40,220,360")
    assert response.status_code == 200
    assert len(response.json()["people"]) == 1
    assert response.json()["people"][0]["decision"]["top1_reference_id"] == "green-person"


def test_bad_box_is_rejected(env):
    assert env.predict(scene_png(RED), mode="box", box="1,2,3").status_code == 422
    assert env.predict(scene_png(RED), mode="box", box="a,b,c,d").status_code == 422
    assert env.predict(scene_png(RED), mode="box").status_code == 422
    assert env.predict(scene_png(RED), mode="box", box="500,500,600,600").status_code == 422  # outside the image


def test_response_reports_per_stage_timings(env):
    enrol_three(env)
    timings = env.predict(crop_png(RED)).json()["timings_ms"]
    assert {"preprocess_ms", "embed_ms", "retrieval_and_decision_ms", "total_ms"} <= set(timings)
    assert timings["total_ms"] >= timings["embed_ms"] >= 0


# ----------------------------------------------------------------------- upload safety
def test_non_image_upload_is_unsupported_media(env):
    response = env.post("/api/reid/predict", role="viewer", data={"mode": "crop"},
                        files={"image": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_text_renamed_to_png_is_still_rejected(env):
    response = env.post("/api/reid/predict", role="viewer", data={"mode": "crop"},
                        files={"image": ("evil.png", b"<script>alert(1)</script>", "image/png")})
    assert response.status_code == 415 and response.json()["error"]["code"] == "unsupported_image"


def test_oversized_image_is_refused(env):
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (env.settings.max_upload_bytes + 10)
    response = env.post("/api/reid/predict", role="viewer", data={"mode": "crop"},
                        files={"image": ("big.png", big, "image/png")})
    assert response.status_code == 413


def test_top_k_is_validated(env):
    assert env.predict(crop_png(RED), top_k="0").status_code == 422
    assert env.predict(crop_png(RED), top_k="11").status_code == 422


# --------------------------------------------------------------------------- history
def test_history_lists_requests_without_any_raw_image_data(env):
    enrol_three(env)
    first = env.predict(crop_png(RED)).json()["request_id"]
    env.predict(crop_png(YELLOW))
    page = env.get("/api/reid/history").json()
    assert page["total"] == 2 and page["items"][0]["top_outcome"] in ("accepted", "unknown")
    detail = env.get(f"/api/reid/history/{first}").json()
    assert detail["people"][0]["decision"]["outcome"] == "accepted"
    assert "embedding" not in str(detail)  # embeddings are never stored in history


def test_history_can_be_filtered_by_outcome(env):
    enrol_three(env)
    env.predict(crop_png(RED))
    env.predict(crop_png(YELLOW))
    unknown = env.get("/api/reid/history", params={"outcome": "unknown"}).json()
    assert unknown["total"] == 1
    assert env.get("/api/reid/history", params={"outcome": "bogus"}).status_code == 422


def test_stored_query_crop_is_available_then_removed_by_retention(env):
    enrol_three(env)
    request_id = env.predict(crop_png(RED)).json()["request_id"]
    url = f"/api/reid/history/{request_id}/crops/0"
    assert env.get(url).status_code == 200
    assert len(list(env.runtime.queries.root.glob("*.jpg"))) == 1

    with env.runtime.session_factory() as session:  # pretend the retention window has passed
        for result in session.scalars(select(InferenceResult)):
            result.crop_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
        maintenance_service.run_cleanup(session, env.runtime, "admin")
    assert env.get(url).status_code == 404
    assert list(env.runtime.queries.root.glob("*.jpg")) == []
    assert env.get(f"/api/reid/history/{request_id}").status_code == 200  # the scores remain


def test_query_images_are_not_stored_when_retention_is_zero(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import KEYS, make_settings
    from tests.fakes import FakeDetector, FakeExtractor

    settings = make_settings(tmp_path, query_retention_hours=0)
    with TestClient(create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())) as client:
        response = client.post("/api/reid/predict", headers={"X-API-Key": KEYS["viewer"]}, data={"mode": "crop"},
                               files={"image": ("q.png", crop_png(RED), "image/png")})
        assert response.json()["people"][0]["crop_url"] is None
        assert list((settings.data_dir / "queries").glob("*.jpg")) == []


def test_unknown_history_request_is_404(env):
    assert env.get("/api/reid/history/doesnotexist").status_code == 404


# ------------------------------------------------------------------------ overview
def test_overview_shows_real_numbers_and_honest_empty_states(env):
    empty = env.get("/api/overview").json()
    assert empty["inference"]["requests"] == 0 and empty["inference"]["acceptance_rate"] is None
    assert empty["inference"]["average_latency_ms"] is None
    assert empty["latest_evaluation"]["far"] is None and empty["latest_evaluation"]["note"] == "Not evaluated."

    enrol_three(env)
    env.predict(crop_png(RED))
    env.predict(crop_png(YELLOW))
    filled = env.get("/api/overview").json()
    assert filled["gallery"] == {"identities": 3, "images": 9}
    assert filled["inference"]["requests"] == 2 and filled["inference"]["unknown_or_rejected"] == 1
    assert filled["inference"]["acceptance_rate"] == 0.5  # 1 accepted of 2 decided
    assert filled["inference"]["average_latency_ms"] > 0
    assert np.isclose(filled["policy"]["accept_threshold"], 0.70)
