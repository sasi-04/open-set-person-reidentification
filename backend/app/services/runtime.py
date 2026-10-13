"""
The runtime: everything that is created ONCE when the server starts.

In plain words: loading a neural network takes a moment and uses memory, so the
server loads the embedding model and the person detector a single time and keeps
them for its whole life, together with the in-memory gallery index and the file
stores. Request handlers receive this object and use it; they never load models.

If a model cannot be loaded (weights missing, corrupted ...) the server still
starts: the problem is remembered and shown by ``/api/readiness`` and in the UI,
and the features that need that model respond with a clear 503 error.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np
import torch
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import Settings
from ..core.device import describe_device, resolve_device
from ..core.errors import AppError, ModelUnavailable
from ..cv.detection.detector import PersonDetector
from ..cv.embedding.extractor import OSNetExtractor
from ..cv.embedding.factory import build_extractor
from ..cv.face.engine import FaceEngine
from ..cv.face.registry import FACE_DIM
from ..cv.retrieval.gallery_index import GalleryIndex, IndexEntry
from ..cv.retrieval.validation import InvalidEmbedding, check_embedding
from ..db.models import FaceTemplate, Identity, ReferenceImage
from .storage import FileStore

if TYPE_CHECKING:  # avoids an import cycle: the job service itself needs Runtime
    from .evaluation_service import EvaluationJobs

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    settings: Settings
    session_factory: sessionmaker[Session]
    index: GalleryIndex
    references: FileStore
    queries: FileStore
    device: torch.device | None = None
    extractor: OSNetExtractor | None = None
    extractor_error: str | None = None
    detector: PersonDetector | None = None
    detector_error: str | None = None
    face_engine: FaceEngine | None = None
    face_error: str | None = None
    face_index: GalleryIndex = field(default_factory=lambda: GalleryIndex(dim=FACE_DIM))  # one row per usable reference face
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    index_lock: threading.Lock = field(default_factory=threading.Lock)
    jobs: EvaluationJobs | None = None  # attached by the application factory
    demo_sandbox: object | None = None  # the built-in example's private gallery (services/demo_service); never touches the real one
    demo_lock: threading.Lock = field(default_factory=threading.Lock)

    # ---------------------------------------------------------------- creation
    @classmethod
    def create(
        cls,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        load_models: bool = True,
        extractor=None,
        detector=None,
        face_engine=None,
    ) -> Runtime:
        """``extractor`` / ``detector`` / ``face_engine`` let tests plug in fakes instead of loading real networks."""
        settings.ensure_directories()
        runtime = cls(
            settings=settings,
            session_factory=session_factory,
            index=GalleryIndex(dim=0),
            references=FileStore(settings.reference_dir),
            queries=FileStore(settings.query_dir),
        )
        if extractor is not None or detector is not None:
            runtime.extractor, runtime.detector = extractor, detector
            if extractor is None:
                runtime.extractor_error = "No embedding model was provided."
            if detector is None:
                runtime.detector_error = "No detector was provided."
            runtime.face_engine = face_engine
            if face_engine is None:
                runtime.face_error = "No face model was provided."
        elif load_models:
            runtime._load_models()
        else:
            runtime.extractor_error = runtime.detector_error = "Model loading is disabled."
            runtime.face_error = "Model loading is disabled."

        if runtime.extractor is not None:
            runtime.index = GalleryIndex(dim=runtime.extractor.dim)
        return runtime

    def _load_models(self) -> None:
        try:
            self.device = resolve_device(self.settings.device)
        except AppError as exc:
            self.extractor_error = self.detector_error = exc.message
            logger.error("Device selection failed: %s", exc.message)
            return

        try:
            self.extractor = build_extractor(self.settings, self.device)  # type: ignore[assignment]
        except AppError as exc:
            self.extractor_error = exc.message
            logger.error("Embedding model unavailable: %s", exc.message)

        try:
            self.detector = PersonDetector.load(
                self.settings.detector_model,
                self.settings.weights_dir,
                self.device,
                min_size=self.settings.detector_min_size,
                score_threshold=self.settings.detector_score_threshold,
                max_people=self.settings.detector_max_people,
            )
        except AppError as exc:
            self.detector_error = exc.message
            logger.warning("Person detector unavailable (crop/box modes still work): %s", exc.message)

        if not self.settings.face_matching:
            self.face_error = "Face matching is switched off (REID_FACE_MATCHING=false): body evidence only."
            return
        try:
            self.face_engine = FaceEngine.load(self.settings.weights_dir)
        except AppError as exc:  # optional: without it the system runs on body evidence, as before
            self.face_error = exc.message
            logger.warning("Face models unavailable (matching uses the body only): %s", exc.message)

    # ------------------------------------------------------------------- guards
    def require_extractor(self) -> OSNetExtractor:
        if self.extractor is None:
            raise ModelUnavailable(self.extractor_error or "The embedding model is not loaded.")
        return self.extractor

    def require_detector(self) -> PersonDetector:
        if self.detector is None:
            raise ModelUnavailable(
                (self.detector_error or "The person detector is not loaded.")
                + " You can still upload a tight crop of one person and choose 'image is a crop'."
            )
        return self.detector

    @property
    def fingerprint(self) -> str | None:
        return self.extractor.fingerprint if self.extractor else None

    @property
    def device_info(self) -> dict:
        if self.device is None:
            return {"type": "unavailable"}
        return describe_device(self.device)

    # --------------------------------------------------------------- gallery index
    def sync_gallery(self, session: Session) -> None:
        """Mark embeddings made by a different model as stale, then rebuild the in-memory index.

        Call after any change to the gallery. Safe to call from several threads.
        """
        if self.extractor is None:
            return
        with self.index_lock:
            started = time.perf_counter()
            fingerprint, dim = self.extractor.fingerprint, self.extractor.dim
            session.execute(
                update(ReferenceImage)
                .where(
                    ReferenceImage.embedding_status == "ready",
                    (ReferenceImage.embedding_model != fingerprint) | (ReferenceImage.embedding_dim != dim),
                )
                .values(embedding_status="stale")
            )
            session.flush()

            rows = session.execute(
                select(ReferenceImage.image_uid, ReferenceImage.embedding, ReferenceImage.identity_id)
                .where(ReferenceImage.embedding_status == "ready", ReferenceImage.embedding.is_not(None))
            ).all()
            reference_of = {pk: ref for pk, ref in session.execute(select(Identity.id, Identity.reference_id)).all()}
            entries: list[IndexEntry] = []
            corrupt: list[str] = []
            for uid, blob, identity_id in rows:
                if identity_id not in reference_of:
                    continue
                try:  # a stored fingerprint that is damaged must not poison every search: set it aside
                    vector = check_embedding(np.frombuffer(blob, dtype=np.float32), dim)
                except (InvalidEmbedding, ValueError) as exc:
                    corrupt.append(uid)
                    logger.warning("Stored reference embedding %s is unusable and was excluded: %s", uid, getattr(exc, "message", exc))
                    continue
                entries.append(IndexEntry(reference_of[identity_id], uid, vector))
            if corrupt:
                session.execute(update(ReferenceImage).where(ReferenceImage.image_uid.in_(corrupt)).values(embedding_status="failed"))
                session.flush()
            snapshot = self.index.replace(entries)
            faces = self._sync_faces(session, reference_of)
            logger.info(
                "Gallery index v%d: %d identities, %d images, %d usable faces (%.1f ms)",
                snapshot.version, snapshot.n_identities, snapshot.n_images, faces, (time.perf_counter() - started) * 1000,
            )

    def _sync_faces(self, session: Session, reference_of: dict[int, str]) -> int:
        """Rebuild the face index from the stored face fingerprints. Returns how many usable faces it holds."""
        if self.face_engine is None:
            self.face_index.replace([])
            return 0
        fingerprint = self.face_engine.fingerprint
        session.execute(
            update(FaceTemplate)
            .where(FaceTemplate.status.in_(("ready", "weak")), FaceTemplate.embedding_model != fingerprint)
            .values(status="stale")
        )
        session.flush()
        rows = session.execute(
            select(FaceTemplate.id, FaceTemplate.embedding, ReferenceImage.image_uid, ReferenceImage.identity_id)
            .join(ReferenceImage, ReferenceImage.id == FaceTemplate.image_id)
            .where(FaceTemplate.status == "ready", FaceTemplate.embedding.is_not(None))
        ).all()
        entries: list[IndexEntry] = []
        corrupt: list[int] = []
        for template_id, blob, uid, identity_id in rows:
            if identity_id not in reference_of:
                continue
            try:
                vector = check_embedding(np.frombuffer(blob, dtype=np.float32), self.face_engine.dim)
            except (InvalidEmbedding, ValueError) as exc:
                corrupt.append(template_id)
                logger.warning("Stored face fingerprint of image %s is unusable and was excluded: %s", uid, getattr(exc, "message", exc))
                continue
            entries.append(IndexEntry(reference_of[identity_id], uid, vector))
        if corrupt:
            session.execute(update(FaceTemplate).where(FaceTemplate.id.in_(corrupt)).values(status="failed"))
            session.flush()
        self.face_index.replace(entries)
        return len(entries)
