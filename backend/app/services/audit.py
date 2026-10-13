"""
Audit trail.

In plain words: every sensitive action (enrolling, deleting, resetting,
changing thresholds, running evaluations, cleaning up) writes one row saying
WHO (role) did WHAT to WHICH subject and WHEN. Details never include images or
embeddings.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import AuditEvent


def record_audit(session: Session, role_name: str, action: str, subject: str | None = None, **detail) -> None:
    session.add(AuditEvent(actor_role=role_name.lower(), action=action, subject=subject, detail=detail))
