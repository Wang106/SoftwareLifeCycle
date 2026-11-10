#!/usr/bin/env python3
"""Explicit same-run migrated API rehearsal; import/help/defaults do no work.

Actual --run requires separate acquisition, container, trust, DDL and API approval.
No external target, old/company database, export, upload, retry or deployment.
"""
import json
import math
import os
from pathlib import Path
import signal
import sys

# Never execute the coordinator as __main__: the probe borrows its exact live
# OwnedContainer type. This thin script has no second copy of that class.
import offline_migration_database_rehearsal as joint

ROOT=Path(__file__).resolve().parents[1]
SOURCES=frozenset({'scripts/offline_migrated_api_rehearsal.py',
                  '.github/workflows/offline-migrated-api-rehearsal.yml'})
STAMP='MIGRATION_REHEARSAL_STARTED_NS'
ENTRY_RESERVE=1330
MAX_SOURCE=65536
require=joint.require


def verify_sources(commit,budget):
    require(type(commit) is str and joint.builder.migration.HEX40.fullmatch(commit),'SOURCE_REJECTED')
    require(type(budget) is joint.builder.Budget and type(budget.deadline) in (int,float)
            and math.isfinite(budget.deadline),'ORIGINAL_BUDGET_REQUIRED')
    require(Path(__file__).absolute()==ROOT/'scripts/offline_migrated_api_rehearsal.py'
            and joint.__name__=='offline_migration_database_rehearsal'
            and Path(joint.__file__).absolute()==ROOT/'scripts/offline_migration_database_rehearsal.py',
            'ENTRYPOINT_LOCATION_REJECTED')
    deadline=budget.deadline
    def check():
        require(budget.deadline==deadline,'BUDGET_CHANGED')
        budget.reserve(ENTRY_RESERVE)
    # Same hardened local Git policy as the original source reader, but each
    # new read uses remaining shared time. Do not modify/monkeypatch that reader.
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':'/nonexistent',
         'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_NO_LAZY_FETCH':'1',
         'GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0'}
    prefix=['/usr/bin/git','--no-pager','--no-replace-objects','--no-lazy-fetch',
            '-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null']
    check()
    migration=joint.builder.migration
    with migration.directory(ROOT) as repo_fd:
        for path in sorted(SOURCES):
            check()
            raw=migration.bounded_command(prefix+['show',commit+':'+path],env=env,
                cwd=f'/proc/self/fd/{repo_fd}',pass_fds=(repo_fd,),limit=MAX_SOURCE,
                timeout=budget.allowance(20,ENTRY_RESERVE))
            target=ROOT/path
            with migration.directory(target.parent) as source_fd:
                local=migration.read_at(source_fd,target.name,MAX_SOURCE)
            require(raw==local,'ENTRYPOINT_SOURCE_MISMATCH')
        check()


def main(argv=None):
    try:
        parser=joint.Parser(description=__doc__)
        parser.add_argument('--run',action='store_true')
        parser.add_argument('--expected-commit',required=True)
        args=parser.parse_args(argv)
        require(args.run and joint.builder.migration.HEX40.fullmatch(args.expected_commit),'ARGUMENTS_REJECTED')
        previous=signal.getsignal(signal.SIGTERM)
        try:
            def interrupted(_sig,_frame): raise KeyboardInterrupt()
            signal.signal(signal.SIGTERM,interrupted)
            marker=os.environ.get(STAMP)
            budget=joint.shared_budget()
            budget.reserve(ENTRY_RESERVE)
            verify_sources(args.expected_commit,budget)
            require(os.environ.get(STAMP)==marker,'BUDGET_MARKER_CHANGED')
            budget.reserve(ENTRY_RESERVE)
            result=joint.run(args.expected_commit,include_api=True)
        finally:
            signal.signal(signal.SIGTERM,previous)
        # Restore process state before emitting a successful receipt.
        print(json.dumps(result,sort_keys=True))
        return 0
    except (Exception,KeyboardInterrupt):
        print('MIGRATED_API_REHEARSAL_BLOCKED_OR_UNCERTAIN; no automatic retry or deployment acceptance.',file=sys.stderr)
        return 2


if __name__=='__main__': sys.exit(main())
