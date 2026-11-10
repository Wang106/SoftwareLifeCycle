"""API-only preparation contracts. No real acquisition, Docker or database."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
if importlib.util.find_spec('offline_api_image_preparation'):
    import offline_api_image_preparation as m
else:
    m = None


class PreparationContractTests(unittest.TestCase):
    def test_internal_entrypoint_exists(self):
        self.assertIsNotNone(m)
        self.assertTrue(callable(m.prepare))

    def test_context_builder_exists(self):
        self.assertIsNotNone(m)
        self.assertTrue(callable(m.build_context))

    def test_source_binding_exists(self):
        self.assertIsNotNone(m)
        self.assertTrue(callable(m.source_inputs))

    def test_no_execution_cli(self):
        self.assertIsNotNone(m)
        self.assertFalse(hasattr(m, 'main'))

    def test_minimum_downstream_budget(self):
        self.assertIsNotNone(m)
        self.assertGreaterEqual(m.DOWNSTREAM_RESERVE, 630)

    def test_no_false_acceptance_claims(self):
        self.assertIsNotNone(m)
        value = m.receipt('a'*40, 'sha256:'+'b'*64, 'c'*64, 'd'*64)
        for key in ('application_started', 'database_connected', 'provenance_authenticated'):
            self.assertIs(value[key], False)




import hashlib
import json
import os
import runpy
import tarfile
import tempfile
import time
from unittest.mock import patch

COMMIT = 'a'*40
IMAGE = 'sha256:'+'b'*64


class SourceTests(unittest.TestCase):
    def setUp(self):
        names = m.FIXED | m.TOOLS | {'backend/app/main.py'}
        self.contents = {name: (ROOT / name).read_bytes() for name in names}
        self.objects = {hashlib.sha1(name.encode()).hexdigest(): raw for name, raw in self.contents.items()}
        self.records = b''.join(('100644 blob '+hashlib.sha1(name.encode()).hexdigest()+'\t'+name+'\0').encode()
                                for name in sorted(names))

    def git(self, fd, args, *unused):
        if args[0] == 'config': return b''
        if args[0] == 'rev-parse': return COMMIT.encode()+b'\n'
        if args[0] == 'status': return b''
        if args[0] == 'ls-tree': return self.records
        if args[0] == 'cat-file': return self.objects[args[2]]
        self.fail(args)

    def read(self, path, limit):
        return self.contents[str(Path(path).relative_to(ROOT))]

    def test_exact_source_selection_and_no_migrations_or_web(self):
        with patch.object(m.migration, 'git_read', side_effect=self.git), patch.object(m.migration, 'safe_read', side_effect=self.read):
            sources, inventory = m.source_inputs(COMMIT)
        self.assertEqual(set(sources), m.FIXED | {'backend/app/main.py'})
        self.assertEqual(len(inventory['artifacts']), 30)

    def test_checkout_filter_dirty_wrong_commit_and_tool_bytes_rejected(self):
        for mode in ('filter', 'dirty', 'commit', 'bytes'):
            with self.subTest(mode=mode):
                def git(fd, args, *rest):
                    if mode == 'filter' and args[0] == 'config': return b'filter.bad.clean\nfalse\0'
                    if mode == 'dirty' and args[0] == 'status': return b' M file\n'
                    if mode == 'commit' and args[0] == 'rev-parse': return b'f'*40
                    return self.git(fd, args, *rest)
                def read(path, limit):
                    raw = self.read(path, limit)
                    return raw+b'\n' if mode == 'bytes' else raw
                with patch.object(m.migration, 'git_read', side_effect=git), patch.object(m.migration, 'safe_read', side_effect=read):
                    with self.assertRaises(Exception): m.source_inputs(COMMIT)

    def test_missing_recipe_symlink_and_source_limit_rejected(self):
        original = self.records
        for mode in ('missing', 'symlink', 'limit'):
            with self.subTest(mode=mode):
                self.records = original.replace(b'100644', b'120000', 1) if mode == 'symlink' else original
                if mode == 'missing':
                    self.records = b'\0'.join(r for r in original.split(b'\0') if b'deploy/offline/api.Dockerfile' not in r)
                with patch.object(m.migration, 'git_read', side_effect=self.git), patch.object(m.migration, 'safe_read', side_effect=self.read), patch.object(m.migration, 'MAX_SOURCE_FILES', 1 if mode == 'limit' else 512):
                    with self.assertRaises(Exception): m.source_inputs(COMMIT)

    def test_context_paths_are_closed(self):
        for name in ('../x', 'backend/app/../x.py', 'backend/app/.secret.py', 'backend/app/key_credentials.py', 'frontend/app/x.py'):
            with self.subTest(name=name), self.assertRaises(Exception): m.context_name(name)


class ContextTests(unittest.TestCase):
    def build(self, root, *, changed=False, wrong_source=False):
        sources = {'backend/app/main.py': b'print(1)', 'deploy/offline/api.Dockerfile': b'FROM pinned'}
        wheel = b'synthetic-wheel'
        wheels = root/'wheels'; wheels.mkdir(); (wheels/'fixture.whl').write_bytes(wheel+b'changed' if changed else wheel)
        inventory = {'artifacts':[{'filename':'fixture.whl', 'sha256':m.digest(wheel), 'size_bytes':len(wheel)}]}
        expected = m.digest(m.encoded(m.source_manifest(sources)))
        with patch.object(m, 'source_inputs', return_value=(sources, inventory)), patch.object(m.wheels, 'verify_artifacts') as verify:
            result = m.build_context(COMMIT, wheels, root/'api.tar', 'f'*64 if wrong_source else expected)
        verify.assert_called_once()
        return result

    def test_sealed_api_tar_contains_exact_members_and_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); result = self.build(root)
            self.assertEqual(result['build_context_sha256'], m.digest((root/'api.tar').read_bytes()))
            with tarfile.open(root/'api.tar') as archive:
                self.assertEqual(set(archive.getnames()), {'app/main.py','Dockerfile','wheels/fixture.whl','api-build-context.json'})
                self.assertTrue(all(v.isfile() for v in archive.getmembers()))
                manifest = archive.extractfile('api-build-context.json').read()
                self.assertEqual(result['context_manifest_sha256'], m.digest(manifest))

    def test_context_rejects_changed_source_or_wheel(self):
        for key in ('changed', 'wrong_source'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as td, self.assertRaises(Exception):
                self.build(Path(td), **{key:True})

    def test_context_never_overwrites_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'api.tar').write_bytes(b'old')
            with self.assertRaises(FileExistsError): self.build(root)
            self.assertEqual((root/'api.tar').read_bytes(), b'old')


class LifecycleTests(unittest.TestCase):
    def execute(self, mode=None, expected_error=BaseException):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'run'; budget=m.builder.Budget(time.monotonic()); initial=budget.deadline
            calls=[]; archive_bytes=b'sealed-test-archive'; build_digest=m.digest(archive_bytes)
            source={'inventory':{'artifacts':[{}]*30}, 'source_manifest_sha256':'c'*64}
            context={'source_commit':COMMIT, 'source_manifest_sha256':'c'*64,
                     'context_manifest_sha256':'d'*64, 'build_context_sha256':build_digest}
            def command(args, **kwargs):
                calls.append((args, kwargs))
                self.assertGreater(kwargs['timeout'], 0)
                self.assertLessEqual(kwargs['timeout'], budget.deadline-time.monotonic()-m.DOWNSTREAM_RESERVE-29)
                if args[0] == sys.executable:
                    if 's,i=m.source_inputs' in args[4]:
                        value=dict(source)
                        if mode == 'source_receipt': value['source_manifest_sha256']='bad'
                        return 0,json.dumps(value).encode()
                    (root/'api-context.tar').write_bytes(archive_bytes)
                    value=dict(context)
                    if mode == 'context_receipt': value['source_commit']='f'*40
                    if mode == 'archive_changed': (root/'api-context.tar').write_bytes(b'changed')
                    if mode == 'iid_collision': (root/'api.iid').write_text(IMAGE)
                    return 0,json.dumps(value).encode()
                action=args[1:]
                if action[0] == 'pull':
                    if mode == 'pull_failure': return 2,b''
                    return 0,b''
                if action[:2] == ['image','inspect']:
                    if action[2] == m.migration.BASE:
                        return 0,json.dumps([{'Id':'bad' if mode == 'base' else m.migration.BASE_CONFIG,
                                             'Os':'linux','Architecture':'amd64'}]).encode()
                    if mode == 'image_failure': return 2,b''
                    return 0,b'[]'
                if action[0] == 'build':
                    self.assertEqual(kwargs['stdin'].read(), archive_bytes)
                    self.assertIn('--network=none', action)
                    self.assertNotIn('--tag', action)
                    if mode == 'interrupt': raise KeyboardInterrupt()
                    if mode == 'build_failure': return 2,b''
                    if mode == 'budget_changed': budget.deadline+=1
                    if mode == 'post_changed': (root/'api-context.tar').write_bytes(b'changed')
                    if mode != 'missing_iid': (root/'api.iid').write_text('bad' if mode == 'bad_iid' else IMAGE+'\n')
                    return 0,b''
                self.fail(action)
            original_read_at=m.migration.read_at
            def read_at(fd,name,limit):
                if name == 'api.iid' and mode in ('iid_keyboard','iid_exit'):
                    raise (KeyboardInterrupt if mode == 'iid_keyboard' else SystemExit)('stop')
                return original_read_at(fd,name,limit)
            with patch.object(m.migration,'read_at',side_effect=read_at), patch.object(m.builder, 'command', side_effect=command), patch.object(m.builder, 'host', return_value=(['docker'], {})) as host, patch.object(m.builder, 'acquire_child') as acquire, patch.object(m.startup, 'verify_image') as verify:
                if mode:
                    with self.assertRaises(expected_error): m.prepare(COMMIT, root=root, budget=budget)
                else:
                    result=m.prepare(COMMIT, root=root, budget=budget)
                    self.assertEqual(result['image_id'], IMAGE)
                    self.assertEqual(budget.deadline, initial)
                    verify.assert_called_once_with(b'[]', IMAGE, COMMIT)
                    host.assert_called_once()
                    self.assertEqual(host.call_args.args[0],root)
                    self.assertIsInstance(host.call_args.args[1],m._HostBudget)
                    acquire.assert_called_once()
            operations=[args[1] for args,_ in calls if args[0]=='docker']
            self.assertLessEqual(operations.count('build'),1)
            self.assertLessEqual(operations.count('pull'),1)
            self.assertTrue(set(operations) <= {'pull','image','build'})
            return operations

    def test_full_mock_path_builds_only_api(self):
        self.assertEqual(self.execute(), ['pull','image','build','image'])

    def test_fail_closed_without_retries(self):
        for mode in ('source_receipt','context_receipt','archive_changed','iid_collision','pull_failure',
                     'base','image_failure','build_failure','interrupt','budget_changed','post_changed','missing_iid','bad_iid'):
            with self.subTest(mode=mode): self.execute(mode)

    def test_iid_interrupts_escape_full_preparation(self):
        self.execute('iid_keyboard',expected_error=KeyboardInterrupt)
        self.execute('iid_exit',expected_error=SystemExit)

    def test_insufficient_original_budget_before_side_effects(self):
        budget=m.builder.Budget(time.monotonic()-3000)
        with tempfile.TemporaryDirectory() as td, patch.object(m.builder,'command') as command:
            root=Path(td)/'run'
            with self.assertRaises(Exception): m.prepare(COMMIT,root=root,budget=budget)
            self.assertFalse(root.exists()); command.assert_not_called()

    def test_collision_before_commands(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m.builder,'command') as command:
            with self.assertRaises(Exception): m.prepare(COMMIT,root=td,budget=m.builder.Budget(time.monotonic()))
            command.assert_not_called()

    def test_no_budget_creation_or_cli_activation(self):
        with patch.object(m.builder,'command') as command, patch.object(m.builder.Budget,'from_environment') as budget:
            runpy.run_path(str(ROOT/'scripts/offline_api_image_preparation.py'),run_name='__main__')
            command.assert_not_called(); budget.assert_not_called()


class DirectExecutionTests(unittest.TestCase):
    def test_main_guard_follows_every_test_class(self):
        import ast
        tree=ast.parse(Path(__file__).read_text())
        guards=[i for i,node in enumerate(tree.body) if isinstance(node,ast.If)
                and '__name__' in ast.unparse(node.test)]
        classes=[i for i,node in enumerate(tree.body) if isinstance(node,ast.ClassDef)]
        self.assertEqual(len(guards),1)
        self.assertGreater(guards[0],max(classes))


class ReviewRegressionTests(unittest.TestCase):
    def test_real_host_adapter_retains_downstream_reserve(self):
        class StopHost(Exception): pass
        observed=[]
        source={'inventory':{'artifacts':[{}]*30},'source_manifest_sha256':'c'*64}
        def command(args, **kwargs):
            if args[0] == sys.executable: return 0,json.dumps(source).encode()
            observed.append(kwargs['timeout'])
            raise StopHost()
        with tempfile.TemporaryDirectory() as td, patch.object(m.builder.time,'monotonic',return_value=1000):
            budget=m.builder.Budget(1000)
            with patch.object(m.builder.time,'monotonic',return_value=3639), patch.object(m.builder.sys,'version_info',(3,12,0)), patch.object(m.builder.platform,'machine',return_value='x86_64'), patch.object(m.builder.shutil,'which',return_value='/usr/bin/docker'), patch.object(m.builder.shutil,'disk_usage',return_value=type('Disk',(),{'free':30*1024**3})()), patch.object(m.builder.fetcher,'reject_inherited_proxy'), patch.dict(os.environ,{},clear=True), patch.object(m.builder,'command',side_effect=command):
                with self.assertRaises(StopHost): m.prepare(COMMIT,root=Path(td)/'run',budget=budget)
            self.assertEqual(budget.deadline,4300)
        self.assertEqual(observed,[1])

    def test_iid_reader_preserves_control_exceptions(self):
        for error in (KeyboardInterrupt,SystemExit):
            with self.subTest(error=error.__name__), tempfile.TemporaryDirectory() as td:
                path=Path(td)/'api.iid'; path.write_text(IMAGE)
                with patch.object(m.migration,'read_at',side_effect=error('stop')):
                    with self.assertRaises(error): m.read_iid(path)

    def test_iid_reader_exact_bounds_and_regular_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); path=root/'api.iid'
            for raw in (IMAGE.encode(),(IMAGE+'\n').encode()):
                path.write_bytes(raw)
                self.assertEqual(m.read_iid(path),raw)
            path.write_bytes(b'x'*73)
            with self.assertRaises(Exception): m.read_iid(path)
            path.unlink(); path.symlink_to(root/'other')
            with self.assertRaises(Exception): m.read_iid(path)
            path.unlink(); path.mkdir()
            with self.assertRaises(Exception): m.read_iid(path)

    def test_iid_reader_ordinary_read_errors_stay_blocked(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m.migration,'read_at',side_effect=OSError('private detail')):
            with self.assertRaises(m.migration.Blocked) as caught:
                m.read_iid(Path(td)/'api.iid')
            self.assertNotIn('private detail',str(caught.exception))


if __name__ == '__main__':
    unittest.main()
