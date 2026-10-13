"""
Gallery management: enroll people, add images, inspect, delete, rebuild.

In plain words: this is the "who is enrolled" module. Safety rules baked in:

  * enrolling requires an explicit confirmation that the person is authorised;
  * identities are named by a pseudonymous ``reference_id`` (letters, digits, . _ -),
    never by a database ID or file name;
  * we store our own JPEG of the PERSON CROP, not the raw upload;
  * a photo with several people is rejected (we will not guess which one to enroll);
  * deleting an identity needs its reference_id typed back, and removes its files too;
  * a rejected query is never enrolled automatically - enrollment is always a deliberate act.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import AppError, Conflict, NotFound, ValidationFailed
from ..cv.geometry import Box, crop_person, pad_to_person_aspect
from ..cv.imaging import DecodedImage, decode_image, load_rgb_file
from ..cv.quality import assess_crop
from ..db.models import FaceTemplate, Identity, ReferenceImage, utcnow
from ..schemas.gallery import (
    EnrollFileResult,
    EnrollResponse,
    GalleryImageModel,
    GalleryPage,
    GallerySummary,
    IdentityDetail,
    IdentitySummary,
)
from . import face_service
from .audit import record_audit
from .runtime import Runtime

logger = logging.getLogger(__name__)

REFERENCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
MAX_IMAGES_PER_IDENTITY = 30
DUPLICATE_PERSON_WARNING_SCORE = 0.90  # a NEW enrollee this similar to an existing one may be a duplicate


@dataclass
class UploadedFile:
    filename: str
    content_type: str | None
    data: bytes


def validate_reference_id(reference_id: str) -> str:
    reference_id = (reference_id or "").strip()
    if not REFERENCE_ID_PATTERN.fullmatch(reference_id):
        raise ValidationFailed(
            "The reference ID must be 2-64 characters: letters, digits, '.', '_' or '-', starting with a letter or digit. "
            "Use a pseudonymous label - not a real name or an ID number."
        )
    return reference_id


# ---------------------------------------------------------------------------------
# Reading the gallery
# ---------------------------------------------------------------------------------
def _status_of(images: list[ReferenceImage]) -> str:
    statuses = {image.embedding_status for image in images}
    if not statuses:
        return "ready"
    return statuses.pop() if len(statuses) == 1 else "mixed"


def _image_url(reference_id: str, image_uid: str) -> str:
    return f"/api/gallery/{reference_id}/images/{image_uid}"


def to_summary(identity: Identity) -> IdentitySummary:
    first = identity.images[0] if identity.images else None
    return IdentitySummary(
        reference_id=identity.reference_id,
        label=identity.label,
        n_images=len(identity.images),
        created_at=identity.created_at,
        updated_at=identity.updated_at,
        embedding_status=_status_of(identity.images),
        thumbnail_url=_image_url(identity.reference_id, first.image_uid) if first else None,
        n_faces=sum(1 for image in identity.images if image.face is not None and image.face.status == "ready"),
    )


def _face_fields(image: ReferenceImage) -> dict:
    face = image.face
    if face is None:
        return {"face_status": "not_analysed", "face_note": face_service.explain("not_analysed", [])}
    return {"face_status": face.status, "face_note": face_service.explain(face.status, list(face.flags or [])), "face_box": face.face_box}


def to_detail(identity: Identity) -> IdentityDetail:
    return IdentityDetail(
        **to_summary(identity).model_dump(),
        consent_confirmed=identity.consent_confirmed,
        images=[
            GalleryImageModel(
                image_uid=image.image_uid, width=image.width, height=image.height, created_at=image.created_at,
                embedding_status=image.embedding_status, quality_flags=list(image.quality_flags or []),
                url=_image_url(identity.reference_id, image.image_uid), **_face_fields(image),
            )
            for image in identity.images
        ],
    )


def get_identity(session: Session, reference_id: str) -> Identity:
    identity = session.scalar(select(Identity).where(Identity.reference_id == reference_id))
    if identity is None:
        raise NotFound(f"No enrolled identity with reference ID '{reference_id}'.")
    return identity


def summarise(session: Session, runtime: Runtime) -> GallerySummary:
    per_status = session.execute(
        select(ReferenceImage.embedding_status, func.count()).group_by(ReferenceImage.embedding_status)
    ).all()
    counts = dict(per_status)
    face_counts = dict(session.execute(select(FaceTemplate.status, func.count()).group_by(FaceTemplate.status)).all())
    images = sum(counts.values())
    snapshot = runtime.index.snapshot
    return GallerySummary(
        identities=session.scalar(select(func.count()).select_from(Identity)) or 0,
        images=images,
        embeddings_ready=counts.get("ready", 0),
        embeddings_stale=counts.get("stale", 0),
        embeddings_failed=counts.get("failed", 0),
        index_version=snapshot.version,
        index_identities=snapshot.n_identities,
        index_images=snapshot.n_images,
        embedding_model=runtime.fingerprint,
        faces_usable=face_counts.get("ready", 0),
        faces_without_usable_face=face_counts.get("weak", 0) + face_counts.get("no_face", 0),
        faces_not_analysed=max(0, images - sum(face_counts.values())) + face_counts.get("stale", 0) + face_counts.get("failed", 0),
        face_model=runtime.face_engine.fingerprint if runtime.face_engine else None,
    )


_SORT_COLUMNS = {"reference_id": Identity.reference_id, "created_at": Identity.created_at, "updated_at": Identity.updated_at}


def list_gallery(
    session: Session, runtime: Runtime, *, search: str | None, sort: str, descending: bool,
    status: str | None, limit: int, offset: int,
) -> GalleryPage:
    query = select(Identity)
    if search:
        needle = f"%{search.strip().lower()}%"
        query = query.where(
            func.lower(Identity.reference_id).like(needle) | func.lower(func.coalesce(Identity.label, "")).like(needle)
        )
    column = _SORT_COLUMNS.get(sort, Identity.reference_id)
    ordering = column.desc() if descending else column.asc()

    items = [to_summary(identity) for identity in session.scalars(query.order_by(ordering, Identity.id))]
    if status:
        items = [item for item in items if item.embedding_status == status]
    if sort == "n_images":
        items.sort(key=lambda item: (item.n_images, item.reference_id), reverse=descending)
    return GalleryPage(
        items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset,
        summary=summarise(session, runtime),
    )


# ---------------------------------------------------------------------------------
# Enrolling and adding images
# ---------------------------------------------------------------------------------
def enroll(
    session: Session, runtime: Runtime, *, reference_id: str, label: str | None, files: list[UploadedFile],
    images_are_crops: bool, consent_confirmed: bool, role_name: str,
) -> EnrollResponse:
    """Create a NEW identity from one or more images."""
    reference_id = validate_reference_id(reference_id)
    label = (label or "").strip() or None
    if label and len(label) > 80:
        raise ValidationFailed("The label may be at most 80 characters.")
    if session.scalar(select(Identity.id).where(Identity.reference_id == reference_id)) is not None:
        raise Conflict(f"'{reference_id}' is already enrolled. Use 'Add images' to extend it.")
    if not consent_confirmed:
        raise ValidationFailed("Confirm that this person is authorised to be enrolled (consent_confirmed must be true).")
    return _ingest(session, runtime, None, reference_id, label, files, images_are_crops, role_name, "gallery.enroll")


def add_images(
    session: Session, runtime: Runtime, *, reference_id: str, files: list[UploadedFile],
    images_are_crops: bool, role_name: str,
) -> EnrollResponse:
    """Add more reference images to an EXISTING identity."""
    identity = get_identity(session, reference_id)
    return _ingest(session, runtime, identity, reference_id, None, files, images_are_crops, role_name, "gallery.add_images")


def _prepare_reference_crop(
    runtime: Runtime, image: DecodedImage, images_are_crops: bool
) -> tuple[np.ndarray, str, list[str]]:
    """Return (crop pixels, source label, quality flags), or raise ValidationFailed with the reason."""
    box: Box | None = None
    detector_score: float | None = None
    if images_are_crops:
        crop, source = pad_to_person_aspect(image.pixels), "crop"
    else:
        detections = runtime.require_detector().detect(image.pixels)
        if not detections:
            raise ValidationFailed("No person was detected. Upload a clearer photo, or tick 'image is a person crop'.")
        if len(detections) > 1:
            raise ValidationFailed(
                f"{len(detections)} people were detected. Upload a photo with only the person to enroll, or crop it "
                "first, so the wrong person is never enrolled by mistake."
            )
        box, detector_score = detections[0].box, detections[0].score
        crop, source = crop_person(image.pixels, box), "detected"

    report = assess_crop(
        crop, source_box=box, image_size=(image.width, image.height) if box else None, detector_score=detector_score
    )
    if not report.usable:
        raise ValidationFailed(report.blocking_reason or "The crop is unusable.")
    return crop, source, report.flags


@dataclass
class _Prepared:
    decoded: DecodedImage
    crop: np.ndarray
    source: str
    flags: list[str]
    result: EnrollFileResult


def _ingest(
    session: Session, runtime: Runtime, identity: Identity | None, reference_id: str, label: str | None,
    files: list[UploadedFile], images_are_crops: bool, role_name: str, audit_action: str,
) -> EnrollResponse:
    if not files:
        raise ValidationFailed("Upload at least one image.")
    if len(files) > runtime.settings.max_enroll_files:
        raise ValidationFailed(f"At most {runtime.settings.max_enroll_files} images can be uploaded at once.")
    extractor = runtime.require_extractor()

    seen_hashes = {image.sha256 for image in identity.images} if identity else set()
    room = MAX_IMAGES_PER_IDENTITY - (len(identity.images) if identity else 0)

    # 1) Validate and crop every file; a bad file is reported but never sinks the others.
    prepared: list[_Prepared] = []
    results: list[EnrollFileResult] = []
    for file in files:
        name = _display_name(file.filename)
        try:
            if len(prepared) >= room:
                raise ValidationFailed(f"An identity can hold at most {MAX_IMAGES_PER_IDENTITY} reference images.")
            decoded = decode_image(file.data, filename=file.filename, content_type=file.content_type, settings=runtime.settings)
            if decoded.sha256 in seen_hashes:
                raise ValidationFailed("This exact image is already enrolled for this identity.")
            crop, source, flags = _prepare_reference_crop(runtime, decoded, images_are_crops)
        except AppError as exc:
            results.append(EnrollFileResult(filename=name, status="rejected", reason=exc.message))
            continue
        except Exception:
            logger.exception("Unexpected error while preparing an enrollment image")
            results.append(EnrollFileResult(filename=name, status="rejected", reason="The image could not be processed."))
            continue
        seen_hashes.add(decoded.sha256)
        result = EnrollFileResult(filename=name, status="enrolled")
        prepared.append(_Prepared(decoded, crop, source, flags, result))
        results.append(result)

    if not prepared:
        raise ValidationFailed("None of the images could be enrolled.", details={"files": [r.model_dump() for r in results]})

    # 2) One batched forward pass for all accepted crops.
    embeddings = extractor.embed([item.crop for item in prepared])
    warnings = _duplicate_person_warnings(runtime, reference_id, embeddings)

    # 2b) Face analysis of each reference picture (when the face models are loaded): a usable face adds a second fingerprint.
    analyses: list[face_service.ReferenceAnalysis | None] = [None] * len(prepared)
    if runtime.face_engine is not None:
        analyses = [face_service.analyse_reference_crop(runtime.face_engine, item.crop) for item in prepared]
        warnings += _duplicate_face_warnings(runtime, reference_id, analyses)
        warnings += _face_enrolment_warnings(identity is None, analyses)

    # 3) Save files and database rows.
    if identity is None:
        identity = Identity(reference_id=reference_id, label=label, consent_confirmed=True)
        session.add(identity)
    identity.updated_at = utcnow()
    for item, embedding, analysis in zip(prepared, embeddings, analyses, strict=True):
        stored_name = runtime.references.save_jpeg(item.crop)
        item.result.image_uid = stored_name.removesuffix(".jpg")
        row = ReferenceImage(
            image_uid=item.result.image_uid, file_path=stored_name, sha256=item.decoded.sha256,
            width=item.crop.shape[1], height=item.crop.shape[0], source=item.source, quality_flags=item.flags,
            embedding=embedding.astype(np.float32).tobytes(), embedding_model=extractor.fingerprint,
            embedding_dim=extractor.dim, embedding_status="ready",
        )
        identity.images.append(row)
        if analysis is not None:
            face_service.store_template(session, runtime, row, analysis)
            item.result.face_status, item.result.face_note = analysis.status, analysis.note
        else:
            item.result.face_status = "not_analysed"

    session.flush()
    record_audit(session, role_name, audit_action, reference_id, images=len(prepared), rejected=len(results) - len(prepared))
    runtime.sync_gallery(session)  # refresh the in-memory index (bumps its version)
    session.commit()
    session.refresh(identity)
    return EnrollResponse(identity=to_detail(identity), files=results, warnings=warnings)


FACE_DUPLICATE_WARNING_SCORE = 0.50  # a NEW face this similar to ANOTHER enrolled person is probably the same human


def _duplicate_face_warnings(runtime: Runtime, reference_id: str, analyses: list) -> list[str]:
    warnings = set()
    for analysis in analyses:
        if analysis is None or analysis.status != "ready" or analysis.reading is None:
            continue
        for candidate in runtime.face_index.search(analysis.reading.embedding, top_k=2):
            if candidate.reference_id != reference_id and candidate.score >= FACE_DUPLICATE_WARNING_SCORE:
                warnings.add(
                    f"The face in a new image for '{reference_id}' is very similar (face similarity {candidate.score:.2f}) to the "
                    f"enrolled identity '{candidate.reference_id}'. Check that the same person is not enrolled twice."
                )
    return sorted(warnings)


def _face_enrolment_warnings(is_new: bool, analyses: list) -> list[str]:
    """Tell the operator, in plain words, when an enrolment adds no usable face (so that identity can only be matched by body)."""
    if not analyses or any(a is not None and a.status == "ready" for a in analyses):
        return []
    reasons = sorted({a.note for a in analyses if a is not None and a.note})
    start = "No usable face was found in these images" if is_new else "None of the new images has a usable face"
    return [f"{start}, so face matching cannot verify this person - only clothing and build can, which is weaker evidence. "
            "Add a clear, front-facing photo of the face for reliable matching. " + " ".join(reasons)]


def _display_name(name: str | None) -> str:
    """File names are only echoed back for display; strip any directory part and cap the length."""
    return (name or "upload").replace("\\", "/").rsplit("/", 1)[-1][:80]


def _duplicate_person_warnings(runtime: Runtime, reference_id: str, embeddings: np.ndarray) -> list[str]:
    warnings = set()
    for embedding in embeddings:
        for candidate in runtime.index.search(embedding, top_k=2):
            if candidate.reference_id != reference_id and candidate.score >= DUPLICATE_PERSON_WARNING_SCORE:
                warnings.add(
                    f"A new image for '{reference_id}' is very similar (score {candidate.score:.2f}) to the existing "
                    f"identity '{candidate.reference_id}'. Check that the same person is not enrolled twice."
                )
    return sorted(warnings)


# ---------------------------------------------------------------------------------
# Deleting, resetting, rebuilding
# ---------------------------------------------------------------------------------
def delete_identity(session: Session, runtime: Runtime, reference_id: str, confirm: str | None, role_name: str) -> int:
    identity = get_identity(session, reference_id)
    if confirm != reference_id:
        raise ValidationFailed("Deleting needs confirmation: pass the identity's reference ID as 'confirm'.")
    names = [image.file_path for image in identity.images]
    session.delete(identity)
    record_audit(session, role_name, "gallery.delete", reference_id, images=len(names))
    session.flush()
    runtime.sync_gallery(session)
    session.commit()
    for name in names:  # files are removed only after the database change succeeded
        runtime.references.delete(name)
    return len(names)


def reset_gallery(session: Session, runtime: Runtime, role_name: str) -> tuple[int, int]:
    identities = list(session.scalars(select(Identity)))
    n_images = sum(len(identity.images) for identity in identities)
    for identity in identities:
        session.delete(identity)
    record_audit(session, role_name, "gallery.reset", None, identities=len(identities), images=n_images)
    session.flush()
    runtime.sync_gallery(session)
    session.commit()
    runtime.references.clear()
    return len(identities), n_images


def rebuild_embeddings(session: Session, runtime: Runtime, role_name: str) -> dict:
    """Re-embed every stored reference crop with the CURRENT model (needed after a model change)."""
    extractor = runtime.require_extractor()
    images = list(session.scalars(select(ReferenceImage).order_by(ReferenceImage.id)))
    rebuilt = failed = 0
    batch_size = max(8, extractor.batch_size)

    for start in range(0, len(images), batch_size):
        crops, usable = [], []
        for image in images[start : start + batch_size]:
            try:
                crops.append(load_rgb_file(runtime.references.path_for(image.file_path)))
                usable.append(image)
            except Exception:  # missing or corrupt file: mark it failed and carry on
                logger.warning("Reference image %s could not be read during rebuild", image.image_uid)
                image.embedding_status = "failed"
                failed += 1
        if crops:
            for image, vector in zip(usable, extractor.embed(crops), strict=True):
                image.embedding = vector.astype(np.float32).tobytes()
                image.embedding_model, image.embedding_dim = extractor.fingerprint, extractor.dim
                image.embedding_status = "ready"
                rebuilt += 1

    record_audit(session, role_name, "gallery.rebuild", None, rebuilt=rebuilt, failed=failed)
    session.flush()
    runtime.sync_gallery(session)
    session.commit()
    return {"rebuilt": rebuilt, "failed": failed, "total": len(images)}
