"""Identity: the Cognito ``sub`` claim, as verified by the API Gateway JWT authorizer.

The Lambda never validates tokens itself. API Gateway's JWT authorizer rejects
unauthenticated requests before they reach us and places the verified claims
at ``event.requestContext.authorizer.jwt.claims``; Mangum exposes the raw event
as ``request.scope["aws.event"]``.

Local development: set ``DEV_USER_SUB`` to act as that user without a token.
This is refused outright when ``ENVIRONMENT == "prod"``.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request, status


def _dev_override() -> str | None:
    dev_sub = os.environ.get("DEV_USER_SUB")
    if dev_sub and os.environ.get("ENVIRONMENT", "").lower() == "prod":
        raise RuntimeError("DEV_USER_SUB is set while ENVIRONMENT=prod. Refusing to serve requests.")
    return dev_sub or None


def get_current_user_sub(request: Request) -> str:
    dev_sub = _dev_override()
    if dev_sub:
        return dev_sub
    event = request.scope.get("aws.event") or {}
    claims = (
        event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    )
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return sub
