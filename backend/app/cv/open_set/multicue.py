"""
Open-set decisions that use the FACE as well as the whole BODY.

In plain words: the body fingerprint (``cv/embedding``) mostly sees clothing colour and build, so two different people
in similar clothes can look alike to it - the "low inter-class variance" problem this project is about. A face
fingerprint sees the face itself. This module decides what the system may conclude when it has BOTH kinds of evidence.

It is a pure function, like ``decision_engine.decide``: scores in, decision out, no database, no images.

The rules, first one that applies wins
--------------------------------------
There are two situations.

A. The picture has a USABLE FACE and at least one enrolled person has a face on file -> the FACE decides:

    1. best face similarity  >= face threshold                       -> MATCH   (margin rule, if configured, may say REVIEW/UNKNOWN)
    2. within the review band just below the face threshold          -> REVIEW  (too close to call automatically)
    3. below that                                                    -> UNKNOWN
       ... unless an enrolled person WITHOUT a face on file passes the body threshold -> REVIEW (nothing to verify the face against)

    Clothing similarity can NOT turn a failed face into a MATCH. That is the whole point: a stranger in the same
    jacket gets UNKNOWN. The body score is reported next to the face score - "agrees" or "differs" - as supporting
    evidence; a low body score with a matching face is normal when the person simply changed clothes.

B. No usable face (none found, or too small / blurry / turned), or nobody enrolled has a face -> the BODY decides,
   with the original rules (quality flags -> REVIEW, below threshold -> UNKNOWN, margin rule). Because clothing alone is
   weak evidence, a body-only pass is sent to REVIEW instead of MATCH unless the policy says ``body_only_action = accept``.

The face threshold is a starting value from the model's authors (see docs/FACE_AND_BODY_MATCHING.md for what was measured);
like the body threshold it is UNVALIDATED until someone calibrates it on their own camera data.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ..retrieval.types import Candidate
from .decision_engine import Decision, decide
from .policy import BodyOnlyAction, DecisionPolicy, MarginAction, Outcome

_FACE_STATE_TEXT = {
    "no_face": "No face was found in the picture.",
    "unusable": "A face was found but it is not good enough to compare",
    "not_enrolled": "A usable face was found, but no enrolled person has a face on file.",
}


def _tag_body(candidates: Sequence[Candidate]) -> tuple[Candidate, ...]:
    return tuple(replace(c, basis="body", body_score=c.score) for c in candidates)


def decide_multicue(
    body: Sequence[Candidate],
    face: Sequence[Candidate] | None,
    policy: DecisionPolicy,
    *,
    body_quality_flags: Sequence[str] = (),
    face_status: str = "usable",
    face_flags: Sequence[str] = (),
) -> Decision:
    """``body``: every enrolled person scored by body. ``face``: enrolled people WITH a face, scored by face; None if the
    picture has no usable face (then ``face_status`` says why: no_face | unusable)."""
    multicue = policy.multicue
    if multicue is None:
        raise ValueError("decide_multicue needs a policy with a multicue block; use decide() for body-only policies.")
    t_body, t_face = policy.accept_threshold, multicue.face_accept_threshold
    body_policy = replace(policy, multicue=None)  # the original rules, used for body-only evidence

    if face is not None and len(face) == 0:
        face, face_status = None, "not_enrolled"  # a usable face, but nobody to compare it with

    # ------------------------------------------------------------------------------ B. body-only evidence
    if face is None:
        legacy = decide(body, body_policy, quality_flags=body_quality_flags)
        note = _FACE_STATE_TEXT.get(face_status, "")
        if face_status == "unusable":
            note += f" ({', '.join(face_flags) or 'poor quality'})."
        top = legacy.candidates[0] if legacy.candidates else None
        common = dict(basis="body", face_status=face_status, top1_body_score=legacy.top1_score, body_threshold=t_body,
                      face_threshold=t_face, candidates=_tag_body(legacy.candidates))
        if legacy.outcome is Outcome.ACCEPTED and multicue.body_only_action is BodyOnlyAction.REVIEW and top is not None:
            return replace(
                legacy, outcome=Outcome.REVIEW_REQUIRED, reason_code="body_only_review", accepted_reference_id=None,
                reason=(f"{note} Body/clothing evidence alone: '{top.reference_id}' scored {top.score:.3f}, at or above the body "
                        f"threshold {t_body:.3f}, but clothing and build are not enough for an automatic MATCH - a person should confirm."),
                **common,
            )
        reason = f"{legacy.reason} {note}".strip() if note else legacy.reason
        return replace(legacy, reason=reason, **common)

    # ------------------------------------------------------------------------------ A. the face decides
    body_by = {c.reference_id: c for c in body}
    ranked_face = sorted(face, key=lambda c: -c.score)  # stable: ties keep their gallery order
    top, second = ranked_face[0], (ranked_face[1] if len(ranked_face) > 1 else None)
    f_top = top.score
    margin = (f_top - second.score) if second else None
    others = sorted((c for c in body if c.reference_id not in {x.reference_id for x in face}), key=lambda c: -c.score)

    shown: list[Candidate] = []
    for rank, c in enumerate(ranked_face, 1):
        mate = body_by.get(c.reference_id)
        shown.append(Candidate(rank, c.reference_id, c.score, c.best_image_uid, mate.n_images if mate else c.n_images,
                               basis="face", face_score=c.score, body_score=mate.score if mate else None, face_image_uid=c.best_image_uid))
    for c in others:
        shown.append(Candidate(len(shown) + 1, c.reference_id, c.score, c.best_image_uid, c.n_images, basis="body", body_score=c.score))

    top_body = body_by.get(top.reference_id)
    b_top = top_body.score if top_body else None

    def build(outcome: Outcome, code: str, reason: str, accepted: bool = False) -> Decision:
        return Decision(
            outcome=outcome, reason_code=code, reason=reason, accepted_reference_id=top.reference_id if accepted else None,
            top1_reference_id=top.reference_id, top1_score=f_top, top2_score=second.score if second else None, margin=margin,
            accept_threshold=t_face, min_margin=policy.min_margin, policy_version=policy.version, policy_status=policy.status.value,
            candidates=tuple(shown), quality_flags=tuple(face_flags), basis="face", face_status="usable", top1_face_score=f_top,
            top1_body_score=b_top, face_threshold=t_face, body_threshold=t_body,
        )

    if f_top >= t_face:
        if policy.min_margin is not None and margin is not None and margin < policy.min_margin:
            detail = (f"Face of '{top.reference_id}' scored {f_top:.3f} but the runner-up '{second.reference_id}' scored "
                      f"{second.score:.3f}: the margin {margin:.3f} is below the required {policy.min_margin:.3f}.")
            if policy.margin_action is MarginAction.REVIEW:
                return build(Outcome.REVIEW_REQUIRED, "ambiguous_margin", f"Ambiguous face match. {detail}")
            return build(Outcome.UNKNOWN, "ambiguous_margin_rejected", f"Rejected as ambiguous. {detail}")
        if b_top is None:
            support = ""
        elif b_top >= t_body:
            support = f" The body/clothing fingerprint agrees (similarity {b_top:.3f}, body threshold {t_body:.3f})."
        else:
            support = (f" The body/clothing fingerprint is lower ({b_top:.3f}; body threshold {t_body:.3f}) - clothing or build "
                       "differs, which is normal if the person changed clothes.")
        return build(Outcome.ACCEPTED, "accepted_by_face",
                     f"Accepted by face: '{top.reference_id}' face similarity {f_top:.3f} is at or above the face threshold {t_face:.3f}.{support}",
                     accepted=True)

    if f_top >= t_face - multicue.face_review_band:
        return build(Outcome.REVIEW_REQUIRED, "face_near_threshold",
                     f"The face of '{top.reference_id}' scored {f_top:.3f}, just below the face threshold {t_face:.3f} "
                     f"(review band {multicue.face_review_band:.2f}): too close to call automatically.")

    # The face does not match anyone with a face on file. Clothing never overrides that - except that a person who has NO
    # face on file cannot be ruled out by a face, so a strong body match for them goes to a human.
    strong_without_face = [c for c in others if c.score >= t_body]
    if strong_without_face:
        c = strong_without_face[0]
        if multicue.body_only_action is BodyOnlyAction.ACCEPT:
            legacy = decide(strong_without_face, body_policy, quality_flags=body_quality_flags)
            return replace(legacy, basis="body", face_status="usable", top1_body_score=legacy.top1_score, body_threshold=t_body,
                           face_threshold=t_face, candidates=tuple(shown),
                           reason=f"{legacy.reason} (The face matched nobody with a face on file; '{c.reference_id}' has no face enrolled.)")
        return build(Outcome.REVIEW_REQUIRED, "no_face_on_file_review",
                     f"The face matched nobody who has a face on file (best {f_top:.3f} < {t_face:.3f}), but '{c.reference_id}' has no face "
                     f"enrolled and passes the body threshold ({c.score:.3f} >= {t_body:.3f}). A face cannot rule them out, so a person should check.")

    clothing = ""
    best_body = max(body, key=lambda c: c.score, default=None)
    if best_body is not None and best_body.score >= t_body:
        clothing = (f" Body/clothing similarity alone is NOT accepted when a face is available (best body score {best_body.score:.3f} "
                    f"for '{best_body.reference_id}').")
    return build(Outcome.UNKNOWN, "face_below_threshold",
                 f"No supported match: a usable face was compared with {len(face)} enrolled face holder(s); the closest, "
                 f"'{top.reference_id}', scored {f_top:.3f}, below the face threshold {t_face:.3f}.{clothing}")
