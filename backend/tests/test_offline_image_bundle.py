"""Synthetic handoff contracts. No Docker, network, runnable images or DB."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_image_bundle as bundle

COMMIT = 'a' * 40


class ImageBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'run'
        self.source.mkdir()
        self.dest = self.root / 'handoff'
        self.manifest = {'format': 'slc-offline-readonly-v1', 'source_commit': COMMIT,
                         'required_db_revision': bundle.preflight.REVISION, 'images': {}}
        for role in ('api', 'web'):
            layer = ('synthetic ' + role).encode()
            config = json.dumps({'os': 'linux', 'architecture': 'amd64', 'config': {
                'Labels': {'org.opencontainers.image.revision': COMMIT}, 'Env': []},
                'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + hashlib.sha256(layer).hexdigest()]}}).encode()
            values = {'config.json': config, 'layer.tar': layer, 'manifest.json': json.dumps([
                {'Config': 'config.json', 'RepoTags': [], 'Layers': ['layer.tar']}]).encode()}
            path = self.source / (role + '.tar')
            with tarfile.open(path, 'w') as archive:
                for name, value in values.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(value)
                    archive.addfile(member, io.BytesIO(value))
            self.manifest['images'][role] = {'archive': path.name, 'size': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'image_id': 'sha256:' + hashlib.sha256(config).hexdigest(),
                'platform': 'linux/amd64', 'source_commit': COMMIT}
        self.evidence = {'status': bundle.REHEARSAL_STATUS, 'source_commit': COMMIT,
                         'images': copy.deepcopy(self.manifest['images']),
                         'compose': {'status': 'COMPOSE_PARSED_ONLY', 'operator_approval': False,
                                     'application_started': False},
                         'native_smoke': {'api': 'PRIVATE_API_LOG', 'web': 'PRIVATE_WEB_LOG'},
                         'host': {'private': 'PRIVATE_HOST'}, 'source_sha256': {'private': 'PRIVATE_PATH'}}

    def export(self):
        return bundle.export_bundle(self.source, self.manifest, self.evidence, self.dest)

    def verify(self, **kwargs):
        return bundle.verify_bundle(self.dest, expected_commit=kwargs.get('expected_commit', COMMIT),
            expected_manifest_sha256=kwargs.get('expected_manifest_sha256', self.result['manifest_sha256']))

    def ready(self):
        self.result = self.export()

    def incomplete(self):
        self.assertFalse((self.dest / 'COMPLETE').exists())

    def test_export_then_verify_no_side_effect_or_secret_copy(self):
        (self.source / 'commands.log').write_text('PRIVATE_LOG')
        (self.source / 'database.env').write_text('PRIVATE_DATABASE')
        (self.source / 'operator.json').write_text('PRIVATE_APPROVAL')
        self.ready()
        self.assertEqual(set(p.name for p in self.dest.iterdir()), bundle.FILES | {'COMPLETE'})
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.dest.iterdir()}
        with patch('subprocess.run', side_effect=AssertionError('must not spawn')), \
             patch('socket.create_connection', side_effect=AssertionError('must not connect')), \
             patch.object(tarfile.TarFile, 'extractall', side_effect=AssertionError('must not extract')):
            result = self.verify()
        self.assertEqual(result['status'], 'IMAGE_BUNDLE_VERIFIED_NOT_OFFLINE_ACCEPTANCE')
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.dest.iterdir()})
        text = (self.dest / 'evidence.json').read_text()
        self.assertNotIn('PRIVATE_', text)
        self.assertEqual((self.source / 'api.tar').read_bytes(), (self.dest / 'api.tar').read_bytes())

    def test_existing_destination_never_overwritten_even_empty(self):
        for existing in ('directory', 'file', 'symlink'):
            with self.subTest(existing=existing):
                self.dest = self.root / existing
                if existing == 'directory':
                    self.dest.mkdir()
                elif existing == 'file':
                    self.dest.write_bytes(b'original')
                else:
                    self.dest.symlink_to(self.source, target_is_directory=True)
                with self.assertRaises(bundle.BundleError):
                    self.export()
        self.assertEqual((self.root / 'file').read_bytes(), b'original')

    def test_paths_reject_relative_traversal_and_symlink_ancestors(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        for path in ('relative', str(self.root) + '/../escape', str(alias / 'new'), str(self.root) + '//new'):
            with self.subTest(path=path):
                self.dest = path
                with self.assertRaises(bundle.BundleError):
                    self.export()

    def test_sources_reject_symlink_and_hardlink(self):
        original = self.source / 'api.tar'
        original.rename(self.source / 'old.tar')
        original.symlink_to(self.source / 'old.tar')
        with self.assertRaises(bundle.BundleError):
            self.export()
        self.incomplete()
        original.unlink()
        os.link(self.source / 'old.tar', original)
        with self.assertRaises(bundle.BundleError):
            self.export()
        self.incomplete()

    def test_source_archive_name_cannot_override_controlled_role(self):
        for name in ('../api.tar', '/api.tar', 'web.tar', 'api.tar/extra', 'commands.log'):
            with self.subTest(name=name):
                self.manifest['images']['api']['archive'] = name
                with self.assertRaises(bundle.BundleError):
                    self.export()
        self.assertFalse(self.dest.exists())

    def test_not_success_or_cross_commit_never_exports(self):
        for change in ('status', 'commit', 'images', 'compose', 'native'):
            with self.subTest(change=change):
                evidence = copy.deepcopy(self.evidence)
                if change == 'status': evidence['status'] = 'failed'
                elif change == 'commit': evidence['source_commit'] = 'b' * 40
                elif change == 'images': evidence['images']['api']['sha256'] = 'b' * 64
                elif change == 'compose': evidence['compose']['operator_approval'] = 0
                else: evidence['native_smoke'] = {}
                with self.assertRaises(bundle.BundleError):
                    bundle.export_bundle(self.source, self.manifest, evidence, self.dest)
        self.assertFalse(self.dest.exists())

    def test_manifest_exact_fields_types_sizes_and_roles(self):
        changes = [lambda m: m.update(extra='PRIVATE'), lambda m: m.update(source_commit='B' * 40),
            lambda m: m['images'].update(other=m['images']['api']),
            lambda m: m['images']['api'].update(size=True), lambda m: m['images']['api'].update(size=0),
            lambda m: m['images']['api'].update(size=1.0), lambda m: m['images']['api'].update(size='10240'),
            lambda m: m['images']['api'].update(platform='linux/arm64'),
            lambda m: m['images']['api'].update(source_commit='b' * 40),
            lambda m: m['images']['api'].update(extra='PRIVATE')]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                with self.assertRaises(bundle.BundleError):
                    bundle.export_bundle(self.source, manifest, self.evidence, self.dest)
        self.assertFalse(self.dest.exists())

    def test_capacity_and_total_limit_fail_before_creation(self):
        with patch.object(bundle.os, 'fstatvfs', return_value=type('Disk', (), {'f_bavail': 0, 'f_frsize': 4096})()):
            with self.assertRaises(bundle.BundleError): self.export()
        self.assertFalse(self.dest.exists())
        with patch.object(bundle, 'MAX_TOTAL_BYTES', 10):
            with self.assertRaises(bundle.BundleError): self.export()
        self.assertFalse(self.dest.exists())

    def test_tampered_or_truncated_sources_fail_without_complete(self):
        for raw in (b'changed', b''):
            with self.subTest(raw=raw):
                (self.source / 'api.tar').write_bytes(raw)
                with self.assertRaises(bundle.BundleError): self.export()
                self.incomplete()
                self.dest = self.root / ('next' + str(len(raw)))

    def test_copy_and_hash_use_bounded_reads(self):
        original = bundle.os.read
        sizes = []
        def bounded(fd, size):
            sizes.append(size)
            self.assertLessEqual(size, bundle.CHUNK)
            return original(fd, size)
        with patch.object(bundle.os, 'read', side_effect=bounded):
            self.ready()
            self.verify()
        self.assertTrue(sizes)

    def test_write_failure_short_write_and_interruption_leave_incomplete(self):
        for failure in (OSError('PRIVATE_WRITE'), KeyboardInterrupt()):
            with self.subTest(failure=type(failure)):
                self.dest = self.root / type(failure).__name__
                with patch.object(bundle.os, 'write', side_effect=failure):
                    with self.assertRaises(bundle.BundleError if isinstance(failure, Exception) else KeyboardInterrupt):
                        self.export()
                self.incomplete()
        self.dest = self.root / 'zero-write'
        with patch.object(bundle.os, 'write', return_value=0):
            with self.assertRaises(bundle.BundleError): self.export()
        self.incomplete()

    def test_short_writes_are_finished_without_repeating_actions(self):
        write = bundle.os.write
        def partial(fd, data): return write(fd, data[:min(17, len(data))])
        with patch.object(bundle.os, 'write', side_effect=partial): self.ready()
        self.verify()

    def test_missing_marker_any_file_or_added_file_is_rejected(self):
        self.ready()
        for name in bundle.FILES | {'COMPLETE'}:
            with self.subTest(name=name):
                original = self.dest / name
                hidden = self.root / ('hidden-' + name)
                original.rename(hidden)
                with self.assertRaises(bundle.BundleError): self.verify()
                hidden.rename(original)
        (self.dest / 'operator.json').write_text('{}')
        with self.assertRaises(bundle.BundleError): self.verify()

    def test_expected_commit_and_hash_required_and_checked(self):
        self.ready()
        for commit, digest in ((None, None), (True, 'a' * 64), ('b' * 40, self.result['manifest_sha256']),
                               (COMMIT, 'b' * 64), (COMMIT, 'A' * 64)):
            with self.subTest(commit=commit, digest=digest):
                with self.assertRaises(bundle.BundleError):
                    self.verify(expected_commit=commit, expected_manifest_sha256=digest)

    def test_modified_archive_evidence_or_marker_is_rejected(self):
        self.ready()
        for name in ('api.tar', 'web.tar', 'evidence.json', 'COMPLETE'):
            with self.subTest(name=name):
                path = self.dest / name
                raw = path.read_bytes()
                path.write_bytes(raw + b'X')
                with self.assertRaises(bundle.BundleError): self.verify()
                path.write_bytes(raw)

    def test_duplicate_json_and_nonfinite_are_rejected_with_matching_hash(self):
        self.ready()
        path = self.dest / 'manifest.json'
        for raw in (b'{"format": 1, "format": 1}', b'{"format": NaN}', b'[]', b'\xff', b'{'):
            path.write_bytes(raw)
            with self.assertRaises(bundle.BundleError):
                self.verify(expected_manifest_sha256=hashlib.sha256(raw).hexdigest())

    def test_bundle_file_symlink_or_directory_alias_rejected(self):
        self.ready()
        raw = (self.dest / 'api.tar').read_bytes()
        (self.dest / 'api.tar').unlink()
        (self.dest / 'api.tar').symlink_to(self.source / 'api.tar')
        with self.assertRaises(bundle.BundleError): self.verify()
        alias = self.root / 'alias'
        alias.symlink_to(self.dest, target_is_directory=True)
        with self.assertRaises(bundle.BundleError):
            bundle.verify_bundle(alias, expected_commit=COMMIT, expected_manifest_sha256=self.result['manifest_sha256'])
        self.assertEqual(raw, (self.source / 'api.tar').read_bytes())

    def test_fd_adapter_keeps_archive_gate_pinned_when_name_replaced(self):
        self.ready()
        original = bundle.preflight.archive_image
        visited = []
        def swap(path, item, commit):
            visited.append(item['archive'])
            target = self.dest / item['archive']
            target.rename(self.root / ('moved-' + item['archive']))
            target.symlink_to(self.source / item['archive'])
            # The old immutable descriptor, not the substituted path, is inspected.
            original(path, item, commit)
        with patch.object(bundle.preflight, 'archive_image', side_effect=swap):
            with self.assertRaises(bundle.BundleError): self.verify()
        self.assertEqual(visited, ['api.tar'])

    def test_source_mutation_during_copy_detected(self):
        original = bundle.os.read
        changed = False
        def mutate(fd, size):
            nonlocal changed
            value = original(fd, size)
            if not changed and value:
                changed = True
                with (self.source / 'api.tar').open('ab') as stream: stream.write(b'change')
            return value
        with patch.object(bundle.os, 'read', side_effect=mutate):
            with self.assertRaises(bundle.BundleError): self.export()
        self.incomplete()

    def test_directory_replacement_during_copy_detected_without_escape(self):
        original = bundle.os.write
        moved = self.root / 'moved'
        other = self.root / 'other'
        other.mkdir()
        changed = False
        def replace(fd, data):
            nonlocal changed
            if not changed:
                changed = True
                self.dest.rename(moved)
                self.dest.symlink_to(other, target_is_directory=True)
            return original(fd, data)
        with patch.object(bundle.os, 'write', side_effect=replace):
            with self.assertRaises(bundle.BundleError): self.export()
        self.assertEqual(list(other.iterdir()), [])
        self.assertFalse((moved / 'COMPLETE').exists())

    def test_gate_rejection_is_redacted_and_no_completion(self):
        with patch.object(bundle.preflight, 'archive_image', side_effect=ValueError('PRIVATE_ARCHIVE')):
            with self.assertRaises(bundle.BundleError) as context: self.export()
        self.assertNotIn('PRIVATE', str(context.exception))
        self.incomplete()

    def test_cli_is_readonly_and_hides_raw_errors(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
             patch.object(bundle, 'verify_bundle', side_effect=OSError('PRIVATE_PATH')):
            code = bundle.main(['verify', '/PRIVATE_PATH', '--expected-commit', COMMIT,
                                '--expected-manifest-sha256', 'a' * 64])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('BLOCKED', err.getvalue())
        self.assertNotIn('PRIVATE', err.getvalue())


    def test_final_marker_close_uncertain_is_not_retried_or_reported_success(self):
        original = bundle.os.close
        closed_marker = []
        def close(fd):
            try:
                target = os.readlink('/proc/self/fd/' + str(fd))
            except OSError:
                target = ''
            original(fd)
            if target.endswith('/COMPLETE'):
                closed_marker.append(fd)
                raise OSError('PRIVATE_CLOSE_OUTCOME')
        with patch.object(bundle.os, 'close', side_effect=close):
            with self.assertRaises(bundle.BundleError) as error:
                self.export()
        self.assertEqual(error.exception.code, 'BUNDLE_COMPLETION_UNCERTAIN')
        self.assertEqual(len(closed_marker), 1)
        # Payload was fully verified before the atomic commit; resolve the
        # uncertain result by reading it, never by attempting another export.
        digest = hashlib.sha256((self.dest / 'manifest.json').read_bytes()).hexdigest()
        bundle.verify_bundle(self.dest, expected_commit=COMMIT, expected_manifest_sha256=digest)

    def test_payload_close_uncertain_does_not_retry_or_create_marker(self):
        original = bundle.os.close
        failed = []
        def close(fd):
            try:
                target = os.readlink('/proc/self/fd/' + str(fd))
            except OSError:
                target = ''
            original(fd)
            if target == str(self.dest / 'api.tar') and not failed:
                failed.append(fd)
                raise OSError('PRIVATE_CLOSE_OUTCOME')
        with patch.object(bundle.os, 'close', side_effect=close):
            with self.assertRaises(bundle.BundleError): self.export()
        self.assertEqual(len(failed), 1)
        self.incomplete()

    def test_fsync_and_gate_interruptions_leave_files_for_inspection(self):
        for failure in (OSError('PRIVATE_FSYNC'), KeyboardInterrupt(), SystemExit(3)):
            self.dest = self.root / ('fsync-' + type(failure).__name__)
            with patch.object(bundle.os, 'fsync', side_effect=failure):
                with self.assertRaises(bundle.BundleError if isinstance(failure, Exception) else type(failure)):
                    self.export()
            self.assertTrue(self.dest.is_dir())
            self.incomplete()
        self.dest = self.root / 'gate-interrupt'
        with patch.object(bundle.preflight, 'archive_image', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.export()
        self.incomplete()

    def test_source_directory_symlink_and_file_fifo_are_rejected(self):
        real = self.source
        alias = self.root / 'source-alias'
        alias.symlink_to(real, target_is_directory=True)
        self.source = alias
        with self.assertRaises(bundle.BundleError): self.export()
        self.source = real
        (real / 'api.tar').unlink()
        os.mkfifo(real / 'api.tar')
        with self.assertRaises(bundle.BundleError): self.export()
        self.assertFalse(self.dest.exists())

    def test_verifier_rejects_hardlinks_and_oversized_metadata(self):
        self.ready()
        os.link(self.dest / 'api.tar', self.root / 'archive-alias')
        with self.assertRaises(bundle.BundleError): self.verify()
        (self.root / 'archive-alias').unlink()
        (self.dest / 'evidence.json').write_bytes(b' ' * (bundle.MAX_JSON_BYTES + 1))
        with self.assertRaises(bundle.BundleError): self.verify()

    def test_verifier_strict_manifest_even_when_expected_digest_matches(self):
        self.ready()
        original = json.loads((self.dest / 'manifest.json').read_bytes())
        changes = [lambda m: m.update(extra='PRIVATE'), lambda m: m.update(source_commit='b' * 40),
                   lambda m: m.update(format=True), lambda m: m.update(evidence_sha256=True),
                   lambda m: m['images']['api'].update(size=True),
                   lambda m: m['images']['api'].update(archive='../api.tar'),
                   lambda m: m['images']['web'].update(source_commit='b' * 40),
                   lambda m: m['images']['api'].update(size=bundle.MAX_TOTAL_BYTES + 1)]
        for mutate in changes:
            value = copy.deepcopy(original)
            mutate(value)
            raw = json.dumps(value).encode()
            (self.dest / 'manifest.json').write_bytes(raw)
            with self.assertRaises(bundle.BundleError):
                self.verify(expected_manifest_sha256=hashlib.sha256(raw).hexdigest())

    def test_evidence_schema_and_bool_alias_rejected_even_with_matching_hashes(self):
        self.ready()
        manifest = json.loads((self.dest / 'manifest.json').read_bytes())
        original = json.loads((self.dest / 'evidence.json').read_bytes())
        for field, value in (('checks', {'strict_archives': 1, 'dependency_only_native_smoke': True,
                                       'compose_project_and_model': True}), ('source_commit', 'b' * 40),
                             ('operator_approval', False), ('native_smoke', 'PRIVATE')):
            evidence = copy.deepcopy(original)
            evidence[field] = value
            raw = json.dumps(evidence).encode()
            (self.dest / 'evidence.json').write_bytes(raw)
            manifest['evidence_sha256'] = hashlib.sha256(raw).hexdigest()
            manifest_raw = json.dumps(manifest).encode()
            (self.dest / 'manifest.json').write_bytes(manifest_raw)
            with self.assertRaises(bundle.BundleError):
                self.verify(expected_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest())

    def test_verifier_archive_inode_mutation_is_rejected_after_gate(self):
        self.ready()
        original = bundle.preflight.archive_image
        def mutate(path, item, commit):
            original(path, item, commit)
            with (self.dest / item['archive']).open('r+b') as file:
                file.write(b'changed!')
        with patch.object(bundle.preflight, 'archive_image', side_effect=mutate):
            with self.assertRaises(bundle.BundleError): self.verify()

    def test_all_ancestors_rechecked_after_verification(self):
        self.ready()
        original = bundle.preflight.archive_image
        real = self.root / 'relocated'
        moved = False
        def rename(path, item, commit):
            nonlocal moved
            original(path, item, commit)
            if not moved:
                moved = True
                self.dest.rename(real)
                self.dest.mkdir()
        with patch.object(bundle.preflight, 'archive_image', side_effect=rename):
            with self.assertRaises(bundle.BundleError): self.verify()
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_destination_precheck_is_readonly_and_rejects_existing_dangling_link(self):
        bundle.check_destination(self.dest)
        self.assertFalse(self.dest.exists())
        self.dest.symlink_to(self.root / 'missing')
        with self.assertRaises(bundle.BundleError): bundle.check_destination(self.dest)
        self.assertTrue(self.dest.is_symlink())

    def test_interrupt_is_not_hidden_by_readonly_cli(self):
        with patch.object(bundle, 'verify_bundle', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                bundle.main(['verify', str(self.dest), '--expected-commit', COMMIT,
                             '--expected-manifest-sha256', 'a' * 64])


    def test_uncertain_completion_error_retains_only_trusted_safe_receipt(self):
        original = bundle.os.close
        def close(fd):
            name = os.readlink('/proc/self/fd/' + str(fd))
            original(fd)
            if name.endswith('/COMPLETE'):
                raise OSError('PRIVATE_CLOSE')
        with patch.object(bundle.os, 'close', side_effect=close):
            with self.assertRaises(bundle.BundleError) as error: self.export()
        receipt = error.exception.receipt
        self.assertEqual(set(receipt), {'source_commit', 'manifest_sha256'})
        self.assertEqual(receipt['source_commit'], COMMIT)
        self.assertEqual(receipt['manifest_sha256'], hashlib.sha256((self.dest / 'manifest.json').read_bytes()).hexdigest())
        self.assertNotIn('PRIVATE', str(error.exception))

    def test_final_marker_interrupts_are_safe_and_carry_trusted_receipt(self):
        original = bundle.os.close
        for failure in (KeyboardInterrupt('PRIVATE_INTERRUPT'), SystemExit('PRIVATE_EXIT')):
            self.dest = self.root / ('interrupt-' + type(failure).__name__)
            def close(fd):
                name = os.readlink('/proc/self/fd/' + str(fd))
                original(fd)
                if name.endswith('/COMPLETE'):
                    raise failure
            with patch.object(bundle.os, 'close', side_effect=close):
                with self.assertRaises(bundle.CompletionInterrupted) as error: self.export()
            self.assertIsInstance(error.exception, KeyboardInterrupt)
            self.assertEqual(error.exception.receipt['source_commit'], COMMIT)
            self.assertNotIn('PRIVATE', str(error.exception))
            bundle.verify_bundle(self.dest, expected_commit=COMMIT,
                                 expected_manifest_sha256=error.exception.receipt['manifest_sha256'])

    def test_directory_enumeration_is_streamed_and_stops_on_first_extra(self):
        self.ready()
        with patch.object(bundle.os, 'listdir', side_effect=AssertionError('unbounded enumeration')):
            self.verify()

    def make_outer_pax(self, *, global_headers=None, member_headers=None, extra_count=0):
        for role in ('api', 'web'):
            path = self.source / (role + '.tar')
            with tarfile.open(path, 'r:') as old:
                values = [(member.name, old.extractfile(member).read()) for member in old if member.isfile()]
            with tarfile.open(path, 'w', format=tarfile.PAX_FORMAT, pax_headers=global_headers) as archive:
                for name, value in values + [('extra/' + str(n), b'') for n in range(extra_count)]:
                    item = tarfile.TarInfo(name)
                    item.size = len(value)
                    item.pax_headers = member_headers or {}
                    archive.addfile(item, io.BytesIO(value))
            self.manifest['images'][role].update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.evidence['images'] = copy.deepcopy(self.manifest['images'])

    def test_outer_oversized_pax_is_rejected_before_original_gate(self):
        self.make_outer_pax(member_headers={'comment': 'x' * (2 * bundle.CHUNK)})
        with patch.object(bundle.preflight, 'archive_image', wraps=bundle.preflight.archive_image) as gate:
            with self.assertRaises(bundle.BundleError): self.export()
        gate.assert_not_called()
        self.incomplete()

    def test_outer_header_and_inherited_metadata_cache_limits_precede_gate(self):
        self.make_outer_pax(global_headers={'comment': 'x' * 1024}, extra_count=20)
        for name, limit in (('MAX_OUTER_HEADERS', 10), ('MAX_OUTER_PAX_ITEMS', 3), ('MAX_OUTER_PAX_CHARS', 5000)):
            self.dest = self.root / name
            with patch.object(bundle, name, limit), \
                 patch.object(bundle.preflight, 'archive_image', wraps=bundle.preflight.archive_image) as gate:
                with self.assertRaises(bundle.BundleError): self.export()
            gate.assert_not_called()
            self.incomplete()

    def test_valid_outer_pax_passes_with_original_strict_gate(self):
        self.make_outer_pax(global_headers={'comment': 'safe-small-value'}, extra_count=2)
        with patch.object(bundle.preflight, 'archive_image', wraps=bundle.preflight.archive_image) as gate:
            self.ready()
            self.verify()
        self.assertEqual(gate.call_count, 4)


    def test_actual_archive_size_checked_before_prescan(self):
        self.ready()
        with (self.dest / 'api.tar').open('r+b') as stream:
            stream.truncate(8 * bundle.CHUNK)
        with patch.object(bundle, 'bounded_outer_scan', side_effect=AssertionError('must reject size first')) as scan:
            with self.assertRaises(bundle.BundleError): self.verify()
        scan.assert_not_called()

    def test_outer_metadata_and_name_budgets_precede_original_gate(self):
        self.make_outer_pax(member_headers={'comment': 'small'}, extra_count=2)
        for name, limit in (('MAX_OUTER_METADATA', 511), ('MAX_OUTER_NAME_CHARS', 3)):
            self.dest = self.root / name
            with patch.object(bundle, name, limit), \
                 patch.object(bundle.preflight, 'archive_image', wraps=bundle.preflight.archive_image) as gate:
                with self.assertRaises(bundle.BundleError): self.export()
            gate.assert_not_called()

    def test_outer_extension_reads_are_bounded_before_allocation(self):
        self.make_outer_pax(member_headers={'comment': 'x' * (2 * bundle.CHUNK)})
        original = bundle.PinnedArchive.open
        reads = []
        class Reader:
            def __init__(self, file): self.file = file
            def __enter__(self): return self
            def __exit__(self, *args): self.file.close()
            def tell(self): return self.file.tell()
            def seek(self, *args): return self.file.seek(*args)
            def read(self, size):
                reads.append(size)
                if size < 0 or size > bundle.CHUNK: raise AssertionError('oversized allocation')
                return self.file.read(size)
        with patch.object(bundle.PinnedArchive, 'open', lambda path, mode: Reader(original(path, mode))):
            with self.assertRaises(bundle.BundleError): self.export()
        self.assertTrue(reads)
        self.assertLessEqual(max(reads), bundle.CHUNK)

    def test_outer_missing_terminators_or_nonzero_tail_fail_before_gate(self):
        for suffix in ('missing', 'nonzero'):
            self.dest = self.root / suffix
            path = self.source / 'api.tar'
            raw = path.read_bytes()
            if suffix == 'missing':
                # Three regular members, each exactly header + one data block.
                raw = raw[:3072]
            else:
                raw = raw + b'x' * 512
            path.write_bytes(raw)
            self.manifest['images']['api'].update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            self.evidence['images'] = copy.deepcopy(self.manifest['images'])
            with patch.object(bundle.preflight, 'archive_image', wraps=bundle.preflight.archive_image) as gate:
                with self.assertRaises(bundle.BundleError): self.export()
            gate.assert_not_called()

    def test_receipt_rejects_unknown_fields_types_and_private_content(self):
        for value in ({'source_commit': COMMIT, 'manifest_sha256': 'a' * 64, 'path': 'PRIVATE'},
                      {'source_commit': 'PRIVATE', 'manifest_sha256': 'a' * 64},
                      {'source_commit': COMMIT, 'manifest_sha256': True}, None):
            self.assertIsNone(bundle.BundleError('BUNDLE_COMPLETION_UNCERTAIN', receipt=value).receipt)
            self.assertIsNone(bundle.CompletionInterrupted(value).receipt)



    def test_outer_sparse_logical_expansion_is_rejected_before_gate(self):
        logical_size = 16 * bundle.CHUNK
        for role in ('api', 'web'):
            path = self.source / (role + '.tar')
            with tarfile.open(path, 'r:') as archive:
                config = json.loads(archive.extractfile('config.json').read())
            config['rootfs']['diff_ids'] = ['sha256:' + hashlib.sha256(b'\0' * logical_size).hexdigest()]
            config_raw = json.dumps(config).encode()
            with tarfile.open(path, 'w', format=tarfile.PAX_FORMAT) as archive:
                for name, value in (('config.json', config_raw), ('layer.tar', b''),
                    ('manifest.json', json.dumps([{'Config': 'config.json', 'RepoTags': [], 'Layers': ['layer.tar']}]).encode())):
                    member = tarfile.TarInfo(name)
                    member.size = len(value)
                    if name == 'layer.tar':
                        member.pax_headers = {'GNU.sparse.map': '0,0', 'GNU.sparse.realsize': str(logical_size)}
                    archive.addfile(member, io.BytesIO(value))
            self.manifest['images'][role].update(size=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                image_id='sha256:' + hashlib.sha256(config_raw).hexdigest())
        self.evidence['images'] = copy.deepcopy(self.manifest['images'])
        with patch.object(bundle.preflight, 'archive_image', wraps=bundle.preflight.archive_image) as gate:
            with self.assertRaises(bundle.BundleError): self.export()
        gate.assert_not_called()
        self.incomplete()

    def test_each_outer_sparse_parser_is_rejected_before_mapping_allocation(self):
        for name in ('_proc_sparse', '_proc_gnusparse_00', '_proc_gnusparse_01', '_proc_gnusparse_10'):
            with self.subTest(name=name), self.assertRaises(bundle.BundleError):
                getattr(bundle.OuterTarInfo(), name)(None, None, None)


if __name__ == '__main__':
    unittest.main()
