"""
One person's decision, shared by the single-image workflow and the video workflow.

In plain words: both ``reid_service`` (a photo) and ``video_service`` (the frames of a clip) have, for each person, a body
fingerprint and possibly a face. This function turns those into ONE ``Decision`` so the two workflows can never disagree.

    policy has face rules AND the face models are loaded  -> compare the face (if usable) and the body, decide with multicue.py
    otherwise                                             -> the original body-only engine (decision_engine.decide)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import numpy as np

from ..cv.open_set.confidence import ConfidenceModel
from ..cv.open_set.decision_engine import Decision, decide
from ..cv.open_set.multicue import decide_multicue
from ..cv.open_set.policy import DecisionPolicy
from .face_service import QueryFace
from .runtime import Runtime


def decide_person(
    runtime: Runtime,
    policy: DecisionPolicy,
    body_vector: np.ndarray,
    *,
    body_flags: Sequence[str],
    face: QueryFace | None,
    top_k: int,
    confidence_model: ConfidenceModel | None = None,
) -> Decision:
    """Raises ``InvalidEmbedding`` (a PROCESSING ERROR for this person) when either fingerprint is broken."""
    if policy.multicue is None or runtime.face_engine is None:
        return decide(runtime.index.search(body_vector, top_k), policy, quality_flags=body_flags, confidence_model=confidence_model)

    n_people = max(1, runtime.index.snapshot.n_identities)  # score EVERY enrolled person: the face and the body are looked up per person
    body = runtime.index.search(body_vector, n_people)
    vector = face.vector if face is not None else None
    faces = runtime.face_index.search(vector, max(1, runtime.face_index.snapshot.n_identities)) if vector is not None else None
    status = "no_face" if face is None else ("usable" if vector is not None else face.status)
    decision = decide_multicue(body, faces, policy, body_quality_flags=body_flags, face_status=status,
                               face_flags=face.flags if face else ())
    return replace(decision, candidates=decision.candidates[:top_k])
