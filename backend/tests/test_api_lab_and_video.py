"""
Lookalike Failure Lab, threshold sandbox, decision-record export and Video Explorer - through the HTTP API.

Fake networks stand in for the models (see ``tests/fakes.py``), so these tests check the plumbing, the safety rules
and the honesty of the output - not how accurate the real model is. Videos are REAL files written with OpenCV and
read back with OpenCV, so the decoding, sampling and cleanup code runs for real.
"""

from __future__ import annotations

import csv
import io
import os
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.evaluation import lookalike_export
from app.main import create_app
from app.services import video_service
from tests.conftest import Env, make_settings
from tests.fakes import BLUE, GREEN, RED, FakeDetector, FakeExtractor, crop_png, detection, scene_png
from tests.test_evaluation_pipeline import make_dataset

SMALL_PROTOCOL = {"gallery_shots": 2, "dev_fraction": 0.2, "calibration_fraction": 0.3, "max_images_per_identity": 6}
SMALL_LAB = {"dataset": "toy", "protocol": SMALL_PROTOCOL, "target": {"mode": "fixed_recall", "target_recall": 0.5},
             "top_pairs": 8, "images_per_pair": 2, "max_failures": 5}


def wait_for(env, url, states=("succeeded", "failed", "cancelled"), timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = env.get(url).json()
        if run["status"] in states:
            return run
        time.sleep(0.05)
    raise AssertionError(f"{url} did not reach {states}: {run}")


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    """An app with a small labelled dataset; the background worker uses a fake extractor."""
    settings = make_settings(tmp_path)
    make_dataset(settings.datasets_dir / "toy")
    extractor = FakeExtractor(noise=0.02)
    monkeypatch.setattr("app.services.evaluation_service.make_extractor_factory", lambda *a, **k: (lambda checkpoint: extractor))
    app = create_app(settings, extractor=extractor, detector=FakeDetector())
    with TestClient(app) as client:
        yield Env(client, extractor, FakeDetector(), settings, app.state.runtime)


def start_lab(env, **overrides):
    return env.post("/api/lookalike/run", json={**SMALL_LAB, **overrides})


@pytest.fixture()
def finished_lab(lab):
    started = start_lab(lab)
    assert started.status_code == 202, started.text
    run = wait_for(lab, f"/api/lookalike/runs/{started.json()['run_id']}")
    assert run["status"] == "succeeded", run
    return lab, run


# ====================================================================================== the lab through the API
def test_a_lab_experiment_runs_in_the_background_and_returns_its_sections(finished_lab):
    env, run = finished_lab
    result = run["result"]
    assert run["kind"] == "lookalike" and run["progress"] == 1.0
    assert result["challenge_set"]["identity_pairs"] and result["models"]["baseline"]["status"] == "ok"
    assert result["models"]["improved"]["status"] == "unavailable"
    assert "sandbox" not in result and result["sandbox_available"] is True  # the bulky table is served separately
    assert run["headline"]["improved_status"] == "unavailable" and run["headline"]["challenge_far"] is not None


def test_lab_runs_appear_in_the_experiment_history_but_not_in_other_kinds(finished_lab):
    env, run = finished_lab
    assert [r["run_id"] for r in env.get("/api/lookalike/runs").json()["items"]] == [run["run_id"]]
    assert run["run_id"] in [r["run_id"] for r in env.get("/api/evaluation/runs").json()["items"]]
    assert env.get("/api/evaluation/runs", params={"kind": "evaluation"}).json()["items"] == []


def test_a_normal_evaluation_run_is_not_a_lab_experiment(lab):
    started = lab.post("/api/evaluation/run", json={"dataset": "toy", "protocol": SMALL_PROTOCOL, "bootstrap_samples": 10,
                                                    "target": {"mode": "fixed_recall", "target_recall": 0.5}}).json()
    wait_for(lab, f"/api/evaluation/runs/{started['run_id']}")
    assert lab.get(f"/api/lookalike/runs/{started['run_id']}").status_code == 404


def test_missing_dataset_and_bad_checkpoint_names_are_refused_before_any_work(lab):
    assert lab.post("/api/lookalike/run", json={"dataset": "nope"}).status_code == 404
    assert start_lab(lab, finetuned_checkpoint="../../etc/passwd.pt").status_code == 422  # a bare file name only
    missing = start_lab(lab, finetuned_checkpoint="ghost.pt")
    assert missing.status_code == 422 and "was not found" in missing.json()["error"]["message"]


def test_only_one_job_runs_at_a_time_across_all_kinds(lab):
    lab.extractor.delay = 0.05
    first = start_lab(lab)
    second = start_lab(lab)
    assert second.status_code == 409 and "already running" in second.json()["error"]["message"]
    wait_for(lab, f"/api/lookalike/runs/{first.json()['run_id']}")


def test_lab_actions_need_the_right_role_when_keys_are_on(lab):
    assert lab.post("/api/lookalike/run", role="operator", json=SMALL_LAB).status_code == 403
    assert lab.get("/api/lookalike/runs", role="viewer").status_code == 200


# ----------------------------------------------------------------------------------------------- exports
def test_every_export_format_is_downloadable_and_parseable(finished_lab):
    env, run = finished_lab
    base = f"/api/lookalike/runs/{run['run_id']}/export"
    as_json = env.get(base, params={"format": "json"})
    assert "attachment" in as_json.headers["content-disposition"] and as_json.json()["metadata"]["experiment_id"] == run["run_id"]
    assert "sandbox" in as_json.json()  # the JSON is the complete record

    pairs = list(csv.reader(io.StringIO(env.get(base, params={"format": "pairs_csv"}).text)))
    assert pairs[0][:5] == ["rank", "comparison_type", "split", "identity_a", "identity_b"] and len(pairs) > 2
    failures = env.get(base, params={"format": "failures_csv"}).text
    assert failures.splitlines()[0].startswith("model,id,observed_category") and "UNPROVEN" in failures.splitlines()[0]
    summary = {(r[0], r[1], r[2]): r[3] for r in csv.reader(io.StringIO(env.get(base, params={"format": "summary_csv"}).text))}
    assert summary[("experiment", "", "experiment_id")] == run["run_id"]
    assert ("challenge_set", "baseline", "far_all_pairs_reference") in summary
    markdown = env.get(base, params={"format": "md"}).text
    assert markdown.startswith("# Lookalike Failure Lab") and "## Limitations" in markdown and "## Reproducibility" in markdown


def test_a_format_that_makes_no_sense_for_the_kind_is_refused_with_the_valid_ones(finished_lab):
    env, run = finished_lab
    response = env.get(f"/api/evaluation/runs/{run['run_id']}/report", params={"format": "html"})
    assert response.status_code == 422 and "pairs_csv" in response.json()["error"]["message"]


def test_spreadsheet_formulas_in_labels_are_neutralised():
    assert lookalike_export._cell("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert lookalike_export._cell("+1") == "'+1" and lookalike_export._cell("@SUM(A1)") == "'@SUM(A1)"
    assert lookalike_export._cell("0042") == "0042" and lookalike_export._cell(None) == "" and lookalike_export._cell(0.5) == 0.5


# ----------------------------------------------------------------------------------------- image serving
def test_the_lab_serves_only_images_the_experiment_recorded(finished_lab):
    env, run = finished_lab
    ref = run["result"]["challenge_set"]["identity_pairs"][0]["image_a"]
    served = env.get(f"/api/lookalike/runs/{run['run_id']}/image", params={"ref": ref})
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg" and served.content[:2] == b"\xff\xd8"
    for bad in ("../toy/dataset.json", "dataset.json", "P000/does-not-exist.png", "..\\..\\x", "/etc/passwd"):
        assert env.get(f"/api/lookalike/runs/{run['run_id']}/image", params={"ref": bad}).status_code == 404


# =========================================================================================== threshold sandbox
def test_the_sandbox_describes_what_it_can_do_and_never_writes_policy(finished_lab):
    env, run = finished_lab
    info = env.get(f"/api/evaluation/runs/{run['run_id']}/sandbox").json()
    assert info["writes_policy"] is False and set(info["splits"]) == {"calibration", "test"}
    assert info["reference"]["threshold"] == run["result"]["models"]["baseline"]["rule"]["threshold"]


def test_trying_thresholds_changes_the_counts_but_never_the_active_policy(finished_lab):
    env, run = finished_lab
    before = env.get("/api/config").json()["policy"]
    url = f"/api/evaluation/runs/{run['run_id']}/sandbox"
    loose = env.post(url, json={"split": "calibration", "threshold": 0.0}).json()
    strict = env.post(url, json={"split": "calibration", "threshold": 1.0}).json()
    assert loose["trial"]["metrics"]["far"] == 1.0 and strict["trial"]["metrics"]["far"] == 0.0
    assert loose["decisions_changed"] >= 0 and loose["writes_policy"] is False and loose["changed_examples"] is not None
    assert env.get("/api/config").json()["policy"] == before  # untouched
    assert env.get("/api/config/history").json()[0]["version"] == before["version"]


def test_the_test_split_view_carries_the_tuning_warning(finished_lab):
    env, run = finished_lab
    body = env.post(f"/api/evaluation/runs/{run['run_id']}/sandbox", json={"split": "test", "threshold": 0.9}).json()
    assert "tuning on the test set" in body["warning"]


def test_sandbox_inputs_are_validated(finished_lab):
    env, run = finished_lab
    url = f"/api/evaluation/runs/{run['run_id']}/sandbox"
    for bad in ({"split": "dev", "threshold": 0.5}, {"split": "test", "threshold": 1.5}, {"split": "test", "threshold": "high"},
                {"split": "test", "threshold": 0.5, "min_margin": -1}, {"threshold": 0.5, "margin_action": "delete"}):
        assert env.post(url, json=bad).status_code == 422


def test_runs_without_a_sandbox_say_so(lab):
    started = lab.post("/api/evaluation/calibrate", json={"dataset": "toy", "protocol": SMALL_PROTOCOL,
                                                           "target": {"mode": "fixed_recall", "target_recall": 0.5}}).json()
    wait_for(lab, f"/api/evaluation/runs/{started['run_id']}")
    response = lab.get(f"/api/evaluation/runs/{started['run_id']}/sandbox")
    assert response.status_code == 404 and "no threshold sandbox" in response.json()["error"]["message"]
    assert lab.get(f"/api/evaluation/runs/{'a' * 32}/sandbox").status_code == 404


def test_an_ordinary_evaluation_run_also_gets_a_sandbox_whose_reference_is_its_calibrated_rule(lab):
    started = lab.post("/api/evaluation/run", json={"dataset": "toy", "protocol": SMALL_PROTOCOL, "bootstrap_samples": 10,
                                                    "target": {"mode": "fixed_recall", "target_recall": 0.5}}).json()
    run = wait_for(lab, f"/api/evaluation/runs/{started['run_id']}")
    info = lab.get(f"/api/evaluation/runs/{run['run_id']}/sandbox").json()
    selected = run["result"]["variants"]["thr_margin"]["per_seed"][0]["selected"]
    assert info["reference"]["threshold"] == selected["threshold"]
    replay = lab.post(f"/api/evaluation/runs/{run['run_id']}/sandbox",
                      json={"split": "test", "threshold": selected["threshold"], "min_margin": selected["min_margin"]}).json()
    assert replay["decisions_changed"] == 0
    assert replay["trial"]["metrics"]["far"] == run["result"]["variants"]["thr_margin"]["per_seed"][0]["test"]["far"]


# ======================================================================================= decision-record export
def test_a_decision_record_can_be_downloaded_as_json_and_csv(env):
    env.enroll("p-red", RED)
    env.detector.boxes = [detection(80, 40, 220, 360)]
    prediction = env.predict(scene_png(RED), mode="all").json()
    base = f"/api/reid/history/{prediction['request_id']}/export"
    as_json = env.get(base, params={"format": "json"})
    assert "attachment" in as_json.headers["content-disposition"] and "not a probability" in as_json.json()["notice"]
    person = as_json.json()["record"]["people"][0]
    assert person["decision"]["outcome"] == "accepted" and person["candidates"][0]["reference_id"] == "p-red"
    rows = list(csv.DictReader(io.StringIO(env.get(base, params={"format": "csv"}).text)))
    assert len(rows) == 1 and rows[0]["outcome"] == "accepted" and rows[0]["top1_reference_id"] == "p-red"
    assert "not a probability" in rows[0]["notice"]
    assert env.get(base, params={"format": "xml"}).status_code == 422
    assert env.get("/api/reid/history/doesnotexist/export").status_code == 404


# =============================================================================================== video helpers
def write_avi(path: Path, colours, *, fps=10, size=(320, 240), box=(110, 20, 210, 220), seed=0) -> Path:
    """A real MJPG .avi: one frame per colour, a textured person-shaped rectangle on a grey background."""
    rng = np.random.default_rng(seed)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    assert writer.isOpened()
    for colour in colours:
        frame = np.clip(rng.normal(128, 8, (size[1], size[0], 3)), 0, 255)
        x1, y1, x2, y2 = box
        frame[y1:y2, x1:x2] = np.clip(np.array(colour) + rng.normal(0, 14, (y2 - y1, x2 - x1, 3)), 0, 255)
        writer.write(cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_RGB2BGR))
    writer.release()
    return path


def upload(env, path: Path, *, name=None, **form):
    with path.open("rb") as handle:
        return env.post("/api/video/analyze", files={"video": (name or path.name, handle, "video/x-msvideo")},
                        data={"every_seconds": "0.5", "max_frames": "30", **{k: str(v) for k, v in form.items()}})


def video_env_with_person(env):
    env.enroll("p-red", RED)
    env.detector.boxes = [detection(110, 20, 210, 220)]
    return env


@pytest.fixture()
def clip(tmp_path):
    # 2 seconds at 10 fps; sampled every 0.5 s -> frames 0, 5, 10, 15: red, red, blue, blue
    return write_avi(tmp_path / "clip.avi", [RED] * 10 + [BLUE] * 10)


# =============================================================================================== Video Explorer
def test_video_limits_are_published_for_the_interface(env):
    limits = env.get("/api/video/limits").json()
    assert limits["detector_ready"] is True and ".avi" in limits["extensions"] and limits["max_frames"] >= 1
    assert "not multi-object tracking" in limits["scope"]


def test_a_video_is_sampled_and_every_frame_gets_its_own_honest_decision(env, clip):
    video_env_with_person(env)
    started = upload(env, clip)
    assert started.status_code == 202, started.text
    job = wait_for(env, f"/api/video/jobs/{started.json()['run_id']}")
    assert job["status"] == "succeeded", job
    result = job["result"]

    frames = result["frames"]
    assert [f["time_seconds"] for f in frames] == [0.0, 0.5, 1.0, 1.5]  # one frame every 0.5 s of a 10 fps clip
    outcomes = [f["people"][0]["outcome"] for f in frames]
    assert outcomes == ["accepted", "accepted", "unknown", "unknown"]
    assert frames[0]["people"][0]["accepted_reference_id"] == "p-red"
    for frame in frames:
        assert {"decode_ms", "detect_ms", "embed_ms", "match_ms", "processing_ms"} <= set(frame["timings_ms"])

    summary = result["summary"]
    assert summary["frames_processed"] == 4 and summary["outcomes"] == {"accepted": 2, "unknown": 2}
    (seen,) = summary["identities_seen"]
    assert seen["reference_id"] == "p-red" and seen["frames"] == 2 and seen["last_seen_seconds"] == 0.5
    assert summary["latency_ms"]["processing_per_frame"]["n"] == 4
    assert any("NOT followed from frame to frame" in note and "not multi-object tracking" in note for note in result["notes"])
    assert result["metadata"]["sampling"]["every_n_frames"] == 5 and result["metadata"]["video"]["fps"] == 10.0
    assert job["headline"]["people_detected"] == 4


def test_the_upload_is_deleted_and_previews_are_served_only_for_real_frames(env, clip):
    video_env_with_person(env)
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    assert list(env.settings.video_upload_dir.glob("*")) == []  # the original video is never kept
    preview = env.get(f"/api/video/jobs/{job['run_id']}/frames/0")
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg" and preview.content[:2] == b"\xff\xd8"
    assert env.get(f"/api/video/jobs/{job['run_id']}/frames/99").status_code == 404
    assert env.get(f"/api/video/jobs/{'0' * 32}/frames/0").status_code == 404


def test_only_real_job_ids_can_name_a_preview_folder(tmp_path):
    from app.core.errors import NotFound

    settings = make_settings(tmp_path)
    for bad in ("../x", "..\\..\\x", "", "A" * 32, "a" * 31, "a" * 33, "a" * 31 + "/"):
        with pytest.raises(NotFound):
            video_service.frame_folder(settings, bad)
    assert video_service.frame_folder(settings, "a" * 32).parent == settings.video_frame_dir


def test_video_jobs_have_their_own_list_and_stay_out_of_the_experiment_history(env, clip):
    video_env_with_person(env)
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    assert [j["run_id"] for j in env.get("/api/video/jobs").json()["items"]] == [job["run_id"]]
    assert env.get("/api/evaluation/runs").json()["items"] == []
    assert env.get(f"/api/lookalike/runs/{job['run_id']}").status_code == 404
    assert env.get(f"/api/video/jobs/{'f' * 32}").status_code == 404


def test_video_exports_cover_every_person_in_every_frame(env, clip):
    video_env_with_person(env)
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    rows = list(csv.DictReader(io.StringIO(env.get(f"/api/video/jobs/{job['run_id']}/export", params={"format": "frames_csv"}).text)))
    assert [r["outcome"] for r in rows] == ["accepted", "accepted", "unknown", "unknown"] and rows[1]["time_seconds"] == "0.5"
    assert env.get(f"/api/video/jobs/{job['run_id']}/export").json()["kind"] == "video"
    assert env.get(f"/api/video/jobs/{job['run_id']}/export", params={"format": "pdf"}).status_code == 422


def test_an_empty_gallery_means_unknown_never_an_invented_match(env, clip):
    env.detector.boxes = [detection(110, 20, 210, 220)]
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    assert job["result"]["summary"]["outcomes"] == {"unknown": 4}
    assert any("gallery is empty" in note for note in job["result"]["notes"])


def test_frames_with_nobody_in_them_are_recorded_as_empty(env, clip):
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")  # the detector finds nobody
    assert [f["people"] for f in job["result"]["frames"]] == [[], [], [], []] and job["result"]["summary"]["people_detected"] == 0


def test_the_maximum_number_of_frames_is_respected(env, clip):
    video_env_with_person(env)
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip, max_frames=2).json()['run_id']}")
    assert job["result"]["summary"]["frames_processed"] == 2


