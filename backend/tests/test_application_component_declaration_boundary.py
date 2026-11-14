"""Regression first: private declaration boundary is independently disabled."""
import pytest
from fastapi.testclient import TestClient
from app import main
from app.core.config import settings

@pytest.mark.parametrize('method,path', [
    ('GET','/api/v1/application-component-declaration/context'),
    ('HEAD','/api/v1/application-component-declaration/context/'),
    ('GET','/api/v1/application-component-declaration/receipts/00000000-0000-0000-0000-000000000001'),
    ('POST','/api/v1/application-component-declarations'),
])
def test_component_boundary_fails_closed(monkeypatch, method, path):
    monkeypatch.setattr(settings, 'auth_mode', 'disabled')
    monkeypatch.setattr(settings, 'read_only_mode', False)
    with TestClient(main.app) as client: response = client.request(method, path)
    assert response.status_code in (401,403)
    assert response.headers['cache-control'] == 'private, no-store'
    assert 'x-browser-session' in response.headers['vary'].lower()

@pytest.mark.parametrize('readonly,enabled,expected',[(True,False,'read_only_mode'),(False,False,'asrc_disabled'),(False,True,'oidc_not_enabled')])
def test_gate_precedence_before_provider(monkeypatch,readonly,enabled,expected):
    monkeypatch.setattr(settings,'auth_mode','disabled')
    monkeypatch.setattr(settings,'read_only_mode',readonly)
    monkeypatch.setattr(settings,'application_component_declaration_enabled',enabled)
    def forbidden(*a): raise AssertionError('provider must not be called')
    monkeypatch.setattr(main,'authenticate_write_request',forbidden)
    with TestClient(main.app) as client: response=client.post('/api/v1/application-component-declarations',json={})
    assert response.status_code in (401,403) and response.json()['detail']==expected
    assert response.headers['cache-control']=='private, no-store'
