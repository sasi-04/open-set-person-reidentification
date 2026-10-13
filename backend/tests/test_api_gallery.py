"""Gallery management through the real HTTP API."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import AuditEvent
from tests.fakes import BLUE, GREEN, RED, YELLOW, crop_png, detection, scene_png


def image_files(*pngs: bytes, name="u"):
    return [("images", (f"{name}{i}.png", data, "image/png")) for i, data in enumerate(pngs)]


def test_empty_gallery_lists_nothing(env):
    body = env.get("/api/gallery").json()
    assert body["items"] == [] and body["total"] == 0 and body["summary"]["identities"] == 0


def test_enroll_requires_explicit_consent(env):
    response = env.post("/api/gallery/enroll", role="operator", data={"reference_id": "subject-001", "images_are_crops": "true"},
                        files=image_files(crop_png(RED)))
    assert response.status_code == 422 and "authorised" in response.json()["error"]["message"]
    assert env.get("/api/gallery").json()["total"] == 0  # nothing was stored


def test_enroll_stores_embeddings_and_updates_the_index(env):
    response = env.enroll("subject-001", RED, n=3, label="Lobby test")
    assert response.status_code == 201
    body = response.json()
    assert body["identity"]["n_images"] == 3 and body["identity"]["embedding_status"] == "ready"
    assert [f["status"] for f in body["files"]] == ["enrolled"] * 3
    assert env.get("/api/gallery").json()["summary"]["index_images"] == 3
    # the real files exist on disk under server-chosen names only
    stored = list(env.runtime.references.root.glob("*.jpg"))
    assert len(stored) == 3 and all(len(p.stem) == 32 for p in stored)


def test_database_ids_are_not_exposed(env):
    env.enroll("subject-001", RED)
    text = env.get("/api/gallery/subject-001").text
    assert '"id"' not in text and "identity_id" not in text


def test_invalid_reference_ids_are_rejected(env):
    for bad in ("../etc/passwd", "a b", "x", "name;drop table", "é" * 4, "-leading"):
        response = env.post("/api/gallery/enroll", role="operator",
                            data={"reference_id": bad, "consent_confirmed": "true", "images_are_crops": "true"},
                            files=image_files(crop_png(RED)))
        assert response.status_code == 422, bad


def test_duplicate_reference_id_conflicts(env):
    assert env.enroll("subject-001", RED).status_code == 201
    assert env.enroll("subject-001", RED).status_code == 409


def test_add_images_extends_an_identity_and_rejects_exact_duplicates(env):
    env.enroll("subject-001", RED, n=1)
    same = crop_png(RED, seed=0)  # identical bytes to the first enrolled image
    fresh = crop_png(RED, seed=7)
    response = env.post("/api/gallery/subject-001/images", role="operator", data={"images_are_crops": "true"},
                        files=image_files(same, fresh))
    body = response.json()
    assert response.status_code == 200
    assert [f["status"] for f in body["files"]] == ["rejected", "enrolled"]
    assert "already enrolled" in body["files"][0]["reason"]
    assert body["identity"]["n_images"] == 2


def test_one_bad_file_does_not_sink_the_others(env):
    response = env.post("/api/gallery/enroll", role="operator",
                        data={"reference_id": "subject-002", "consent_confirmed": "true", "images_are_crops": "true"},
                        files=image_files(b"definitely not an image", crop_png(GREEN)))
    assert response.status_code == 201
    statuses = [f["status"] for f in response.json()["files"]]
    assert statuses == ["rejected", "enrolled"]


def test_all_bad_files_is_an_error_and_creates_nothing(env):
    response = env.post("/api/gallery/enroll", role="operator",
                        data={"reference_id": "subject-003", "consent_confirmed": "true", "images_are_crops": "true"},
                        files=image_files(b"nope", b"nope2"))
    assert response.status_code == 422
    assert env.get("/api/gallery").json()["total"] == 0


def test_too_many_files_are_refused(env):
    pngs = [crop_png(RED, seed=i) for i in range(env.settings.max_enroll_files + 1)]
    response = env.post("/api/gallery/enroll", role="operator",
                        data={"reference_id": "subject-004", "consent_confirmed": "true", "images_are_crops": "true"},
                        files=image_files(*pngs))
    assert response.status_code == 422


def test_uploading_a_photo_with_two_people_is_refused(env):
    env.detector.boxes = [detection(10, 10, 100, 200), detection(150, 10, 240, 200)]
    response = env.post("/api/gallery/enroll", role="operator",
                        data={"reference_id": "subject-005", "consent_confirmed": "true"},
                        files=image_files(scene_png(RED)))
    assert response.status_code == 422
    assert "2 people" in str(response.json()["error"]["details"])


def test_single_person_photo_is_detected_and_cropped(env):
    env.detector.boxes = [detection(80, 40, 220, 360)]
    response = env.post("/api/gallery/enroll", role="operator",
                        data={"reference_id": "subject-006", "consent_confirmed": "true"},
                        files=image_files(scene_png(RED)))
    assert response.status_code == 201
    assert response.json()["identity"]["n_images"] == 1


def test_a_photo_with_nobody_in_it_is_refused(env):
    env.detector.boxes = []
    response = env.post("/api/gallery/enroll", role="operator",
                        data={"reference_id": "subject-007", "consent_confirmed": "true"}, files=image_files(scene_png(RED)))
    assert response.status_code == 422 and "No person" in str(response.json()["error"]["details"])


def test_list_search_sort_and_pagination(env):
    for ref, colour in (("alpha-1", RED), ("bravo-2", GREEN), ("charlie-3", BLUE)):
        env.enroll(ref, colour, n=2 if ref != "bravo-2" else 3)
    assert [i["reference_id"] for i in env.get("/api/gallery").json()["items"]] == ["alpha-1", "bravo-2", "charlie-3"]
    assert [i["reference_id"] for i in env.get("/api/gallery", params={"search": "BRAVO"}).json()["items"]] == ["bravo-2"]
    by_size = env.get("/api/gallery", params={"sort": "n_images", "order": "desc"}).json()["items"]
    assert by_size[0]["reference_id"] == "bravo-2"
    page = env.get("/api/gallery", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_reference_image_is_served_as_jpeg_only_for_its_own_identity(env):
    env.enroll("subject-001", RED)
    env.enroll("subject-002", GREEN)
    detail = env.get("/api/gallery/subject-001").json()
    url = detail["images"][0]["url"]
    image = env.get(url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg" and image.content[:2] == b"\xff\xd8"
    other = url.replace("subject-001", "subject-002")
    assert env.get(other).status_code == 404  # an image UID does not unlock another identity


def test_path_traversal_through_image_uid_is_impossible(env):
    env.enroll("subject-001", RED)
    for evil in ("..%2F..%2Fpyproject.toml", "....//....//x", "%2e%2e%2fsecret"):
        assert env.get(f"/api/gallery/subject-001/images/{evil}").status_code == 404


def test_delete_requires_confirmation_and_removes_the_files(env):
    env.enroll("subject-001", RED, n=2)
    assert env.delete("/api/gallery/subject-001", role="operator").status_code == 422  # no confirm
    assert env.delete("/api/gallery/subject-001", role="operator", params={"confirm": "wrong"}).status_code == 422
    assert len(list(env.runtime.references.root.glob("*.jpg"))) == 2
    assert env.delete("/api/gallery/subject-001", role="operator", params={"confirm": "subject-001"}).status_code == 200
    assert list(env.runtime.references.root.glob("*.jpg")) == []
    assert env.get("/api/gallery/subject-001").status_code == 404
    assert env.get("/api/gallery").json()["summary"]["index_identities"] == 0


def test_viewer_cannot_delete(env):
    env.enroll("subject-001", RED)
    assert env.delete("/api/gallery/subject-001", role="viewer", params={"confirm": "subject-001"}).status_code == 403


def test_reset_needs_admin_and_the_exact_phrase(env):
    env.enroll("subject-001", RED)
    assert env.post("/api/gallery/reset", json={"confirm": "yes"}).status_code == 422
    assert env.get("/api/gallery").json()["total"] == 1
    assert env.post("/api/gallery/reset", json={"confirm": "RESET DEMO GALLERY"}).status_code == 200
    assert env.get("/api/gallery").json()["total"] == 0
    assert list(env.runtime.references.root.glob("*.jpg")) == []


def test_possible_double_enrollment_produces_a_warning(env):
    env.enroll("subject-001", RED)
    response = env.enroll("subject-002", RED)  # the same colour = near-identical embedding
    assert response.status_code == 201
    assert any("subject-001" in w for w in response.json()["warnings"])


def test_changing_the_model_marks_embeddings_stale_until_rebuilt(env):
    env.enroll("subject-001", RED, n=2)
    env.extractor.fingerprint = "a-different-model"  # simulate swapping the backbone
    with env.runtime.session_factory() as session:
        env.runtime.sync_gallery(session)
        session.commit()
    summary = env.get("/api/gallery").json()["summary"]
    assert summary["embeddings_stale"] == 2 and summary["index_images"] == 0  # stale images are NOT searched
    assert env.get("/api/gallery/subject-001").json()["embedding_status"] == "stale"

    rebuilt = env.post("/api/gallery/rebuild", role="operator")
    assert rebuilt.status_code == 200 and rebuilt.json()["detail"]["rebuilt"] == 2
    summary = env.get("/api/gallery").json()["summary"]
    assert summary["embeddings_ready"] == 2 and summary["index_images"] == 2


def test_gallery_actions_are_audited(env):
    env.enroll("subject-001", RED)
    env.delete("/api/gallery/subject-001", role="operator", params={"confirm": "subject-001"})
    with env.runtime.session_factory() as session:
        actions = [e.action for e in session.scalars(select(AuditEvent).order_by(AuditEvent.id))]
    assert "gallery.enroll" in actions and "gallery.delete" in actions
    log = env.get("/api/audit", role="admin").json()
    assert all("embedding" not in str(entry) for entry in log)  # audit never carries embeddings


def test_yellow_enrollee_does_not_disturb_others(env):
    env.enroll("subject-001", RED)
    env.enroll("subject-002", YELLOW)
    assert env.get("/api/gallery").json()["summary"]["index_identities"] == 2