# ---------------------------------------------------------------------------- refusing bad uploads
def test_files_that_are_not_videos_are_refused_by_their_content_not_their_name(env, tmp_path):
    fake = tmp_path / "evil.mp4"
    fake.write_bytes(b"MZ\x90\x00this is an executable pretending to be a video" * 40)
    response = upload(env, fake)
    assert response.status_code == 415 and "content" in response.json()["error"]["message"]
    assert upload(env, fake, name="clip.exe").status_code == 415  # unsupported extension
    assert list(env.settings.video_upload_dir.glob("*")) == []


def test_a_corrupted_video_is_refused_and_leaves_nothing_behind(env, tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\x00\x00\x00\x18ftypmp42" + os.urandom(4000))  # looks like MP4 for 12 bytes, then garbage
    response = upload(env, broken)
    assert response.status_code == 415 and "could not be" in response.json()["error"]["message"]
    assert list(env.settings.video_upload_dir.glob("*")) == []


def test_an_empty_upload_is_refused(env, tmp_path):
    empty = tmp_path / "empty.avi"
    empty.write_bytes(b"")
    assert upload(env, empty).status_code == 422


def test_an_oversized_video_is_refused_while_it_is_being_read(tmp_path):
    settings = make_settings(tmp_path, max_video_mb=1)
    app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())
    with TestClient(app) as client:
        slightly_over = tmp_path / "over.mp4"  # passes the cheap request-size check, so the streaming limit must catch it
        slightly_over.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (1024 * 1024 + 300_000))
        with slightly_over.open("rb") as handle:
            response = client.post("/api/video/analyze", headers={"X-API-Key": "viewer-secret"},
                                   files={"video": ("over.mp4", handle, "video/mp4")})
    assert response.status_code == 413 and "1 MB limit" in response.json()["error"]["message"]
    assert list(settings.video_upload_dir.glob("*")) == []  # the partly written file was removed


