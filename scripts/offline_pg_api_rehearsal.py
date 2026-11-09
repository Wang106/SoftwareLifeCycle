"""CI-only source API process harness. Import does nothing; no database client.

This is not an offline-image installer, a role isolation proof or a deployment gate.
"""
import http.client
import json
import os
from pathlib import Path
import re
import signal
import threading
from contextlib import contextmanager
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit, urlencode

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
MAX_RESPONSE = 65536
WORK_SECONDS = 90
BOOTSTRAP = """import sys
sys.path.insert(0, sys.argv[1])
import uvicorn
uvicorn.run('app.main:app', fd=int(sys.argv[2]), workers=1, access_log=False, log_level='critical', timeout_graceful_shutdown=3)
"""
ALLOWED = {('GET', '/health/live'), ('GET', '/health/ready'),
           ('GET', '/api/v1/release-catalog/application?limit=1'),
           ('GET', '/api/v1/audit/events?limit=1'),
           ('GET', '/api/v1/security/me'),
           ('POST', '/api/v1/deployments')}


class RehearsalError(ValueError):
    def __init__(self):
        super().__init__('PG_API_REHEARSAL_FAILED')


def validate_ci():
    if (os.name != 'posix' or sys.platform != 'linux'
            or os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('CI') != 'true'
            or os.environ.get('GITHUB_REPOSITORY') != 'Wang106/SoftwareLifeCycle'
            or any(key.startswith('PG') for key in os.environ)):
        raise RehearsalError()


def scoped_url(base, namespace):
    try:
        if type(namespace) is not str or not re.fullmatch(r'ci_(?:catalog|api)_[0-9a-f]{32}', namespace):
            raise RehearsalError()
        if type(base) is not str or len(base) > 2048 or any(ord(c) < 32 for c in base):
            raise RehearsalError()
        parsed = urlsplit(base)
        if (parsed.scheme != 'postgresql+psycopg' or parsed.hostname != '127.0.0.1'
                or parsed.port != 5432 or parsed.username != 'slc_ci' or not parsed.password
                or parsed.path != '/software_lifecycle_ci' or parsed.query or parsed.fragment):
            raise RehearsalError()
        options = (f'-csearch_path={namespace} -cdefault_transaction_read_only=on '
                   '-cstatement_timeout=5000 -clock_timeout=1000 -cidle_in_transaction_session_timeout=15000')
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                           urlencode({'options': options, 'connect_timeout': '5'}), ''))
    except Exception:
        raise RehearsalError() from None


def child_environment(base, namespace):
    return {'LANG': 'C.UTF-8', 'DATABASE_URL': scoped_url(base, namespace),
            'READ_ONLY_MODE': 'true', 'AUTH_MODE': 'disabled', 'SEED_ON_STARTUP': 'false',
            'ADMIN_OPERATOR_ENABLED': 'false', 'REQUEST_TELEMETRY_ENABLED': 'false',
            'CORS_ORIGINS': '', 'REQUIRED_DB_REVISION': '0029_changeover_batch_history'}


def json_body(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise RehearsalError()
            result[key] = value
        return result
    def reject(_value): raise RehearsalError()
    try:
        if type(body) is not bytes or len(body) > MAX_RESPONSE: raise RehearsalError()
        value = json.loads(body.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject)
        if type(value) is not dict: raise RehearsalError()
        return value
    except Exception:
        raise RehearsalError() from None


@contextmanager
def http_deadline(seconds):
    """Bound the whole header/body exchange, not just each socket receive."""
    if (threading.current_thread() is not threading.main_thread()
            or not hasattr(signal, 'setitimer') or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0)):
        raise RehearsalError()
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_signal, _frame):
        raise TimeoutError('PG_API_HTTP_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        try:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
            finally:
                # Cancellation failure must not skip the restoration attempt.
                signal.signal(signal.SIGALRM, previous)
        except Exception:
            raise RehearsalError() from None


class APIProcess:
    """One owned uvicorn process; no retries/restarts or arbitrary HTTP targets."""
    def __init__(self, base_url, namespace):
        self.base_url, self.namespace = base_url, namespace
        self.process = None
        self.port = None
        self.deadline = 0
        self.directory = None

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise RehearsalError()
        return remaining

    def __enter__(self):
        validate_ci()
        env = child_environment(self.base_url, self.namespace)
        self.deadline = time.monotonic() + WORK_SECONDS
        self.directory = tempfile.TemporaryDirectory(prefix='slc-ci-api-')
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen(16)
                self.port = listener.getsockname()[1]
                fd = listener.fileno()
                self.process = subprocess.Popen(
                    [sys.executable, '-I', '-c', BOOTSTRAP, str(BACKEND), str(fd)],
                    cwd=self.directory.name, env=env, pass_fds=(fd,), close_fds=True,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
            # Readiness polling never restarts a failed process or follows redirects.
            startup = min(self.deadline, time.monotonic() + 30)
            while time.monotonic() < startup:
                if self.process.poll() is not None: raise RehearsalError()
                try:
                    status, body = self.request('GET', '/health/live')
                except (ConnectionError, TimeoutError, OSError):
                    time.sleep(min(0.1, self.remaining()))
                    continue
                if status != 200 or json_body(body).get('status') != 'ok': raise RehearsalError()
                return self
            raise RehearsalError()
        except BaseException as original:
            cleanup_failed = False
            try:
                self.stop()
            except BaseException:
                cleanup_failed = True
            finally:
                try:
                    if self.directory is not None: self.directory.cleanup(); self.directory = None
                except BaseException:
                    cleanup_failed = True
            if not isinstance(original, Exception):
                if cleanup_failed: original.add_note('PG_API_STARTUP_CLEANUP_UNCONFIRMED')
                raise
            raise RehearsalError() from None

    def request(self, method, path):
        if (method, path) not in ALLOWED: raise RehearsalError()
        timeout = min(2.0, self.remaining())
        if self.process is None or self.process.poll() is not None: raise RehearsalError()
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=timeout)
        try:
            payload = b'{}' if method == 'POST' else None
            with http_deadline(timeout):
                connection.request(method, path, body=payload,
                                   headers={'Connection': 'close', 'Content-Type': 'application/json'})
                response = connection.getresponse()
                body = response.read(MAX_RESPONSE + 1)
            self.remaining()
            if len(body) > MAX_RESPONSE: raise RehearsalError()
            return response.status, body
        finally:
            connection.close()

    def stop(self):
        process, self.process = self.process, None
        if process is None: return
        try:
            if process.poll() is not None:
                # An unexpected early exit is never a successful rehearsal.
                raise RehearsalError()
            process.terminate()
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise RehearsalError()
            if code != 0: raise RehearsalError()
        except Exception:
            raise RehearsalError() from None

    def __exit__(self, _type, _value, _traceback):
        try:
            self.stop()
        finally:
            if self.directory is not None: self.directory.cleanup(); self.directory = None
        return False
