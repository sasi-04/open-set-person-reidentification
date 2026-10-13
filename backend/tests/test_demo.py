"""
The built-in example demo (open-set analysis).

In plain words: these tests prove the example is HONEST and SAFE - it judges each photo by the same decision code as the real screens,
reports a clothes-only decision next to the face + body decision, never touches the real gallery or history, and can only serve the
files its manifest names. They use stand-in networks, so they check the plumbing and the rules; the real-model numbers are produced by
running the example itself (docs/OPEN_SET_EXAMPLE.md).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.demo_service import verdict
from tests.conftest import KEYS, Env, make_settings
from tests.fakes import BLUE, GREEN, PURPLE, RED, YELLOW, FakeDetector, FakeExtractor, FakeFaceEngine, person_png

MANIFEST = {
    "schema": 1, "title": "Test example", "intro": "intro",
    "groups": [{"id": g, "title": g, "blurb": g} for g in ("known", "no_face", "stranger", "lookalike")],
    "people": [
        {"id": "ann", "label": "Ann", "note": "n", "photos": ["enroll/ann_1.png", "enroll/ann_2.png"]},
        {"id": "bob", "label": "Bob", "note": "n", "photos": ["enroll/bob_1.png"]},
    ],
    "cases": [
        {"id": "known-1", "group": "known", "title": "Ann in new clothes", "story": "s", "file": "test/known.png", "expect": {"kind": "match", "person": "ann"}},
        {"id": "same-1", "group": "lookalike", "title": "Stranger in Ann's clothes", "story": "s", "file": "test/same.png", "expect": {"kind": "unknown"}},
        {"id": "stranger-1", "group": "stranger", "title": "Stranger", "story": "s", "file": "test/stranger.png", "expect": {"kind": "unknown"}},
        {"id": "noface-1", "group": "no_face", "title": "Ann, no face", "story": "s", "file": "test/noface.png", "expect": {"kind": "review", "person": "ann"}},
    ],
}


def write_demo(folder, manifest=MANIFEST):
    pictures = {
        "enroll/ann_1.png": person_png(RED, GREEN, seed=1), "enroll/ann_2.png": person_png(BLUE, GREEN, seed=2),
        "enroll/bob_1.png": person_png(BLUE, YELLOW, seed=3),
        "test/known.png": person_png(GREEN, GREEN, seed=9),      # Ann's face, clothes nobody enrolled wears
        "test/same.png": person_png(RED, PURPLE, seed=11),       # a stranger in exactly Ann's red clothes
        "test/stranger.png": person_png(GREEN, PURPLE, seed=12),   # nobody's face, nobody's clothes
        "test/noface.png": person_png(RED, None, seed=13),       # Ann's clothes, no face visible
    }
    for name, data in pictures.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    (folder / "demo_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "secret.txt").write_text("not an example photo", encoding="utf-8")


@pytest.fixture()
def demo(tmp_path):
    folder = tmp_path / "demo_files"
    folder.mkdir()
    write_demo(folder)
    settings = make_settings(tmp_path, demo_dir=folder)
    extractor, detector, faces = FakeExtractor(), FakeDetector(), FakeFaceEngine()
    with TestClient(create_app(settings, extractor=extractor, detector=detector, face_engine=faces)) as client:
        yield Env(client, extractor, detector, settings, client.app.state.runtime, faces), folder


def run_all(env):
    env.post("/api/demo/prepare", role="viewer")
    return {c["id"]: env.post(f"/api/demo/cases/{c['id']}", role="viewer").json() for c in env.get("/api/demo").json()["cases"]}


class TestDescription:
    def test_it_lists_the_people_cases_and_the_rules_in_force(self, demo):
        env, _ = demo
        body = env.get("/api/demo").json()
        assert body["available"] and [p["id"] for p in body["people"]] == ["ann", "bob"] and len(body["cases"]) == 4
        assert body["rules"]["matching_mode"] == "face_body" and body["rules"]["face_threshold"] == pytest.approx(0.465)
        assert body["cases"][0]["expect"]["text"] == "Enrolled: Ann. The right answer is MATCH Ann."
        assert body["cases"][1]["expect"]["kind"] == "unknown" and "stranger" in body["cases"][1]["expect"]["text"]
        assert all(c["image_url"].startswith("/api/demo/files/") for c in body["cases"]) and body["disclaimer"]

    def test_preparing_reports_which_reference_photos_have_a_usable_face(self, demo):
        env, _ = demo
        prepared = env.post("/api/demo/prepare", role="viewer").json()
        assert [p["n_faces"] for p in prepared["people"]] == [2, 1]
        assert {ph["face_status"] for p in prepared["people"] for ph in p["photos"]} == {"ready"}

    def test_a_missing_manifest_is_explained_not_a_crash(self, tmp_path):
        settings = make_settings(tmp_path, demo_dir=tmp_path / "nothing_here")
        app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector(), face_engine=FakeFaceEngine())
        with TestClient(app) as client:
            env = Env(client, None, None, settings, None)
            body = env.get("/api/demo").json()
            assert body["available"] is False and "not installed" in body["reason"]
            assert env.post("/api/demo/prepare", role="viewer").status_code == 404

    def test_a_manifest_that_names_a_missing_photo_is_refused_with_the_name(self, demo):
        env, folder = demo
        (folder / "test" / "same.png").unlink()
        body = env.get("/api/demo").json()
        assert body["available"] is False and "test/same.png" in body["reason"]

    def test_without_the_face_models_the_example_says_so(self, tmp_path):
        folder = tmp_path / "d"
        folder.mkdir()
        write_demo(folder)
        settings = make_settings(tmp_path, demo_dir=folder)
        with TestClient(create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())) as client:
            env = Env(client, None, None, settings, None)
            body = env.get("/api/demo").json()
            assert body["available"] is False and "face models" in body["reason"]
            assert env.post("/api/demo/prepare", role="viewer").status_code == 503


class TestAnalysis:
    def test_a_known_person_in_new_clothes_is_matched_by_the_face_and_missed_by_clothes(self, demo):
        env, _ = demo
        r = run_all(env)["known-1"]
        assert r["face_body"]["outcome"] == "accepted" and r["face_body"]["accepted_person"] == "ann" and r["face_body"]["verdict"] == "correct"
        assert r["face_body"]["basis"] == "face" and r["face_body"]["face_score"] > 0.9
        assert r["clothes_only"]["outcome"] == "unknown" and r["clothes_only"]["verdict"] == "missed"
        assert r["face"]["status"] == "usable"

    def test_a_stranger_in_the_same_clothes_is_the_open_set_failure_clothes_alone_cannot_avoid(self, demo):
        env, _ = demo
        r = run_all(env)["same-1"]
        assert r["face_body"]["outcome"] == "unknown" and r["face_body"]["verdict"] == "correct"
        assert r["clothes_only"]["outcome"] == "accepted" and r["clothes_only"]["accepted_person"] == "ann"
        assert r["clothes_only"]["verdict"] == "false_accept"
        assert r["clothes_only"]["body_score"] > 0.9 and r["face_body"]["face_score"] < 0.465  # clothes alike, faces not

    def test_the_reasons_name_people_by_their_label_not_their_internal_id(self, demo):
        env, _ = demo
        r = run_all(env)["same-1"]
        for column in ("face_body", "clothes_only"):
            assert "'ann'" not in r[column]["reason"] and "'bob'" not in r[column]["reason"]
        assert "'Ann'" in r["face_body"]["reason"]

    def test_a_plain_stranger_is_rejected_by_both(self, demo):
        env, _ = demo
        r = run_all(env)["stranger-1"]
        assert r["face_body"]["verdict"] == "correct" and r["clothes_only"]["verdict"] == "correct"

    def test_no_usable_face_goes_to_review_while_clothes_alone_would_accept(self, demo):
        env, _ = demo
        r = run_all(env)["noface-1"]
        assert r["face"]["status"] == "no_face"
        assert r["face_body"]["outcome"] == "review_required" and r["face_body"]["verdict"] == "correct"
        assert r["clothes_only"]["outcome"] == "accepted" and r["clothes_only"]["verdict"] == "risky"

    def test_every_candidate_is_listed_with_its_own_scores(self, demo):
        env, _ = demo
        r = run_all(env)["known-1"]
        assert [c["person"] for c in r["face_body"]["candidates"]][0] == "ann"
        top = r["face_body"]["candidates"][0]
        assert top["basis"] == "face" and top["face_score"] is not None and top["body_score"] is not None

    def test_the_active_policy_decides_the_thresholds_and_is_not_changed(self, demo):
        env, _ = demo
        before = env.get("/api/config").json()["policy"]["version"]
        env.set_policy(accept_threshold=0.80, face_accept_threshold=0.9)
        info = env.get("/api/demo").json()
        assert info["rules"]["face_threshold"] == pytest.approx(0.9) and info["rules"]["body_threshold"] == pytest.approx(0.80)
        run_all(env)
        assert env.get("/api/config").json()["policy"]["version"] == before + 1  # only OUR set_policy created a version

    def test_a_body_only_policy_still_shows_the_comparison_using_the_default_face_rules(self, demo):
        env, _ = demo
        env.set_policy(matching_mode="body")
        info = env.get("/api/demo").json()
        assert info["rules"]["matching_mode"] == "body" and info["rules"]["face_threshold"] == pytest.approx(0.465)
        assert run_all(env)["known-1"]["face_body"]["verdict"] == "correct"

    def test_an_unknown_case_is_a_404(self, demo):
        env, _ = demo
        assert env.post("/api/demo/cases/nope", role="viewer").status_code == 404


class TestItNeverTouchesYourData:
    def test_the_real_gallery_history_and_audit_trail_are_untouched(self, demo):
        env, _ = demo
        env.enroll_person("real-person", RED, GREEN)  # somebody the user really enrolled
        gallery_before = env.get("/api/gallery").json()
        index_version = env.runtime.index.snapshot.version
        run_all(env)
        gallery_after = env.get("/api/gallery").json()
        assert [i["reference_id"] for i in gallery_after["items"]] == ["real-person"] and gallery_after["total"] == gallery_before["total"] == 1
        assert env.runtime.index.snapshot.version == index_version
        assert env.get("/api/reid/history").json()["total"] == 0
        assert not any(a["action"].startswith("demo") for a in env.get("/api/audit", role="admin").json())

    def test_the_example_people_are_not_findable_by_a_real_query(self, demo):
        env, _ = demo
        run_all(env)
        r = env.predict(person_png(RED, GREEN, seed=2)).json()["people"][0]["decision"]
        assert r["outcome"] == "unknown"  # the real gallery is empty; the sandbox is invisible to it

    def test_the_sandbox_can_be_forgotten(self, demo):
        env, _ = demo
        run_all(env)
        assert env.runtime.demo_sandbox is not None
        assert env.delete("/api/demo/sandbox", role="viewer").status_code == 200
        assert env.runtime.demo_sandbox is None


class TestFilesAndAccess:
    def test_only_files_named_in_the_manifest_are_served(self, demo):
        env, _ = demo
        ok = env.get("/api/demo/files/test/known.png", role="viewer")
        assert ok.status_code == 200 and ok.headers["content-type"] == "image/png"
        assert env.get("/api/demo/files/secret.txt", role="viewer").status_code == 404           # exists, but not in the manifest
        assert env.get("/api/demo/files/demo_manifest.json", role="viewer").status_code == 404
        assert env.get("/api/demo/files/nope.png", role="viewer").status_code == 404

    @pytest.mark.parametrize("path", ["..%2Fsecret.txt", "%2e%2e/secret.txt", "test/..%2F..%2Fsecret.txt", "..%5Csecret.txt", "/etc/passwd"])
    def test_path_traversal_is_impossible(self, demo, path):
        env, _ = demo
        assert env.get(f"/api/demo/files/{path}", role="viewer").status_code in (404, 405)

    def test_a_key_is_required_when_keys_are_on_and_a_viewer_key_is_enough(self, demo):
        env, _ = demo
        assert env.client.get("/api/demo").status_code == 401
        assert env.client.post("/api/demo/prepare").status_code == 401
        assert env.client.get("/api/demo", headers={"X-API-Key": KEYS["viewer"]}).status_code == 200


@pytest.mark.parametrize("kind,person,outcome,accepted,expected", [
    ("match", "ann", "accepted", "ann", "correct"), ("match", "ann", "accepted", "bob", "wrong_person"),
    ("match", "ann", "review_required", None, "review"), ("match", "ann", "unknown", None, "missed"),
    ("unknown", None, "unknown", None, "correct"), ("unknown", None, "accepted", "ann", "false_accept"),
    ("unknown", None, "review_required", None, "review"),
    ("review", "ann", "review_required", None, "correct"), ("review", "ann", "accepted", "ann", "risky"), ("review", "ann", "unknown", None, "cautious"),
])
def test_what_counts_as_a_right_answer(kind, person, outcome, accepted, expected):
    assert verdict(kind, person, outcome, accepted) == expected
