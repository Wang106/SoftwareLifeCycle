"""Local metadata consistency only; NOT evidence of operator authorization."""
import json
import os
from pathlib import Path
import re
import subprocess

SOURCE_HEAD = '3816b41f48fcc5b43bd44baba9db8a4f1e540488'
REPOSITORY = 'Wang106/SoftwareLifeCycle'
REF = 'refs/heads/diagnostics/pr210-pkg-inspection'
WORKFLOW_REF = REPOSITORY + '/.github/workflows/browser-diagnostics.yml@' + REF
APPROVAL = 'static-only-no-install-no-launch'


def validate(event, env, tooling_checkout, source_checkout):
    if not isinstance(event, dict) or not isinstance(event.get('inputs'), dict):
        raise ValueError('Malformed dispatch metadata')
    inputs = event['inputs']
    tooling = inputs.get('tooling_head')
    if not all((
        env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
        env.get('GITHUB_REPOSITORY') == REPOSITORY,
        env.get('GITHUB_RUN_ATTEMPT') == '1',
        env.get('GITHUB_REF') == REF,
        env.get('GITHUB_WORKFLOW_REF') == WORKFLOW_REF,
        isinstance(tooling, str) and re.fullmatch('[0-9a-f]{40}', tooling) is not None,
        tooling == env.get('GITHUB_SHA') == tooling_checkout,
        inputs.get('source_head') == SOURCE_HEAD == source_checkout,
        inputs.get('approval') == APPROVAL,
    )):
        raise ValueError('Outside the fixed PR210 source and diagnostic workflow scope')
    return {'source_pr': 210, 'source_head': SOURCE_HEAD, 'tooling_head': tooling,
            'acceptance': False, 'authorization_verified_by_script': False}


def head(path):
    return subprocess.run(['git', '-C', path, 'rev-parse', 'HEAD'], check=True,
                          capture_output=True, text=True, timeout=10).stdout.strip()


def main():
    path = Path(os.environ['GITHUB_EVENT_PATH'])
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Oversized dispatch event')
    print(json.dumps(validate(json.loads(path.read_text()), os.environ,
                              head('tooling'), head('source')), sort_keys=True))


if __name__ == '__main__': main()
