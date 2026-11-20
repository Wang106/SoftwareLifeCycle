"""Synthetic snapshots only: never launch a browser or inspect this host."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('linux_evidence', Path(__file__).parents[1] / 'linux_sandbox_evidence.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def sample():
    return {
        'schema': 1, 'platform': 'linux', 'arch': 'x86_64', 'runner_label': 'ubuntu-24.04',
        'runner_image': '20261111.127.1', 'uid': 1001,
        'executable': '/opt/google/chrome/chrome', 'launcher': '/usr/bin/google-chrome',
        'version': '158.0.8127.37', 'sha256': 'a'*64,
        'chromium_sandbox': True, 'arguments': ['--headless=new'],
        'browser': {'pid': 100, 'start_ticks': 123, 'uid': 1001, 'pid_ns': 10, 'net_ns': 20, 'user_ns': 30},
        'renderer': {'pid': 101, 'start_ticks': 124, 'uid': 1001, 'pid_ns': 11, 'net_ns': 21, 'user_ns': 31,
                     'seccomp': 2, 'no_new_privs': 1, 'ancestry': [101, 100]},
        'sandbox_page': {'namespace': True, 'suid': False, 'pid': True, 'network': True, 'seccomp_bpf': True},
        'after': {'browser_pid': 100, 'browser_start_ticks': 123, 'renderer_pid': 101, 'renderer_start_ticks': 124, 'sha256': 'a'*64},
        'network': {'origin': 'http://127.0.0.1:43123', 'requests': ['http://127.0.0.1:43123/probe'], 'blocked_external': 1},
        'cleanup': {'browser_exited': True, 'listener_closed': True, 'profile_removed': True},
    }


class EvidenceTests(unittest.TestCase):
    def test_consistent_observations_are_not_attestation(self):
        result = module.evaluate(sample())
        self.assertEqual(result['status'], 'OBSERVATIONS_CONSISTENT')
        self.assertIs(result['publisher_signature_verified'], False)
        self.assertIs(result['runner_qualified'], False)
        self.assertEqual(result['observed_version'], '158.0.8127.37')

    def test_negative_observations(self):
        mutations = [
            ('uid', 0), ('uid', True), ('arch', 'aarch64'), ('platform', 'darwin'),
            ('runner_label', 'ubuntu-latest'), ('runner_image', ''), ('version', 'stable'),
            ('executable', '/tmp/chrome'), ('launcher', '/tmp/google-chrome'), ('sha256', 'x'*64),
            ('chromium_sandbox', False), ('chromium_sandbox', 1),
            ('arguments', ['--no-sandbox']), ('arguments', ['--disable-setuid-sandbox']),
            ('arguments', ['--disable-seccomp-filter-sandbox']), ('arguments', ['--remote-debugging-address=0.0.0.0']),
            ('renderer.seccomp', 0), ('renderer.no_new_privs', 0), ('renderer.uid', 0),
            ('renderer.pid_ns', 10), ('renderer.net_ns', 20), ('renderer.user_ns', 30),
            ('renderer.ancestry', [101, 999]), ('renderer.pid', 100),
            ('sandbox_page.namespace', False), ('sandbox_page.seccomp_bpf', False),
            ('after.renderer_start_ticks', 999), ('after.sha256', 'b'*64),
            ('network.requests', ['https://example.com/']), ('network.requests', []),
            ('network.origin', 'http://localhost:43123'), ('network.blocked_external', 0),
            ('cleanup.browser_exited', False), ('cleanup.listener_closed', False), ('cleanup.profile_removed', False),
        ]
        for path, value in mutations:
            with self.subTest(path=path, value=value):
                data=sample(); target=data; parts=path.split('.')
                for part in parts[:-1]: target=target[part]
                target[parts[-1]]=value
                with self.assertRaises(ValueError): module.evaluate(data)

    def test_suid_route_requires_namespace_observations_too(self):
        data=sample(); data['sandbox_page'].update(namespace=False, suid=True)
        data['renderer']['user_ns']=30
        self.assertEqual(module.evaluate(data)['status'], 'OBSERVATIONS_CONSISTENT')
        data['renderer']['pid_ns']=10
        with self.assertRaises(ValueError): module.evaluate(data)

    def test_ancestor_cannot_start_after_renderer(self):
        data=sample(); data['browser']['start_ticks']=10000
        data['after']['browser_start_ticks']=10000
        with self.assertRaises(ValueError): module.evaluate(data)

    def test_missing_and_extra_keys_refused(self):
        for key in sample():
            with self.subTest(key=key):
                data=sample(); del data[key]
                with self.assertRaises(ValueError): module.evaluate(data)
        data=sample(); data['publisher_signature_verified']=True
        with self.assertRaises(ValueError): module.evaluate(data)

    def test_bounded_json_no_duplicates_or_nonfinite(self):
        for raw in [b'{}', b'{"schema":1,"schema":1}', b'{"x":NaN}', b' '*32769, b'\xff', b'[]']:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ValueError): module.parse(raw)

if __name__ == '__main__': unittest.main()
