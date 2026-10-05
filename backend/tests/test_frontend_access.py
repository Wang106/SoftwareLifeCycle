"""Access probes must distinguish edge denial from app/identity readiness."""
from email.message import Message
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'scripts/check_frontend.py'
spec = importlib.util.spec_from_file_location('frontend_access', SCRIPT)
access = importlib.util.module_from_spec(spec); spec.loader.exec_module(access)


class Response(BytesIO):
    def __init__(self, status, headers, body):
        super().__init__(body.encode() if isinstance(body, str) else body)
        self.status = status
        self.headers = Message()
        for key, value in headers.items(): self.headers[key] = value


class Client:
    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.handler:
            return self.handler(request)
        if request.full_url.endswith('/account'):
            zh = request.get_header('Cookie') == 'slc_language=zh'
            language, text = ('zh-CN', '此环境暂未开放登录。') if zh else ('en', 'Login is not available in this environment.')
            return Response(200, {'Content-Type': 'text/html', 'Cache-Control': 'private,no-store'}, f'<html lang="{language}"><p>{text}</p></html>')
        login = request.full_url.endswith('/login')
        return Response(405 if login else 503, {'Content-Type': 'application/json', 'Cache-Control': 'private,no-store', 'Vary': 'Cookie', 'Allow': 'POST'},
                        json.dumps({'error': 'method_not_allowed' if login else 'login_not_configured'}))


@pytest.mark.parametrize('url', ['http://softwarelifecycle.whf969.com', 'https://user:secret@softwarelifecycle.whf969.com',
    'https://softwarelifecycle.whf969.com/account', 'https://softwarelifecycle.whf969.com?token=secret',
    'https://softwarelifecycle.whf969.com#fragment', 'https://softwarelifecycle.whf969.com:8443',
    'https://softwarelifecycle.whf969.com.evil.test', 'https://can.whf969.com', 'https://127.0.0.1',
    'https://other.whf969.workers.dev', 'https://bbddba4c-softwarelifecycle.whf969.workers.dev.evil.test',
    'https://softwarelifecycle.whf969.com\n'])
def test_unapproved_target_rejected_before_request(url):
    client = Client()
    with pytest.raises(ValueError, match='approved HTTPS'):
        access.check(url, opener=client)
    assert not client.calls


@pytest.mark.parametrize('url', ['https://softwarelifecycle.whf969.com/', 'https://softwarelifecycle.whf969.com:443',
    'https://bbddba4c-softwarelifecycle.whf969.workers.dev', 'https://codex-browser-session-revocation-20261006-softwarelifecycle.whf969.workers.dev'])
def test_bilingual_disabled_checks_are_read_only_bounded_and_credential_free(url):
    client = Client(); report = access.check(url, opener=client)
    assert report['all_passed'] and report['browser_provider_acceptance'] == 'not_checked'
    assert len(report['results']) == len(client.calls) == 5
    for request, timeout in client.calls:
        assert request.get_method() == 'GET' and request.data is None and timeout == 10
        assert request.get_header('User-agent') == access.USER_AGENT
        assert request.get_header('Authorization') is None
        assert request.get_header('Cookie') in (None, 'slc_language=zh', 'slc_language=en')


@pytest.mark.parametrize('status,headers,body,classification', [
    (403, {}, 'error code: 1010', 'cloudflare_1010'),
    (403, {'server': 'cloudflare', 'cf-ray': 'abc-NRT'}, '<h1>Error 1010</h1>', 'cloudflare_1010'),
    (403, {'server': 'cloudflare'}, '<h1>Error 1020</h1>', 'cloudflare_1020'),
    (403, {'server': 'cloudflare', 'cf-error-origin': 'security'}, 'Access denied', 'cloudflare_denied'),
    (401, {}, '{"error":"session_required"}', 'unexpected_status'),
    (302, {'location': 'https://evil.test?token=private'}, '', 'redirect_not_followed'),
    (200, {'content-type':'text/html'}, '<html/>', 'missing_no_store'),
    (200, {'content-type':'text/html','cache-control':'no-store'}, '<html lang="zh-CN"><script>此环境暂未开放登录。</script></html>', 'unexpected_account_state'),
    (200, {'content-type':'text/html','cache-control':'no-store'}, '<html lang="zh-CN"><p>此环境暂未开放登录。</p><form action="/auth/login"/></html>', 'unexpected_account_state'),
    (200, {'content-type':'application/json','cache-control':'no-store'}, '{}', 'invalid_html_response'),
])
def test_edge_error_and_application_mismatch_never_pass(status, headers, body, classification):
    result = access.inspect_response('/account', 'zh', 200, status, headers, body)
    assert not result['passed'] and result['classification'] == classification
    if body:
        assert body not in json.dumps(result)
    assert 'private' not in json.dumps(result) or headers.get('cache-control') == 'private,no-store'


