"""
Retention and cleanup.

In plain words: query crops are only kept for ``REID_QUERY_RETENTION_HOURS`` so
the history screen can show them briefly, and history rows are removed after
``REID_HISTORY_RETENTION_DAYS``. This runs at startup and whenever an admin
presses "Run cleanup now". Reference images are NOT touched here: they live
until someone deliberately deletes the identity.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import InferenceRecord, InferenceResult
from . import video_service
from .audit import record_audit
from .runtime import Runtime

logger = logging.getLogger(__name__)


def run_cleanup(session: Session, runtime: Runtime, role_name: str) -> dict:
    now = datetime.now(UTC)

    # 1) expired query crops: delete the file, forget the path
    expired = list(session.scalars(select(InferenceResult).where(
        InferenceResult.crop_path.is_not(None), InferenceResult.crop_expires_at <= now)))
    for result in expired:
        runtime.queries.delete(result.crop_path)
        result.crop_path = result.crop_expires_at = None

    # 2) old history rows
    cutoff = now - timedelta(days=runtime.settings.history_retention_days)
    old_ids = list(session.scalars(select(InferenceRecord.id).where(InferenceRecord.created_at < cutoff)))
    removed_files = 0
    if old_ids:
        for path in session.scalars(select(InferenceResult.crop_path).where(
                InferenceResult.record_id.in_(old_ids), InferenceResult.crop_path.is_not(None))):
            runtime.queries.delete(path)
            removed_files += 1
        session.execute(delete(InferenceResult).where(InferenceResult.record_id.in_(old_ids)))
        session.execute(delete(InferenceRecord).where(InferenceRecord.id.in_(old_ids)))

    # 3) orphaned crop files older than the retention window (e.g. after a crash)
    orphans = runtime.queries.delete_older_than(timedelta(hours=max(runtime.settings.query_retention_hours, 1)) + timedelta(hours=1))
    orphans += video_service.remove_expired(runtime.settings)  # video frame previews and any stray video upload

    summary = {"expired_crops_removed": len(expired), "history_rows_removed": len(old_ids), "orphan_files_removed": orphans + removed_files}
    record_audit(session, role_name, "maintenance.cleanup", None, **summary)
    session.commit()
    logger.info("Cleanup finished: %s", summary)
    return summary
