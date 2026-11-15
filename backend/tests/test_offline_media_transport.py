"""Synthetic transport bytes only: no Docker, network or upload."""
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
import test_offline_media_retention as fixtures
SOURCE = fixtures.SOURCE
import offline_media_transport as transport

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.MediaRetentionTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture.root
        self.outer = self.source.parent / 'transport.tar'
        self.destination = self.source.parent / 'received'
        self.kw = dict(expected_commit=SOURCE, expected_manifest_sha256=self.fixture.digest)

    def pack(self):
        return transport.pack(self.source, self.outer, **self.kw)

    def unpack(self, digest):
        return transport.unpack(self.outer, self.destination, expected_transport_sha256=digest, **self.kw)

    def test_roundtrip_preserves_inner_bytes_and_distinct_trust(self):
        before = self.fixture.snapshot()
        with patch('subprocess.run', side_effect=AssertionError('no process')):
            result = self.pack()
            self.assertEqual(result['transport_bytes'], self.outer.stat().st_size)
            self.assertEqual(result['transport_sha256'], hashlib.sha256(self.outer.read_bytes()).hexdigest())
            self.assertNotEqual(result['transport_sha256'], self.fixture.digest)
            self.assertFalse(result['upload_authorized'])
            self.assertFalse(result['inventory']['stored_artifact_size_verified'])
            restored = self.unpack(result['transport_sha256'])
        self.assertEqual(restored['inventory']['handoff_manifest_sha256'], self.fixture.digest)
        self.assertEqual(before, self.fixture.snapshot())
        self.assertEqual({p.name:p.read_bytes() for p in self.destination.iterdir()}, {n:v[0] for n,v in before.items()})

    def test_bad_inner_digest_and_source_refused_before_output(self):
        for key, value in [('expected_commit','b'*40), ('expected_manifest_sha256','b'*64)]:
            with self.subTest(key=key):
                args = {**self.kw,key:value}
                with self.assertRaises(transport.TransportError): transport.pack(self.source,self.outer,**args)
                self.assertFalse(self.outer.exists())

    def test_existing_output_never_overwritten(self):
        self.outer.write_bytes(b'keep')
        with self.assertRaises(transport.TransportError): self.pack()
        self.assertEqual(self.outer.read_bytes(),b'keep')

    def test_corrupt_outer_rejected_before_destination(self):
        result = self.pack()
        raw = self.outer.read_bytes()
        for data in (raw[:-1],raw+b'x',b'../escape'+raw[9:],raw[:512]+b'x'+raw[513:]):
            self.outer.write_bytes(data)
            with self.assertRaises(transport.TransportError): self.unpack(result['transport_sha256'])
            self.assertFalse(self.destination.exists())

    def test_noncanonical_header_rejected_even_with_matching_outer_hash(self):
        self.pack()
        raw = self.outer.read_bytes()
        for offset, value in [(0,b'../'),(156,b'2'),(100,b'0000777')]:
            data = raw[:offset]+value+raw[offset+len(value):]
            self.outer.write_bytes(data)
            with self.assertRaises(transport.TransportError): self.unpack(hashlib.sha256(data).hexdigest())
            self.assertFalse(self.destination.exists())

    def test_outer_cap_includes_headers_and_padding(self):
        total = sum(p.stat().st_size for p in self.source.iterdir())
        with patch.object(transport.media,'MAX_UPLOAD_BYTES',total):
            with self.assertRaises(transport.TransportError): self.pack()
        self.assertFalse(self.outer.exists())

    def test_symlink_source_and_output_refused(self):
        self.outer.symlink_to(self.source/'api.tar')
        with self.assertRaises(transport.TransportError): self.pack()
        self.assertTrue(self.outer.is_symlink())

    def test_valid_but_forbidden_tar_records_and_trailers(self):
        self.pack()
        original = self.outer.read_bytes()
        import tarfile
        headers = []
        for name, kind in [('../escape',tarfile.REGTYPE),('COMPLETE',tarfile.SYMTYPE),
                           ('COMPLETE',tarfile.LNKTYPE),('COMPLETE',tarfile.DIRTYPE),
                           ('api.tar',tarfile.REGTYPE),('COMPLETE',tarfile.XHDTYPE)]:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.mode = 0o600
            headers.append(info.tobuf(format=tarfile.USTAR_FORMAT))
        cases = [h+original[512:] for h in headers]
        cases += [original+b'\0'*512,original[:-1],original[:-1]+b'x']
        for data in cases:
            with self.subTest(header=data[:20]):
                self.outer.write_bytes(data)
                with self.assertRaises(transport.TransportError): self.unpack(hashlib.sha256(data).hexdigest())
                self.assertFalse(self.destination.exists())

    def test_wrong_inner_trust_not_replaced_by_outer_digest(self):
        result = self.pack()
        with self.assertRaises(transport.TransportError):
            transport.unpack(self.outer,self.destination,expected_commit=SOURCE,
                expected_manifest_sha256='b'*64,expected_transport_sha256=result['transport_sha256'])
        self.assertFalse(self.destination.exists())

    def test_existing_unpack_destination_preserved(self):
        result = self.pack()
        self.destination.mkdir()
        (self.destination/'keep').write_bytes(b'keep')
        with self.assertRaises(transport.TransportError): self.unpack(result['transport_sha256'])
        self.assertEqual((self.destination/'keep').read_bytes(),b'keep')

    def test_write_failure_leaves_exclusive_output_no_receipt_or_retry(self):
        with patch.object(transport,'write',side_effect=OSError('PRIVATE')):
            with self.assertRaisesRegex(transport.TransportError,'^MEDIA_TRANSPORT_REJECTED_OR_UNCONFIRMED$'): self.pack()
        self.assertTrue(self.outer.exists())
        with self.assertRaises(transport.TransportError): self.pack()

    def test_pack_interrupt_remains_interrupt(self):
        with patch.object(transport,'write',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.pack()

    def test_unpack_interrupt_has_no_complete_marker(self):
        result = self.pack()
        with patch.object(transport,'write',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.unpack(result['transport_sha256'])
        self.assertFalse((self.destination/'COMPLETE').exists())

    def test_unpack_payload_close_failure_has_no_complete_marker(self):
        import offline_image_bundle as bundle
        result = self.pack()
        close = bundle.Descriptor.close
        def failing(value):
            fd = value.fd
            is_payload = fd is not None and os.readlink('/proc/self/fd/'+str(fd)).startswith(str(self.destination)+'/')
            close(value)
            if is_payload: raise OSError('PRIVATE_CLOSE')
        with patch.object(bundle.Descriptor,'close',failing):
            with self.assertRaises(transport.TransportError): self.unpack(result['transport_sha256'])
        self.assertFalse((self.destination/'COMPLETE').exists())

    def test_low_capacity_rejected_before_output(self):
        with patch.object(transport,'capacity',side_effect=OSError('full')):
            with self.assertRaises(transport.TransportError): self.pack()
        self.assertFalse(self.outer.exists())

    def test_inner_invalid_payload_has_no_completion_marker(self):
        self.pack()
        data = bytearray(self.outer.read_bytes())
        # COMPLETE header at0, API header at512, API bytes at1024.
        data[1024] ^= 1
        self.outer.write_bytes(data)
        with self.assertRaises(transport.TransportError): self.unpack(hashlib.sha256(data).hexdigest())
        self.assertFalse((self.destination/'COMPLETE').exists())

    def test_member_size_limit_rejected_before_output(self):
        with patch.object(transport,'MAX_MEMBER_BYTES',10):
            with self.assertRaises(transport.TransportError): self.pack()
        self.assertFalse(self.outer.exists())

    def test_default_cli_inert(self):
        with patch.object(transport,'pack', side_effect=AssertionError):
            self.assertEqual(transport.main([]),0)

if __name__ == '__main__': unittest.main()