def test_success_page_mentioning_1010_is_not_classified_as_edge_denial():
    assert access.edge_error(200, {'server':'cloudflare'}, 'Error 1010') is None
    assert access.edge_error(403, {}, '<p>User text mentions error 1010</p>') is None


@pytest.mark.parametrize('payload,patch,classification', [
    ('not JSON', {}, 'invalid_json_response'),
    ('{"error":"session_required"}', {}, 'unexpected_auth_state'),
    ('{"error":"login_not_configured","token":"secret"}', {}, 'unexpected_auth_state'),
    ('{"error":"login_not_configured"}', {'vary':''}, 'invalid_private_response'),
    ('{"error":"login_not_configured"}', {'cache-control':'public,no-store'}, 'invalid_private_response'),
])
def test_disabled_auth_requires_exact_private_response(payload, patch, classification):
    headers = {'content-type':'application/json','cache-control':'private,no-store','vary':'Cookie', **patch}
    result = access.inspect_response('/auth/session', None, 503, 503, headers, payload)
    assert not result['passed'] and result['classification'] == classification
    assert 'secret' not in json.dumps(result)


@pytest.mark.parametrize('error', [URLError('private-network-value'), TimeoutError('private-timeout-value')])
def test_network_failure_is_recorded_without_private_exception_text(error):
    def fail(request): raise error
    report = access.check('https://softwarelifecycle.whf969.com', opener=Client(fail))
    assert not report['all_passed'] and all(r['classification']=='request_failed' for r in report['results'])
    assert 'private-' not in json.dumps(report)


def test_large_and_invalid_utf8_bodies_fail_without_being_recorded():
    for body, classification in [(b'x'*(access.MAX_BODY+1), 'response_too_large'), (b'\xff', 'request_failed')]:
        report = access.check('https://softwarelifecycle.whf969.com', opener=Client(lambda _: Response(200, {}, body)))
        assert not report['all_passed'] and all(r['classification']==classification for r in report['results'])


def test_http_errors_are_classified_and_secret_headers_are_discarded():
    headers = Message(); headers['Server']='cloudflare';headers['CF-RAY']='abc-NRT';headers['Set-Cookie']='private-session';headers['Authorization']='secret'
    def fail(request): raise HTTPError(request.full_url, 403, 'Denied', headers, BytesIO(b'error code: 1010'))
    report = access.check('https://softwarelifecycle.whf969.com', opener=Client(fail))
    assert all(r['classification']=='cloudflare_1010' and r['headers']['cf-ray']=='abc-NRT' for r in report['results'])
    assert 'private-session' not in json.dumps(report) and 'secret' not in json.dumps(report)


def test_redirect_handler_never_follows_an_external_target():
    assert access.NoRedirect().redirect_request(None,None,302,'Found',{},'https://evil.test') is None


@pytest.mark.parametrize('timeout', [0, -1, 31, True, float('nan'), float('inf')])
def test_timeout_rejected_before_network(timeout):
    client=Client()
    with pytest.raises(ValueError, match='Timeout'):
        access.check('https://softwarelifecycle.whf969.com', opener=client, timeout=timeout)
    assert not client.calls


def test_cli_records_failure_evidence_and_exit_status(monkeypatch, tmp_path, capsys):
    report={'all_passed':False,'results':[{'classification':'cloudflare_1010','passed':False}]}
    monkeypatch.setattr(access, 'check', lambda *args,**kwargs:report)
    path=tmp_path/'nested/report.json'
    assert access.main(['https://softwarelifecycle.whf969.com','--output',str(path)]) == 1
    assert json.loads(path.read_text()) == report == json.loads(capsys.readouterr().out)


def test_cli_invalid_origin_fails_before_network():
    result = subprocess.run([sys.executable,str(SCRIPT),'https://company.example'],capture_output=True,text=True)
    assert result.returncode == 2 and 'approved HTTPS' in result.stderr


def test_proxied_application403_is_not_mislabeled_as_cloudflare_denial():
    headers = {'server':'cloudflare','cf-ray':'abc-NRT','content-type':'application/json'}
    body = '{"detail":"invalid_origin"}'
    assert access.edge_error(403, headers, body) is None
    assert access.inspect_response('/auth/session', None, 503, 403, headers, body)['classification'] == 'unexpected_status'
