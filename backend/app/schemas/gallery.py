"""Request/response shapes for gallery management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GalleryImageModel(BaseModel):
    image_uid: str
    width: int
    height: int
    created_at: datetime
    embedding_status: str = Field(description="ready | stale (model changed - rebuild) | failed")
    quality_flags: list[str] = Field(default_factory=list)
    url: str
    face_status: str = Field(
        default="not_analysed",
        description="ready (usable face on file) | weak (face found but unusable) | no_face | stale | failed | not_analysed",
    )
    face_note: str | None = Field(default=None, description="Plain-language reason when the face is not used.")
    face_box: list[float] | None = Field(default=None, description="[x1, y1, x2, y2] of the face inside this stored picture")


class IdentitySummary(BaseModel):
    reference_id: str
    label: str | None = None
    n_images: int
    created_at: datetime
    updated_at: datetime
    embedding_status: str = Field(description="ready | stale | failed | mixed")
    thumbnail_url: str | None = None
    n_faces: int = Field(default=0, description="How many reference images have a usable face on file.")


class IdentityDetail(IdentitySummary):
    consent_confirmed: bool
    images: list[GalleryImageModel]


class GallerySummary(BaseModel):
    identities: int
    images: int
    embeddings_ready: int
    embeddings_stale: int
    embeddings_failed: int
    index_version: int
    index_identities: int
    index_images: int
    embedding_model: str | None = None
    faces_usable: int = Field(default=0, description="Reference images with a usable face on file.")
    faces_without_usable_face: int = Field(default=0, description="Reference images analysed but with no usable face (body matching only).")
    faces_not_analysed: int = Field(default=0, description="Reference images the face analysis has not looked at yet.")
    face_model: str | None = None
    strategy: str = "Individual image embeddings per identity; an identity's score is its best-matching image."


class GalleryPage(BaseModel):
    items: list[IdentitySummary]
    total: int
    limit: int
    offset: int
    summary: GallerySummary


class EnrollFileResult(BaseModel):
    filename: str
    status: str = Field(description="enrolled | rejected")
    reason: str | None = None
    image_uid: str | None = None
    face_status: str | None = Field(default=None, description="ready | weak | no_face | not_analysed (face models not loaded)")
    face_note: str | None = None


class EnrollResponse(BaseModel):
    identity: IdentityDetail
    files: list[EnrollFileResult]
    warnings: list[str] = Field(default_factory=list)


class ResetRequest(BaseModel):
    confirm: str = Field(description="Must equal 'RESET DEMO GALLERY'.")


class MutationResult(BaseModel):
    ok: bool = True
    message: str
    detail: dict = Field(default_factory=dict)
