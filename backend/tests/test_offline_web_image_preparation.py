"""Synthetic Web preparation contracts: never acquire or invoke a daemon."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
C = 'a' * 40
I = 'sha256:' + 'b' * 64


class WebPreparationTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('offline_web_image_preparation')

    def test_no_cli_and_fixed_false_receipt(self):
        m = self.m
        self.assertFalse(hasattr(m, 'main'))
        r = m.receipt(C, I, 'c'*64, 'd'*64)
        self.assertEqual(r['status'], 'WEB_IMAGE_PREPARED_NOT_STARTED')
        for k in ('application_started', 'database_connected', 'provenance_authenticated'):
            self.assertIs(r[k], False)
        for args in ((True, I, 'c'*64, 'd'*64), (C, 'tag', 'c'*64, 'd'*64), (C, I, 1, 'd'*64)):
            with self.subTest(args=args), self.assertRaises(m.Blocked): m.receipt(*args)

    def test_only_frontend_allowlisted_sources(self):
        m = self.m
        for name in ('frontend/app/page.tsx', 'frontend/components/Test.tsx', 'frontend/lib/a.json'):
            self.assertTrue(m.source_name(name))
        for name in ('backend/app/main.py', 'frontend/.env', 'frontend/lib/secret.json', 'frontend/app/../x.ts'):
            self.assertFalse(m.source_name(name))
        self.assertEqual(m.context_name('deploy/offline/web.Dockerfile'), 'Dockerfile')

    def source_fixture(self):
        m = self.m
        names = m.FIXED | m.TOOLS | {'frontend/app/page.tsx', 'frontend/components/x.tsx', 'frontend/lib/x.ts'}
        contents = {n: (ROOT/n).read_bytes() if (ROOT/n).exists() else b'fixture' for n in names}
        objects = {hashlib.sha1(n.encode()).hexdigest(): raw for n, raw in contents.items()}
        records = b''.join(('100644 blob '+hashlib.sha1(n.encode()).hexdigest()+'\t'+n+'\0').encode() for n in sorted(names))
        def git(fd, args, *rest):
            return {'config': b'', 'rev-parse': C.encode(), 'status': b'', 'ls-tree': records}.get(args[0], objects.get(args[-1], b''))
        return contents, git

    def test_exact_git_sources_and_inventory(self):
        m = self.m; contents, git = self.source_fixture()
        with patch.object(m.migration, 'git_read', side_effect=git), patch.object(m, 'read_file', side_effect=lambda p, cap: contents[str(p.relative_to(ROOT))]):
            sources, inventory = m.source_inputs(C)
        self.assertEqual(len(inventory['artifacts']), 399)
        self.assertFalse(any(n.startswith('backend/') for n in sources))

    def test_dirty_filter_wrong_commit_and_changed_bytes(self):
        m = self.m; contents, git = self.source_fixture()
        for mode in ('dirty', 'filter', 'commit', 'bytes', 'symlink', 'missing'):
            def altered(fd, args, *rest):
                raw = git(fd, args, *rest)
                if mode == 'dirty' and args[0] == 'status': return b' M changed'
                if mode == 'filter' and args[0] == 'config': return b'filter.x.clean\ncat\0'
                if mode == 'commit' and args[0] == 'rev-parse': return b'f'*40
                if mode == 'symlink' and args[0] == 'ls-tree': return raw.replace(b'100644', b'120000', 1)
                if mode == 'missing' and args[0] == 'ls-tree': return b''
                return raw
            with self.subTest(mode=mode), patch.object(m.migration, 'git_read', side_effect=altered), patch.object(m, 'read_file', side_effect=lambda p, cap: contents[str(p.relative_to(ROOT))]+(b'changed' if mode == 'bytes' else b'')):
                with self.assertRaises(m.Blocked): m.source_inputs(C)

    def test_original_budget_admission_no_work(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.builder, 'command') as cmd:
            for budget in (None, object()):
                with self.assertRaises(m.Blocked): m.prepare(C, root=Path(tmp)/'work', budget=budget)
            with patch.object(m.builder.time, 'monotonic', return_value=100):
                budget = m.builder.Budget(100)
            with patch.object(m.builder.time, 'monotonic', return_value=3400):
                with self.assertRaises(m.Blocked): m.prepare(C, root=Path(tmp)/'work', budget=budget)
            cmd.assert_not_called()
            self.assertFalse((Path(tmp)/'work').exists())

    def test_private_path_collision_and_symlink_parent(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.builder, 'command') as cmd:
            budget = m.builder.Budget(m.builder.time.monotonic())
            with self.assertRaises(m.Blocked): m.prepare(C, root=tmp, budget=budget)
            alias = Path(tmp)/'alias'; alias.symlink_to(tmp, target_is_directory=True)
            with self.assertRaises(m.Blocked): m.prepare(C, root=alias/'work', budget=budget)
            cmd.assert_not_called()

    def test_reserves_cover_downstream_and_cleanup(self):
        self.assertEqual(self.m.DOWNSTREAM_RESERVE, 1630)
        self.assertGreaterEqual(self.m.CLEANUP_RESERVE, 60)

    def test_errors_redacted(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.builder, 'command', side_effect=RuntimeError('secret-url')):
            with self.assertRaises(m.Blocked) as caught:
                m.prepare(C, root=Path(tmp)/'work', budget=m.builder.Budget(m.builder.time.monotonic()))
            self.assertNotIn('secret', str(caught.exception))



class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('offline_web_image_preparation')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'work'
        self.budget = self.m.builder.Budget(self.m.builder.time.monotonic())
        self.deadline = self.budget.deadline
        self.calls = []
        self.mode = ''

    def command(self, args, **kw):
        m = self.m; self.calls.append((args, kw))
        self.assertGreater(kw['timeout'], 0)
        self.assertLessEqual(kw['timeout'], self.deadline-m.builder.time.monotonic()-30-m.DOWNSTREAM_RESERVE)
        if args[0] != 'fake-docker':
            program = args[4]
            if 's,i=m.source_inputs' in program:
                if self.mode == 'mutation': self.budget.deadline += 100
                if self.mode == 'exhaustion': self.budget.deadline -= 3300
                if self.mode == 'interrupt': raise KeyboardInterrupt()
                value = {'source_manifest_sha256': 'c'*64}
                if self.mode == 'source_extra': value['untrusted'] = True
                return 0, json.dumps(value).encode()
            if 'm.acquire(' in program: return 0, b''
            if 'm.build_context(' in program:
                archive = Path(args[-2]); archive.write_bytes(b'synthetic-tar')
                value = {'source_commit': C, 'source_manifest_sha256': 'c'*64,
                         'context_manifest_sha256': 'd'*64,
                         'build_context_sha256': hashlib.sha256(b'synthetic-tar').hexdigest()}
                if self.mode == 'context': value['source_commit'] = 'f'*40
                if self.mode == 'context_bool': value['build_context_sha256'] = True
                if self.mode == 'archive': archive.write_bytes(b'changed')
                return 0, json.dumps(value).encode()
            if 'shutil.rmtree' in program:
                if self.mode == 'cleanup': return 1, b''
                import shutil
                shutil.rmtree(self.root)
                return 0, b''
            self.fail(args)
        if 'pull' in args:
            if self.mode == 'pull': return 1, b''
            self.assertIn(m.BASE, args)
            return 0, b''
        if 'build' in args:
            self.assertIn('--network=none', args)
            self.assertIn('--pull=false', args)
            self.assertIn('--no-cache', args)
            self.assertEqual(kw['stdin'].read(), b'synthetic-tar')
            if self.mode == 'build': return 1, b''
            (self.root/'web.iid').write_text(I if self.mode != 'iid' else 'mutable:tag')
            return 0, b''
        self.assertIn('inspect', args)
        if args[-1] == m.BASE:
            return 0, json.dumps([{'Id': m.BASE_CONFIG, 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
        self.assertEqual(args[-1], I)
        data = {'Id': I, 'Os': 'linux', 'Architecture': 'amd64', 'Config': {
            'Labels': {'org.opencontainers.image.revision': C}, 'User': '65532:65532',
            'WorkingDir': '/app', 'Entrypoint': ['/bin/false'], 'Cmd': [],
            'Env': ['PATH=/usr/bin', 'NODE_VERSION=22.23.4', 'YARN_VERSION=1.22.22']}}
        if self.mode == 'image': data['Config']['Entrypoint'] = ['/bin/sh']
        if self.mode == 'revision': data['Config']['Labels']['org.opencontainers.image.revision'] = 'f'*40
        if self.mode == 'platform': data['Architecture'] = 'arm64'
        return 0, json.dumps([data]).encode()

    def run_prepare(self):
        m = self.m
        def host(root, budget):
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            budget.allowance(30)
            return ['fake-docker', '--host=unix:///var/run/docker.sock'], {'PATH': '/usr/bin'}
        with patch.object(m.builder, 'command', side_effect=self.command), patch.object(m.builder, 'host', side_effect=host):
            return m.prepare(C, root=self.root, budget=self.budget)

    def test_web_only_exact_build_receipt_original_budget_cleanup(self):
        result = self.run_prepare()
        self.assertEqual(result, self.m.receipt(C, I, 'd'*64, hashlib.sha256(b'synthetic-tar').hexdigest()))
        self.assertEqual(self.budget.deadline, self.deadline)
        self.assertFalse(self.root.exists())
        docker = [a for a, kw in self.calls if a[0] == 'fake-docker']
        self.assertEqual(len(docker), 4)
        self.assertEqual(sum('build' in a for a in docker), 1)
        for a in docker:
            self.assertFalse(set(a) & {'run', 'create', 'start', 'exec', 'save', 'load', 'prune', 'rm'})
            self.assertFalse(any('api' in v or 'python@' in v for v in a))

    def test_mutation_and_exhaustion_stop_before_acquisition(self):
        for mode in ('mutation', 'exhaustion'):
            with self.subTest(mode=mode):
                self.mode = mode
                with self.assertRaises(self.m.Blocked): self.run_prepare()
                self.assertEqual(len(self.calls), 1)
                self.root.rmdir(); self.calls.clear(); self.budget.deadline = self.deadline

    def test_fail_closed_no_retries_or_cleanup_after_uncertain_work(self):
        for mode in ('source_extra', 'context', 'context_bool', 'archive', 'pull', 'build', 'iid', 'image', 'revision', 'platform', 'cleanup'):
            with self.subTest(mode=mode):
                self.mode = mode
                with self.assertRaises(self.m.Blocked): self.run_prepare()
                self.assertTrue(self.root.exists())
                self.assertLessEqual(sum('build' in a for a, kw in self.calls), 1)
                self.assertFalse(any('prune' in a or 'rm' in a for a, kw in self.calls))
                import shutil
                shutil.rmtree(self.root); self.calls.clear()

    def test_control_exception_propagates_and_retains_private_path(self):
        self.mode = 'interrupt'
        with self.assertRaises(KeyboardInterrupt): self.run_prepare()
        self.assertTrue(self.root.is_dir())
        self.assertEqual(len(self.calls), 1)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('offline_web_image_preparation')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.artifacts = self.path/'artifacts'; self.artifacts.mkdir()
        self.raw = b'tiny synthetic artifact'
        self.sha = hashlib.sha512(self.raw).hexdigest()
        self.filename = 'sha512-'+self.sha+'.tgz'
        (self.artifacts/self.filename).write_bytes(self.raw)
        self.sources = {'frontend/package-lock.json': b'{}', 'frontend/app/page.tsx': b'page',
                        'deploy/offline/web.Dockerfile': b'FROM pinned'}
        self.inventory = {'artifacts': [{'filename': self.filename, 'sha512': self.sha, 'size_bytes': len(self.raw)}]}
        self.binding = self.m.digest(self.m.encoded(self.m.source_manifest(self.sources)))

    def build(self, binding=None, audit=None):
        m = self.m
        with patch.object(m, 'source_inputs', return_value=(self.sources, self.inventory)), patch.object(m.npm, 'audit_artifacts', return_value=self.inventory if audit is None else audit), patch.object(m, 'read_file', return_value=b'{}'):
            return m.build_context(C, self.artifacts, self.path/'context.tar', binding or self.binding)

    def test_tar_source_artifact_hashes_and_exclusive_output(self):
        import tarfile
        r = self.build()
        self.assertEqual(r['source_commit'], C)
        self.assertEqual(r['build_context_sha256'], hashlib.sha256((self.path/'context.tar').read_bytes()).hexdigest())
        self.assertEqual((self.path/'context.tar').stat().st_mode & 0o777, 0o600)
        with tarfile.open(self.path/'context.tar') as archive:
            names = archive.getnames()
            self.assertIn('Dockerfile', names)
            self.assertIn('app/page.tsx', names)
            self.assertIn('artifacts/'+self.filename, names)
            self.assertFalse(any(n.startswith('backend') or n.startswith('wheels') for n in names))
        with self.assertRaises(FileExistsError): self.build()

    def test_dynamic_frontend_routes_are_preserved(self):
        self.sources['frontend/app/account/grants/[scope]/[id]/page.tsx'] = (ROOT/'frontend/app/account/grants/[scope]/[id]/page.tsx').read_bytes()
        self.binding = self.m.digest(self.m.encoded(self.m.source_manifest(self.sources)))
        self.build()
        import tarfile
        with tarfile.open(self.path/'context.tar') as archive:
            self.assertEqual(archive.extractfile('app/account/grants/[scope]/[id]/page.tsx').read(), (ROOT/'frontend/app/account/grants/[scope]/[id]/page.tsx').read_bytes())

    def test_context_paths_reject_traversal_secret_and_noncanonical_names(self):
        for name in ('../a', '/app/a', 'app//a', 'app/./a', 'app/../a', 'app/.env',
                     'app/secret.json', 'app/credentials.json', 'app/a\\b', 'app/é.ts',
                     'a/'*17+'page.tsx', 'a'*513):
            with self.subTest(name=name), self.assertRaises(self.m.Blocked):
                self.m.context_path(name)
        for name in ('app/account/grants/[scope]/[id]/page.tsx',
                     'app/(group)/[...slug]/page.tsx', 'app/[[...slug]]/page.tsx'):
            self.m.context_path(name)

    def test_changed_source_audit_and_artifact_rejected(self):
        for mode in ('source', 'audit', 'artifact'):
            with self.subTest(mode=mode):
                if mode == 'artifact': (self.artifacts/self.filename).write_bytes(b'changed')
                with self.assertRaises(Exception):
                    self.build(binding='f'*64 if mode == 'source' else None, audit={} if mode == 'audit' else None)
                (self.path/'context.tar').unlink(missing_ok=True)

    def test_artifact_symlink_and_hardlink_rejected(self):
        import os
        file = self.artifacts/self.filename
        file.unlink(); file.symlink_to(self.path/'missing')
        with self.assertRaises(Exception): self.build()
        file.unlink(); (self.path/'context.tar').unlink(missing_ok=True)
        other = self.path/'other'; other.write_bytes(self.raw); os.link(other, file)
        with self.assertRaises(Exception): self.build()


class CustodyTests(unittest.TestCase):
    def setUp(self): self.m = importlib.import_module('offline_web_image_preparation')

    def test_control_exception_not_normalized_in_source_read(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(self.m.migration, 'read_at', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt): self.m.read_file(Path(tmp)/'file', 10)

    def test_cleanup_owner_mismatch_no_command(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.builder, 'command') as command:
            b = m.builder.Budget(m.builder.time.monotonic())
            with self.assertRaises(m.Blocked): m.cleanup(Path(tmp), (0, 0, 0), b, b.deadline)
            command.assert_not_called()

    def test_cleanup_budget_mutation_no_command(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.builder, 'command') as command:
            b = m.builder.Budget(m.builder.time.monotonic()); deadline = b.deadline; b.deadline += 1
            with self.assertRaises(m.Blocked): m.cleanup(Path(tmp), (), b, deadline)
            command.assert_not_called()


if __name__ == '__main__': unittest.main()
