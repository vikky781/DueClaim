import pytest
from fastapi import HTTPException, Request

from app.auth import get_current_user_sub


def _request(event: dict | None = None) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    if event is not None:
        scope["aws.event"] = event
    return Request(scope)


def _jwt_event(sub: str) -> dict:
    return {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub, "email": "x@y.z"}}}}}


def test_reads_sub_from_api_gateway_jwt_claims(monkeypatch):
    monkeypatch.delenv("DEV_USER_SUB", raising=False)
    assert get_current_user_sub(_request(_jwt_event("cognito-sub-123"))) == "cognito-sub-123"


def test_missing_claims_is_401(monkeypatch):
    monkeypatch.delenv("DEV_USER_SUB", raising=False)
    with pytest.raises(HTTPException) as exc:
        get_current_user_sub(_request())
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException):
        get_current_user_sub(_request({"requestContext": {"authorizer": {}}}))


def test_dev_override_used_outside_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("DEV_USER_SUB", "local-dev-user")
    assert get_current_user_sub(_request()) == "local-dev-user"


def test_dev_override_raises_loudly_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("DEV_USER_SUB", "local-dev-user")
    with pytest.raises(RuntimeError, match="DEV_USER_SUB"):
        get_current_user_sub(_request(_jwt_event("real-sub")))
