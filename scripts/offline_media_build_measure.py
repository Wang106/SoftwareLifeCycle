#!/usr/bin/env python3
"""Explicit fixed-source connected build and measurement; never uploads media.

Uses current tooling with a separate pinned image-source checkout. Dependency
smoke containers are inherited from the builder; no API/Web server or DB starts.
No billing/content clearance, artifact retention, physical offline or company
acceptance follows from a successful measurement. Default invocation is inert.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import offline_image_bundle as bundle
import offline_image_rehearsal as builder
import offline_media_retention as media
import offline_operator_assembly as assembly

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'e2038a9462770a29254674dd86c0e7b26b26a221'
REVISION = '0030_private_upload_sessions'
BUDGET_SECONDS = 55 * 60
# Stop work at 53m25s with95s reserved within the shared55min budget.
# Acquisition stays on the main thread, so the alarm interrupts even open/read;
# no worker-thread join delays owned-CID cleanup (existing30s bound).
CLEANUP_RESERVE = 95


def verify_checkout(root, expected):
    bundle.require(bundle.hexadecimal(expected, 40))
    # No inherited credential/config helpers; Git reads only, never fetches here.
    env = {'PATH': os.environ.get('PATH', ''), 'LANG': 'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
    for args, wanted in ((['rev-parse', 'HEAD'], (expected + '\n').encode()),
                         (['status', '--porcelain', '--untracked-files=all'], b'')):
        result = subprocess.run(['git', *args], cwd=root, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=30, check=True)
        bundle.require(result.stdout == wanted)


@contextmanager
def budget(started_ns):
    """One process-wide deadline, reserving bounded unwind before the hard job cap.

    Raising on TERM/deadline unwinds the builder's existing smoke finally. No
    hard-killed child wrapper, broad cleanup, cleanup retry or success on timeout.
    An unconfirmed CID cleanup remains a failure. Host loss is still uncertain.
    """
    bundle.require(type(started_ns) is int and started_ns > 0)
    elapsed = (time.monotonic_ns() - started_ns) / 10**9
    remaining = BUDGET_SECONDS - CLEANUP_RESERVE - elapsed
    bundle.require(0 <= elapsed and remaining > 0)
    bundle.require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0))
    previous = {s: signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM)}
    def interrupted(_signum, _frame):
        signal.setitimer(signal.ITIMER_REAL, 0)
        raise KeyboardInterrupt('MEDIA_BUILD_INTERRUPTED')
    try:
        for s in previous: signal.signal(s, interrupted)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        yield started_ns + (BUDGET_SECONDS - CLEANUP_RESERVE) * 10**9
        bundle.require(time.monotonic_ns() - started_ns < (BUDGET_SECONDS - CLEANUP_RESERVE) * 10**9)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for s, handler in previous.items(): signal.signal(s, handler)


def build_and_measure(source_root, destination, *, tool_commit, started_ns):
    # Compatibility is from reviewed code, never a received label/user schema flag.
    bundle.require(media.IMAGE_SOURCE == SOURCE and assembly.SOURCE_REVISIONS.get(SOURCE) == REVISION
                   and bundle.preflight.REVISION == REVISION)
    with budget(started_ns) as deadline_ns:
        verify_checkout(ROOT, tool_commit)
        verify_checkout(source_root, SOURCE)
        # Builder snapshots bytes with git show from the checked commit. It checks
        # expected_source_commit again BEFORE dependency acquisition or image build.
        result = builder.run(source_root, bundle_destination=destination, expected_source_commit=SOURCE,
                             deadline_ns=deadline_ns)
        bundle.require(type(result) is dict)
        manifest, _ = bundle.export_inputs({'format': 'slc-offline-readonly-v1',
            'source_commit': SOURCE, 'required_db_revision': REVISION,
            'images': result.get('images')}, result)
        digest = hashlib.sha256(bundle.canonical(manifest)).hexdigest()
        bundle.require(bundle.exact(result.get('image_bundle'), {
            'status': 'IMAGE_BUNDLE_EXPORTED_NOT_OFFLINE_ACCEPTANCE',
            'source_commit': SOURCE, 'manifest_sha256': digest}))
        # Independent expectation is reconstructed from same-run trusted build
        # output, not taken from received manifest bytes or its adjacent hash.
        inventory = media.inspect_candidate(destination, expected_commit=SOURCE,
                                            expected_manifest_sha256=digest)
        verify_checkout(ROOT, tool_commit)
        verify_checkout(source_root, SOURCE)
    return {'status': 'MEDIA_BUILD_MEASURED_NOT_RETAINED_OR_UPLOAD_APPROVED',
            'tool_commit': tool_commit, 'inventory': inventory,
            'application_started': False, 'database_started': False,
            'runtime_media_retained': False,
            'limitations': ['Temporary runner output only; no downloadable artifact',
                'Dependency-only smoke is not API/Web application or company acceptance',
                'Archive sizes are not stored ZIP size, free storage or content clearance',
                'No laptop/server installation or network/USB transfer verified']}


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        raise ValueError('MEDIA_BUILD_REJECTED')


def main(argv=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--tool-commit')
    parser.add_argument('--started-ns', type=int)
    try:
        args = parser.parse_args(argv)
        supplied = (args.source_root, args.destination, args.tool_commit, args.started_ns)
        if not args.run:
            bundle.require(not any(x is not None for x in supplied))
            print('DISABLED: explicit --run required; no build, runtime or upload performed.')
            return 0
        bundle.require(all(x is not None for x in supplied))
        result = build_and_measure(args.source_root, args.destination,
                                   tool_commit=args.tool_commit, started_ns=args.started_ns)
        assembly._emit(sys.stdout, json.dumps(result, sort_keys=True))
        return 0
    except bundle.CompletionInterrupted as error:
        builder.bundle_failure(error)
        return 130
    except bundle.BundleError as error:
        builder.bundle_failure(error)
        return 2
    except builder.CleanupUnconfirmed:
        assembly._emit(sys.stderr, 'MEDIA_BUILD_CLEANUP_UNCONFIRMED: inspect exact owned CID records; no cleanup retry or success claimed.')
        return 2
    except builder.ExportFailure as error:
        assembly._emit(sys.stderr, 'MEDIA_BUILD_EXPORT_REJECTED: role=' + builder.safe_export_role(error.role)
                       + '; code=' + builder.safe_export_code(error.code))
        return 2
    except builder.ComposeFailure as error:
        assembly._emit(sys.stderr, 'MEDIA_BUILD_COMPOSE_REJECTED: phase='
                       + builder.safe_compose_part(error.phase, builder.COMPOSE_PHASES)
                       + '; code=' + builder.safe_compose_part(error.code, builder.COMPOSE_CODES, 'COMPOSE_VALIDATION_FAILED'))
        return 2
    except builder.ProxyBlocked:
        assembly._emit(sys.stderr, 'MEDIA_BUILD_PROXY_REJECTED: no bypass or artifact request performed.')
        return 2
    except KeyboardInterrupt:
        code = 130
    except SystemExit as error:
        return 0 if error.code == 0 else 2
    except Exception:
        code = 2
    try:
        assembly._emit(sys.stderr, 'MEDIA_BUILD_REJECTED_OR_INCOMPLETE: no retry, cleanup expansion or upload; inspect owned records privately.')
    except (Exception, KeyboardInterrupt, SystemExit):
        pass
    return code


if __name__ == '__main__':
    raise SystemExit(main())
