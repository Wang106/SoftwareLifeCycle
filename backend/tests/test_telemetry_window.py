import json
import uuid

import pytest

from app.ops import telemetry_window as window


def row(**changes):
    return {'schema_version': 1, 'event': 'http_request', 'timestamp_ms': 100,
            'request_id': uuid.uuid4().hex, 'method': 'GET', 'route': '/health/ready',
            'status': 200, 'outcome': 'complete', 'duration_ms': 12.0, **changes}


def write(tmp_path, rows):
    path = tmp_path / 'telemetry.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return path


def test_success_reference_window_has_metrics_not_delivery_claim(tmp_path):
    result = window.evaluate_window(write(tmp_path, [row() for _ in range(20)]), start_ms=0, end_ms=200)
    assert result['samples'] == 20 and result['failure_ratio'] == 0
    assert result['duration_p95_ms'] == 12 and result['status_classes'] == {'2xx': 20}
    assert set(result['alerts'].values()) == {'clear'} and result['notifications_sent'] is False
    assert result['coverage'] == 'input_only_not_proof_of_complete_collection'


def test_error_readiness_and_latency_thresholds_with_half_open_window(tmp_path):
    rows = [row(duration_ms=1000) for _ in range(19)] + [row(status=503)]
    rows += [row(timestamp_ms=200, status=500), row(timestamp_ms=0, status=500)]
    result = window.evaluate_window(write(tmp_path, rows), start_ms=1, end_ms=200)
    assert result['samples'] == 20 and result['failed_requests'] == 1
    assert result['failure_ratio'] == .05 and result['duration_p95_ms'] == 1000
    assert set(result['alerts'].values()) == {'triggered'}


def test_no_samples_or_readiness_is_insufficient_not_healthy(tmp_path):
    result = window.evaluate_window(write(tmp_path, []), start_ms=0, end_ms=200)
    assert result['duration_p95_ms'] is None and result['failure_ratio'] is None
    assert set(result['alerts'].values()) == {'insufficient_data'}
    result = window.evaluate_window(write(tmp_path, [row(route='/other')]), start_ms=0, end_ms=200)
    assert set(result['alerts'].values()) == {'insufficient_data'}


@pytest.mark.parametrize('outcome', ['error', 'cancelled', 'disconnected', 'incomplete'])
def test_unsuccessful_stream_even_after_200_counts_failed(tmp_path, outcome):
    result = window.evaluate_window(write(tmp_path, [row(outcome=outcome)]), start_ms=0, end_ms=200)
    assert result['failed_requests'] == 1 and result['readiness_failures'] == 1


@pytest.mark.parametrize('changes', [
    {'secret': 'must-not-echo'}, {'duration_ms': float('nan')}, {'duration_ms': float('inf')},
    {'duration_ms': 10**400}, {'duration_ms': True}, {'timestamp_ms': True}, {'status': 999}, {'status': 0},
    {'request_id': 'secret'}, {'outcome': 'secret'}, {'method': ['secret']}, {'route': None},
])
def test_reject_invalid_record_without_echo(tmp_path, changes):
    with pytest.raises(window.InvalidTelemetry) as exc:
        window.evaluate_window(write(tmp_path, [row(**changes)]), start_ms=0, end_ms=200)
    assert 'secret' not in str(exc.value)


def test_duplicate_record_is_rejected(tmp_path):
    one = row()
    with pytest.raises(window.InvalidTelemetry, match='duplicate'):
        window.evaluate_window(write(tmp_path, [one, one]), start_ms=0, end_ms=200)


@pytest.mark.parametrize('start,end', [(0, 0), (-1, 10), (200, 100), (0, 3_600_001), (True, 10)])
def test_window_bounds(tmp_path, start, end):
    with pytest.raises(window.InvalidTelemetry):
        window.evaluate_window(write(tmp_path, []), start_ms=start, end_ms=end)


def test_input_bounds_and_cli_safe_errors(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'secret-path'; path.write_bytes(b'x' * (window.MAX_LINE_BYTES + 1))
    assert window.main([str(path), '--start-ms', '0', '--end-ms', '200']) == 2
    assert 'secret' not in capsys.readouterr().err
    monkeypatch.setattr(window, 'MAX_LINES', 2)
    with pytest.raises(window.InvalidTelemetry, match='bounded'):
        window.evaluate_window(write(tmp_path, [row(), row(), row()]), start_ms=0, end_ms=200)
    assert window.main([str(tmp_path / 'secret-absent'), '--start-ms', '0', '--end-ms', '200']) == 2
    assert 'secret' not in capsys.readouterr().err
    assert window.main([str(write(tmp_path, [row()])), '--start-ms', '0', '--end-ms', '200']) == 0
    assert json.loads(capsys.readouterr().out)['samples'] == 1


def test_deep_json_is_safe_invalid_input(tmp_path, capsys):
    path = tmp_path / 'nested.jsonl'
    path.write_text('[' * 1000 + '0' + ']' * 1000)
    assert window.main([str(path), '--start-ms', '0', '--end-ms', '200']) == 2
    assert json.loads(capsys.readouterr().err)['status'] == 'invalid_input'
