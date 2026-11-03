"""Access control. Access keys are an OPTIONAL feature and are OFF by default
(``REID_AUTH_REQUIRED=false``): on a single-user demo machine, with the server bound to 127.0.0.1,
every caller is treated as an administrator and nobody has to type a key.
"""

from __future__ import annotations

import enum
import logging
import secrets
from collections.abc import Callable

from fastapi import Depends, Header, Request

from .config import Settings
from .errors import Forbidden, Unauthorized

logger = logging.getLogger(__name__)


class Role(enum.IntEnum):
    """Higher number = more privileges, so ``role >= Role.OPERATOR`` reads naturally."""

    VIEWER = 1
    OPERATOR = 2
    ADMIN = 3


def resolve_role(provided_key: str | None, settings: Settings) -> Role:
    """Turn the key sent by the client into a Role (or raise)."""
    if not settings.auth_required:
        return Role.ADMIN  # keys are switched off (the default): single-user local demo

    if not provided_key:
        raise Unauthorized("An access key is required. Send it in the X-API-Key header.")

    # Check the strongest role first; compare in constant time to avoid timing leaks.
    configured = (
        (Role.ADMIN, settings.admin_key),
        (Role.OPERATOR, settings.operator_key),
        (Role.VIEWER, settings.viewer_key),
    )
    for role, secret in configured:
        if secret is not None and secrets.compare_digest(
            provided_key.encode(), secret.get_secret_value().encode()
        ):
            return role
    raise Unauthorized("The access key was not recognised.")


def current_role(request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> Role:
    # The app owns its settings (app.state.settings), so tests and real runs can differ cleanly.
    return resolve_role(x_api_key, request.app.state.settings)


def require_role(minimum: Role) -> Callable[..., Role]:
    """Dependency factory: ``Depends(require_role(Role.ADMIN))`` protects a route."""

    def checker(role: Role = Depends(current_role)) -> Role:
        if role < minimum:
            raise Forbidden(
                f"This action needs the '{minimum.name.lower()}' role; "
                f"your key has the '{role.name.lower()}' role."
            )
        return role

    return checker


def warn_if_misconfigured(settings: Settings) -> None:
    """Log loud warnings at startup for unsafe configurations."""
    if not settings.auth_required:
        logger.warning(
            "Access keys are OFF (REID_AUTH_REQUIRED=false): anyone who can reach this port has full control. "
            "Keep the server on 127.0.0.1, or set REID_AUTH_REQUIRED=true before sharing it."
        )
        return
    if not any((settings.viewer_key, settings.operator_key, settings.admin_key)):
        logger.warning(
            "No access keys configured: every protected call will be rejected. "
            "Run `python scripts/init_env.py` to generate keys."
        )
