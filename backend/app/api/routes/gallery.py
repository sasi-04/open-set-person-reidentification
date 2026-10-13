"""Gallery routes: enroll, browse, add images, delete, rebuild, reset."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import select

from ...core.errors import NotFound, ValidationFailed
from ...db.models import ReferenceImage
from ...schemas.gallery import EnrollResponse, GalleryPage, IdentityDetail, MutationResult, ResetRequest
from ...services import face_service, gallery_service
from ..deps import AdminRole, OperatorRole, RuntimeDep, SessionDep, ViewerRole, read_upload

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

RESET_PHRASE = "RESET DEMO GALLERY"


@router.get("", response_model=GalleryPage, summary="Browse enrolled identities")
def list_gallery(
    runtime: RuntimeDep, session: SessionDep, _: ViewerRole,
    search: Annotated[str | None, Query(max_length=64)] = None,
    sort: Annotated[Literal["reference_id", "created_at", "updated_at", "n_images"], Query()] = "reference_id",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
    embedding_status: Annotated[Literal["ready", "stale", "failed", "mixed"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GalleryPage:
    return gallery_service.list_gallery(
        session, runtime, search=search, sort=sort, descending=order == "desc", status=embedding_status,
        limit=limit, offset=offset,
    )


@router.post("/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED,
             summary="Enroll a new authorised identity from one or more images")
def enroll(
    runtime: RuntimeDep, session: SessionDep, role: OperatorRole,
    reference_id: Annotated[str, Form(description="Pseudonymous label, e.g. 'subject-017'")],
    images: Annotated[list[UploadFile], File(description="One or more images of the SAME person")],
    consent_confirmed: Annotated[bool, Form(description="Must be true: the person is authorised to be enrolled")] = False,
    label: Annotated[str | None, Form(max_length=80)] = None,
    images_are_crops: Annotated[bool, Form(description="True when each image is already a tight crop of one person")] = False,
) -> EnrollResponse:
    files = [read_upload(f, runtime.settings.max_upload_bytes) for f in images]
    return gallery_service.enroll(
        session, runtime, reference_id=reference_id, label=label, files=files, images_are_crops=images_are_crops,
        consent_confirmed=consent_confirmed, role_name=role.name,
    )


@router.post("/rebuild", response_model=MutationResult, summary="Re-embed every reference image with the current model")
def rebuild(runtime: RuntimeDep, session: SessionDep, role: OperatorRole) -> MutationResult:
    outcome = gallery_service.rebuild_embeddings(session, runtime, role.name)
    return MutationResult(message=f"Rebuilt {outcome['rebuilt']} embeddings ({outcome['failed']} failed).", detail=outcome)


@router.post("/analyse-faces", response_model=MutationResult, summary="Find and fingerprint the faces in reference images that have none on file yet")
def analyse_faces(runtime: RuntimeDep, session: SessionDep, role: OperatorRole,
                  everything: Annotated[bool, Query(description="Re-analyse every reference image, not only the ones without a current face record.")] = False) -> MutationResult:
    outcome = face_service.analyse_missing_faces(session, runtime, role.name, everything=everything)
    return MutationResult(message=outcome["message"], detail=outcome)


@router.post("/reset", response_model=MutationResult, summary="DESTRUCTIVE: delete the whole demonstration gallery")
def reset(body: ResetRequest, runtime: RuntimeDep, session: SessionDep, role: AdminRole) -> MutationResult:
    if body.confirm != RESET_PHRASE:
        raise ValidationFailed(f"To reset, send confirm = '{RESET_PHRASE}'.")
    identities, images = gallery_service.reset_gallery(session, runtime, role.name)
    return MutationResult(message=f"Deleted {identities} identities and {images} images.",
                          detail={"identities": identities, "images": images})


@router.get("/{reference_id}", response_model=IdentityDetail, summary="One identity with its reference images")
def get_identity(reference_id: str, session: SessionDep, _: ViewerRole) -> IdentityDetail:
    return gallery_service.to_detail(gallery_service.get_identity(session, reference_id))


@router.post("/{reference_id}/images", response_model=EnrollResponse, summary="Add reference images to an identity")
def add_images(
    reference_id: str, runtime: RuntimeDep, session: SessionDep, role: OperatorRole,
    images: Annotated[list[UploadFile], File()],
    images_are_crops: Annotated[bool, Form()] = False,
) -> EnrollResponse:
    files = [read_upload(f, runtime.settings.max_upload_bytes) for f in images]
    return gallery_service.add_images(
        session, runtime, reference_id=reference_id, files=files, images_are_crops=images_are_crops, role_name=role.name
    )


@router.delete("/{reference_id}", response_model=MutationResult, summary="Delete an identity and its images")
def delete_identity(
    reference_id: str, runtime: RuntimeDep, session: SessionDep, role: OperatorRole,
    confirm: Annotated[str | None, Query(description="Must equal the reference ID")] = None,
) -> MutationResult:
    removed = gallery_service.delete_identity(session, runtime, reference_id, confirm, role.name)
    return MutationResult(message=f"Deleted '{reference_id}' and {removed} reference images.", detail={"images": removed})


@router.get("/{reference_id}/images/{image_uid}", summary="A reference image (JPEG)")
def reference_image(reference_id: str, image_uid: str, runtime: RuntimeDep, session: SessionDep, _: ViewerRole) -> Response:
    image = session.scalar(
        select(ReferenceImage).join(ReferenceImage.identity).where(
            ReferenceImage.image_uid == image_uid, ReferenceImage.identity.has(reference_id=reference_id))
    )
    if image is None:
        raise NotFound("Image not found.")
    return Response(runtime.references.read_bytes(image.file_path), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})
