"""Bounded offline evaluation of an explicit telemetry window; never sends alerts."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from app.ops.request_telemetry import METHODS

MAX_LINES = 100_000
MAX_LINE_BYTES = 2048
FIELDS = {'schema_version', 'event', 'timestamp_ms', 'request_id', 'method',
          'route', 'status', 'outcome', 'duration_ms'}
OUTCOMES = {'complete', 'error', 'cancelled', 'disconnected', 'incomplete'}


class InvalidTelemetry(ValueError):
    """Safe fixed message only; never echo an input line."""


def evaluate_window(path: Path, *, start_ms: int, end_ms: int) -> dict:
    if type(start_ms) is not int or type(end_ms) is not int or not 0 <= start_ms < end_ms or end_ms - start_ms > 3_600_000:
        raise InvalidTelemetry('window must be positive and at most one hour')
    durations = []
    ids = set()
    statuses: Counter = Counter()
    outcomes: Counter = Counter()
    errors = readiness_samples = readiness_errors = 0
    # Binary bounded readline prevents an unbounded allocation from a huge line.
    with path.open('rb') as source:
        for index in range(MAX_LINES + 1):
            line = source.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if index == MAX_LINES or len(line) > MAX_LINE_BYTES:
                raise InvalidTelemetry('input exceeds the bounded telemetry limit')
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError, RecursionError):
                raise InvalidTelemetry('invalid telemetry record') from None
            if not isinstance(row, dict) or set(row) != FIELDS:
                raise InvalidTelemetry('invalid telemetry schema')
            if (type(row['schema_version']) is not int or row['schema_version'] != 1 or row['event'] != 'http_request'
                    or type(row['timestamp_ms']) is not int or row['timestamp_ms'] < 0
                    or not isinstance(row['request_id'], str) or not re.fullmatch('[0-9a-f]{32}', row['request_id'])
                    or not isinstance(row['method'], str) or row['method'] not in METHODS | {'OTHER'}
                    or not isinstance(row['route'], str) or len(row['route']) > 512
                    or type(row['status']) is not int or row['status'] not in ({0} | set(range(100, 600)))
                    or not isinstance(row['outcome'], str) or row['outcome'] not in OUTCOMES
                    or type(row['duration_ms']) not in (int, float) or not 0 <= row['duration_ms'] <= 2**53
                    or not math.isfinite(row['duration_ms'])
                    or row['outcome'] == 'complete' and row['status'] == 0):
                raise InvalidTelemetry('invalid telemetry fields')
            if not start_ms <= row['timestamp_ms'] < end_ms:
                continue
            if row['request_id'] in ids:
                raise InvalidTelemetry('duplicate request observation in window')
            ids.add(row['request_id'])
            durations.append(row['duration_ms'])
            statuses[str(row['status'] // 100) + 'xx' if row['status'] else 'not_started'] += 1
            outcomes[row['outcome']] += 1
            failed = row['status'] >= 500 or row['outcome'] != 'complete'
            errors += failed
            if row['route'] == '/health/ready' and row['method'] == 'GET':
                readiness_samples += 1
                readiness_errors += failed or row['status'] != 200
    count = len(durations)
    durations.sort()
    p95 = durations[math.ceil(count * .95) - 1] if count else None
    rate = errors / count if count else None
    # Reference thresholds, not a user-approved SLO or a configured notification.
    def state(enough: bool, breached: bool) -> str:
        return 'insufficient_data' if not enough else ('triggered' if breached else 'clear')
    return {
        'schema_version': 1, 'mode': 'offline_evaluation_only',
        'window': {'start_ms_inclusive': start_ms, 'end_ms_exclusive': end_ms},
        'coverage': 'input_only_not_proof_of_complete_collection',
        'samples': count, 'status_classes': dict(sorted(statuses.items())),
        'outcomes': dict(sorted(outcomes.items())), 'failed_requests': errors,
        'failure_ratio': rate, 'duration_p95_ms': p95,
        'readiness_samples': readiness_samples, 'readiness_failures': readiness_errors,
        'alerts': {
            'request_failures': state(count >= 20, rate is not None and rate >= .05),
            'request_duration': state(count >= 20, p95 is not None and p95 >= 1000),
            'readiness': state(readiness_samples >= 1, readiness_errors > 0),
        },
        'notifications_sent': False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--start-ms', required=True, type=int)
    parser.add_argument('--end-ms', required=True, type=int)
    args = parser.parse_args(argv)
    try:
        result = evaluate_window(args.input, start_ms=args.start_ms, end_ms=args.end_ms)
    except (InvalidTelemetry, OSError) as exc:
        message = str(exc) if isinstance(exc, InvalidTelemetry) else 'input could not be read'
        print(json.dumps({'status': 'invalid_input', 'reason': message}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
