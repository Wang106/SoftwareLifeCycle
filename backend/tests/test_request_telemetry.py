import asyncio
import copy
import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ops.request_telemetry import RequestTelemetryMiddleware, configure_json_logger, json_log_sink
from app.ops.telemetry_window import FIELDS


def invoke(inner, *, enabled=True, scope_extra=None, incoming=None, fail_send=False, sink=None):
    records, sent = [], []
    scope = {'type': 'http', 'method': 'GET', 'path': '/items/secret-id',
             'query_string': b'token=secret-query', 'headers': [(b'authorization', b'Bearer secret-token')],
             'client': ('secret-client-ip', 999), **(scope_extra or {})}
    async def receive():
        return incoming or {'type': 'http.request', 'body': b'secret-body'}
    async def send(message):
        if fail_send:
            raise OSError('secret-send-error')
        sent.append(copy.deepcopy(message))
    middleware = RequestTelemetryMiddleware(inner, enabled=enabled, route_templates=['/items/{item_id}'],
                                            sink=records.append if sink is None else sink)
    return middleware, scope, receive, send, records, sent


def test_stream_messages_and_sensitive_inputs_are_unchanged():
    async def inner(scope, receive, send):
        scope['route'] = type('Route', (), {'path': '/items/{item_id}'})()
        assert (await receive())['body'] == b'secret-body'
        await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'x-test', b'secret-response')]})
        await send({'type': 'http.response.body', 'body': b'secret-response', 'more_body': True})
        await send({'type': 'http.response.body', 'body': b'end'})
    middleware, scope, receive, send, records, sent = invoke(inner)
    asyncio.run(middleware(scope, receive, send))
    assert [m['type'] for m in sent] == ['http.response.start', 'http.response.body', 'http.response.body']
    assert sent[1]['body'] == b'secret-response'
    row, = records
    assert set(row) == FIELDS and row['route'] == '/items/{item_id}'
    assert row['status'] == 200 and row['outcome'] == 'complete'
    assert row['duration_ms'] >= 0 and row['timestamp_ms'] > 0
    assert 'secret' not in json.dumps(row)


@pytest.mark.parametrize('scope_extra,enabled', [({}, False), ({'type': 'websocket'}, True), ({'type': 'lifespan'}, True)])
def test_disabled_or_non_http_is_exact_passthrough(scope_extra, enabled):
    seen = []
    async def inner(scope, receive, send):
        seen.append((scope, receive, send))
    middleware, scope, receive, send, records, _ = invoke(inner, enabled=enabled, scope_extra=scope_extra)
    asyncio.run(middleware(scope, receive, send))
    assert seen == [(scope, receive, send)] and records == []


@pytest.mark.parametrize('started', [False, True])
def test_original_exception_propagates_without_text_leak(started):
    error = RuntimeError('secret-exception')
    async def inner(scope, receive, send):
        if started:
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        raise error
    middleware, scope, receive, send, records, _ = invoke(inner)
    with pytest.raises(RuntimeError) as raised:
        asyncio.run(middleware(scope, receive, send))
    assert raised.value is error
    assert records[0]['outcome'] == 'error' and records[0]['status'] == (200 if started else 0)
    assert 'secret' not in json.dumps(records)


def test_cancellation_is_not_swallowed():
    async def inner(scope, receive, send):
        raise asyncio.CancelledError('secret-cancellation')
    middleware, scope, receive, send, records, _ = invoke(inner)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(middleware(scope, receive, send))
    assert records[0]['outcome'] == 'cancelled' and 'secret' not in json.dumps(records)


def test_disconnect_without_final_body_is_not_complete():
    async def inner(scope, receive, send):
        assert (await receive())['type'] == 'http.disconnect'
    middleware, scope, receive, send, records, _ = invoke(inner, incoming={'type': 'http.disconnect'})
    asyncio.run(middleware(scope, receive, send))
    assert records[0]['outcome'] == 'disconnected'


