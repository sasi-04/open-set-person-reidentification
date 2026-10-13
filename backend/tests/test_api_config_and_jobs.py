"""Policy versioning, calibration -> apply, and background evaluation jobs through the HTTP API."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.models import EvaluationRun
from app.main import create_app
from tests.conftest import KEYS, make_settings
from tests.fakes import FakeDetector, FakeExtractor
from tests.test_evaluation_pipeline import make_dataset


# ------------------------------------------------------------------------- policy
def test_initial_policy_is_honestly_labelled_unvalidated(env):
    policy = env.get("/api/config").json()["policy"]
    assert policy["version"] == 1 and policy["status"] == "unvalidated"
    assert "nobody has checked" in policy["status_explanation"]
    assert policy["calibration_run_id"] is None and policy["is_active"] is True


def test_changing_thresholds_requires_confirmation(env):
    response = env.post("/api/config/thresholds", json={"accept_threshold": 0.8, "confirm": False})
    assert response.status_code == 422
    assert env.get("/api/config").json()["policy"]["version"] == 1  # unchanged


@pytest.mark.parametrize("bad", [{"accept_threshold": 1.5}, {"accept_threshold": -0.2}, {"accept_threshold": 0.8, "min_margin": 2},
                                 {"accept_threshold": "high"}, {}])
def test_invalid_policy_values_are_rejected(env, bad):
    assert env.post("/api/config/thresholds", json={**bad, "confirm": True}).status_code == 422
    assert env.get("/api/config").json()["policy"]["version"] == 1


def test_manual_change_creates_a_new_experimental_version_and_keeps_history(env):
    new = env.post("/api/config/thresholds", json={"accept_threshold": 0.82, "min_margin": 0.05, "note": "tighter", "confirm": True}).json()
    assert new["version"] == 2 and new["status"] == "experimental" and new["created_by"] == "admin"
    history = env.get("/api/config/history").json()
    assert [h["version"] for h in history] == [2, 1]
    assert [h["is_active"] for h in history] == [True, False]  # exactly one active version
    assert history[0]["note"] == "tighter" and history[1]["accept_threshold"] == 0.70  # old row untouched


def test_policy_changes_appear_in_the_audit_trail(env):
    env.post("/api/config/thresholds", json={"accept_threshold": 0.8, "confirm": True})
    assert env.get("/api/audit", role="viewer").status_code == 403  # the audit trail is admin-only
    actions = [entry["action"] for entry in env.get("/api/audit", role="admin").json()]
    assert "policy.update" in actions


def test_model_status_reports_embedding_detector_and_device(env):
    body = env.get("/api/model/status").json()
    assert body["embedding"]["ready"] is True and body["embedding"]["embedding_dim"] == 16
    assert body["detector"]["ready"] is True and body["device"]["type"] in ("unavailable", "cpu", "cuda")


def test_cleanup_endpoint_reports_what_it_did(env):
    result = env.post("/api/maintenance/cleanup").json()
    assert set(result) == {"expired_crops_removed", "history_rows_removed", "orphan_files_removed"}


# -------------------------------------------------------------------- job helpers
@pytest.fixture()
def jobs_env(tmp_path, monkeypatch):
    """An app with a small toy dataset and a fake extractor injected into the background worker."""
    from tests.conftest import Env
    from fastapi.testclient import TestClient

    settings = make_settings(tmp_path)
    make_dataset(settings.datasets_dir / "toy")
    extractor = FakeExtractor(noise=0.02)
    monkeypatch.setattr("app.services.evaluation_service.make_extractor_factory",
                        lambda *args, **kwargs: (lambda checkpoint: extractor))  # whatever the real signature is
    app = create_app(settings, extractor=extractor, detector=FakeDetector())
    with TestClient(app) as client:
        yield Env(client, extractor, FakeDetector(), settings, app.state.runtime)


SMALL_PROTOCOL = {"gallery_shots": 2, "dev_fraction": 0.2, "calibration_fraction": 0.3, "max_images_per_identity": 6}


def wait_for(env, run_id, states=("succeeded", "failed", "cancelled"), timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = env.get(f"/api/evaluation/runs/{run_id}").json()
        if run["status"] in states:
            return run
        time.sleep(0.1)
    raise AssertionError(f"run did not reach {states}: {run}")


def start_evaluation(env, **overrides):
    body = {"dataset": "toy", "seeds": [0], "protocol": SMALL_PROTOCOL, "bootstrap_samples": 20,
            "target": {"mode": "fixed_recall", "target_recall": 0.5}, **overrides}
    return env.post("/api/evaluation/run", json=body)


def start_calibration(env, **overrides):
    body = {"dataset": "toy", "protocol": SMALL_PROTOCOL, "target": {"mode": "fixed_recall", "target_recall": 0.5}, **overrides}
    return env.post("/api/evaluation/calibrate", json=body)


# ---------------------------------------------------------------------- datasets
def test_dataset_discovery_lists_what_is_installed(jobs_env):
    items = jobs_env.get("/api/evaluation/datasets").json()
    assert [d["name"] for d in items] == ["toy"] and items[0]["available"] and items[0]["identities"] == 40


def test_no_datasets_is_an_empty_list_not_an_error(env):
    assert env.get("/api/evaluation/datasets").json() == []


def test_running_on_a_missing_dataset_explains_how_to_get_one(env):
    response = env.post("/api/evaluation/run", json={"dataset": "market1501"})
    assert response.status_code == 404 and "README" in response.json()["error"]["message"]


# --------------------------------------------------------------------- checkpoints
def write_checkpoint(env, name="toy_seed0", dev=(), dataset="toy", seed=0):
    import json

    import torch

    folder = env.settings.weights_dir / "finetuned"
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"dev_identities": list(dev), "config": {"dataset": dataset, "seed": seed}, "training_images": 99, "validated": False}
    torch.save({"state_dict": {}, "meta": meta}, folder / f"{name}.pt")
    (folder / f"{name}.json").write_text(json.dumps(meta))


def test_no_checkpoints_is_an_empty_list(jobs_env):
    assert jobs_env.get("/api/evaluation/checkpoints").json() == []


def test_available_checkpoints_are_listed_with_their_provenance_and_never_as_validated(jobs_env):
    write_checkpoint(jobs_env, dev=["P001", "P002"], seed=3)
    (item,) = jobs_env.get("/api/evaluation/checkpoints").json()
    assert item["name"] == "toy_seed0.pt" and item["dataset"] == "toy" and item["seed"] == 3
    assert item["trained_people"] == 2 and item["training_images"] == 99 and item["validated"] is False


def test_a_checkpoint_without_provenance_is_not_used_and_the_run_says_why(jobs_env):
    write_checkpoint(jobs_env, dev=[])  # records nobody -> leakage cannot be ruled out
    run = wait_for(jobs_env, start_evaluation(jobs_env, finetuned_checkpoint="toy_seed0.pt").json()["run_id"])
    assert run["status"] == "succeeded"
    finetuned = run["result"]["variants"]["thr_margin_finetuned"]
    assert finetuned["status"] == "unavailable" and "does not record" in finetuned["reason"]
    assert any("NOT used" in w for w in run["result"]["warnings"])


def test_a_checkpoint_trained_on_the_evaluated_people_is_refused_as_leakage(jobs_env):
    everyone = [f"P{i:03d}" for i in range(40)]  # every person in the toy dataset
    write_checkpoint(jobs_env, dev=everyone)
    run = wait_for(jobs_env, start_evaluation(jobs_env, finetuned_checkpoint="toy_seed0.pt").json()["run_id"])
    assert "LEAKAGE" in run["result"]["variants"]["thr_margin_finetuned"]["reason"]


# --------------------------------------------------------------------- evaluation
def test_evaluation_job_runs_in_the_background_and_reports_real_progress(jobs_env):
    started = start_evaluation(jobs_env)
    assert started.status_code == 202
    run = started.json()
    assert run["status"] in ("queued", "running") and run["kind"] == "evaluation"

    finished = wait_for(jobs_env, run["run_id"])
    assert finished["status"] == "succeeded" and finished["progress"] == 1.0
    result = finished["result"]
    assert result["kind"] == "evaluation" and "selected_variant" in result
    assert result["variants"]["nn_baseline"]["per_seed"][0]["test"]["far"] == 1.0
    assert finished["headline"]["is_benchmark"] is True


def test_report_downloads_in_three_formats(jobs_env):
    run = wait_for(jobs_env, start_evaluation(jobs_env).json()["run_id"])
    base = f"/api/evaluation/runs/{run['run_id']}/report"
    as_json = jobs_env.get(base, params={"format": "json"})
    assert as_json.json()["kind"] == "evaluation" and "attachment" in as_json.headers["content-disposition"]
    markdown = jobs_env.get(base, params={"format": "md"}).text
    assert markdown.startswith("# OpenID Vision - evaluation report") and "| Variant |" in markdown
    page = jobs_env.get(base, params={"format": "html"})
    assert page.headers["content-type"].startswith("text/html") and "<table>" in page.text
    assert jobs_env.get(base, params={"format": "pdf"}).status_code == 422


def test_report_is_unavailable_until_the_run_finishes(jobs_env, monkeypatch):
    jobs_env.extractor.delay = 0.3  # make the job slow enough to catch mid-flight
    run_id = start_evaluation(jobs_env).json()["run_id"]
    response = jobs_env.get(f"/api/evaluation/runs/{run_id}/report")
    assert response.status_code == 409
    jobs_env.post(f"/api/evaluation/runs/{run_id}/cancel")
    wait_for(jobs_env, run_id)


def test_only_one_job_runs_at_a_time(jobs_env):
    jobs_env.extractor.delay = 0.3
    first = start_evaluation(jobs_env).json()["run_id"]
    second = start_calibration(jobs_env)
    assert second.status_code == 409 and "already running" in second.json()["error"]["message"]
    jobs_env.post(f"/api/evaluation/runs/{first}/cancel")
    wait_for(jobs_env, first)


def test_a_running_job_can_be_cancelled(jobs_env):
    jobs_env.extractor.delay = 0.2
    run_id = start_evaluation(jobs_env).json()["run_id"]
    wait_for(jobs_env, run_id, states=("running",))
    assert jobs_env.post(f"/api/evaluation/runs/{run_id}/cancel").status_code == 200
    final = wait_for(jobs_env, run_id)
    assert final["status"] == "cancelled" and final["result"] is None
    assert jobs_env.post(f"/api/evaluation/runs/{run_id}/cancel").status_code == 409  # already over


def test_a_failing_job_is_recorded_and_the_server_keeps_working(jobs_env, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("synthetic failure inside the worker")

    monkeypatch.setattr("app.services.evaluation_service.run_evaluation", explode)
    final = wait_for(jobs_env, start_evaluation(jobs_env).json()["run_id"])
    assert final["status"] == "failed" and "synthetic failure" in final["error"]
    assert jobs_env.get("/api/health").status_code == 200
    assert start_calibration(jobs_env).status_code == 202  # the worker is still alive


def test_run_listing_and_filtering(jobs_env):
    wait_for(jobs_env, start_evaluation(jobs_env).json()["run_id"])
    wait_for(jobs_env, start_calibration(jobs_env).json()["run_id"])
    assert jobs_env.get("/api/evaluation/runs").json()["total"] == 2
    kinds = jobs_env.get("/api/evaluation/runs", params={"kind": "calibration"}).json()["items"]
    assert [r["kind"] for r in kinds] == ["calibration"]


def test_invalid_evaluation_requests_are_rejected(jobs_env):
    assert start_evaluation(jobs_env, seeds=[]).status_code == 422
    assert start_evaluation(jobs_env, seeds=[1, 2, 3, 4, 5, 6]).status_code == 422
    assert start_evaluation(jobs_env, variants=["magic"]).status_code == 422
    assert start_evaluation(jobs_env, target={"mode": "fixed_recall", "target_recall": 1.7}).status_code == 422
    assert start_evaluation(jobs_env, finetuned_checkpoint="../../etc/passwd").status_code == 422
    assert start_evaluation(jobs_env, finetuned_checkpoint="missing.pt").status_code == 422


def test_server_restart_marks_orphaned_jobs_as_failed(tmp_path):
    from fastapi.testclient import TestClient

    settings = make_settings(tmp_path)
    app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())
    with TestClient(app) as client:
        with app.state.runtime.session_factory() as session:
            session.add(EvaluationRun(id="a" * 32, kind="evaluation", status="running", dataset_name="x", config={}))
            session.commit()
    with TestClient(create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())) as client:
        run = client.get(f"/api/evaluation/runs/{'a' * 32}", headers={"X-API-Key": KEYS["viewer"]}).json()
    assert run["status"] == "failed" and "restarted" in run["error"]


# ------------------------------------------------------------ calibration -> policy
def test_calibration_uses_only_the_calibration_split_and_can_be_applied(jobs_env):
    run = wait_for(jobs_env, start_calibration(jobs_env).json()["run_id"])
    result = run["result"]
    assert run["status"] == "succeeded" and result["kind"] == "calibration"
    assert result["metadata"]["split_used"].startswith("calibration") and "test split was not read" in result["metadata"]["split_used"]
    assert result["selected"]["target_achieved"] is True

    applied = jobs_env.post("/api/config/thresholds", json={"from_calibration_run_id": run["run_id"], "confirm": True})
    assert applied.status_code == 200
    policy = applied.json()
    assert policy["status"] == "calibrated" and policy["calibration_run_id"] == run["run_id"]
    assert policy["accept_threshold"] == pytest.approx(result["proposed_policy"]["accept_threshold"])
    assert policy["model_matches_current"] is True
    # ...and it really is the active rule now:
    assert jobs_env.get("/api/config").json()["policy"]["version"] == 2


def test_an_unreachable_target_cannot_be_applied_as_calibrated(jobs_env):
    jobs_env.extractor.noise = 5.0  # pure noise -> nothing is separable
    run = wait_for(jobs_env, start_calibration(jobs_env, target={"mode": "fixed_recall", "target_recall": 0.99}).json()["run_id"])
    assert run["status"] == "succeeded" and run["result"]["selected"]["target_achieved"] is False
    assert run["result"]["proposed_policy"]["status"] == "experimental"
    refused = jobs_env.post("/api/config/thresholds", json={"from_calibration_run_id": run["run_id"], "confirm": True})
    assert refused.status_code == 409 and "did NOT reach its target" in refused.json()["error"]["message"]
    assert jobs_env.get("/api/config").json()["policy"]["version"] == 1


def test_calibration_for_a_different_model_cannot_be_applied(jobs_env):
    run = wait_for(jobs_env, start_calibration(jobs_env).json()["run_id"])
    jobs_env.extractor.fingerprint = "some-other-model-flip0"  # the live model changed afterwards
    refused = jobs_env.post("/api/config/thresholds", json={"from_calibration_run_id": run["run_id"], "confirm": True})
    assert refused.status_code == 409 and "different model" in refused.json()["error"]["message"]


def test_only_finished_calibration_runs_can_be_applied(jobs_env):
    evaluation = wait_for(jobs_env, start_evaluation(jobs_env).json()["run_id"])
    refused = jobs_env.post("/api/config/thresholds", json={"from_calibration_run_id": evaluation["run_id"], "confirm": True})
    assert refused.status_code == 409
    unknown = jobs_env.post("/api/config/thresholds", json={"from_calibration_run_id": "b" * 32, "confirm": True})
    assert unknown.status_code == 404


def test_calibrated_confidence_model_is_only_used_for_the_model_it_was_fitted_on(jobs_env):
    from tests.fakes import RED, crop_png

    jobs_env.enroll("red-person", RED, n=3)
    run = wait_for(jobs_env, start_calibration(jobs_env).json()["run_id"])
    jobs_env.post("/api/config/thresholds", json={"from_calibration_run_id": run["run_id"], "confirm": True})
    query = crop_png(RED, seed=4)
    first = jobs_env.predict(query).json()["people"][0]["decision"]
    assert first["calibrated_confidence"] is None  # one enrolled identity: no margin, so no confidence
    jobs_env.enroll("green-person", (30, 200, 40), n=3)
    with_two = jobs_env.predict(query).json()["people"][0]["decision"]
    assert with_two["calibrated_confidence"] is not None and 0 < with_two["calibrated_confidence"] < 1
    assert with_two["calibrated_confidence"] != with_two["top1_score"]  # distinct quantities
    jobs_env.extractor.fingerprint = "changed"  # the model changed -> confidence model no longer valid
    with jobs_env.runtime.session_factory() as session:
        jobs_env.runtime.sync_gallery(session); session.commit()
    jobs_env.post("/api/gallery/rebuild", role="operator")
    assert jobs_env.predict(query).json()["people"][0]["decision"]["calibrated_confidence"] is None


def test_smoke_test_datasets_never_count_as_a_benchmark_on_the_dashboard(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tests.conftest import Env

    settings = make_settings(tmp_path)
    make_dataset(settings.datasets_dir / "smoky", kind="smoke_test")
    extractor = FakeExtractor(noise=0.02)
    monkeypatch.setattr("app.services.evaluation_service.make_extractor_factory",
                        lambda *args, **kwargs: (lambda checkpoint: extractor))
    with TestClient(create_app(settings, extractor=extractor, detector=FakeDetector())) as client:
        env = Env(client, extractor, FakeDetector(), settings, None)
        wait_for(env, start_evaluation(env, dataset="smoky").json()["run_id"])
        latest = env.get("/api/overview").json()["latest_evaluation"]
    assert latest["benchmark_available"] is False and latest["far"] is None
    assert "smoke-test" in latest["note"]
