"""Static/mocked packaging contracts; these tests never run Docker or download."""
import copy
import hashlib
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_image_rehearsal as rehearsal


class ImageRehearsalTests(unittest.TestCase):
    def test_base_pins_are_official_platform_manifests(self):
        data = rehearsal.load_bases(ROOT)
        self.assertEqual(set(data['images']), {'api', 'web'})
        for role, base in data['images'].items():
            recipe = (ROOT / f'deploy/offline/{role}.Dockerfile').read_text()
            self.assertIn('FROM ' + base['reference'], recipe)
            self.assertEqual(base['platform'], 'linux/amd64')
            self.assertNotEqual(base['manifest_digest'], base['index_digest'])

    def test_base_manifest_rejects_unpinned_or_unofficial(self):
        original = json.loads((ROOT / 'deploy/offline/base-images.json').read_text())
        for value in ['python:latest', 'example.org/python@sha256:' + 'a' * 64,
                      'docker.io/library/python@sha256:' + 'A' * 64]:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'deploy/offline').mkdir(parents=True)
                data = copy.deepcopy(original)
                data['images']['api']['reference'] = value
                (root / 'deploy/offline/base-images.json').write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    rehearsal.load_bases(root)

    def test_source_allowlist(self):
        for name in ['backend/app/main.py', 'frontend/app/page.tsx', 'frontend/lib/api.ts',
                     'frontend/components/Badge.tsx', 'frontend/package-lock.json']:
            self.assertTrue(rehearsal.source_allowed(name), name)
        for name in ['.env', 'backend/.env', 'backend/app/.env', 'frontend/.npmrc',
                     'frontend/app/secrets.json', 'frontend/node_modules/x.js',
                     'backend/entrypoint.sh', 'backend/alembic/env.py',
                     'frontend/tests/example.ts', 'frontend/component-browser/test.ts',
                     'frontend/app/../secret.ts', 'frontend/app/auth.json',
                     'backend/app/key.pem', 'frontend/app/.hidden.ts']:
            self.assertFalse(rehearsal.source_allowed(name), name)

    def test_recipes_preserve_runtime_contract_and_no_baked_settings(self):
        for role in ('api', 'web'):
            text = (ROOT / f'deploy/offline/{role}.Dockerfile').read_text()
            self.assertIn('USER 65532:65532', text)
            self.assertIn('WORKDIR /app', text)
            self.assertIn('org.opencontainers.image.revision', text)
            for instruction in ('ENV ', 'VOLUME ', 'ADD ', 'COPY . ', '--network=none'):
                self.assertFalse(any(line.startswith(instruction) for line in text.splitlines()), instruction)
            self.assertNotIn('apt-get', text)
            self.assertNotIn('curl ', text)
        api = (ROOT / 'deploy/offline/api.Dockerfile').read_text()
        self.assertIn('--no-index', api)
        self.assertIn('--require-hashes', api)
        self.assertNotIn('--no-deps', api)
        self.assertNotIn('entrypoint.sh', api)
        web = (ROOT / 'deploy/offline/web.Dockerfile').read_text()
        self.assertIn('npm ci --offline', web)
        self.assertIn('npm run build', web)
        self.assertIn('COPY --from=build /app/node_modules', web)
        self.assertNotIn('npm ci --offline --ignore-scripts', web)

    def test_host_rejects_wrong_platform_old_compose_and_space(self):
        good = {'OSType': 'linux', 'Architecture': 'x86_64', 'DockerRootDir': '/var/lib/docker'}
        for info, version, free in [(dict(good, Architecture='aarch64'), '2.30.0', 50 * 1024**3),
                                    (dict(good, OSType='windows'), '2.30.0', 50 * 1024**3),
                                    (good, '2.29.9', 50 * 1024**3),
                                    (good, '2.30.0', 1024**3)]:
            with self.subTest(info=info, version=version, free=free):
                with self.assertRaises(ValueError):
                    rehearsal.validate_host(info, version, free, free)
        rehearsal.validate_host(good, 'v2.30.0', 50 * 1024**3, 50 * 1024**3)

    def test_host_probe_failure_stops_before_acquisition(self):
        with patch.object(rehearsal, 'check_host', side_effect=ValueError('not available')), \
             patch.object(rehearsal, 'acquire') as acquire:
            with self.assertRaises(ValueError):
                rehearsal.run(ROOT)
            acquire.assert_not_called()

    @patch.dict(rehearsal.os.environ, {}, clear=True)
    def test_download_hash_size_and_no_overwrite(self):
        raw = b'local synthetic bytes'
        item = {'filename': 'test.whl', 'url': 'https://files.pythonhosted.org/packages/test.whl',
                'size_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        class Response(io.BytesIO):
            status = 200
            url = item['url']
        class Opener:
            def open(self, request, timeout):
                return Response(raw)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            rehearsal.fetch(item, path, 'sha256', Opener())
            self.assertEqual((path / item['filename']).read_bytes(), raw)
            with self.assertRaises(FileExistsError):
                rehearsal.fetch(item, path, 'sha256', Opener())
        for change in ({'sha256': '0' * 64}, {'size_bytes': len(raw) + 1}, {'size_bytes': 1}):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(change=change):
                with self.assertRaises(ValueError):
                    rehearsal.fetch({**item, **change}, Path(tmp), 'sha256', Opener())

    def test_download_redirect_refused(self):
        with self.assertRaises(ValueError):
            rehearsal.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example/')

    def test_smoke_has_readonly_nonroot_and_no_app_start(self):
        for role in ('api', 'web'):
            command = rehearsal.smoke_command(role, 'sha256:' + 'a' * 64, Path('/tmp/synthetic.cid'))
            self.assertIn('--read-only', command)
            self.assertIn('65532:65532', command)
            self.assertIn('/tmp:rw,noexec,nosuid,size=64m', command)
            self.assertNotIn('--network=none', command)
            self.assertNotIn('app.main', ' '.join(command))
            self.assertNotIn('uvicorn app', ' '.join(command))
            self.assertNotIn('next start', ' '.join(command))

    def test_docker_save_is_checked_by_original_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'api.tar').write_bytes(b'not a valid tar')
            with patch.object(rehearsal, 'command', return_value=b''), \
                 patch.object(rehearsal, 'image_id', return_value='sha256:' + 'a' * 64), \
                 patch.object(rehearsal.preflight, 'archive_image', side_effect=ValueError('format')) as check:
                with self.assertRaises(ValueError):
                    rehearsal.export_image('api', 'a' * 40, root)
                self.assertEqual(check.call_count, 1)

    def test_compose_parse_only_never_operator_approval(self):
        manifest = {'images': {role: {'image_id': 'sha256:' + ('a' if role == 'api' else 'b') * 64}
                               for role in ('api', 'web')}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(rehearsal.preflight, 'validate', side_effect=AssertionError('operator approval')), \
                 patch.object(rehearsal, 'command') as command:
                command.side_effect = lambda cmd, **kw: json.dumps(
                    rehearsal.preflight.compose(manifest, root / 'database.env')).encode()
                rehearsal.parse_compose(manifest, root)
                self.assertEqual((root / 'database.env').read_bytes(), b'')
                args = command.call_args.args[0]
                self.assertEqual(args[:2], ['docker', 'compose'])
                self.assertIn('config', args)
                self.assertNotIn('up', args)
                self.assertFalse((root / 'operator.json').exists())

    def test_compose_effective_changes_fail(self):
        manifest = {'images': {role: {'image_id': 'sha256:' + 'a' * 64} for role in ('api', 'web')}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual = rehearsal.preflight.compose(manifest, root / 'database.env')
            actual['services']['web']['read_only'] = False
            with patch.object(rehearsal, 'command', return_value=json.dumps(actual).encode()):
                with self.assertRaises(ValueError):
                    rehearsal.parse_compose(manifest, root)

    def test_workflow_is_manual_standard_readonly_and_bounded(self):
        text = (ROOT / '.github/workflows/offline-image-rehearsal.yml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('contents: read', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('timeout-minutes:', text)
        self.assertIn('cancel-in-progress: false', text)
        for forbidden in ['pull_request:', 'push:', 'schedule:', 'upload-artifact', 'actions/cache',
                          'secrets.', 'setup-docker', 'sudo ', 'docker/login-action']:
            self.assertNotIn(forbidden, text)
        self.assertLess(text.index('Check existing host prerequisites'), text.index('actions/checkout@'))

    def test_python_native_smoke_cannot_silently_use_python_fallbacks(self):
        for name in ('psycopg_binary._psycopg', 'pydantic_core._pydantic_core',
                     'yaml._yaml', 'markupsafe._speedups', 'websockets.speedups',
                     'greenlet._greenlet', 'httptools.parser.parser', 'uvloop.loop',
                     'watchfiles._rust_notify', 'sqlalchemy.cyextension.collections'):
            self.assertIn(name, rehearsal.PYTHON_SMOKE)

    def test_native_smoke_uses_installed_workerd_export(self):
        self.assertIn("require('workerd').default", rehearsal.NODE_SMOKE)
        self.assertNotIn("require('workerd').workerd", rehearsal.NODE_SMOKE)

    def test_sources_reject_dotenv_and_sensitive_named_files(self):
        for name in ('frontend/app/npmrc', 'frontend/app/secret.json',
                     'frontend/lib/credentials.ts', 'backend/app/token.key',
                     'backend/app/.env.production', 'backend/app/auth.json'):
            self.assertFalse(rehearsal.source_allowed(name), name)

    def test_host_commands_use_explicit_default_local_context(self):
        with patch.object(rehearsal.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'ok', b'')) as run:
            rehearsal.command(['docker', 'version'])
            self.assertEqual(run.call_args.kwargs['env']['DOCKER_CONTEXT'], 'default')

    def test_snapshot_rejects_dirty_checkout_before_reading_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rehearsal, 'command', return_value=b' M app.py') as run:
            with self.assertRaises(ValueError):
                rehearsal.snapshot(ROOT, Path(tmp))
            self.assertEqual(run.call_count, 1)

    def test_snapshot_rejects_tracked_symlink(self):
        results = [b'', b'a' * 40, b'120000 blob deadbeef\tfrontend/app/page.tsx\0']
        with tempfile.TemporaryDirectory() as tmp, patch.object(rehearsal, 'command', side_effect=results):
            with self.assertRaises(ValueError):
                rehearsal.snapshot(ROOT, Path(tmp))

    def test_snapshot_reads_commit_not_working_copy(self):
        names = sorted(rehearsal.SOURCE_FILES | rehearsal.TOOLS | {
            'backend/app/main.py', 'frontend/app/page.tsx',
            'frontend/components/Button.tsx', 'frontend/lib/api.ts'})
        tree = b''.join(b'100644 blob deadbeef\t' + name.encode() + b'\0' for name in names)
        def git(cmd, **kwargs):
            if cmd[1] == 'status': return b''
            if cmd[1] == 'rev-parse': return b'a' * 40
            if cmd[1] == 'ls-tree': return tree
            self.assertEqual(cmd[:2], ['git', 'show'])
            self.assertTrue(cmd[2].startswith('a' * 40 + ':'))
            return b'trusted commit bytes'
        with tempfile.TemporaryDirectory() as tmp, patch.object(rehearsal, 'command', side_effect=git):
            target = Path(tmp)
            commit, hashes = rehearsal.snapshot(ROOT, target)
            self.assertEqual(commit, 'a' * 40)
            self.assertEqual(set(hashes), set(names))
            self.assertEqual((target / 'frontend/app/page.tsx').read_bytes(), b'trusted commit bytes')

    @patch.dict(rehearsal.os.environ, {}, clear=True)
    def test_acquisition_checks_reviewed_lock_before_any_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'backend').mkdir()
            (root / 'backend/requirements.txt').write_bytes((ROOT / 'backend/requirements.txt').read_bytes())
            (root / 'backend/offline-python-wheelhouse.json').write_bytes((ROOT / 'backend/offline-python-wheelhouse.json').read_bytes())
            (root / 'backend/requirements-linux-cp312.lock').write_text('changed')
            with patch.object(rehearsal, 'fetch') as fetch:
                with self.assertRaises(ValueError):
                    rehearsal.acquire(root, root, root)
                fetch.assert_not_called()

    def test_export_never_converts_format_and_preserves_size_hash(self):
        raw = b'synthetic archive bytes'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def save(cmd, **kwargs):
                self.assertEqual(cmd[:3], ['docker', 'image', 'save'])
                (root / 'web.tar').write_bytes(raw)
                return b''
            with patch.object(rehearsal, 'command', side_effect=save) as command, \
                 patch.object(rehearsal, 'image_id', return_value='sha256:' + 'b' * 64), \
                 patch.object(rehearsal.preflight, 'archive_image') as check:
                result = rehearsal.export_image('web', 'a' * 40, root)
                self.assertEqual(result['size'], len(raw))
                self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(command.call_count, 1)
                check.assert_called_once_with(root / 'web.tar', result, 'a' * 40)

    def test_public_result_only_after_all_stages(self):
        source = (ROOT / 'scripts/offline_image_rehearsal.py').read_text()
        self.assertLess(source.index("compose = parse_compose(manifest, run_dir)"),
                        source.index("'status': 'IMAGE_REHEARSAL_PASSED_NOT_OFFLINE_ACCEPTANCE'"))
        self.assertNotIn('preflight.validate(', source)
        self.assertNotIn('docker-compose', source)
        self.assertNotIn("'up'", source)

    def test_image_defaults_fail_closed_without_starting_app(self):
        for role in ('api', 'web'):
            text = (ROOT / f'deploy/offline/{role}.Dockerfile').read_text()
            entry = [line for line in text.splitlines() if line.startswith('ENTRYPOINT ')][-1]
            default = [line for line in text.splitlines() if line.startswith('CMD ')][-1]
            self.assertEqual(json.loads(entry.removeprefix('ENTRYPOINT ')), ['/bin/false'])
            self.assertEqual(json.loads(default.removeprefix('CMD ')), [])

    def test_proxy_overrides_block_before_network_or_output_file(self):
        item = {'filename': 'example.whl', 'url': 'https://files.pythonhosted.org/packages/example.whl',
                'size_bytes': 1, 'sha256': 'a' * 64}
        for name in ('HTTP_PROXY', 'https_proxy', 'ALL_PROXY', 'No_PrOxY', 'ftp_proxy'):
            for value in ('http://SECRET_USER:SECRET_PASSWORD@proxy.example', ''):
                with self.subTest(name=name, empty=not value), tempfile.TemporaryDirectory() as tmp, \
                     patch.dict(rehearsal.os.environ, {name: value}, clear=True), \
                     patch.object(rehearsal.urllib.request, 'build_opener') as opener:
                    with self.assertRaises(ValueError):
                        rehearsal.fetch(item, Path(tmp), 'sha256')
                    opener.assert_not_called()
                    self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_proxy_failure_is_explicit_and_does_not_echo_credentials(self):
        with patch.object(rehearsal, 'run', side_effect=rehearsal.ProxyBlocked('SECRET_SENTINEL')), \
             patch('sys.stderr', new_callable=io.StringIO) as err, \
             patch('sys.stdout', new_callable=io.StringIO) as out:
            self.assertEqual(rehearsal.main(['--run']), 2)
            self.assertIn('inherited proxy configuration', err.getvalue())
            self.assertNotIn('SECRET_SENTINEL', err.getvalue())
            self.assertEqual(out.getvalue(), '')

    def smoke_simulation(self, target, failure=None, cleanup_failure=False, cid='c' * 64):
        calls = []
        def docker(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ['docker', 'create']:
                Path(cmd[cmd.index('--cidfile') + 1]).write_text(cid + '\n')
                return (cid + '\n').encode()
            if cmd[:3] == ['docker', 'start', '--attach']:
                if failure is not None:
                    raise failure
                return b'native smoke passed'
            if cmd[:3] == ['docker', 'container', 'inspect']:
                return b'0\n'
            if cmd[:4] == ['docker', 'container', 'rm', '--force']:
                if cleanup_failure:
                    raise ValueError('cleanup failed')
                return (cid + '\n').encode()
            raise AssertionError('unexpected Docker operation')
        return calls, docker

    def test_smoke_records_cid_before_start_and_removes_only_that_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls, docker = self.smoke_simulation(root)
            with patch.object(rehearsal, 'command', side_effect=docker):
                self.assertEqual(rehearsal.smoke('api', 'sha256:' + 'a' * 64, root), b'native smoke passed')
            self.assertEqual(calls[-1], ['docker', 'container', 'rm', '--force', 'c' * 64])
            self.assertEqual(calls[1], ['docker', 'start', '--attach', 'c' * 64])
            self.assertEqual(len(list(root.glob('*/container.cid'))), 1)
            self.assertNotIn('--rm', calls[0])
            self.assertFalse(any('prune' in cmd for cmd in calls))

    def test_smoke_timeout_or_failure_still_removes_exact_cid(self):
        failures = [subprocess.TimeoutExpired(['docker', 'start'], 120), ValueError('smoke failed')]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                calls, docker = self.smoke_simulation(root, failure=failure)
                with patch.object(rehearsal, 'command', side_effect=docker):
                    with self.assertRaises(type(failure)):
                        rehearsal.smoke('web', 'sha256:' + 'a' * 64, root)
                self.assertEqual(calls[-1], ['docker', 'container', 'rm', '--force', 'c' * 64])

    def test_smoke_nonzero_container_exit_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls, docker = self.smoke_simulation(root)
            def fail_inspect(cmd, **kwargs):
                return b'7\n' if cmd[:3] == ['docker', 'container', 'inspect'] else docker(cmd, **kwargs)
            with patch.object(rehearsal, 'command', side_effect=fail_inspect):
                with self.assertRaises(ValueError):
                    rehearsal.smoke('web', 'sha256:' + 'a' * 64, root)
            self.assertEqual(calls[-1], ['docker', 'container', 'rm', '--force', 'c' * 64])

    def test_smoke_cleanup_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls, docker = self.smoke_simulation(root, cleanup_failure=True)
            with patch.object(rehearsal, 'command', side_effect=docker):
                with self.assertRaises(rehearsal.CleanupUnconfirmed):
                    rehearsal.smoke('api', 'sha256:' + 'a' * 64, root)
            self.assertEqual(calls[-1], ['docker', 'container', 'rm', '--force', 'c' * 64])

    def test_invalid_or_missing_cid_does_not_delete_an_unidentified_container(self):
        for cid in ('short', ''):
            with self.subTest(cid=cid), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                calls, docker = self.smoke_simulation(root, cid=cid)
                with patch.object(rehearsal, 'command', side_effect=docker):
                    with self.assertRaises(rehearsal.CleanupUnconfirmed):
                        rehearsal.smoke('api', 'sha256:' + 'a' * 64, root)
                self.assertEqual(len(calls), 1)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(rehearsal, 'command', side_effect=subprocess.TimeoutExpired(['docker', 'create'], 120)) as command:
            with self.assertRaises(rehearsal.CleanupUnconfirmed):
                rehearsal.smoke('api', 'sha256:' + 'a' * 64, Path(tmp))
            self.assertEqual(command.call_count, 1)

    def test_cleanup_failure_has_explicit_safe_diagnostic(self):
        with patch.object(rehearsal, 'run', side_effect=rehearsal.CleanupUnconfirmed('SECRET_SENTINEL')), \
             patch('sys.stderr', new_callable=io.StringIO) as err, \
             patch('sys.stdout', new_callable=io.StringIO) as out:
            self.assertEqual(rehearsal.main(['--run']), 2)
            self.assertIn('container cleanup failed or unconfirmed', err.getvalue())
            self.assertNotIn('SECRET_SENTINEL', err.getvalue())
            self.assertEqual(out.getvalue(), '')

    def test_safe_error_does_not_echo_raw_exception(self):
        with patch.object(rehearsal, 'check_host', side_effect=ValueError('SECRET_SENTINEL')), \
             patch('sys.stderr', new_callable=io.StringIO) as err:
            self.assertEqual(rehearsal.main(['--check-host']), 2)
            self.assertNotIn('SECRET_SENTINEL', err.getvalue())
            self.assertIn('BLOCKED', err.getvalue())


class ExportDiagnosticTests(unittest.TestCase):
    SENTINEL = 'PRIVATE_SENTINEL_password_url_path'
    COMMIT = 'a' * 40

    def archive(self, *, extra=None, config_change=None, manifest_bytes=None, layer_bytes=None,
                sources=False, source_change=None, layer_transform=None):
        layer = b'synthetic layer bytes'
        if sources:
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode='w') as archive:
                info = tarfile.TarInfo('synthetic')
                info.size = len(layer)
                archive.addfile(info, io.BytesIO(layer))
            layer = payload.getvalue()
        if layer_transform:
            layer = layer_transform(layer)
        config = {'os': 'linux', 'architecture': 'amd64',
                  'config': {'Labels': {'org.opencontainers.image.revision': self.COMMIT},
                             'Env': ['PATH=/usr/local/bin:/usr/bin:/bin']},
                  'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + hashlib.sha256(layer).hexdigest()]}}
        if config_change:
            config['config'].update(config_change)
        config_raw = json.dumps(config).encode()
        identity = 'sha256:' + hashlib.sha256(config_raw).hexdigest()
        config_name, layer_name = 'config.json', 'layer.tar'
        if sources:
            config_name = 'blobs/sha256/' + identity[7:]
            layer_name = 'blobs/sha256/' + hashlib.sha256(layer).hexdigest()
        manifest = {'Config': config_name, 'RepoTags': None, 'Layers': [layer_name]}
        if sources:
            diff_id = config['rootfs']['diff_ids'][0]
            manifest['LayerSources'] = {diff_id: {'mediaType': 'application/vnd.oci.image.layer.v1.tar',
                                                'digest': diff_id, 'size': len(layer)}}
            if source_change:
                source_change(manifest['LayerSources'], diff_id)
        manifest.update(extra or {})
        members = [(config_name, config_raw),
                   ('manifest.json', manifest_bytes if manifest_bytes is not None else json.dumps([manifest]).encode()),
                   (layer_name, layer if layer_bytes is None else layer_bytes)]
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w') as archive:
            for name, raw in members:
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
        return output.getvalue(), identity

    def export_cli(self, raw=None, identity=None, *, inspect_error=None, save_error=None, role='api'):
        if raw is None:
            raw, identity = self.archive()
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            def save(cmd, **kwargs):
                calls.append(cmd)
                self.assertEqual(cmd[:3], ['docker', 'image', 'save'])
                if save_error is not None:
                    raise save_error
                Path(cmd[cmd.index('--output') + 1]).write_bytes(raw)
                return b''
            with patch.object(rehearsal, 'image_id', return_value=identity, side_effect=inspect_error), \
                 patch.object(rehearsal, 'command', side_effect=save), \
                 patch.object(rehearsal, 'run', side_effect=lambda: rehearsal.export_image(role, self.COMMIT, target)), \
                 patch('sys.stdout', new_callable=io.StringIO) as out, \
                 patch('sys.stderr', new_callable=io.StringIO) as err:
                code = rehearsal.main(['--run'])
                return code, out.getvalue(), err.getvalue(), calls

    def assert_code(self, result, expected):
        code, out, err, _calls = result
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('code=' + expected + ';', err)
        self.assertNotIn(self.SENTINEL, err)

    def test_real_valid_synthetic_archive_still_passes_unchanged_gate(self):
        code, out, err, calls = self.export_cli()
        self.assertEqual(code, 0)
        self.assertEqual(err, '')
        self.assertEqual(json.loads(out)['source_commit'], self.COMMIT)
        self.assertEqual(len(calls), 1)

    def test_unreviewed_layersources_mapping_is_still_rejected_without_disclosure(self):
        raw, identity = self.archive(sources=True, extra={'LayerSources': {self.SENTINEL: {'urls': [self.SENTINEL]}}})
        self.assert_code(self.export_cli(raw, identity), 'ARCHIVE_LAYER_SOURCES_MAPPING_REJECTED')

    def test_verified_classic_sources_passes_real_gate_once_without_rewriting(self):
        raw, identity = self.archive(sources=True)
        original = rehearsal.preflight.archive_image
        def verify(path, item, commit):
            self.assertEqual(path.read_bytes(), raw)
            return original(path, item, commit)
        with patch.object(rehearsal.preflight, 'archive_image', side_effect=verify) as gate:
            result = self.export_cli(raw, identity)
            self.assertEqual(result[0], 0)
            self.assertEqual(result[2], '')
            self.assertEqual(len(result[3]), 1)
            gate.assert_called_once()

    def test_manifest_structure_diagnostics_do_not_assume_layersources(self):
        cases = (([None], 'ARCHIVE_MANIFEST_RECORD_REJECTED'),
                 ([{'Config': self.SENTINEL}], 'ARCHIVE_MANIFEST_FIELDS_MISSING'),
                 ([{'Config': self.SENTINEL, 'RepoTags': [], 'Layers': [], self.SENTINEL: 1}],
                  'ARCHIVE_MANIFEST_FIELDS_REJECTED'))
        for manifest, code in cases:
            with self.subTest(code=code):
                raw, identity = self.archive(manifest_bytes=json.dumps(manifest).encode())
                self.assert_code(self.export_cli(raw, identity), code)

    def test_source_descriptor_diagnostics_are_fixed_and_redacted(self):
        cases = (({'urls': [self.SENTINEL]}, 'ARCHIVE_LAYER_SOURCE_FIELDS_REJECTED'),
                 ({'annotations': {self.SENTINEL: self.SENTINEL}}, 'ARCHIVE_LAYER_SOURCE_FIELDS_REJECTED'),
                 ({'mediaType': self.SENTINEL}, 'ARCHIVE_LAYER_SOURCE_MEDIA_TYPE_REJECTED'),
                 ({'digest': self.SENTINEL}, 'ARCHIVE_LAYER_SOURCE_DIGEST_MISMATCH'),
                 ({'size': self.SENTINEL}, 'ARCHIVE_LAYER_SOURCE_SIZE_MISMATCH'))
        for change, code in cases:
            with self.subTest(code=code):
                raw, identity = self.archive(sources=True, source_change=lambda src, key: src[key].update(change))
                self.assert_code(self.export_cli(raw, identity, role='web'), code)

    def test_actual_compressed_layer_cannot_pass_with_consistent_uncompressed_claim(self):
        raw, identity = self.archive(sources=True, layer_transform=gzip.compress)
        self.assert_code(self.export_cli(raw, identity), 'ARCHIVE_LAYER_SOURCE_TAR_REJECTED')

    def test_inner_numeric_parser_overflow_has_fixed_tar_code(self):
        def oversized(_raw):
            info = tarfile.TarInfo(self.SENTINEL)
            info.type = tarfile.XHDTYPE
            info.size = 2**80
            return info.tobuf(format=tarfile.GNU_FORMAT) + b'\0' * 1024
        raw, identity = self.archive(sources=True, layer_transform=oversized)
        self.assert_code(self.export_cli(raw, identity), 'ARCHIVE_LAYER_SOURCE_TAR_REJECTED')

    def test_sources_blob_path_diagnostic_hides_path_and_preserves_role(self):
        raw, identity = self.archive(sources=True, extra={'Config': self.SENTINEL})
        result = self.export_cli(raw, identity, role='web')
        self.assert_code(result, 'ARCHIVE_LAYER_SOURCES_PATH_REJECTED')
        self.assertIn('role=web;', result[2])

    def test_actual_environment_and_layer_digest_rejections_are_distinct(self):
        raw, identity = self.archive(config_change={'Env': ['DATABASE_URL=' + self.SENTINEL]})
        self.assert_code(self.export_cli(raw, identity), 'ARCHIVE_ENV_REJECTED')
        raw, identity = self.archive(layer_bytes=self.SENTINEL.encode())
        self.assert_code(self.export_cli(raw, identity), 'ARCHIVE_LAYER_DIGEST_MISMATCH')

    def test_invalid_tar_and_json_are_hidden_behind_fixed_codes(self):
        self.assert_code(self.export_cli(self.SENTINEL.encode(), 'sha256:' + 'a' * 64), 'ARCHIVE_TAR_INVALID')
        raw, identity = self.archive(manifest_bytes=('{' + self.SENTINEL).encode())
        self.assert_code(self.export_cli(raw, identity), 'ARCHIVE_JSON_INVALID')

    def test_inspect_failure_does_not_attempt_save_or_archive_validation(self):
        for error, code in [(rehearsal.preflight.Invalid('command failed'), 'IMAGE_INSPECT_FAILED'),
                            (subprocess.TimeoutExpired(['docker', self.SENTINEL], 120), 'IMAGE_INSPECT_TIMEOUT'),
                            (RuntimeError(self.SENTINEL), 'IMAGE_INSPECT_ERROR')]:
            with self.subTest(code=code), patch.object(rehearsal.preflight, 'archive_image') as validate:
                result = self.export_cli(inspect_error=error)
                self.assert_code(result, code)
                self.assertEqual(result[3], [])
                validate.assert_not_called()

    def test_save_failure_or_timeout_does_not_reach_archive_validation(self):
        for error, code in [(rehearsal.preflight.Invalid('command failed'), 'SAVE_COMMAND_FAILED'),
                            (subprocess.TimeoutExpired(['docker', self.SENTINEL], 600), 'SAVE_COMMAND_TIMEOUT'),
                            (OSError(self.SENTINEL), 'SAVE_COMMAND_ERROR')]:
            with self.subTest(code=code), patch.object(rehearsal.preflight, 'archive_image') as validate:
                result = self.export_cli(save_error=error)
                self.assert_code(result, code)
                self.assertEqual(len(result[3]), 1)
                validate.assert_not_called()

    def test_hash_read_failure_is_separate_from_preflight_rejection(self):
        with patch.object(rehearsal.preflight, 'digest', side_effect=OSError(self.SENTINEL)), \
             patch.object(rehearsal.preflight, 'archive_image') as validate:
            self.assert_code(self.export_cli(), 'ARCHIVE_READ_FAILED')
            validate.assert_not_called()

    def test_each_known_preflight_reason_maps_to_a_fixed_code(self):
        for reason, code in rehearsal.ARCHIVE_REASON_CODES.items():
            with self.subTest(code=code), \
                 patch.object(rehearsal.preflight, 'archive_image', side_effect=rehearsal.preflight.Invalid(reason)):
                self.assert_code(self.export_cli(), code)

    def test_unknown_or_lookalike_preflight_errors_never_disclose_text(self):
        for error in (ValueError(self.SENTINEL), KeyError(self.SENTINEL),
                      rehearsal.preflight.Invalid('unexpected or missing fields ' + self.SENTINEL),
                      rehearsal.preflight.Invalid({'secret': self.SENTINEL})):
            with self.subTest(kind=type(error).__name__), \
                 patch.object(rehearsal.preflight, 'archive_image', side_effect=error):
                self.assert_code(self.export_cli(), 'ARCHIVE_VALIDATION_FAILED')

    def test_unknown_exception_string_method_is_not_called(self):
        class HostileError(Exception):
            def __str__(self):
                raise AssertionError('exception text must not be evaluated')
        with patch.object(rehearsal.preflight, 'archive_image', side_effect=HostileError()):
            self.assert_code(self.export_cli(), 'ARCHIVE_VALIDATION_FAILED')

    def test_export_diagnostic_keeps_allowlisted_role_without_raw_step(self):
        for role in ('api', 'web'):
            with self.subTest(role=role), patch.object(rehearsal, 'STEP', self.SENTINEL), \
                 patch.object(rehearsal.preflight, 'archive_image',
                              side_effect=rehearsal.preflight.Invalid('unexpected or missing fields')):
                result = self.export_cli(role=role)
                self.assert_code(result, 'ARCHIVE_FIELDS_REJECTED')
                self.assertIn('role=' + role + ';', result[2])

    def test_diagnostic_constructor_and_emitter_reject_unknown_roles(self):
        for role in (self.SENTINEL, None, ['api'], {'role': 'api'}):
            for mutate in (False, True):
                failure = rehearsal.ExportFailure('SAVE_COMMAND_FAILED', role=role)
                if mutate:
                    failure.role = role
                with self.subTest(kind=type(role).__name__, mutate=mutate), \
                     patch.object(rehearsal, 'run', side_effect=failure), \
                     patch.object(rehearsal, 'STEP', self.SENTINEL), \
                     patch('sys.stdout', new_callable=io.StringIO) as out, \
                     patch('sys.stderr', new_callable=io.StringIO) as err:
                    self.assertEqual(rehearsal.main(['--run']), 2)
                    self.assertEqual(out.getvalue(), '')
                    self.assertIn('role=unknown;', err.getvalue())
                    self.assertIn('code=SAVE_COMMAND_FAILED;', err.getvalue())
                    self.assertNotIn(self.SENTINEL, err.getvalue())

    def test_diagnostic_constructor_and_emitter_reject_unknown_codes(self):
        for mutate in (False, True):
            failure = rehearsal.ExportFailure(self.SENTINEL)
            if mutate:
                failure.code = self.SENTINEL
            with patch.object(rehearsal, 'run', side_effect=failure), \
                 patch('sys.stdout', new_callable=io.StringIO) as out, \
                 patch('sys.stderr', new_callable=io.StringIO) as err:
                self.assertEqual(rehearsal.main(['--run']), 2)
                self.assertEqual(out.getvalue(), '')
                self.assertIn('code=ARCHIVE_VALIDATION_FAILED;', err.getvalue())
                self.assertNotIn(self.SENTINEL, err.getvalue())


class ComposeDualViewTests(unittest.TestCase):
    SENTINEL = 'PRIVATE_SENTINEL_path_password_raw_step'

    def invoke(self, *, project_omits=False, change_project=None, change_model=None,
               raw_project=None, raw_model=None, project_error=None, model_error=None):
        calls = []
        manifest = {'images': {role: {'image_id': 'sha256:' + char * 64}
                               for role, char in (('api', 'a'), ('web', 'b'))}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = rehearsal.preflight.compose(manifest, root / 'database.env')
            def command(args, **kwargs):
                calls.append(args)
                self.assertEqual(args[:2], ['docker', 'compose'])
                self.assertIn('--no-env-resolution', args)
                for forbidden in ('up', 'build', 'pull', '--no-consistency', '--no-normalize', '--resolve-image-digests'):
                    self.assertNotIn(forbidden, args)
                is_model = '--no-interpolate' in args
                error = model_error if is_model else project_error
                if error is not None:
                    raise error
                raw = raw_model if is_model else raw_project
                if raw is not None:
                    return raw
                value = copy.deepcopy(document)
                if project_omits and not is_model:
                    value['services']['api'].pop('env_file')
                change = change_model if is_model else change_project
                if change:
                    change(value)
                return json.dumps(value).encode()
            with patch.object(rehearsal, 'command', side_effect=command), \
                 patch.object(rehearsal.preflight, 'validate', side_effect=AssertionError('no operator approval')), \
                 patch.object(rehearsal, 'run', side_effect=lambda: rehearsal.parse_compose(manifest, root)), \
                 patch.object(rehearsal, 'STEP', self.SENTINEL), \
                 patch('sys.stdout', new_callable=io.StringIO) as out, \
                 patch('sys.stderr', new_callable=io.StringIO) as err:
                status = rehearsal.main(['--run'])
            self.assertEqual((root / 'database.env').read_bytes(), b'')
            self.assertEqual((root / 'database.env').stat().st_mode & 0o777, 0o600)
            self.assertFalse((root / 'operator.json').exists())
            self.assertEqual(json.loads((root / 'compose.json').read_bytes()), document)
            return status, out.getvalue(), err.getvalue(), calls

    def blocked(self, result, *, phase, code='COMPOSE_POLICY_REJECTED', role=None, field=None):
        status, out, err, _calls = result
        self.assertEqual(status, 2)
        self.assertEqual(out, '')
        self.assertIn('phase=' + phase + ';', err)
        self.assertIn('code=' + code + ';', err)
        if role:
            self.assertIn('role=' + role + ';', err)
        if field:
            self.assertIn('field=' + field + ';', err)
        self.assertNotIn(self.SENTINEL, err)

    def test_complete_project_and_model_views_both_required(self):
        status, out, err, calls = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(err, '')
        self.assertEqual(json.loads(out), {'status': 'COMPOSE_PARSED_ONLY',
                                        'operator_approval': False, 'application_started': False})
        self.assertEqual(len(calls), 2)
        self.assertNotIn('--no-interpolate', calls[0])
        self.assertIn('--no-interpolate', calls[1])

    def test_actual_2382_project_omission_passes_only_with_exact_complete_model(self):
        status, _out, err, calls = self.invoke(project_omits=True)
        self.assertEqual(status, 0)
        self.assertEqual(err, '')
        self.assertEqual(len(calls), 2)

    def test_model_cannot_omit_raw_required_path_or_env_file(self):
        mutations = [lambda d: d['services']['api'].pop('env_file')]
        mutations += [lambda d, key=key: d['services']['api']['env_file'][0].pop(key)
                      for key in ('path', 'required', 'format')]
        mutations += [lambda d, key=key, value=value: d['services']['api']['env_file'][0].update({key: value})
                      for key, value in (('required', False), ('required', 1), ('format', ''), ('path', self.SENTINEL))]
        for change in mutations:
            with self.subTest(change=mutations.index(change)):
                self.blocked(self.invoke(project_omits=True, change_model=change), phase='model', role='api', field='env_file')

    def test_unobserved_project_env_file_shapes_are_not_accepted(self):
        for value in (None, [], [self.SENTINEL], {}, [{'path': self.SENTINEL, 'required': False, 'format': 'raw'}]):
            with self.subTest(value=value):
                change = lambda d: d['services']['api'].update(env_file=value)
                self.blocked(self.invoke(change_project=change), phase='project', role='api', field='env_file')

    def test_web_env_file_addition_is_not_the_supported_api_omission(self):
        for view in ('project', 'model'):
            with self.subTest(view=view):
                self.blocked(self.invoke(**{'change_' + view: lambda d: d['services']['web'].update(env_file=[])}),
                             phase=view, role='web', field='env_file')

    def test_every_existing_service_field_is_required_and_exact_in_both_views(self):
        fixture = rehearsal.preflight.compose({'images': {r: {'image_id': 'sha256:' + 'a' * 64} for r in ('api', 'web')}}, Path('/synthetic'))
        for view in ('project', 'model'):
            for role, service in fixture['services'].items():
                for field in service:
                    if view == 'project' and role == 'api' and field == 'env_file':
                        continue  # This sole project omission still needs the full model.
                    for mode in ('missing', 'changed'):
                        with self.subTest(view=view, role=role, field=field, mode=mode):
                            def change(d):
                                if mode == 'missing':
                                    d['services'][role].pop(field)
                                else:
                                    d['services'][role][field] = self.SENTINEL
                            self.blocked(self.invoke(**{'change_' + view: change}), phase=view, role=role, field=field)

    def test_unknown_fields_services_and_root_keys_fail_without_echoing_names(self):
        mutations = ((lambda d: d.update({self.SENTINEL: True}), 'unknown', 'document'),
                     (lambda d: d['services'].update({self.SENTINEL: {}}), 'unknown', 'services'),
                     (lambda d: d['services']['api'].update({self.SENTINEL: True}), 'api', 'unknown'),
                     (lambda d: d['services']['api'].update(privileged=True), 'api', 'unknown'))
        for view in ('project', 'model'):
            for change, role, field in mutations:
                with self.subTest(view=view, field=field):
                    self.blocked(self.invoke(**{'change_' + view: change}), phase=view, role=role, field=field)

    def test_boolean_number_aliases_are_not_equal_policy(self):
        for view in ('project', 'model'):
            for field, value in (('read_only', 1), ('healthcheck', {'disable': 1})):
                with self.subTest(view=view, field=field):
                    self.blocked(self.invoke(**{'change_' + view: lambda d: d['services']['api'].update({field: value})}),
                                 phase=view, role='api', field=field)

    def test_top_level_name_and_malformed_containers_are_rejected(self):
        for view in ('project', 'model'):
            for raw, field in ((b'null', 'document'), (b'[]', 'document'),
                               (b'{"name":"PRIVATE_SENTINEL_path_password_raw_step","services":{}}', 'name')):
                with self.subTest(view=view, raw=raw):
                    self.blocked(self.invoke(**{'raw_' + view: raw}), phase=view, field=field)

    def test_json_duplicate_keys_nonfinite_and_invalid_bytes_are_safe(self):
        for view in ('project', 'model'):
            for raw in (b'PRIVATE_SENTINEL_path_password_raw_step', b'\xff',
                        b'{"services":{},"services":{}}', b'{"value":NaN}', b'{"value":Infinity}'):
                with self.subTest(view=view, raw=raw):
                    self.blocked(self.invoke(**{'raw_' + view: raw}), phase=view, code='COMPOSE_JSON_INVALID')

    def test_project_command_failure_never_uses_model_as_fallback(self):
        for error, code in ((rehearsal.preflight.Invalid('command failed'), 'COMPOSE_COMMAND_FAILED'),
                            (subprocess.TimeoutExpired([self.SENTINEL], 30), 'COMPOSE_COMMAND_TIMEOUT'),
                            (OSError(self.SENTINEL), 'COMPOSE_COMMAND_ERROR')):
            with self.subTest(code=code):
                result = self.invoke(project_error=error)
                self.blocked(result, phase='project', code=code)
                self.assertEqual(len(result[3]), 1)

    def test_model_command_failure_cannot_leave_project_only_success(self):
        for error, code in ((rehearsal.preflight.Invalid('command failed'), 'COMPOSE_COMMAND_FAILED'),
                            (subprocess.TimeoutExpired([self.SENTINEL], 30), 'COMPOSE_COMMAND_TIMEOUT'),
                            (RuntimeError(self.SENTINEL), 'COMPOSE_COMMAND_ERROR')):
            with self.subTest(code=code):
                result = self.invoke(project_omits=True, model_error=error)
                self.blocked(result, phase='model', code=code)
                self.assertEqual(len(result[3]), 2)

    def test_unknown_exception_string_methods_are_never_called(self):
        class HostileError(Exception):
            def __str__(self):
                raise AssertionError('must not format exception')
        self.blocked(self.invoke(project_error=HostileError()), phase='project', code='COMPOSE_COMMAND_ERROR')

    def test_prepare_failure_is_fixed_and_private(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(rehearsal.preflight, 'compose', side_effect=OSError(self.SENTINEL)), \
             patch.object(rehearsal, 'run', side_effect=lambda: rehearsal.parse_compose({}, Path(tmp))), \
             patch.object(rehearsal, 'command') as command, \
             patch('sys.stdout', new_callable=io.StringIO) as out, \
             patch('sys.stderr', new_callable=io.StringIO) as err:
            self.assertEqual(rehearsal.main(['--run']), 2)
            self.blocked((2, out.getvalue(), err.getvalue(), []), phase='prepare', code='COMPOSE_PREPARE_FAILED')
            command.assert_not_called()

    def test_diagnostic_constructor_and_emitter_allowlist_every_dimension(self):
        for value in (self.SENTINEL, None, [], {'api': True}):
            for mutate in (False, True):
                with self.subTest(value=type(value).__name__, mutate=mutate):
                    failure = rehearsal.ComposeFailure(value, phase=value, role=value, field=value)
                    if mutate:
                        failure.code = failure.phase = failure.role = failure.field = value
                    with patch.object(rehearsal, 'run', side_effect=failure), \
                         patch.object(rehearsal, 'STEP', self.SENTINEL), \
                         patch('sys.stdout', new_callable=io.StringIO) as out, \
                         patch('sys.stderr', new_callable=io.StringIO) as err:
                        self.assertEqual(rehearsal.main(['--run']), 2)
                        self.blocked((2, out.getvalue(), err.getvalue(), []), phase='unknown',
                                     code='COMPOSE_VALIDATION_FAILED', role='unknown', field='unknown')

    def test_compose_boundary_preserves_process_interrupts(self):
        for error in (KeyboardInterrupt(), SystemExit(17)):
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                self.invoke(project_error=error)

    def test_missing_flags_stop_run_before_any_directories_or_downloads(self):
        version = {'Client': {'Version': '28.0.4'}, 'Server': {'Version': '28.0.4'}}
        info = {'OSType': 'linux', 'Architecture': 'amd64', 'DockerRootDir': '/tmp'}
        def command(args, **kwargs):
            if args[:2] == ['docker', 'version']: return json.dumps(version).encode()
            if args[:2] == ['docker', 'info']: return json.dumps(info).encode()
            if args == ['docker', 'compose', 'version', '--short']: return b'2.38.2\n'
            if args == ['docker', 'compose', 'config', '--help']: return b'      --no-env-resolution   available\n'
            raise AssertionError('unexpected command')
        with patch.dict(rehearsal.os.environ, {}, clear=True), \
             patch.object(rehearsal.platform, 'machine', return_value='x86_64'), \
             patch.object(rehearsal.sys, 'platform', 'linux'), \
             patch.object(rehearsal.sys, 'version_info', (3, 12, 14)), \
             patch.object(rehearsal.shutil, 'disk_usage', return_value=type('Usage', (), {'free': 50 * 1024**3})()), \
             patch.object(rehearsal, 'command', side_effect=command), \
             patch.object(rehearsal.tempfile, 'mkdtemp', side_effect=AssertionError('must stop before directories')) as mkdir, \
             patch.object(rehearsal, 'acquire') as acquire, \
             patch('sys.stdout', new_callable=io.StringIO) as out, \
             patch('sys.stderr', new_callable=io.StringIO) as err:
            self.assertEqual(rehearsal.main(['--run']), 2)
            self.blocked((2, out.getvalue(), err.getvalue(), []), phase='capability', code='COMPOSE_CAPABILITY_MISSING')
            mkdir.assert_not_called()
            acquire.assert_not_called()

    def test_capability_probe_requires_actual_help_option_lines(self):
        for raw in (b'      --no-interpolate option\n', b'notes about --no-interpolate and --no-env-resolution', b'\xff'):
            with self.subTest(raw=raw), patch.object(rehearsal, 'command', return_value=raw), self.assertRaises(ValueError):
                rehearsal.check_compose_capabilities()
        with patch.object(rehearsal, 'command', return_value=b'      --no-env-resolution option\n      --no-interpolate option\n') as command:
            rehearsal.check_compose_capabilities()
            self.assertEqual(command.call_args.args[0], ['docker', 'compose', 'config', '--help'])




class ImageBundleIntegrationTests(unittest.TestCase):
    def test_export_is_opt_in_and_incompatible_with_host_only(self):
        with patch.object(rehearsal, 'run', return_value={}) as run, patch('builtins.print'):
            self.assertEqual(rehearsal.main(['--run']), 0)
        run.assert_called_once_with()
        with patch.object(rehearsal, 'run', return_value={}) as run, patch('builtins.print'):
            self.assertEqual(rehearsal.main(['--run', '--export-bundle', '/new-handoff']), 0)
        run.assert_called_once_with(bundle_destination='/new-handoff')
        with patch.object(rehearsal, 'check_host') as host, self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            rehearsal.main(['--check-host', '--export-bundle', '/new-handoff'])
        host.assert_not_called()

    def test_export_occurs_only_after_successful_smoke_and_dual_compose(self):
        events = []
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            commit = 'a' * 40
            bases = {'images': {role: {'reference': role, 'config_digest': 'sha256:' + role}
                                for role in ('api', 'web')}}
            def command(args, **_kwargs):
                if args[:3] == ['docker', 'image', 'inspect']:
                    return json.dumps([{'Id': 'sha256:' + args[-1], 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
                return b''
            def export(*args):
                events.append('bundle')
                self.assertEqual(args[0], directory)
                self.assertEqual(args[2]['status'], rehearsal.bundle.REHEARSAL_STATUS)
                return {'status': 'IMAGE_BUNDLE_EXPORTED_NOT_OFFLINE_ACCEPTANCE'}
            patches = [patch.object(rehearsal, 'LOG_ROOT', None), patch.object(rehearsal, 'RUN_ENV', None),
                patch.object(rehearsal, 'STEP', 'host prerequisites'),
                patch.object(rehearsal, 'check_host', return_value={}),
                patch.object(rehearsal.tempfile, 'mkdtemp', return_value=raw),
                patch.object(rehearsal, 'snapshot', return_value=(commit, {})),
                patch.object(rehearsal, 'load_bases', return_value=bases),
                patch.object(rehearsal, 'prepare_contexts', return_value={'api': directory, 'web': directory}),
                patch.object(rehearsal, 'acquire', return_value={}), patch.object(rehearsal, 'command', side_effect=command),
                patch.object(rehearsal, 'export_image', side_effect=lambda role, *_: {'image_id': role}),
                patch.object(rehearsal, 'smoke', side_effect=lambda role, *_: events.append(role + '-smoke') or b'safe'),
                patch.object(rehearsal.bundle, 'check_destination'),
                patch.object(rehearsal.bundle, 'export_bundle', side_effect=export),
                patch.object(rehearsal, 'parse_compose', side_effect=lambda *_: events.append('compose') or {})]
            import contextlib
            with contextlib.ExitStack() as stack:
                for item in patches: stack.enter_context(item)
                result = rehearsal.run(ROOT, bundle_destination='/new-handoff')
            self.assertEqual(events, ['api-smoke', 'web-smoke', 'compose', 'bundle'])
            self.assertEqual(result['image_bundle']['status'], 'IMAGE_BUNDLE_EXPORTED_NOT_OFFLINE_ACCEPTANCE')

    def test_bundle_failure_is_safe_and_never_prints_rehearsal_success(self):
        out, err = io.StringIO(), io.StringIO()
        import contextlib
        with patch.object(rehearsal, 'run', side_effect=rehearsal.bundle.BundleError()), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(rehearsal.main(['--run', '--export-bundle', '/PRIVATE_PATH']), 2)
        self.assertEqual(out.getvalue(), '')
        self.assertNotIn('PRIVATE', err.getvalue())
        self.assertIn('BLOCKED', err.getvalue())


    def test_uncertain_bundle_cli_emits_trusted_receipt_without_raw_values(self):
        import contextlib
        receipt = {'source_commit': 'a' * 40, 'manifest_sha256': 'b' * 64}
        out, err = io.StringIO(), io.StringIO()
        error = rehearsal.bundle.BundleError('BUNDLE_COMPLETION_UNCERTAIN', receipt=receipt)
        with patch.object(rehearsal, 'run', side_effect=error), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(rehearsal.main(['--run', '--export-bundle', '/PRIVATE_PATH']), 2)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('manifest_sha256=' + 'b' * 64, err.getvalue())
        self.assertNotIn('PRIVATE', err.getvalue())

    def test_final_bundle_interrupt_reports_safe_receipt_and_remains_interrupt(self):
        import contextlib
        receipt = {'source_commit': 'a' * 40, 'manifest_sha256': 'b' * 64}
        out, err = io.StringIO(), io.StringIO()
        with patch.object(rehearsal, 'run', side_effect=rehearsal.bundle.CompletionInterrupted(receipt)), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(KeyboardInterrupt):
            rehearsal.main(['--run', '--export-bundle', '/PRIVATE_PATH'])
        self.assertEqual(out.getvalue(), '')
        self.assertIn('BUNDLE_COMPLETION_UNCERTAIN', err.getvalue())
        self.assertIn('manifest_sha256=' + 'b' * 64, err.getvalue())
        self.assertNotIn('PRIVATE', err.getvalue())

    def test_bundle_receipt_emitter_resanitizes_mutated_exception(self):
        import contextlib
        error = rehearsal.bundle.BundleError('BUNDLE_COMPLETION_UNCERTAIN')
        error.receipt = {'source_commit': 'a' * 40, 'manifest_sha256': 'PRIVATE'}
        out = io.StringIO()
        with contextlib.redirect_stderr(out): rehearsal.bundle_failure(error)
        self.assertNotIn('PRIVATE', out.getvalue())
        self.assertNotIn('manifest_sha256=', out.getvalue())


if __name__ == '__main__':
    unittest.main()
