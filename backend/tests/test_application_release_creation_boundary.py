"""HTTP boundary regression, independent of new service imports and databases."""
import pytest
from fastapi.testclient import TestClient
from app import main
from app.core.config import settings


@pytest.mark.parametrize('method,path', [
    ('GET','/api/v1/application-release-creation/context'),
    ('HEAD','/api/v1/application-release-creation/context/'),
    ('GET','/api/v1/application-release-creation/receipts/00000000-0000-0000-0000-000000000001'),
    ('HEAD','/api/v1/application-release-creation/receipts/00000000-0000-0000-0000-000000000001/'),
    ('POST','/api/v1/releases/application'),
])
def test_new_private_routes_fail_closed_without_oidc(monkeypatch, method, path):
    monkeypatch.setattr(settings, 'auth_mode', 'disabled')
    monkeypatch.setattr(settings, 'read_only_mode', False)
    def forbidden(*args): raise AssertionError('provider must not be called')
    monkeypatch.setattr(main, 'authenticate_write_request', forbidden)
    with TestClient(main.app) as client:
        response = client.request(method, path)
    assert response.status_code == 401
    assert response.headers['cache-control'] == 'private, no-store'
    assert 'authorization' in response.headers['vary'].lower()


def test_read_only_rejects_before_provider(monkeypatch):
    monkeypatch.setattr(settings, 'auth_mode', 'oidc')
    monkeypatch.setattr(settings, 'read_only_mode', True)
    def forbidden(*args): raise AssertionError('provider must not be called')
    monkeypatch.setattr(main, 'authenticate_write_request', forbidden)
    with TestClient(main.app) as client:
        response = client.post('/api/v1/releases/application', json={})
    assert response.status_code == 403 and response.json()['detail'] == 'read_only_mode'
    assert response.headers['cache-control'] == 'private, no-store'
