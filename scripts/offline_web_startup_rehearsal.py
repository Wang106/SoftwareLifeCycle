#!/usr/bin/env python3
"""Default-off Web startup acceptance preparation; no workflow integration.

Only explicit runtime authorization plus an independently trusted, same-commit
LOCAL image permits --run. Mock tests do not constitute startup evidence.
"""
import json
from pathlib import Path
import re
import shutil
import signal
import sys
import tempfile
import time
import uuid

import offline_api_startup_rehearsal as custody
from offline_api_startup_rehearsal import (Blocked, require, exact, document, environment,
    prepare_runtime, run_child, ERROR_CODES)
from offline_readonly_preflight import GATES

NODE = '/usr/local/bin/node'
NEXT_ARGS = ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3000']
LABEL = 'org.software-lifecycle.web-startup-rehearsal'
SUCCESS = 'WEB_STARTUP_SSR_PASSED_NOT_BROWSER_OR_OFFLINE_ACCEPTANCE'
LIMITATIONS = ('Caller must independently trust the exact reviewed local build; IDs and labels do not authenticate '
    'provenance. Mock/static tests do not execute runtime. Runtime checks cover bounded completed server HTML '
    'and disabled login only, not browser hydration, real API integration, database, OIDC, '
    'physical host isolation, offline transfer or company acceptance.')
ENVIRONMENT = {**dict.fromkeys(GATES, 'disabled'),
    'PATH': '/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/tmp',
    'API_BASE_URL': 'http://127.0.0.1:8000', 'NEXT_PUBLIC_API_URL': '',
    'NEXT_PUBLIC_API_BASE_URL': '', 'NEXT_TELEMETRY_DISABLED': '1', 'NODE_ENV': 'production'}
SAFE_IMAGE_ENV = {'PATH', 'NODE_VERSION', 'YARN_VERSION'}
CASES = ('dashboard_unavailable', 'login_disabled')
PROBE_PROGRAM = Path(__file__).with_name('offline_web_startup_probe.cjs').read_text()


def verify_image(raw, image_id, commit):
    data = document(raw)
    require(type(data) is list and len(data) == 1 and type(data[0]) is dict, 'IMAGE_IDENTITY_REJECTED')
    item = data[0]; config = item.get('Config')
    require(type(config) is dict and type(config.get('Labels')) is dict, 'IMAGE_IDENTITY_REJECTED')
    require(item.get('Id') == image_id and item.get('Os') == 'linux' and item.get('Architecture') == 'amd64'
        and not item.get('Variant') and config['Labels'].get('org.opencontainers.image.revision') == commit
        and config.get('User') == '65532:65532' and config.get('WorkingDir') == '/app'
        and exact(config.get('Entrypoint'), ['/bin/false']) and config.get('Cmd') in (None, [])
        and config.get('Volumes') in (None, {}) and config.get('Healthcheck') in (None, {})
        and config.get('OnBuild') in (None, []), 'IMAGE_IDENTITY_REJECTED')
    result = environment(config.get('Env'), SAFE_IMAGE_ENV)
    require(result.get('NODE_VERSION') == '22.23.4' and result.get('YARN_VERSION') == '1.22.22',
            'IMAGE_IDENTITY_REJECTED')
    return result


def verify_probe(name, code, raw):
    require(name in (*CASES, 'process') and code == 0
            and exact(document(raw), {'case': name, 'passed': True}), 'PROBE_REJECTED')


class Container(custody.Container):
    label = LABEL
    name_prefix = 'slc-web-startup-'
    runtime_environment = ENVIRONMENT
    executable = NODE
    command = NEXT_ARGS

    def execute(self, name):
        require(name in (*CASES, 'process'), 'PROBE_REJECTED')
        self.inspect(running=True)
        return self.child(['exec', '--user=65532:65532', self.cid, NODE, '-e', PROBE_PROGRAM, name],
                          limit=4096, timeout=25)

    def process_ready(self):
        for _ in range(20):
            code, value = self.execute('process')
            if code == 0:
                verify_probe('process', code, value)
                return
            require(code == 2 and value == b'', 'PROCESS_REJECTED')
            time.sleep(.5)
        raise Blocked('STARTUP_TIMEOUT')


