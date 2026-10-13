"""
Face + body matching.

In plain words: these tests prove the RULES. The headline case is the one that motivated the feature - a stranger wearing
the same clothes as an enrolled person must NOT be matched, because the face disagrees - plus the safe fallbacks (no
face, bad face, nobody with a face on file). They use stand-in networks, so they say nothing about how accurate the real
face model is; that is measured separately on the LFW benchmark (docs/FACE_AND_BODY_MATCHING.md).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.errors import ValidationFailed
from app.cv.open_set.decision_engine import decide
from app.cv.open_set.multicue import decide_multicue
from app.cv.open_set.policy import BodyOnlyAction, DecisionPolicy, MultiCuePolicy, Outcome
from app.cv.retrieval.types import Candidate
from tests.fakes import BLUE, GREEN, PURPLE, RED, YELLOW, crop_png, person_png

T_BODY, T_FACE = 0.70, MultiCuePolicy().face_accept_threshold  # 0.465: see MultiCuePolicy for where it comes from


def policy(**kw):
    multicue = kw.pop("multicue", MultiCuePolicy())
    return DecisionPolicy(version=3, accept_threshold=T_BODY, multicue=multicue, **kw)


def cands(*pairs):
    """Candidates from (reference_id, score) pairs, best first."""
    return [Candidate(i + 1, ref, score, f"img-{ref}", 2) for i, (ref, score) in enumerate(sorted(pairs, key=lambda p: -p[1]))]


# =====================================================================================================
# The decision rules (pure functions)
# =====================================================================================================
class TestFaceDecides:
    def test_a_matching_face_is_accepted_even_when_the_clothes_differ(self):
        d = decide_multicue(cands(("ann", 0.31)), cands(("ann", 0.74)), policy())
        assert d.outcome is Outcome.ACCEPTED and d.accepted_reference_id == "ann"
        assert d.basis == "face" and d.top1_score == 0.74 and d.accept_threshold == T_FACE
        assert d.top1_face_score == 0.74 and d.top1_body_score == 0.31
        assert "changed clothes" in d.reason  # the low body score is explained, not hidden

    def test_a_matching_face_with_matching_clothes_says_both_agree(self):
        d = decide_multicue(cands(("ann", 0.91)), cands(("ann", 0.80)), policy())
        assert d.outcome is Outcome.ACCEPTED and "agrees" in d.reason

    def test_SAME_CLOTHES_DIFFERENT_FACE_is_not_a_match(self):
        """The motivating case: body similarity 0.97 (identical uniform) but the face is a different person."""
        d = decide_multicue(cands(("ann", 0.97)), cands(("ann", 0.08)), policy())
        assert d.outcome is Outcome.UNKNOWN and d.accepted_reference_id is None
        assert d.reason_code == "face_below_threshold"
        assert "NOT accepted when a face is available" in d.reason
        # ... and the original body-only engine WOULD have accepted this stranger:
        legacy = decide(cands(("ann", 0.97)), DecisionPolicy(version=1, accept_threshold=T_BODY))
        assert legacy.outcome is Outcome.ACCEPTED

    def test_a_face_just_below_the_threshold_goes_to_a_person(self):
        d = decide_multicue(cands(("ann", 0.5)), cands(("ann", 0.40)), policy())  # inside the 0.10 band below 0.465
        assert d.outcome is Outcome.REVIEW_REQUIRED and d.reason_code == "face_near_threshold"

    def test_below_the_band_is_unknown(self):
        assert decide_multicue(cands(("ann", 0.5)), cands(("ann", 0.30)), policy()).outcome is Outcome.UNKNOWN

    def test_the_review_band_can_be_switched_off(self):
        d = decide_multicue(cands(("ann", 0.5)), cands(("ann", 0.40)), policy(multicue=MultiCuePolicy(face_review_band=0.0)))
        assert d.outcome is Outcome.UNKNOWN

    def test_the_face_ranking_not_the_body_ranking_picks_the_person(self):
        body = cands(("ann", 0.95), ("bob", 0.40))  # clothes say Ann...
        face = cands(("ann", 0.10), ("bob", 0.66))  # ...the face says Bob
        d = decide_multicue(body, face, policy())
        assert d.outcome is Outcome.ACCEPTED and d.accepted_reference_id == "bob"
        assert [c.reference_id for c in d.candidates] == ["bob", "ann"]
        assert d.candidates[0].face_score == 0.66 and d.candidates[0].body_score == 0.40

    def test_margin_rule_applies_to_the_face_scores(self):
        p = policy(min_margin=0.10)
        d = decide_multicue(cands(("ann", 0.5), ("bob", 0.5)), cands(("ann", 0.60), ("bob", 0.55)), p)
        assert d.outcome is Outcome.REVIEW_REQUIRED and d.reason_code == "ambiguous_margin"
        assert d.margin == pytest.approx(0.05)

    def test_threshold_is_inclusive(self):
        d = decide_multicue(cands(("ann", 0.1)), cands(("ann", T_FACE)), policy())
        assert d.outcome is Outcome.ACCEPTED

    def test_body_quality_flags_do_not_block_a_good_face(self):
        d = decide_multicue(cands(("ann", 0.6)), cands(("ann", 0.7)), policy(), body_quality_flags=["low_resolution"])
        assert d.outcome is Outcome.ACCEPTED


class TestBodyOnlyFallback:
    def test_no_face_and_strong_clothes_asks_for_review_not_a_match(self):
        d = decide_multicue(cands(("ann", 0.93)), None, policy(), face_status="no_face")
        assert d.outcome is Outcome.REVIEW_REQUIRED and d.reason_code == "body_only_review"
        assert "No face was found" in d.reason and d.basis == "body"
        assert d.accepted_reference_id is None

    def test_no_face_and_weak_clothes_is_unknown(self):
        d = decide_multicue(cands(("ann", 0.40)), None, policy(), face_status="no_face")
        assert d.outcome is Outcome.UNKNOWN

    def test_body_only_action_accept_restores_the_original_behaviour(self):
        p = policy(multicue=MultiCuePolicy(body_only_action=BodyOnlyAction.ACCEPT))
        d = decide_multicue(cands(("ann", 0.93)), None, p, face_status="no_face")
        assert d.outcome is Outcome.ACCEPTED and d.accepted_reference_id == "ann"

    def test_unusable_face_is_reported_with_its_reasons(self):
        d = decide_multicue(cands(("ann", 0.93)), None, policy(), face_status="unusable", face_flags=["face_small", "face_blurry"])
        assert d.outcome is Outcome.REVIEW_REQUIRED
        assert "not good enough" in d.reason and "face_small" in d.reason

    def test_body_quality_flags_still_send_body_only_evidence_to_review(self):
        d = decide_multicue(cands(("ann", 0.2)), None, policy(), body_quality_flags=["blurry"], face_status="no_face")
        assert d.outcome is Outcome.REVIEW_REQUIRED and d.reason_code == "quality_review"

    def test_a_usable_face_but_nobody_with_a_face_on_file_falls_back_to_the_body(self):
        d = decide_multicue(cands(("ann", 0.93)), [], policy())
        assert d.outcome is Outcome.REVIEW_REQUIRED and d.face_status == "not_enrolled"
        assert "no enrolled person has a face on file" in d.reason

    def test_empty_gallery_is_unknown(self):
        assert decide_multicue([], [], policy()).outcome is Outcome.UNKNOWN
        assert decide_multicue([], None, policy(), face_status="no_face").outcome is Outcome.UNKNOWN


class TestMixedGallery:
    def test_a_person_without_a_face_on_file_cannot_be_ruled_out_by_a_face(self):
        body = cands(("ann", 0.20), ("guard", 0.96))  # Ann has a face on file, "guard" was enrolled from a back view
        d = decide_multicue(body, cands(("ann", 0.05)), policy())
        assert d.outcome is Outcome.REVIEW_REQUIRED and d.reason_code == "no_face_on_file_review"
        assert "guard" in d.reason and d.accepted_reference_id is None

    def test_a_weak_body_match_for_a_person_without_a_face_is_still_unknown(self):
        body = cands(("ann", 0.20), ("guard", 0.50))
        assert decide_multicue(body, cands(("ann", 0.05)), policy()).outcome is Outcome.UNKNOWN

    def test_faceless_people_are_listed_after_the_face_ranked_ones(self):
        d = decide_multicue(cands(("ann", 0.2), ("guard", 0.5)), cands(("ann", 0.05)), policy())
        assert [(c.reference_id, c.basis) for c in d.candidates] == [("ann", "face"), ("guard", "body")]


class TestPolicyValues:
    def test_decide_multicue_needs_a_multicue_policy(self):
        with pytest.raises(ValueError):
            decide_multicue(cands(("a", 0.9)), None, DecisionPolicy(version=1, accept_threshold=0.7))

    @pytest.mark.parametrize("threshold", [0.0, 1.0, -0.2, float("nan")])
    def test_a_nonsense_face_threshold_is_refused(self, threshold):
        with pytest.raises(ValidationFailed):
            MultiCuePolicy(face_accept_threshold=threshold)

    def test_a_nonsense_review_band_is_refused(self):
        with pytest.raises(ValidationFailed):
            MultiCuePolicy(face_review_band=0.9)

    def test_round_trip_through_json(self):
        original = MultiCuePolicy(0.4, 0.05, BodyOnlyAction.ACCEPT)
        assert MultiCuePolicy.from_dict(original.to_dict()) == original
        assert MultiCuePolicy.from_dict(None) is None


# =====================================================================================================
# The whole application with stand-in networks
# =====================================================================================================
def person(r):
    return r.json()["people"][0]


class TestEnrolment:
    def test_a_usable_face_is_found_and_counted(self, face_env):
        r = face_env.enroll_person("ann", RED, GREEN)
        assert r.status_code == 201
        files = r.json()["files"]
        assert [f["face_status"] for f in files] == ["ready", "ready"]
        assert r.json()["identity"]["n_faces"] == 2
        assert all(i["face_status"] == "ready" and i["face_box"] for i in r.json()["identity"]["images"])
        summary = face_env.get("/api/gallery").json()["summary"]
        assert summary["faces_usable"] == 2 and summary["face_model"] == "face-fake0000-fake0000"
        assert face_env.runtime.face_index.snapshot.n_identities == 1

    def test_a_picture_without_a_face_still_enrols_but_warns(self, face_env):
        r = face_env.enroll_person("backview", RED, None)
        assert r.status_code == 201
        assert [f["face_status"] for f in r.json()["files"]] == ["no_face", "no_face"]
        assert any("No usable face was found" in w for w in r.json()["warnings"])
        assert r.json()["identity"]["n_faces"] == 0
        assert face_env.runtime.face_index.snapshot.n_identities == 0

    def test_a_tiny_face_is_stored_as_weak_and_not_used(self, face_env):
        r = face_env.enroll_person("tiny", RED, GREEN, face_px=30)
        assert [f["face_status"] for f in r.json()["files"]] == ["weak", "weak"]
        assert "too small" in r.json()["files"][0]["face_note"]
        assert face_env.runtime.face_index.snapshot.n_identities == 0

    def test_the_same_face_enrolled_under_two_ids_is_flagged(self, face_env):
        face_env.enroll_person("ann", RED, GREEN)
        r = face_env.enroll_person("ann2", BLUE, GREEN)
        assert any("not enrolled twice" in w and "'ann'" in w for w in r.json()["warnings"])

    def test_deleting_an_identity_removes_its_faces(self, face_env):
        face_env.enroll_person("ann", RED, GREEN)
        assert face_env.delete("/api/gallery/ann", params={"confirm": "ann"}).status_code == 200
        assert face_env.runtime.face_index.snapshot.n_identities == 0
        with face_env.runtime.session_factory() as session:
            from sqlalchemy import func, select

            from app.db.models import FaceTemplate

            assert session.scalar(select(func.count()).select_from(FaceTemplate)) == 0

    def test_without_face_models_enrolment_is_unchanged(self, env):
        r = env.enroll("ann", RED)
        assert r.status_code == 201
        assert r.json()["files"][0]["face_status"] == "not_analysed"
        assert "faces_not_analysed" in env.get("/api/gallery").json()["summary"]


class TestMatching:
    @pytest.fixture()
    def world(self, face_env):
        face_env.enroll_person("ann", RED, GREEN)
        face_env.enroll_person("bob", BLUE, YELLOW)
        return face_env

    def test_the_same_face_in_different_clothes_is_a_match(self, world):
        r = world.predict(person_png(PURPLE, GREEN, seed=9))  # Ann's face, purple clothes
        p = person(r)
        assert p["decision"]["outcome"] == "accepted" and p["decision"]["accepted_reference_id"] == "ann"
        assert p["decision"]["basis"] == "face" and p["decision"]["matching_mode"] == "face_body"
        assert p["decision"]["top1_face_score"] > 0.9 and p["face"]["status"] == "usable"
        assert r.json()["matching_mode"] == "face_body" and r.json()["face_model"]

    def test_SAME_CLOTHES_a_stranger_is_unknown(self, world):
        """Ann's exact red clothes, somebody else's face."""
        r = world.predict(person_png(RED, PURPLE, seed=11))
        p = person(r)
        assert p["decision"]["outcome"] == "unknown" and p["decision"]["basis"] == "face"
        assert any(c["body_score"] and c["body_score"] > 0.7 for c in p["candidates"]), "the clothes DO look alike - that is the point"

    def test_the_body_only_policy_would_have_accepted_that_stranger(self, world):
        stranger = person_png(RED, PURPLE, seed=11)
        assert world.set_policy(matching_mode="body").status_code == 200
        p = person(world.predict(stranger))
        assert p["decision"]["outcome"] == "accepted" and p["decision"]["matching_mode"] == "body"
        assert p["face"] is None

    def test_no_face_in_the_query_asks_for_review_instead_of_matching_on_clothes(self, world):
        p = person(world.predict(person_png(RED, None, seed=3)))
        assert p["decision"]["outcome"] == "review_required" and p["decision"]["reason_code"] == "body_only_review"
        assert p["face"]["status"] == "no_face"

    def test_a_tiny_face_in_the_query_is_unusable_and_explained(self, world):
        p = person(world.predict(person_png(RED, GREEN, face_px=30, seed=3)))
        assert p["face"]["status"] == "unusable" and "face_small" in p["face"]["flags"]
        assert p["decision"]["outcome"] == "review_required"
        assert "too small" in p["face"]["message"]

    def test_each_person_is_scored_by_face_and_by_body(self, world):
        p = person(world.predict(person_png(RED, GREEN, seed=2)))
        top = p["candidates"][0]
        assert top["reference_id"] == "ann" and top["basis"] == "face"
        assert top["face_score"] > 0.9 and top["body_score"] > 0.5

    def test_history_keeps_the_face_evidence(self, world):
        request_id = world.predict(person_png(PURPLE, GREEN, seed=9)).json()["request_id"]
        detail = world.get(f"/api/reid/history/{request_id}").json()["people"][0]
        assert detail["decision"]["basis"] == "face" and detail["decision"]["top1_face_score"] > 0.9
        assert detail["face"]["status"] == "usable"
        csv = world.get(f"/api/reid/history/{request_id}/export", params={"format": "csv"}).text
        header, row = csv.splitlines()[0], csv.splitlines()[1]
        assert "decided_by" in header and ",face," in row

    def test_policy_changes_keep_the_face_rules_unless_told_otherwise(self, world):
        v = world.set_policy(accept_threshold=0.8, face_accept_threshold=0.5).json()
        assert v["matching_mode"] == "face_body" and v["face_accept_threshold"] == 0.5
        v2 = world.set_policy(accept_threshold=0.75).json()  # only the body threshold changes
        assert v2["matching_mode"] == "face_body" and v2["face_accept_threshold"] == 0.5
        v3 = world.set_policy(matching_mode="body").json()
        assert v3["matching_mode"] == "body" and v3["face_accept_threshold"] is None
        v4 = world.set_policy(matching_mode="face_body").json()  # switching back restores defaults
        assert v4["matching_mode"] == "face_body" and v4["face_accept_threshold"] == pytest.approx(0.465)

    def test_a_face_threshold_of_nonsense_is_refused(self, world):
        assert world.set_policy(face_accept_threshold=1.5).status_code == 422


class TestFallbackWithoutModels:
    def test_a_face_policy_without_face_models_matches_on_the_body_and_says_so(self, env):
        env.enroll("ann", RED)
        policy = env.get("/api/config").json()["policy"]
        assert policy["matching_mode"] == "face_body" and policy["face_models_loaded"] is False
        r = env.predict(crop_png(RED, seed=7))
        p = person(r)
        assert p["decision"]["outcome"] == "accepted" and p["decision"]["matching_mode"] == "body"
        assert any("face models are not loaded" in n for n in r.json()["notes"])

    def test_readiness_stays_ready_without_face_models(self, env):
        body = env.client.get("/api/readiness").json()
        assert body["status"] in ("ready", "degraded")
        assert body["components"]["face_models"]["ok"] is False

    def test_switching_face_matching_off_in_the_settings(self, tmp_path):
        from fastapi.testclient import TestClient

        from app.main import create_app
        from tests.conftest import KEYS, make_settings
        from tests.fakes import FakeDetector, FakeExtractor

        settings = make_settings(tmp_path, face_matching=False)
        with TestClient(create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())) as client:
            policy = client.get("/api/config", headers={"X-API-Key": KEYS["viewer"]}).json()["policy"]
            assert policy["matching_mode"] == "body"
            refused = client.post("/api/config/thresholds", headers={"X-API-Key": KEYS["admin"]},
                                  json={"accept_threshold": 0.7, "matching_mode": "face_body", "confirm": True})
            assert refused.status_code == 409


class TestUpgradingAnExistingGallery:
    def test_faces_are_added_to_identities_enrolled_before_face_matching(self, face_env):
        # Enrol with the face models "missing", then bring them in - as happens when someone downloads the weights later.
        engine = face_env.runtime.face_engine
        face_env.runtime.face_engine = None
        face_env.enroll_person("ann", RED, GREEN)
        assert face_env.runtime.face_index.snapshot.n_identities == 0
        face_env.runtime.face_engine = engine

        r = face_env.post("/api/gallery/analyse-faces")
        assert r.status_code == 200 and r.json()["detail"]["usable"] == 2
        assert face_env.runtime.face_index.snapshot.n_identities == 1
        assert face_env.get("/api/gallery/ann").json()["images"][0]["face_status"] == "ready"
        # ... and the new evidence is used straight away
        assert person(face_env.predict(person_png(PURPLE, GREEN, seed=4)))["decision"]["outcome"] == "accepted"
        # running it again finds nothing left to do
        assert face_env.post("/api/gallery/analyse-faces").json()["detail"]["analysed"] == 0

    def test_a_changed_face_model_marks_old_fingerprints_stale_and_refreshes_them(self, face_env):
        face_env.enroll_person("ann", RED, GREEN)
        face_env.runtime.face_engine.fingerprint = "face-another-model"
        with face_env.runtime.session_factory() as session:
            face_env.runtime.sync_gallery(session)
            session.commit()
        assert face_env.runtime.face_index.snapshot.n_identities == 0  # stale fingerprints are never compared
        assert face_env.get("/api/gallery").json()["summary"]["faces_not_analysed"] == 2
        assert face_env.post("/api/gallery/analyse-faces").json()["detail"]["usable"] == 2
        assert face_env.runtime.face_index.snapshot.n_identities == 1

    def test_analyse_faces_without_models_explains_itself(self, env):
        env.enroll("ann", RED)
        r = env.post("/api/gallery/analyse-faces")
        assert r.status_code == 200 and r.json()["detail"]["analysed"] == 0 and "face model" in r.json()["message"].lower()


class TestOlderDatabases:
    def test_new_columns_are_added_to_an_existing_database_without_losing_rows(self, tmp_path):
        from sqlalchemy import create_engine, inspect, text

        from app.db.database import add_missing_columns, init_db

        url = f"sqlite:///{(tmp_path / 'old.sqlite').as_posix()}"
        engine = create_engine(url)
        with engine.begin() as c:  # the layout of the previous release: no `multicue`, no `evidence`, no face_templates
            c.execute(text("CREATE TABLE policy_versions (id INTEGER PRIMARY KEY, version INTEGER UNIQUE, accept_threshold FLOAT, "
                           "min_margin FLOAT, margin_action VARCHAR(10), review_on_quality_flags BOOLEAN, status VARCHAR(14), "
                           "calibration_run_id VARCHAR(32), confidence_model JSON, model_fingerprint VARCHAR(100), note TEXT, "
                           "created_by VARCHAR(16), created_at DATETIME, is_active BOOLEAN)"))
            c.execute(text("INSERT INTO policy_versions (version, accept_threshold, margin_action, review_on_quality_flags, status, "
                           "note, created_by, is_active) VALUES (1, 0.7, 'review', 1, 'unvalidated', 'kept', 'system', 1)"))
        init_db(engine)
        assert "multicue" in {c["name"] for c in inspect(engine).get_columns("policy_versions")}
        assert inspect(engine).has_table("face_templates")
        with engine.connect() as c:
            row = c.execute(text("SELECT note, accept_threshold, multicue FROM policy_versions")).one()
        assert (row[0], row[1], row[2]) == ("kept", 0.7, None)  # nothing lost; the old policy stays body-only
        assert add_missing_columns(engine) == []  # idempotent


class TestAppearanceCues:
    def test_colours_are_named_and_compared(self):
        from app.cv.face.appearance import compare_cues, extract_cues

        def body(upper, lower):
            image = np.full((300, 120, 3), 200, dtype=np.uint8)
            image[int(0.26 * 300) : int(0.46 * 300)] = upper
            image[int(0.56 * 300) : int(0.84 * 300)] = lower
            return image

        red_blue, red_blue2, green_blue = body((200, 30, 30), (40, 80, 200)), body((210, 40, 35), (45, 85, 195)), body((40, 150, 60), (40, 80, 200))
        a, b, c = extract_cues(red_blue, None), extract_cues(red_blue2, None), extract_cues(green_blue, None)
        assert a["upper_clothing"].label == "red" and a["lower_clothing"].label == "blue"
        same = {r["cue"]: r["verdict"] for r in compare_cues(a, b)}
        assert same == {"upper_clothing": "similar", "lower_clothing": "similar"}
        diff = {r["cue"]: r["verdict"] for r in compare_cues(a, c)}
        assert diff == {"upper_clothing": "different", "lower_clothing": "similar"}

    def test_skin_and_hair_need_a_face_and_are_skipped_otherwise(self):
        from app.cv.face.appearance import extract_cues

        image = np.full((300, 120, 3), 90, dtype=np.uint8)
        assert "skin_tone" not in extract_cues(image, None) and "hair" not in extract_cues(image, None)
        image[40:100, 30:90] = (224, 172, 140)  # skin-coloured patch
        cues = extract_cues(image, (30.0, 40.0, 90.0, 100.0))
        assert cues["skin_tone"].label in {"very light", "light", "intermediate"}

    def test_a_headshot_has_no_clothing_cues(self):
        from app.cv.face.appearance import extract_cues

        assert "upper_clothing" not in extract_cues(np.full((120, 120, 3), 100, dtype=np.uint8), None)


class TestPaddingTrim:
    def test_grey_bars_are_removed_and_real_content_kept(self):
        from app.cv.geometry import pad_to_person_aspect
        from app.services.face_service import trim_padding

        content = np.random.default_rng(1).integers(0, 255, (80, 80, 3), dtype=np.uint8)  # a square: padding adds rows
        padded = pad_to_person_aspect(content)
        assert padded.shape[0] == 160
        trimmed, top, left = trim_padding(padded)
        assert trimmed.shape[:2] == (80, 80) and (top, left) == (40, 0)
        assert np.array_equal(trimmed, content)

    def test_an_unpadded_picture_is_left_alone(self):
        from app.services.face_service import trim_padding

        picture = np.random.default_rng(2).integers(0, 255, (200, 100, 3), dtype=np.uint8)
        assert trim_padding(picture)[0].shape == picture.shape