def test_an_absurdly_large_video_is_refused_before_it_is_read_at_all(tmp_path):
    settings = make_settings(tmp_path, max_video_mb=1)
    app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())
    with TestClient(app) as client:
        huge = tmp_path / "huge.mp4"
        huge.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (3 * 1024 * 1024))
        with huge.open("rb") as handle:
            response = client.post("/api/video/analyze", headers={"X-API-Key": "viewer-secret"},
                                   files={"video": ("huge.mp4", handle, "video/mp4")})
    assert response.status_code == 413 and response.json()["error"]["code"] == "payload_too_large"
    assert list(settings.video_upload_dir.glob("*")) == []


def test_a_too_long_video_is_refused_before_any_processing(tmp_path, clip):
    settings = make_settings(tmp_path / "limited", max_video_seconds=1)  # the clip is 2 s long
    app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())
    with TestClient(app) as client:
        env = Env(client, FakeExtractor(), FakeDetector(), settings, app.state.runtime)
        response = upload(env, clip)
    assert response.status_code == 422 and "limit is 1 s" in response.json()["error"]["message"]
    assert list(settings.video_upload_dir.glob("*")) == []


@pytest.mark.parametrize("form", [{"every_seconds": 0}, {"every_seconds": 500}, {"every_seconds": "nan"}, {"max_frames": 0},
                                  {"max_frames": 100000}])
