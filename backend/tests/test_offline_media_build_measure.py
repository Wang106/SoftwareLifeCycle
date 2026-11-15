"""Synthetic fixed-source coordination: never builds images or contacts Docker."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import time
from unittest.mock import MagicMock
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
import test_offline_image_bundle as fixtures
import offline_image_bundle as bundle
import offline_image_rehearsal as builder
import offline_media_build_measure as measure

SOURCE = 'e2038a9462770a29254674dd86c0e7b26b26a221'
TOOL = '9c43a5d3dde4b719cc6c2f19cbd4920da9d1349f'


class BuildMeasureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ImageBundleTests(methodName='runTest')
        with patch.object(fixtures, 'COMMIT', SOURCE): self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture.root / 'checkout'
        self.source.mkdir()
        self.receipt = copy.deepcopy(self.fixture.evidence)
        self.receipt['image_bundle'] = self.fixture.export()
        self.destination = self.fixture.dest

    def run_measure(self, receipt=None):
        with patch.object(measure, 'verify_checkout') as checkout, \
             patch.object(measure, 'budget', return_value=contextlib.nullcontext()), \
             patch.object(builder, 'run', return_value=receipt or self.receipt) as run:
            result = measure.build_and_measure(self.source, self.destination,
                tool_commit=TOOL, started_ns=time.monotonic_ns())
        return result, checkout, run

    def test_receipt_feeds_real_inspector_and_preserves_original_five_files(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.destination.iterdir()}
        result, checkout, run = self.run_measure()
        self.assertEqual(checkout.call_args_list[0].args, (measure.ROOT, TOOL))
        self.assertEqual(checkout.call_args_list[1].args, (self.source, SOURCE))
        run.assert_called_once_with(self.source, bundle_destination=self.destination,
                                    expected_source_commit=SOURCE, deadline_ns=None)
        self.assertEqual(result['tool_commit'], TOOL)
        self.assertEqual(result['inventory']['image_source_commit'], SOURCE)
        self.assertEqual(result['inventory']['payload_bytes'], sum(len(x[0]) for x in before.values()))
        self.assertIs(result['inventory']['upload_authorized'], False)
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.destination.iterdir()})
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn(str(self.destination), json.dumps(result))

    def test_rejects_wrong_source_or_tool_before_builder(self):
        for fail in (1, 2):
            with self.subTest(fail=fail), patch.object(measure, 'verify_checkout',
                    side_effect=[ValueError('private')] if fail == 1 else [None, ValueError('private')]), \
                 patch.object(builder, 'run') as run, self.assertRaises(ValueError):
                measure.build_and_measure(self.source, self.destination, tool_commit=TOOL,
                                          started_ns=time.monotonic_ns())
            run.assert_not_called()

    def test_reconstructed_digest_not_received_manifest_controls_trust(self):
        for mutate in ('receipt_digest', 'source', 'image', 'status', 'compose', 'native'):
            bad = copy.deepcopy(self.receipt)
            if mutate == 'receipt_digest': bad['image_bundle']['manifest_sha256'] = 'b' * 64
            elif mutate == 'source': bad['source_commit'] = TOOL
            elif mutate == 'image': bad['images']['api']['size'] += 1
            elif mutate == 'status': bad['status'] = 'success'
            elif mutate == 'compose': bad['compose']['application_started'] = True
            else: bad['native_smoke']['api'] = ''
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): self.run_measure(bad)

    def test_modified_handoff_rejected_without_retry(self):
        (self.destination / 'api.tar').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.run_measure()

    def test_builder_failure_and_interrupt_never_inspect_or_retry(self):
        for error in (RuntimeError('private'), KeyboardInterrupt()):
            with self.subTest(error=type(error)), patch.object(measure, 'verify_checkout'), \
                 patch.object(measure, 'budget', return_value=contextlib.nullcontext()), \
                 patch.object(builder, 'run', side_effect=error) as run, \
                 patch.object(measure.media, 'inspect_candidate') as inspect:
                with self.assertRaises(type(error)):
                    measure.build_and_measure(self.source, self.destination, tool_commit=TOOL,
                                              started_ns=time.monotonic_ns())
                run.assert_called_once()
                inspect.assert_not_called()

    def test_snapshot_mismatch_stops_before_any_copy_or_acquisition(self):
        with patch.object(builder, 'command', side_effect=[b'', (TOOL + '\n').encode()]) as command:
            with self.assertRaises(ValueError):
                builder.snapshot(self.source, self.fixture.root / 'absent', expected_commit=SOURCE)
        self.assertEqual(command.call_count, 2)
        self.assertFalse((self.fixture.root / 'absent').exists())

    def test_expired_or_future_budget_rejected_before_body(self):
        for stamp in (0, True, time.monotonic_ns() + 10**12, time.monotonic_ns() - 3300 * 10**9):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                with measure.budget(stamp): self.fail('must not enter')

    def test_budget_restores_handlers_on_failure_and_preserves_interrupt(self):
        before = [signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM)]
        with self.assertRaises(KeyboardInterrupt):
            with measure.budget(time.monotonic_ns()):
                signal.getsignal(signal.SIGALRM)(signal.SIGALRM, None)
        self.assertEqual([signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM)], before)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_default_help_unknown_options_do_not_build(self):
        with patch.object(measure, 'build_and_measure') as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(measure.main([]), 0)
            self.assertEqual(measure.main(['--help']), 0)
            self.assertEqual(measure.main(['--approve-upload']), 2)
        run.assert_not_called()

    def test_safe_uncertain_completion_and_cleanup_diagnostics(self):
        trusted = {'source_commit': SOURCE, 'manifest_sha256': 'b' * 64}
        for error, code, expected in (
                (bundle.CompletionInterrupted(trusted), 130, 'BUNDLE_COMPLETION_UNCERTAIN'),
                (bundle.BundleError('BUNDLE_COMPLETION_UNCERTAIN', receipt=trusted), 2, 'BUNDLE_COMPLETION_UNCERTAIN'),
                (builder.CleanupUnconfirmed('PRIVATE'), 2, 'MEDIA_BUILD_CLEANUP_UNCONFIRMED')):
            output = io.StringIO()
            with self.subTest(error=type(error)), patch.object(measure, 'build_and_measure', side_effect=error) as run, contextlib.redirect_stderr(output):
                self.assertEqual(measure.main(['--run', '--source-root', '/source', '--destination', '/new',
                    '--tool-commit', TOOL, '--started-ns', '1']), code)
            run.assert_called_once()
            self.assertIn(expected, output.getvalue())
            self.assertNotIn('PRIVATE', output.getvalue())
            if isinstance(error, (bundle.CompletionInterrupted, bundle.BundleError)):
                self.assertIn(trusted['manifest_sha256'], output.getvalue())
                self.assertIn(SOURCE, output.getvalue())

    def test_early_term_disarms_alarm_before_cleanup(self):
        with self.assertRaises(KeyboardInterrupt):
            with measure.budget(time.monotonic_ns()):
                try:
                    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                finally:
                    self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    @patch.dict(builder.os.environ, {}, clear=True)
    def test_bounded_fetch_checks_deadline_around_single_reads(self):
        raw = b'test'
        item = {'filename': 'bounded.whl', 'url': 'https://files.pythonhosted.org/packages/test.whl',
                'size_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        class Response(io.BytesIO):
            status = 200
            url = item['url']
            def read(self, size=-1): raise AssertionError('unbounded buffered read forbidden')
            def read1(self, size=-1):
                clock[0] += 2 * 10**9
                return super().read1(size)
        clock = [time.monotonic_ns()]
        opener = MagicMock()
        opener.open.return_value = Response(raw)
        target = self.fixture.root / 'bounded'
        target.mkdir()
        with patch.object(builder.time, 'monotonic_ns', side_effect=lambda: clock[0]), self.assertRaises(ValueError):
            builder.fetch(item, target, 'sha256', opener, deadline_ns=clock[0] + 10**9)
        self.assertLessEqual(opener.open.call_args.kwargs['timeout'], 1)
        self.assertEqual((target / item['filename']).read_bytes(), b'')
        opener.reset_mock()
        with self.assertRaises(ValueError):
            builder.fetch(item, target, 'sha256', opener,
                          deadline_ns=time.monotonic_ns() - 1)
        opener.open.assert_not_called()

    @patch.dict(builder.os.environ, {}, clear=True)
    def test_deadline_acquisition_is_serial_and_interrupt_stops_next_get(self):
        api = self.fixture.root / 'api-context'
        web = self.fixture.root / 'web-context'
        api.mkdir(); web.mkdir()
        with patch.object(builder, 'ThreadPoolExecutor') as pool, \
             patch.object(builder, 'fetch', side_effect=KeyboardInterrupt) as fetch:
            with self.assertRaises(KeyboardInterrupt):
                builder.acquire(ROOT, api, web, deadline_ns=time.monotonic_ns()+10**9)
        pool.assert_not_called()
        fetch.assert_called_once()
        self.assertIn('deadline_ns', fetch.call_args.kwargs)

    def test_workflow_fixed_checkouts_default_off_and_no_upload(self):
        text = (ROOT / '.github/workflows/offline-media-build-measure.yml').read_text()
        self.assertIn('default: false', text)
        self.assertIn('if: ${{ inputs.build_and_measure }}', text)
        self.assertIn('ref: ' + SOURCE, text)
        self.assertEqual(text.count('persist-credentials: false'), 2)
        self.assertIn('contents: read', text)
        self.assertIn('timeout-minutes: 60', text)
        self.assertIn('cancel-in-progress: false', text)
        for forbidden in ('upload-artifact', 'actions/cache', 'secrets.', 'docker push', 'ghcr.io', 'pull_request:', 'push:'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__': unittest.main()
