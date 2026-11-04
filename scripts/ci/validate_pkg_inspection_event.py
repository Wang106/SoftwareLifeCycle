"""One bounded PR transition; reads event metadata and local git, never network."""
import json
import os
from pathlib import Path
import re
import subprocess

PARENT = 'c8f3deacfd4ab0d453fbed29f8d8cbe0f32dae94'
REPOSITORY = 'Wang106/SoftwareLifeCycle'
BRANCH = 'docs/b2-evidence-b3-recovery'
FILES = frozenset({
    '.github/workflows/browser-pkg-inspection.yml',
    'docs/browser-pkg-static-inspection.md',
    'scripts/ci/inspect_pkg_candidate.py',
    'scripts/ci/validate_pkg_inspection_event.py',
    'scripts/ci/tests/test_inspect_pkg_candidate.py',
    'scripts/ci/tests/test_validate_pkg_inspection_event.py',
})


def validate(event, env, checkout, parents, changes):
    pr = event.get('pull_request', {})
    head, base = pr.get('head', {}), pr.get('base', {})
    sha = head.get('sha', '')
    checks = [
        env.get('GITHUB_EVENT_NAME') == 'pull_request',
        env.get('GITHUB_REPOSITORY') == REPOSITORY,
        env.get('GITHUB_RUN_ATTEMPT') == '1',
        event.get('action') == 'synchronize',
        event.get('number') == 176,
        pr.get('number') == 176,
        event.get('repository', {}).get('full_name') == REPOSITORY,
        head.get('repo', {}).get('full_name') == REPOSITORY,
        head.get('repo', {}).get('fork') is False,
        base.get('repo', {}).get('full_name') == REPOSITORY,
        head.get('ref') == BRANCH,
        base.get('ref') == 'main',
        pr.get('state') == 'open',
        bool(re.fullmatch(r'[0-9a-f]{40}', sha)),
        event.get('after') == sha,
        event.get('before') == PARENT,
        checkout == sha,
        parents == [sha, PARENT],
        len(changes) == len(FILES),
        set(changes) == {'A\t' + path for path in FILES},
    ]
    if not all(checks):
        raise RuntimeError('Static inspection rejected: outside the reviewed single PR transition')
    return sha


def git(*args):
    return subprocess.run(['git', *args], check=True, capture_output=True,
                          text=True, timeout=10).stdout.strip()


def main():
    event_path = Path(os.environ['GITHUB_EVENT_PATH'])
    if event_path.stat().st_size > 2 * 1024 * 1024:
        raise RuntimeError('Oversized event metadata')
    event = json.loads(event_path.read_text())
    checkout = git('rev-parse', 'HEAD')
    parents = git('rev-list', '--parents', '-n', '1', 'HEAD').split()
    changes = git('diff', '--no-renames', '--name-status', 'HEAD^', 'HEAD').splitlines()
    sha = validate(event, os.environ, checkout, parents, changes)
    print(json.dumps({'reviewed_parent': PARENT, 'checkout_head': sha,
                      'event_merge_sha': os.environ.get('GITHUB_SHA'),
                      'acceptance': False}, sort_keys=True))


if __name__ == '__main__':
    main()