def test_nonsense_sampling_settings_are_refused(env, clip, form):
    assert upload(env, clip, **form).status_code == 422


def test_video_needs_the_detector_and_says_so(tmp_path, clip):
    settings = make_settings(tmp_path / "nodet")
    app = create_app(settings, extractor=FakeExtractor(), detector=None)
    with TestClient(app) as client:
        env = Env(client, FakeExtractor(), FakeDetector(), settings, app.state.runtime)
        response = upload(env, clip)
    assert response.status_code == 503 and response.json()["error"]["code"] == "model_unavailable"


# ------------------------------------------------------------------ the job lifecycle
def test_a_running_video_job_can_be_cancelled_and_leaves_no_previews(env, tmp_path):
    video_env_with_person(env)
    env.extractor.delay = 0.25  # slow the model so there is time to cancel
    long_clip = write_avi(tmp_path / "long.avi", [RED] * 40)
    job = upload(env, long_clip).json()
    wait_for(env, f"/api/video/jobs/{job['run_id']}", states=("running",))
    time.sleep(0.4)
    assert env.post(f"/api/video/jobs/{job['run_id']}/cancel", role="viewer").status_code == 200
    final = wait_for(env, f"/api/video/jobs/{job['run_id']}")
    assert final["status"] == "cancelled" and final["result"] is None
    assert not (env.settings.video_frame_dir / job["run_id"]).exists()
    assert list(env.settings.video_upload_dir.glob("*")) == []