def test_send_failure_does_not_report_delivered_status():
    async def inner(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
    middleware, scope, receive, send, records, _ = invoke(inner, fail_send=True)
    with pytest.raises(OSError):
        asyncio.run(middleware(scope, receive, send))
    assert records[0]['status'] == 0 and records[0]['outcome'] == 'error'


def test_sink_failure_never_changes_response_or_original_error():
    def broken_sink(record):
        raise OSError('secret-log-location')
    async def okay(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 204, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
    middleware, scope, receive, send, _, sent = invoke(okay, sink=broken_sink)
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]['status'] == 204
    async def broken(scope, receive, send):
        raise ValueError('original')
    middleware, scope, receive, send, _, _ = invoke(broken, sink=broken_sink)
    with pytest.raises(ValueError, match='^original$'):
        asyncio.run(middleware(scope, receive, send))


def test_unknown_method_and_route_are_bounded_and_incoming_id_ignored():
    async def inner(scope, receive, send):
        scope['route'] = type('Route', (), {'path': '/secret-arbitrary-route'})()
        await send({'type': 'http.response.start', 'status': 404, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
    middleware, scope, receive, send, records, _ = invoke(inner, scope_extra={'method': 'SECRET', 'headers': [(b'x-request-id', b'secret-user-id')]})
    asyncio.run(middleware(scope, receive, send)); asyncio.run(middleware(scope, receive, send))
    assert all(r['method'] == 'OTHER' and r['route'] == '__unmatched__' for r in records)
    assert len({r['request_id'] for r in records}) == 2 and 'secret' not in json.dumps(records)


def test_json_sink_does_not_reconfigure_root_and_emits_only_record(monkeypatch):
    logger = logging.getLogger('slc.request_telemetry')
    old_handlers, old_level, old_propagate = logger.handlers[:], logger.level, logger.propagate
    root_handlers = logging.getLogger().handlers[:]
    stream = io.StringIO(); monkeypatch.setattr('sys.stdout', stream)
    try:
        logger.handlers = []
        configure_json_logger(); configure_json_logger(); json_log_sink({'event': 'http_request'})
        assert stream.getvalue() == '{"event":"http_request"}\n'
        assert len(logger.handlers) == 1 and not logger.propagate
        assert logging.getLogger().handlers == root_handlers
    finally:
        logger.handlers, logger.level, logger.propagate = old_handlers, old_level, old_propagate


def test_real_application_guard_and_health_routes_are_observed(monkeypatch):
    from app import main
    records = []
    observed = RequestTelemetryMiddleware(main.app, enabled=True,
        route_templates=[r.path for r in main.app.routes], sink=records.append)
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    monkeypatch.setattr(main.settings, 'auth_mode', 'disabled')
    with TestClient(observed) as client:
        assert client.get('/health/live?secret=hidden').status_code == 200
        assert client.post('/api/v1/snapshots', json={'secret': 'hidden'}).status_code == 403
        response = client.get('/api/v1/security/me', headers={'Authorization': 'Bearer hidden'})
        assert response.status_code == 401 and response.headers['cache-control'] == 'private, no-store'
        assert client.get('/not-a-route/hidden').status_code == 404
    assert [r['status'] for r in records] == [200, 403, 401, 404]
    assert records[0]['route'] == '/health/live'
    assert all(r['route'] == '__unmatched__' for r in records[1:])
    assert 'hidden' not in json.dumps(records)
    installed = main.app.user_middleware[0]
    assert installed.cls is RequestTelemetryMiddleware and installed.kwargs['enabled'] is False


def test_fastapi_real_error_and_readiness_unavailable(monkeypatch):
    from app import main
    from sqlalchemy.exc import SQLAlchemyError
    records = []
    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError('secret-database-url')
    monkeypatch.setattr(main, 'engine', BrokenEngine())
    observed = RequestTelemetryMiddleware(main.app, enabled=True,
        route_templates=[r.path for r in main.app.routes], sink=records.append)
    with TestClient(observed) as client:
        response = client.get('/health/ready')
        assert response.status_code == 503 and response.json()['reason'] == 'database_unavailable'
    assert records[0]['route'] == '/health/ready' and records[0]['status'] == 503
    assert 'secret' not in json.dumps(records)
    app = FastAPI()
    @app.get('/broken/{id}')
    def broken(id: str):
        raise RuntimeError('secret-exception')
    observed = RequestTelemetryMiddleware(app, enabled=True, route_templates=['/broken/{id}'], sink=records.append)
    with TestClient(observed, raise_server_exceptions=False) as client:
        assert client.get('/broken/secret').status_code == 500
    assert records[-1]['outcome'] == 'error' and records[-1]['status'] == 500
    assert records[-1]['route'] == '/broken/{id}' and 'secret' not in json.dumps(records)


def test_production_user_middleware_position_preserves_outer_500_and_records_unknown_status():
    records = []
    app = FastAPI()
    @app.get('/broken/{item_id}')
    def broken(item_id: str):
        raise RuntimeError('secret-stack')
    app.add_middleware(RequestTelemetryMiddleware, enabled=True,
                       route_templates=['/broken/{item_id}'], sink=records.append)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/broken/secret')
        assert response.status_code == 500 and response.text == 'Internal Server Error'
    assert records[0]['status'] == 0 and records[0]['outcome'] == 'error'
    assert records[0]['route'] == '/broken/{item_id}'
    assert 'secret' not in json.dumps(records)


def test_error_after_final_body_is_not_claimed_success():
    async def inner(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
        raise RuntimeError('secret-background-error')
    middleware, scope, receive, send, records, sent = invoke(inner)
    with pytest.raises(RuntimeError):
        asyncio.run(middleware(scope, receive, send))
    assert sent[-1]['body'] == b''
    assert records[0]['status'] == 200 and records[0]['outcome'] == 'error'


def test_incomplete_stream_is_not_claimed_success():
    async def inner(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'part', 'more_body': True})
    middleware, scope, receive, send, records, sent = invoke(inner)
    asyncio.run(middleware(scope, receive, send))
    assert records[0]['outcome'] == 'incomplete' and records[0]['status'] == 200


def test_actual_asgi_records_feed_offline_alert_evaluator(tmp_path, monkeypatch):
    from app import main
    from app.ops.telemetry_window import evaluate_window
    from sqlalchemy.exc import SQLAlchemyError
    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError('secret-database')
    monkeypatch.setattr(main, 'engine', BrokenEngine())
    records = []
    observed = RequestTelemetryMiddleware(main.app, enabled=True,
        route_templates=[r.path for r in main.app.routes], sink=records.append)
    with TestClient(observed) as client:
        for _ in range(19):
            assert client.get('/health/live').status_code == 200
        assert client.get('/health/ready').status_code == 503
    path = tmp_path / 'own-synthetic-requests.jsonl'
    original = ''.join(json.dumps(r) + '\n' for r in records)
    path.write_text(original)
    result = evaluate_window(path, start_ms=min(r['timestamp_ms'] for r in records),
                             end_ms=max(r['timestamp_ms'] for r in records) + 1)
    assert result['samples'] == 20 and result['failed_requests'] == 1
    assert result['alerts']['request_failures'] == result['alerts']['readiness'] == 'triggered'
    assert result['notifications_sent'] is False and 'secret' not in json.dumps(result)
    assert path.read_text() == original
