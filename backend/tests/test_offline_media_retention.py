"""Synthetic local upload-candidate inventory; no image build or upload."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
import test_offline_image_bundle as fixtures
import offline_image_bundle as bundle
import offline_media_retention as media

SOURCE = 'e2038a9462770a29254674dd86c0e7b26b26a221'


class MediaRetentionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ImageBundleTests(methodName='runTest')
        with patch.object(fixtures, 'COMMIT', SOURCE):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.ready()
        self.root = self.fixture.dest
        self.digest = self.fixture.result['manifest_sha256']

    def inspect(self, **kwargs):
        return media.inspect_candidate(self.root,
            expected_commit=kwargs.get('commit', SOURCE),
            expected_manifest_sha256=kwargs.get('digest', self.digest))

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino)
                for p in self.root.iterdir()}

    def test_exact_inventory_and_retention_are_not_upload_permission(self):
        before = self.snapshot()
        with patch('subprocess.run', side_effect=AssertionError('no processes')), \
             patch('socket.create_connection', side_effect=AssertionError('no network')):
            result = self.inspect()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(result['image_source_commit'], SOURCE)
        self.assertEqual(result['required_db_revision'], '0030_private_upload_sessions')
        self.assertEqual(result['handoff_manifest_sha256'], self.digest)
        self.assertEqual(result['status'], 'MEDIA_CANDIDATE_INVENTORIED_NOT_UPLOAD_APPROVED')
        self.assertEqual(result['retention_days'], 7)
        self.assertEqual(result['file_count'], 5)
        self.assertEqual(set(result['files']), bundle.FILES | {'COMPLETE'})
        for name, item in result['files'].items():
            self.assertEqual(item, {'size': len(before[name][0]),
                                   'sha256': hashlib.sha256(before[name][0]).hexdigest()})
        size = sum(len(v[0]) for v in before.values())
        self.assertEqual(result['payload_bytes'], size)
        self.assertEqual(result['payload_byte_hours'], size * 168)
        self.assertEqual(result['artifact_size_limit_bytes'], 16 * 1024**3)
        self.assertEqual(result['maximum_artifact_gib_hours'], 2688)
        for flag in ('upload_authorized', 'zero_incremental_cost_verified',
                     'content_clearance_verified', 'stored_artifact_size_verified',
                     'artifact_expiration_verified'):
            self.assertIs(result[flag], False)
        self.assertEqual(result['blockers'], ['ZERO_INCREMENTAL_COST_UNVERIFIED',
            'PUBLIC_CONTENT_CLEARANCE_UNVERIFIED', 'STORED_ARTIFACT_SIZE_UNVERIFIED',
            'UPLOAD_AND_EXPIRATION_UNVERIFIED'])
        text = json.dumps(result)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn('PRIVATE', text)

    def test_total_limit_includes_metadata_and_empty_marker(self):
        archive_bytes = sum((self.root / (r + '.tar')).stat().st_size for r in ('api', 'web'))
        with patch.object(media, 'MAX_UPLOAD_BYTES', archive_bytes):
            with self.assertRaises(media.RetentionError): self.inspect()
        total = sum(p.stat().st_size for p in self.root.iterdir())
        with patch.object(media, 'MAX_UPLOAD_BYTES', total): self.inspect()
        with patch.object(media, 'MAX_UPLOAD_BYTES', total - 1):
            with self.assertRaises(media.RetentionError): self.inspect()

    def test_old_or_unknown_commit_rejected_without_source_open(self):
        for value in ('576a6452194d36377ea92dc28f3e0ffec1241cf1', 'b' * 40,
                      'a6b6e593a27d6146b25a0a3a4ebc498bb0e7c292', True, None):
            with self.subTest(value=value), patch.object(bundle.Directory, 'open', side_effect=AssertionError('no input access')) as opened:
                with self.assertRaises(media.RetentionError): self.inspect(commit=value)
                opened.assert_not_called()

    def test_digest_and_schema_mismatch_refused(self):
        with self.assertRaises(media.RetentionError): self.inspect(digest='b' * 64)
        with patch.object(bundle.preflight, 'REVISION', '0029_changeover_batch_history'):
            with self.assertRaises(media.RetentionError): self.inspect()

    def test_extra_file_and_nonempty_marker_refused(self):
        extra = self.root / 'database.env'
        extra.write_text('PRIVATE_SECRET')
        with self.assertRaises(media.RetentionError): self.inspect()
        extra.unlink()
        (self.root / 'COMPLETE').write_text('x')
        with self.assertRaises(media.RetentionError): self.inspect()

    def test_mutation_between_verification_and_inventory_refused(self):
        original = bundle.verify_files
        def changing(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.root / 'evidence.json').write_bytes(b'changed')
            return result
        with patch.object(bundle, 'verify_files', side_effect=changing):
            with self.assertRaises(media.RetentionError): self.inspect()

    def test_hashing_and_close_failures_never_return_success(self):
        for method in ('stream_hash', 'close'):
            target = media if method == 'stream_hash' else bundle.Descriptor
            original = getattr(target, method)
            if method == 'close':
                def fail(value):
                    original(value)
                    raise OSError('PRIVATE_CLOSE')
            else:
                def fail(*args): raise OSError('PRIVATE_HASH')
            with patch.object(target, method, fail):
                with self.assertRaisesRegex(media.RetentionError, '^MEDIA_CANDIDATE_REJECTED$'):
                    self.inspect()

    def test_interrupt_remains_interrupt(self):
        with patch.object(media, 'stream_hash', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.inspect()

    def test_default_and_help_do_not_read_input(self):
        for args in ([], ['--help']):
            with patch.object(bundle.Directory, 'open', side_effect=AssertionError('no input access')), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(media.main(args), 0)

    def test_cli_has_no_cost_or_clearance_override(self):
        args = ['inspect', str(self.root), '--expected-commit', SOURCE,
                '--expected-manifest-sha256', self.digest]
        for option in ('--cost-approved', '--upload', '--content-approved', '--retention-days'):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(media.main(args + [option]), 2)

    def test_cli_success_is_inventory_only(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(media.main(['inspect', str(self.root), '--expected-commit', SOURCE,
                '--expected-manifest-sha256', self.digest]), 0)
        self.assertFalse(json.loads(output.getvalue())['upload_authorized'])

    def test_workflow_default_off_has_no_upload_build_or_secret_access(self):
        text = (ROOT / '.github/workflows/offline-media-retention-preparation.yml').read_text()
        self.assertIn('default: false', text)
        self.assertIn('if: ${{ inputs.validate_preparation }}', text)
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('contents: read', text)
        self.assertIn('cancel-in-progress: false', text)
        self.assertIn('test_offline_media_retention.py', text)
        for forbidden in ('upload-artifact@', 'actions/cache@', 'secrets.', 'docker ',
                          'offline_image_rehearsal.py --run', 'pull_request_target:'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__': unittest.main()