def test_a_second_upload_while_one_is_running_is_refused_and_not_kept(env, tmp_path):
    video_env_with_person(env)
    env.extractor.delay = 0.2
    first = upload(env, write_avi(tmp_path / "a.avi", [RED] * 30)).json()
    second = upload(env, write_avi(tmp_path / "b.avi", [RED] * 30, seed=1))
    assert second.status_code == 409
    wait_for(env, f"/api/video/jobs/{first['run_id']}", states=("running", "succeeded"))
    env.post(f"/api/video/jobs/{first['run_id']}/cancel", role="viewer")
    wait_for(env, f"/api/video/jobs/{first['run_id']}")
    assert list(env.settings.video_upload_dir.glob("*")) == []


def test_finished_jobs_can_be_deleted_with_their_previews_but_running_ones_cannot(env, clip, tmp_path):
    video_env_with_person(env)
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    folder = env.settings.video_frame_dir / job["run_id"]
    assert folder.is_dir()
    assert env.delete(f"/api/video/jobs/{job['run_id']}", role="viewer").status_code == 403  # operators and above only
    assert env.delete(f"/api/video/jobs/{job['run_id']}", role="operator").status_code == 204
    assert not folder.exists() and env.get(f"/api/video/jobs/{job['run_id']}").status_code == 404
    actions = [e["action"] for e in env.get("/api/audit", role="admin").json()]
    assert "video.delete" in actions and "video.start" in actions


