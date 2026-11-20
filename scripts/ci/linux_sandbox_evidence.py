"""Offline consistency checks for future Linux Chrome observations, NOT attestation.

No collection, browser launch, network, filesystem inspection, or trusted signature
verification occurs here. Even a consistent report does not qualify a runner.
"""
import json
import re
import sys
from urllib.parse import urlsplit

MAX_BYTES = 32768


def require(condition):
    if not condition:
        raise ValueError('Linux sandbox observation contract rejected')


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected.split()))


def integer(value, minimum=1):
    require(type(value) is int and minimum <= value < 2**63)


def matches(value, pattern):
    require(type(value) is str and re.fullmatch(pattern, value) is not None)


def evaluate(data):
    keys(data, 'schema platform arch runner_label runner_image uid executable launcher version sha256 chromium_sandbox arguments browser renderer sandbox_page after network cleanup')
    require(type(data['schema']) is int and data['schema'] == 1)
    require(data['platform'] == 'linux' and data['arch'] == 'x86_64')
    require(data['runner_label'] == 'ubuntu-24.04')
    matches(data['runner_image'], r'[0-9]{8}\.[0-9]+\.[0-9]+')
    integer(data['uid'])
    require(data['launcher'] == '/usr/bin/google-chrome')
    require(data['executable'] == '/opt/google/chrome/chrome')
    matches(data['version'], r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')
    matches(data['sha256'], r'[0-9a-f]{64}')
    require(data['chromium_sandbox'] is True)
    # Narrow observation protocol. New options need review, not a denylist bypass.
    args = data['arguments']
    require(type(args) is list and args == ['--headless=new'])
    browser, renderer = data['browser'], data['renderer']
    keys(browser, 'pid start_ticks uid pid_ns net_ns user_ns')
    keys(renderer, 'pid start_ticks uid pid_ns net_ns user_ns seccomp no_new_privs ancestry')
    for process in (browser, renderer):
        for field in ('pid', 'start_ticks', 'uid', 'pid_ns', 'net_ns', 'user_ns'):
            integer(process[field])
        require(process['uid'] == data['uid'])
    require(browser['pid'] != renderer['pid'])
    require(renderer['start_ticks'] >= browser['start_ticks'])
    ancestry = renderer['ancestry']
    require(type(ancestry) is list and 2 <= len(ancestry) <= 16)
    for pid in ancestry: integer(pid)
    require(len(set(ancestry)) == len(ancestry))
    require(ancestry[0] == renderer['pid'] and ancestry[-1] == browser['pid'])
    require(type(renderer['seccomp']) is int and renderer['seccomp'] == 2)
    require(type(renderer['no_new_privs']) is int and renderer['no_new_privs'] == 1)
    page = data['sandbox_page']
    keys(page, 'namespace suid pid network seccomp_bpf')
    require(all(type(v) is bool for v in page.values()))
    require(page['namespace'] or page['suid'])
    require(page['pid'] and page['network'] and page['seccomp_bpf'])
    require(renderer['pid_ns'] != browser['pid_ns'] and renderer['net_ns'] != browser['net_ns'])
    if page['namespace']:
        require(renderer['user_ns'] != browser['user_ns'])
    after = data['after']
    keys(after, 'browser_pid browser_start_ticks renderer_pid renderer_start_ticks sha256')
    for name, process in (('browser', browser), ('renderer', renderer)):
        for field in ('pid', 'start_ticks'):
            integer(after[name+'_'+field])
            require(after[name+'_'+field] == process[field])
    require(after['sha256'] == data['sha256'])
    network = data['network']
    keys(network, 'origin requests blocked_external')
    matches(network['origin'], r'http://127\.0\.0\.1:[0-9]{1,5}')
    port = urlsplit(network['origin']).port
    require(port is not None and 1024 <= port <= 65535)
    requests = network['requests']
    require(type(requests) is list and 1 <= len(requests) <= 16)
    require(all(type(url) is str and url == network['origin']+'/probe' for url in requests))
    integer(network['blocked_external'])
    keys(data['cleanup'], 'browser_exited listener_closed profile_removed')
    require(all(v is True for v in data['cleanup'].values()))
    return {'status': 'OBSERVATIONS_CONSISTENT', 'publisher_signature_verified': False,
            'runner_qualified': False, 'observed_version': data['version'],
            'observed_sha256': data['sha256'], 'runner_image': data['runner_image'],
            'limitation': 'Input observations are untrusted; no collector or publisher verification executed.'}


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def parse(raw):
    require(type(raw) is bytes and len(raw) <= MAX_BYTES)
    try:
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: require(False))
        return evaluate(data)
    except (UnicodeError, TypeError, KeyError, RecursionError, OverflowError) as error:
        raise ValueError('Linux sandbox observation contract rejected') from error


def main():
    try:
        report = parse(sys.stdin.buffer.read(MAX_BYTES + 1))
    except ValueError:
        print('Linux sandbox observation contract rejected', file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