def run_rehearsal(image_id, source_commit):
    require(type(image_id) is str and re.fullmatch('sha256:[0-9a-f]{64}', image_id) is not None
            and type(source_commit) is str and re.fullmatch('[0-9a-f]{40}', source_commit) is not None,
            'ARGUMENTS_REJECTED')
    root = Path(tempfile.mkdtemp(prefix='slc-web-startup-'))
    container = None
    completed = 0
    phase, reason = 'HOST', None
    deadline = time.monotonic() + 180
    try:
        env, docker = prepare_runtime(root, source_commit)
        def child(args, **kwargs):
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'REHEARSAL_TIMEOUT')
            return run_child([docker, '--host=unix:///var/run/docker.sock', *args], env=env,
                             **(kwargs | {'timeout': min(kwargs.get('timeout', 15), remaining)}))
        code, value = child(['info', '--format', '{{json .}}'])
        require(code == 0, 'COMMAND_FAILED')
        info = document(value)
        require(type(info) is dict and info.get('OSType') == 'linux'
                and info.get('Architecture') in ('amd64', 'x86_64'), 'DAEMON_PLATFORM_REJECTED')
        phase = 'IMAGE'
        code, value = child(['image', 'inspect', image_id])
        require(code == 0, 'IMAGE_IDENTITY_REJECTED')
        baked_env = verify_image(value, image_id, source_commit)
        phase = 'CREATE'
        container = Container(root, child, uuid.uuid4().hex, image_id, source_commit, baked_env)
        container.create()
        phase = 'PROCESS'
        container.process_ready()
        phase = 'PROBES'
        for name in CASES:
            code, value = container.execute(name)
            verify_probe(name, code, value)
            completed += 1
        phase = 'FINAL_PROCESS'
        code, value = container.execute('process')
        require(code == 0 and exact(document(value), {'case': 'process', 'passed': True}), 'PROCESS_REJECTED')
    except (Exception, KeyboardInterrupt) as error:
        reason = str(error) if isinstance(error, Blocked) and str(error) in ERROR_CODES else 'REHEARSAL_FAILED'
    finally:
        if container is not None:
            deadline = time.monotonic() + 35
            try:
                container.cleanup()
            except (Exception, KeyboardInterrupt):
                reason = 'CLEANUP_UNCERTAIN'
        if container is None or not container.attempted or container.cleaned:
            try:
                shutil.rmtree(root)
            except OSError:
                reason = 'LOCAL_CLEANUP_UNCERTAIN'
        # Preserve private custody/CID for uncertain outcomes. No prune, lookup
        # by name, repeated removal or arbitrary user-supplied container ID.
    result = {'status': 'BLOCKED' if reason else SUCCESS, 'phase': phase,
              'cases_passed': completed, 'cases_total': len(CASES),
              'evidence_kind': 'runtime_attempt', 'container_removed': bool(container is not None and container.cleaned),
              'limitations': LIMITATIONS}
    if reason:
        result['reason'] = reason
    else:
        result.update(image_id=image_id, source_commit=source_commit, database_ready=False, api_integration=False, browser_hydration=False, offline_acceptance=False,
                      provenance='caller_supplied_trusted_build_consistency_only')
    return result, 2 if reason else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--help']:
        print('Usage: offline_web_startup_rehearsal.py --run --trusted-local-image --image-id sha256:<64hex> '
              '--source-commit <40hex>\nSeparate runtime approval required. ' + LIMITATIONS)
        return 0
    if not (len(argv) == 6 and argv[0] == '--run' and argv[1] == '--trusted-local-image' and argv[2] == '--image-id'
            and re.fullmatch('sha256:[0-9a-f]{64}', argv[3]) is not None
            and argv[4] == '--source-commit' and re.fullmatch('[0-9a-f]{40}', argv[5]) is not None):
        result, code = {'status': 'BLOCKED', 'reason': 'ARGUMENTS_REJECTED', 'limitations': LIMITATIONS}, 2
    else:
        previous = signal.getsignal(signal.SIGTERM)
        def interrupted(_signum, _frame): raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        try:
            try:
                result, code = run_rehearsal(argv[3], argv[5])
            except (Exception, KeyboardInterrupt):
                result, code = {'status': 'BLOCKED', 'reason': 'REHEARSAL_FAILED', 'limitations': LIMITATIONS}, 2
        finally:
            signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