def test_expired_previews_and_stray_uploads_are_removed_by_the_cleanup(env, clip):
    video_env_with_person(env)
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    folder = env.settings.video_frame_dir / job["run_id"]
    stray = env.settings.video_upload_dir / ("a" * 32 + ".avi")
    stray.write_bytes(b"left over from a crash")
    long_ago = time.time() - 3 * 24 * 3600
    os.utime(folder, (long_ago, long_ago)), os.utime(stray, (long_ago, long_ago))
    result = env.post("/api/maintenance/cleanup").json()
    assert result["orphan_files_removed"] >= 2 and not folder.exists() and not stray.exists()


def test_previews_are_not_stored_at_all_when_retention_is_zero(tmp_path, clip):
    settings = make_settings(tmp_path / "noretain", query_retention_hours=0)
    app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())
    with TestClient(app) as client:
        env = Env(client, FakeExtractor(), FakeDetector(), settings, app.state.runtime)
        env.detector = app.state.runtime.detector
        env.detector.boxes = [detection(110, 20, 210, 220)]
        job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    assert job["result"]["frames"][0]["thumbnail"] is None and not (settings.video_frame_dir / job["run_id"]).exists()
    assert any("retention is set to 0" in note for note in job["result"]["notes"])


def test_the_video_job_cannot_be_reached_through_the_lab_or_a_missing_id(env):
    assert env.post(f"/api/video/jobs/{'a' * 32}/cancel", role="viewer").status_code == 404


# ------------------------------------------------------------------------------ small unit checks
def test_container_sniffing_recognises_real_videos_and_rejects_everything_else():
    assert video_service.sniff_container(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 20) == "mp4"
    assert video_service.sniff_container(b"RIFF\x00\x00\x00\x00AVI LIST") == "avi"
    assert video_service.sniff_container(b"\x1a\x45\xdf\xa3\x01\x00") == "mkv"
    for junk in (b"", b"MZ\x90\x00", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d", b"GIF89a" + b"\x00" * 10, b"RIFF\x00\x00\x00\x00WAVEfmt "):
        assert video_service.sniff_container(junk) is None


def test_display_names_are_harmless():
    assert video_service.safe_display_name("../../etc/passwd") == "passwd"
    assert video_service.safe_display_name("C:\\Users\\me\\clip.mp4") == "clip.mp4"
    assert video_service.safe_display_name("a\x00b\x1b[31mred.mp4") == "ab[31mred.mp4"
    assert video_service.safe_display_name(None) == "video" and len(video_service.safe_display_name("x" * 500)) == 80


def test_unused_helper_import_guard():
    assert crop_png(GREEN)  # keeps the shared test helpers imported together
