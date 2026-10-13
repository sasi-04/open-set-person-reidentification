"""Re-identification routes: detect, predict, history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from ...core.errors import ValidationFailed
from ...cv.imaging import decode_image
from ...schemas.reid import DetectResponse, HistoryDetail, HistoryPage, PredictMode, PredictResponse
from ...services import reid_service
from ..deps import RuntimeDep, SessionDep, ViewerRole, read_upload

router = APIRouter(prefix="/api/reid", tags=["re-identification"])


def _parse_box(text: str | None) -> list[float] | None:
    if not text:
        return None
    try:
        return [float(part) for part in text.split(",")]
    except ValueError:
        raise ValidationFailed("box must be four comma-separated numbers: x1,y1,x2,y2") from None


@router.post("/detect", response_model=DetectResponse, summary="Find the people in an image (no matching)")
def detect(
    runtime: RuntimeDep, request_role: ViewerRole,
    image: Annotated[UploadFile, File(description="JPEG, PNG, WebP or BMP")],
) -> DetectResponse:
    upload = read_upload(image, runtime.settings.max_upload_bytes)
    decoded = decode_image(upload.data, filename=upload.filename, content_type=upload.content_type, settings=runtime.settings)
    return reid_service.detect_people(runtime, decoded, reid_service.new_request_id())


@router.post("/predict", response_model=PredictResponse, summary="Re-identify the people in an image")
def predict(
    runtime: RuntimeDep, session: SessionDep, role: ViewerRole,
    image: Annotated[UploadFile, File(description="JPEG, PNG, WebP or BMP")],
    mode: Annotated[PredictMode, Form(description="all = detect everyone | box = one person | crop = image is one person")] = PredictMode.ALL,
    box: Annotated[str | None, Form(description="x1,y1,x2,y2 in pixels (mode=box)")] = None,
    top_k: Annotated[int, Form(ge=1, le=10)] = 5,
) -> PredictResponse:
    upload = read_upload(image, runtime.settings.max_upload_bytes)
    decoded = decode_image(upload.data, filename=upload.filename, content_type=upload.content_type, settings=runtime.settings)
    return reid_service.predict(
        runtime, session, decoded, mode=mode, raw_box=_parse_box(box), top_k=top_k,
        role_name=role.name, request_id=reid_service.new_request_id(),
    )


@router.get("/history", response_model=HistoryPage, summary="Recent re-identification requests")
def history(
    session: SessionDep, _: ViewerRole,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    outcome: Annotated[str | None, Query(pattern="^(accepted|unknown|review_required|processing_error)$")] = None,
) -> HistoryPage:
    return reid_service.list_history(session, limit=limit, offset=offset, outcome=outcome)


@router.get("/history/{request_id}", response_model=HistoryDetail, summary="One past request in detail")
def history_item(request_id: str, session: SessionDep, _: ViewerRole) -> HistoryDetail:
    return reid_service.history_detail(session, request_id)


@router.get("/history/{request_id}/export", summary="Download the decision record of one request (JSON or CSV)")
def history_export(request_id: str, session: SessionDep, _: ViewerRole,
                   format: Annotated[str, Query(pattern="^(json|csv)$")] = "json") -> Response:
    body, media_type = reid_service.export_record(session, request_id, format)
    return Response(body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="decision-{request_id[:8]}.{format}"'})


@router.get("/history/{request_id}/crops/{index}", summary="The stored query crop (only during the retention window)")
def history_crop(request_id: str, index: int, runtime: RuntimeDep, session: SessionDep, _: ViewerRole) -> Response:
    return Response(reid_service.crop_bytes(runtime, session, request_id, index), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})
