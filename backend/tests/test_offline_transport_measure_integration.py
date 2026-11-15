"""Same-run digest handoff to local packaging, with a synthetic builder only."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'backend/tests'))
import test_offline_media_build_measure as fixtures
import offline_media_build_measure as measure
import offline_media_transport as transport

class TransportMeasureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BuildMeasureTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.target = self.fixture.fixture.root/'transport.tar'

    def run_measure(self,target=None):
        with patch.object(measure,'verify_checkout'), \
             patch.object(measure,'budget',return_value=contextlib.nullcontext()), \
             patch.object(measure.builder,'run',return_value=self.fixture.receipt) as build:
            result = measure.build_and_measure(self.fixture.source,self.fixture.destination,
                tool_commit=fixtures.TOOL,started_ns=time.monotonic_ns(),
                transport_destination=target)
        return result,build

    def test_real_pack_of_synthetic_handoff_uses_same_run_trusted_digest(self):
        before={p.name:p.read_bytes() for p in self.fixture.destination.iterdir()}
        result,build=self.run_measure(self.target)
        build.assert_called_once()
        item=result['transport']
        self.assertEqual(item['handoff_manifest_sha256'],self.fixture.receipt['image_bundle']['manifest_sha256'])
        self.assertEqual(item['transport_sha256'],hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual(item['transport_bytes'],self.target.stat().st_size)
        self.assertEqual(item['inventory'],result['inventory'])
        self.assertFalse(item['upload_authorized'])
        self.assertFalse(result['runtime_media_retained'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.fixture.destination.iterdir()})
        self.assertNotIn(str(self.target),json.dumps(result))

    def test_old_path_does_not_pack(self):
        with patch.object(transport,'pack',side_effect=AssertionError('disabled')):
            result,_=self.run_measure()
        self.assertIsNone(result['transport'])
        self.assertFalse(self.target.exists())

    def test_existing_or_nested_output_refused_before_builder(self):
        self.target.write_bytes(b'preserve')
        for target in (self.target,self.fixture.destination/'media.tar',self.fixture.source/'media.tar'):
            with self.subTest(target=target),patch.object(measure,'verify_checkout'), \
                 patch.object(measure,'budget',return_value=contextlib.nullcontext()), \
                 patch.object(measure.builder,'run') as build:
                with self.assertRaises(ValueError):
                    measure.build_and_measure(self.fixture.source,self.fixture.destination,
                        tool_commit=fixtures.TOOL,started_ns=time.monotonic_ns(),transport_destination=target)
                build.assert_not_called()
        self.assertEqual(self.target.read_bytes(),b'preserve')

    def test_pack_failure_or_interrupt_has_no_retry(self):
        for error in (transport.TransportError(),KeyboardInterrupt()):
            with self.subTest(error=type(error)),patch.object(transport,'pack',side_effect=error) as pack:
                with self.assertRaises(type(error)):self.run_measure(self.target)
                pack.assert_called_once()

    def test_pack_stays_inside_shared_budget(self):
        active=[]
        @contextlib.contextmanager
        def budget(_):
            active.append(True)
            try:yield None
            finally:active.pop()
        original=transport.pack
        def checked(*args,**kwargs):
            self.assertEqual(active,[True])
            return original(*args,**kwargs)
        with patch.object(measure,'budget',side_effect=budget),patch.object(measure,'verify_checkout'), \
             patch.object(measure.builder,'run',return_value=self.fixture.receipt), \
             patch.object(transport,'pack',side_effect=checked):
            measure.build_and_measure(self.fixture.source,self.fixture.destination,tool_commit=fixtures.TOOL,
                started_ns=time.monotonic_ns(),transport_destination=self.target)
        self.assertFalse(active)

    def test_cli_pack_flag_without_run_is_inert_rejection(self):
        import io
        with patch.object(measure,'build_and_measure') as build,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(measure.main(['--transport-destination',str(self.target)]),2)
        build.assert_not_called()

    def test_invalid_build_receipt_never_reaches_pack(self):
        self.fixture.receipt['image_bundle']['manifest_sha256']='b'*64
        with patch.object(transport,'pack') as pack:
            with self.assertRaises(ValueError):self.run_measure(self.target)
        pack.assert_not_called()
        self.assertFalse(self.target.exists())

    def test_cli_explicit_transport_passes_exact_path(self):
        import io
        with patch.object(measure,'build_and_measure',return_value={}) as build, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(measure.main(['--run','--source-root','/source','--destination','/handoff',
                '--tool-commit',fixtures.TOOL,'--started-ns','1',
                '--transport-destination',str(self.target)]),0)
        self.assertEqual(build.call_args.kwargs['transport_destination'],self.target)

    def test_workflow_opt_in_fixed_output_no_uploader(self):
        text=(ROOT/'.github/workflows/offline-media-build-measure.yml').read_text()
        self.assertIn('prepare_transport:',text)
        self.assertEqual(text.count('default: false'),2)
        self.assertIn('PREPARE_TRANSPORT: ${{ inputs.prepare_transport }}',text)
        self.assertIn('$RUNNER_TEMP/slc-fixed-source-transport.tar',text)
        self.assertIn('test_offline_transport_measure_integration.py',text)
        self.assertIn('contents: read',text)
        self.assertIn('timeout-minutes: 60',text)
        for forbidden in ('upload-artifact','actions/cache','secrets.','docker push'):
            self.assertNotIn(forbidden,text)

if __name__=='__main__':unittest.main()
