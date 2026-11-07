"""Static/mocked packaging contracts; these tests never run Docker or download."""
import copy
import hashlib
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

    def archive(self, *, extra=None, config_change=None, manifest_bytes=None, layer_bytes=None):
        layer = b'synthetic layer bytes'
        config = {'os': 'linux', 'architecture': 'amd64',
                  'config': {'Labels': {'org.opencontainers.image.revision': self.COMMIT},
                             'Env': ['PATH=/usr/local/bin:/usr/bin:/bin']},
                  'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + hashlib.sha256(layer).hexdigest()]}}
        if config_change:
            config['config'].update(config_change)
        config_raw = json.dumps(config).encode()
        identity = 'sha256:' + hashlib.sha256(config_raw).hexdigest()
        manifest = {'Config': 'config.json', 'RepoTags': None, 'Layers': ['layer.tar']}
        manifest.update(extra or {})
        members = [('config.json', config_raw),
                   ('manifest.json', manifest_bytes if manifest_bytes is not None else json.dumps([manifest]).encode()),
                   ('layer.tar', layer if layer_bytes is None else layer_bytes)]
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

    def test_moby_extra_layersources_is_diagnosed_but_still_rejected(self):
        raw, identity = self.archive(extra={'LayerSources': {self.SENTINEL: {'urls': [self.SENTINEL]}}})
        self.assert_code(self.export_cli(raw, identity), 'ARCHIVE_FIELDS_REJECTED')

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


if __name__ == '__main__':
    unittest.main()
