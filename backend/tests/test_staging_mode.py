import asyncio
import json

from starlette.requests import Request
from starlette.responses import Response

from app import main
from app.core.config import Settings


def test_database_url_accepts_standard_provider_scheme():
    assert Settings(database_url="postgres://user:pass@db.example/test").database_url == (
        "postgresql+psycopg://user:pass@db.example/test"
    )
    assert Settings(database_url="postgresql://user:pass@db.example/test?sslmode=require").database_url == (
        "postgresql+psycopg://user:pass@db.example/test?sslmode=require"
    )
    assert Settings(database_url="postgresql+psycopg://user:pass@db.example/test").database_url.startswith("postgresql+psycopg://")


def request(method):
    return Request({"type": "http", "method": method, "path": "/api/v1/releases", "headers": []})


async def next_response(_request):
    return Response("allowed", status_code=200)


def test_read_only_mode_rejects_writes_but_allows_reads(monkeypatch):
    monkeypatch.setattr(main.settings, "read_only_mode", True)
    monkeypatch.setattr(main.settings, "auth_mode", "oidc")
    monkeypatch.setattr(main, "authenticate_write_request", lambda *_: (_ for _ in ()).throw(AssertionError()))
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = asyncio.run(main.read_only_guard(request(method), next_response))
        assert response.status_code == 403
        assert json.loads(response.body) == {"detail": "read_only_mode"}
    for method in ("GET", "HEAD", "OPTIONS"):
        assert asyncio.run(main.read_only_guard(request(method), next_response)).status_code == 200


def test_normal_mode_preserves_writes(monkeypatch):
    monkeypatch.setattr(main.settings, "read_only_mode", False)
    monkeypatch.setattr(main.settings, "auth_mode", "disabled")
    assert asyncio.run(main.read_only_guard(request("POST"), next_response)).status_code == 200


def test_oidc_mode_rejects_unauthenticated_writes(monkeypatch):
    monkeypatch.setattr(main.settings, "read_only_mode", False)
    monkeypatch.setattr(main.settings, "auth_mode", "oidc")
    monkeypatch.setattr(
        main,
        "authenticate_write_request",
        lambda *_: (_ for _ in ()).throw(main.AuthenticationError("missing_bearer_token")),
    )
    response = asyncio.run(main.read_only_guard(request("POST"), next_response))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert json.loads(response.body) == {"detail": "missing_bearer_token"}


def test_oidc_mode_allows_an_authenticated_write_to_continue(monkeypatch):
    monkeypatch.setattr(main.settings, "read_only_mode", False)
    monkeypatch.setattr(main.settings, "auth_mode", "oidc")
    monkeypatch.setattr(main, "authenticate_write_request", lambda *_: object())
    assert asyncio.run(main.read_only_guard(request("POST"), next_response)).status_code == 200
