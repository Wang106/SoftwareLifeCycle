"""Receiver source archive tests: synthetic handoff, no containers or network."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
import offline_receiver_toolkit as toolkit
import test_offline_media_retention as fixtures
import offline_media_transport as transport

class ReceiverToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        (self.repo / 'scripts').mkdir(parents=True)
        for module in toolkit.MODULES:
            (self.repo / 'scripts' / (module + '.py')).write_bytes((ROOT / 'scripts' / (module + '.py')).read_bytes())
        self.env = {**os.environ, 'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':os.devnull,
                    'GIT_AUTHOR_NAME':'Synthetic', 'GIT_AUTHOR_EMAIL':'test@example.invalid',
                    'GIT_COMMITTER_NAME':'Synthetic', 'GIT_COMMITTER_EMAIL':'test@example.invalid'}
        self.git('init', '-q')
        self.commit()
        self.output = self.root / 'receiver.pyz'

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, env=self.env, stderr=subprocess.DEVNULL).decode().strip()

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-qm', 'synthetic receiver source')
        self.sha = self.git('rev-parse', 'HEAD')

    def build(self, **kwargs):
        return toolkit.build(self.repo, self.output, expected_tool_commit=kwargs.get('commit', self.sha))

    def cli(self, *args):
        return subprocess.run([sys.executable, '-I', '-S', str(self.output), *map(str,args)],
                              cwd=self.root, env={'PATH':os.environ.get('PATH','')}, capture_output=True, text=True, timeout=20)

    def test_deterministic_exact_committed_sources_no_workspace_secrets(self):
        original = (self.repo / 'scripts/offline_image_bundle.py').read_bytes()
        (self.repo / 'scripts/offline_image_bundle.py').write_text('UNCOMMITTED_POISON')
        (self.repo / 'database.env').write_text('PRIVATE_SENTINEL')
        result = self.build()
        raw = self.output.read_bytes()
        self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['bytes'], len(raw))
        self.assertFalse(result['runtime_included'])
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), {m+'.py' for m in toolkit.MODULES} | {'__main__.py','TOOLKIT.json','README.txt'})
            self.assertEqual(archive.read('offline_image_bundle.py'), original)
            metadata = json.loads(archive.read('TOOLKIT.json'))
            self.assertEqual(metadata['tool_commit'], self.sha)
            self.assertEqual(metadata['image_source_commit'], fixtures.SOURCE)
            for name, entry in metadata['files'].items():
                value = archive.read(name)
                self.assertEqual(entry, {'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()})
        self.assertNotIn(b'PRIVATE_SENTINEL', raw)
        self.output = self.root / 'second.pyz'
        self.build()
        self.assertEqual(raw, self.output.read_bytes())

    def test_all_commands_import_without_repository_or_site_packages(self):
        self.build()
        for command in ('bundle','transport','assembly','retention','preflight'):
            with self.subTest(command=command):
                result = self.cli(command, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(self.cli('unknown').returncode, 2)
        self.assertIn('DISABLED', self.cli('assembly').stdout)

    def test_receiver_roundtrip_preserves_trust_and_unready_defaults(self):
        self.build()
        fixture = fixtures.MediaRetentionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        before = fixture.snapshot()
        outer = self.root / 'media.tar'
        receipt = transport.pack(fixture.root, outer, expected_commit=fixtures.SOURCE, expected_manifest_sha256=fixture.digest)
        restored = self.root / 'received'
        args = ['--expected-commit',fixtures.SOURCE,'--expected-manifest-sha256',fixture.digest]
        bad = self.cli('transport','unpack',outer,restored,*args,'--expected-transport-sha256','a'*64)
        self.assertEqual(bad.returncode,2)
        self.assertFalse(restored.exists())
        good = self.cli('transport','unpack',outer,restored,*args,'--expected-transport-sha256',receipt['transport_sha256'])
        self.assertEqual(good.returncode,0,good.stderr)
        self.assertEqual(self.cli('bundle','verify',restored,*args).returncode,0)
        operator = self.root / 'operator'
        assembled = self.cli('assembly','assemble',restored,operator,'--run',*args)
        self.assertEqual(assembled.returncode,0,assembled.stderr)
        self.assertFalse(json.loads((operator/'operator.json').read_text())['database_preprovisioned'])
        self.assertNotEqual(self.cli('preflight',operator).returncode,0)
        self.assertEqual(self.cli('assembly','assemble',restored,operator,'--run',*args).returncode,2)
        self.assertEqual(before,fixture.snapshot())

    def test_wrong_commit_and_missing_module_refuse_before_output(self):
        with self.assertRaises(toolkit.ToolkitError): self.build(commit='a'*40)
        self.assertFalse(self.output.exists())
        (self.repo/'scripts/offline_media_retention.py').unlink()
        self.commit()
        with self.assertRaises(toolkit.ToolkitError): self.build()
        self.assertFalse(self.output.exists())

    def test_unbundled_dependency_and_changed_source_mapping_refused(self):
        path=self.repo/'scripts/offline_media_retention.py'
        for extra in ('\nimport missing_receiver_dependency\n', "\nIMAGE_SOURCE = '"+'a'*40+"'\n"):
            with self.subTest(extra=extra):
                path.write_bytes((ROOT/'scripts/offline_media_retention.py').read_bytes()+extra.encode())
                self.commit()
                with self.assertRaises(toolkit.ToolkitError): self.build()
                self.assertFalse(self.output.exists())

    def test_existing_and_symlink_output_not_overwritten(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(toolkit.ToolkitError): self.build()
        self.assertEqual(self.output.read_bytes(),b'keep')
        self.output=self.root/'link.pyz'
        self.output.symlink_to(self.root/'receiver.pyz')
        with self.assertRaises(toolkit.ToolkitError): self.build()
        self.assertEqual((self.root/'receiver.pyz').read_bytes(),b'keep')

    def test_write_failure_preserves_partial_and_reports_no_success(self):
        with patch.object(toolkit,'write_output',side_effect=OSError('private path')):
            with self.assertRaisesRegex(toolkit.ToolkitError,'REJECTED_OR_UNCONFIRMED'): self.build()
        self.assertTrue(self.output.exists())
        with self.assertRaises(toolkit.ToolkitError): self.build()

    def test_interrupt_and_close_failure_preserve_owned_output(self):
        with patch.object(toolkit,'write_output',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.build()
        self.assertTrue(self.output.exists())
        self.output = self.root/'close-failed.pyz'
        original = os.fdopen
        class FailedClose:
            def __init__(self,fd,*args): self.file=original(fd,*args)
            def __getattr__(self,name): return getattr(self.file,name)
            def __enter__(self): return self.file
            def close(self):
                self.file.close()
                raise OSError('private close details')
            def __exit__(self,*args): self.close()
        with patch.object(toolkit.os,'fdopen',side_effect=FailedClose):
            with self.assertRaises(toolkit.ToolkitError): self.build()
        self.assertTrue(self.output.exists())
        with self.assertRaises(toolkit.ToolkitError): self.build()

    def test_unknown_image_commit_refused_by_archived_consumer(self):
        self.build()
        dest = self.root/'must-not-exist'
        result=self.cli('assembly','assemble',self.root/'missing-source',dest,'--run',
                        '--expected-commit','a'*40,'--expected-manifest-sha256','b'*64)
        self.assertEqual(result.returncode,2)
        self.assertFalse(dest.exists())

    def test_git_replacement_blob_cannot_change_expected_commit_bytes(self):
        path='scripts/offline_image_bundle.py'
        original=(self.repo/path).read_bytes()
        old=self.git('rev-parse',self.sha+':'+path)
        replacement=self.root/'replacement.py'
        replacement.write_bytes(original+b'\nREPLACEMENT_SENTINEL=True\n')
        new=self.git('hash-object','-w',str(replacement))
        self.git('replace',old,new)
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read('offline_image_bundle.py'),original)

    def test_interrupt_survives_simultaneous_close_failure(self):
        original=os.fdopen
        class FailedClose:
            def __init__(self,fd,*args): self.file=original(fd,*args)
            def close(self):
                self.file.close()
                raise OSError('private close details')
            def __getattr__(self,name): return getattr(self.file,name)
            def __enter__(self): return self.file
            def __exit__(self,*args): self.close()
        with patch.object(toolkit.os,'fdopen',side_effect=FailedClose), \
             patch.object(toolkit,'write_output',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.build()
        self.assertTrue(self.output.exists())

    def test_short_receipt_write_does_not_report_success(self):
        class ShortStream:
            def write(self,text): return max(0,len(text)-1)
            def flush(self): pass
        with patch.object(toolkit.sys,'stdout',ShortStream()):
            code=toolkit.main(['--run','--source-root',str(self.repo),
                               '--destination',str(self.output),'--expected-tool-commit',self.sha])
        self.assertEqual(code,2)
        self.assertTrue(self.output.exists())

if __name__ == '__main__': unittest.main()
