"""Synthetic tarballs test the read-only audit, never installation or downloads."""
import base64
import contextlib
import gzip
import hashlib
import importlib.util
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
sys.path.insert(0, str(ROOT / "scripts"))
import offline_npm_artifacts as audit


class OfflineNpmArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = self.root / "package-lock.json"
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.package = {"name": "example", "version": "1.2.3", "os": ["linux"],
                        "cpu": ["x64"], "libc": ["glibc"],
                        "scripts": {"install": "node install.js", "prepare": "node prepare.js"}}
        self.write_archive()

    def write_archive(self, members=None, raw_json=None, lock_changes=None):
        payload = json.dumps(self.package).encode() if raw_json is None else raw_json
        members = [("package/package.json", payload, tarfile.REGTYPE)] if members is None else members
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as archive:
            for name, data, kind in members:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(data)
                if kind in (tarfile.LNKTYPE, tarfile.SYMTYPE):
                    info.linkname = "../secret"
                archive.addfile(info, io.BytesIO(data))
        raw = buf.getvalue()
        for path in self.artifacts.iterdir():
            path.unlink()
        self.file = self.artifacts / ("sha512-" + hashlib.sha512(raw).hexdigest() + ".tgz")
        self.file.write_bytes(raw)
        entry = {"version": "1.2.3", "resolved": "https://registry.npmjs.org/example/-/example-1.2.3.tgz",
                 "integrity": "sha512-" + base64.b64encode(hashlib.sha512(raw).digest()).decode(),
                 "os": ["linux"], "cpu": ["x64"], "libc": ["glibc"], "hasInstallScript": True}
        entry.update(lock_changes or {})
        self.lock.write_text(json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/example": entry}}))

    def run_cli(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audit.main([str(self.lock), str(self.artifacts)])
        return code, out.getvalue(), err.getvalue()

    def replace_raw(self, raw):
        data = json.loads(self.lock.read_text())
        digest = hashlib.sha512(raw)
        data["packages"]["node_modules/example"]["integrity"] = "sha512-" + base64.b64encode(digest.digest()).decode()
        self.file.unlink()
        self.file = self.artifacts / ("sha512-" + digest.hexdigest() + ".tgz")
        self.file.write_bytes(raw)
        self.lock.write_text(json.dumps(data))

    def rejected(self):
        self.assertEqual(self.run_cli(), (1, "", "offline npm artifacts: validation failed\n"))

    def test_success_deterministic_readonly_and_metadata(self):
        before = self.file.read_bytes(), self.lock.read_bytes()
        first = self.run_cli()
        self.assertEqual(first, self.run_cli())
        self.assertEqual(first[0], 0)
        value = json.loads(first[1])
        self.assertEqual(value["status"], "ARTIFACT_BYTES_VERIFIED_METADATA_RECORDED")
        self.assertEqual(value["total_size_bytes"], self.file.stat().st_size)
        meta = value["artifacts"][0]["archive_metadata"]
        self.assertEqual(meta["lifecycle_scripts"], self.package["scripts"])
        self.assertEqual(meta["libc"], ["glibc"])
        self.assertFalse(meta["binding_gyp"])
        self.assertIn("not", value["limitations"].lower())
        self.assertEqual(before, (self.file.read_bytes(), self.lock.read_bytes()))

    def test_real_manifest_preserves_every_lock_occurrence(self):
        lock, sha256 = audit.inventory.read_lock(ROOT / "frontend/package-lock.json")
        expected = audit.inventory.inventory(lock, sha256)
        recorded = json.loads((ROOT / "frontend/offline-npm-artifacts.json").read_text())
        for field in ("lockfile_sha256", "scope", "package_count", "artifact_count"):
            self.assertEqual(recorded[field], expected[field])
        self.assertEqual(len(recorded["artifacts"]), len(expected["artifacts"]))
        for actual, source in zip(recorded["artifacts"], expected["artifacts"]):
            self.assertEqual({field: actual[field] for field in source}, source)
            self.assertEqual(actual["archive_metadata"]["name"], source["name"])
            self.assertEqual(actual["archive_metadata"]["version"], source["version"])
            self.assertIs(type(actual["size_bytes"]), int)
            self.assertTrue(0 < actual["size_bytes"] <= audit.inventory.MAX_ARTIFACT_BYTES)
        self.assertEqual(recorded["total_size_bytes"], sum(a["size_bytes"] for a in recorded["artifacts"]))
        self.assertEqual(recorded["status"], "ARTIFACT_BYTES_VERIFIED_METADATA_RECORDED")

    def test_optional_dependency_metadata_and_total_expanded_limit(self):
        self.package["optionalDependencies"] = {"@scope/binary": "1.2.3"}
        self.write_archive()
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["artifacts"][0]["archive_metadata"]["optional_dependencies"],
                         self.package["optionalDependencies"])
        with patch.object(audit, "MAX_TOTAL_EXPANDED_BYTES", 1):
            self.rejected()

    def test_missing_duplicate_or_nonregular_package_json(self):
        payload = json.dumps(self.package).encode()
        for members in [[], [("package/other.json", payload, tarfile.REGTYPE)],
                        [("package/package.json", payload, tarfile.REGTYPE)] * 2,
                        [("package/package.json", b"", tarfile.SYMTYPE)],
                        [("package/package.json", b"", tarfile.LNKTYPE)],
                        [("package/./package.json", payload, tarfile.REGTYPE)]]:
            with self.subTest(members=members):
                self.write_archive(members)
                self.rejected()

    def test_package_name_and_version_mismatch(self):
        for field, bad in [("name", "other"), ("version", "1.2.4")]:
            with self.subTest(field=field):
                old = self.package[field]
                self.package[field] = bad
                self.write_archive()
                self.rejected()
                self.package[field] = old

    def test_script_metadata_discrepancies_preserve_both_directions(self):
        for lock_flag, scripts in [(False, {"install": "node install.js"}), (True, {})]:
            with self.subTest(lock_flag=lock_flag):
                self.package["scripts"] = scripts
                self.write_archive(lock_changes={"hasInstallScript": lock_flag})
                code, out, _ = self.run_cli()
                self.assertEqual(code, 0)
                result = json.loads(out)
                self.assertEqual(result["artifacts"][0]["packages"][0]["hasInstallScript"], lock_flag)
                differences = result["artifacts"][0]["archive_metadata"]["install_script_discrepancies"]
                self.assertEqual(differences, [{"location": "node_modules/example",
                                              "lock_has_install_script": lock_flag,
                                              "archive_has_install_script_evidence": not lock_flag}])

    def test_unique_safe_legacy_archive_roots_are_preserved(self):
        for root in ("react", "node-fetch", "node v22.20"):
            with self.subTest(root=root):
                self.write_archive([(root, b"", tarfile.DIRTYPE),
                                    (root + "/package.json", json.dumps(self.package).encode(), tarfile.REGTYPE)])
                code, out, _ = self.run_cli()
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)["artifacts"][0]["archive_metadata"]["archive_root"], root)

    def test_multiple_roots_and_root_file_rejected(self):
        payload = json.dumps(self.package).encode()
        for members in [[("one/package.json", payload, tarfile.REGTYPE), ("two/file", b"x", tarfile.REGTYPE)],
                        [("package", payload, tarfile.REGTYPE)],
                        [("package.json", payload, tarfile.REGTYPE)]]:
            with self.subTest(members=members):
                self.write_archive(members)
                self.rejected()

    def test_platform_mismatch_or_invalid_platform(self):
        for field in ("os", "cpu", "libc"):
            for value in (["other"], "linux", ["linux", "linux"], [True], ["../secret"]):
                with self.subTest(field=field, value=value):
                    old = self.package[field]
                    self.package[field] = value
                    self.write_archive()
                    self.rejected()
                    self.package[field] = old

    def test_absent_lock_libc_preserves_archive_platform(self):
        # npm locks may omit libc even for platform-specific native packages.
        data = json.loads(self.lock.read_text())
        del data["packages"]["node_modules/example"]["libc"]
        self.lock.write_text(json.dumps(data))
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["artifacts"][0]["archive_metadata"]["libc"], ["glibc"])

    def test_default_node_gyp_install_is_recorded(self):
        self.package["scripts"] = {}
        self.write_archive([(name, data, tarfile.REGTYPE) for name, data in
                            [("package/package.json", json.dumps(self.package).encode()),
                             ("package/binding.gyp", b"{}")]])
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["artifacts"][0]["archive_metadata"]["binding_gyp"])

    def test_gypfile_false_is_preserved_not_inferred_install(self):
        self.package.update(scripts={}, gypfile=False)
        self.write_archive([(name, data, tarfile.REGTYPE) for name, data in
                            [("package/package.json", json.dumps(self.package).encode()),
                             ("package/binding.gyp", b"{}")]], lock_changes={"hasInstallScript": False})
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        meta = json.loads(out)["artifacts"][0]["archive_metadata"]
        self.assertFalse(meta["gypfile"])
        self.assertFalse(meta["binding_gyp_default_candidate"])
        self.assertEqual(meta["install_script_discrepancies"], [])

    def test_prepare_alone_is_not_dependency_install_script(self):
        self.package["scripts"] = {"prepare": "node prepare.js"}
        self.write_archive(lock_changes={"hasInstallScript": False})
        self.assertEqual(self.run_cli()[0], 0)

    def test_invalid_json_and_duplicate_keys(self):
        for raw in (b"{", b"[]", b"null", b"\xff", b'{"name":"x","name":"y"}',
                    b'{"x":NaN}', b'{"x":1e999}', b"[" * 70 + b"0" + b"]" * 70):
            with self.subTest(raw=raw):
                self.write_archive(raw_json=raw)
                self.rejected()

    def test_invalid_scripts_and_oversized_scripts(self):
        for value in ([], None, {"install": False}, {"install": "x" * 65537}):
            with self.subTest(value=type(value)):
                self.package["scripts"] = value
                self.write_archive()
                self.rejected()

    def test_archive_and_json_bounds(self):
        for setting, value in [("MAX_JSON_BYTES", 2), ("MAX_EXPANDED_BYTES", 100),
                               ("MAX_MEMBERS", 0), ("MAX_JSON_NODES", 1)]:
            with self.subTest(setting=setting), patch.object(audit, setting, value):
                self.rejected()

    def test_damaged_tarball_with_valid_hash_is_rejected(self):
        raw = b"not a gzip file"
        self.file.write_bytes(raw)
        data = json.loads(self.lock.read_text())
        digest = hashlib.sha512(raw)
        data["packages"]["node_modules/example"]["integrity"] = "sha512-" + base64.b64encode(digest.digest()).decode()
        self.file.rename(self.artifacts / ("sha512-" + digest.hexdigest() + ".tgz"))
        self.lock.write_text(json.dumps(data))
        self.rejected()

    def test_corrupt_gzip_tail_has_fixed_failure(self):
        raw = gzip.compress(gzip.decompress(self.file.read_bytes()) + b"\0" * 20480)
        raw += b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff\x07" + b"\0" * 8
        self.replace_raw(raw)
        self.rejected()

    def test_nonzero_trailing_archive_data_is_rejected(self):
        for suffix in (b"hidden", gzip.decompress(self.file.read_bytes())):
            with self.subTest(size=len(suffix)):
                self.write_archive()
                self.replace_raw(gzip.compress(gzip.decompress(self.file.read_bytes()) + suffix))
                self.rejected()

    def test_malformed_truncated_and_missing_terminal_headers_rejected(self):
        original = gzip.decompress(self.file.read_bytes())
        info = tarfile.TarInfo.frombuf(original[:512], "utf-8", "surrogateescape")
        content = original[:512 + ((info.size + 511) // 512) * 512]
        for suffix in (b"X" * 512 + b"\0" * 1024, b"bad", b""):
            with self.subTest(suffix_size=len(suffix)):
                self.replace_raw(gzip.compress(content + suffix))
                self.rejected()

    def test_unsupported_tarfile_hook_rejected_before_input_reads(self):
        with patch.object(tarfile.TarInfo, "_fromtarfile", None), \
                patch.object(audit.inventory, "read_lock", side_effect=AssertionError("must fail before reading")):
            self.rejected()

    def test_regular_trailing_slash_and_duplicate_paths_are_rejected(self):
        package = ("package/package.json", json.dumps(self.package).encode(), tarfile.REGTYPE)
        for members in ([package, ("package/package.json/", b"{}", tarfile.REGTYPE)],
                        [package, ("package/x", b"one", tarfile.REGTYPE), ("package/x", b"two", tarfile.REGTYPE)]):
            with self.subTest(members=members):
                self.write_archive(members)
                self.rejected()

    def test_extended_headers_are_bounded_before_payload_read(self):
        for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
            with self.subTest(kind=kind):
                info = tarfile.TarInfo("package/extended")
                info.type = kind
                info.size = 65537
                self.replace_raw(gzip.compress(info.tobuf() + b"x" * 65537 + b"\0" * 10240))
                self.rejected()

    def test_extension_limit_precedes_stdlib_allocation(self):
        info = audit.BoundedTarInfo("package/extended")
        info.size = 65537
        for method in ("_proc_pax", "_proc_gnulong"):
            with self.subTest(method=method), self.assertRaises(audit.inventory.InventoryError):
                getattr(info, method)(None)

    def test_pax_sparse_maps_rejected_before_processing(self):
        info = audit.BoundedTarInfo("package/sparse")
        for method in ("_proc_sparse", "_proc_gnusparse_00", "_proc_gnusparse_01", "_proc_gnusparse_10"):
            with self.subTest(method=method), self.assertRaises(audit.inventory.InventoryError):
                getattr(info, method)(None)

    def test_nested_pax_headers_count_against_limit(self):
        info = tarfile.TarInfo("package/PaxHeader")
        info.type = tarfile.XHDTYPE
        self.replace_raw(gzip.compress(info.tobuf() * 3 + gzip.decompress(self.file.read_bytes())))
        with patch.object(audit, "MAX_MEMBERS", 1):
            self.rejected()

    def test_sparse_headers_are_rejected(self):
        info = tarfile.TarInfo("package/sparse")
        info.type = tarfile.GNUTYPE_SPARSE
        self.replace_raw(gzip.compress(info.tobuf() + b"\0" * 10240))
        self.rejected()

    def test_tampered_missing_and_extra_artifacts(self):
        self.file.write_bytes(b"tampered")
        self.rejected()
        self.write_archive()
        self.file.unlink()
        self.rejected()
        self.write_archive()
        (self.artifacts / "extra").write_bytes(b"unexpected")
        self.rejected()

    def test_symlink_and_hardlink_artifacts(self):
        original = self.root / "source"
        self.file.rename(original)
        self.file.symlink_to(original)
        self.rejected()
        self.file.unlink()
        os.link(original, self.file)
        self.rejected()

    def test_cli_argument_errors_are_fixed(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                audit.main(["--SECRET"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "offline npm artifacts: invalid arguments\n")


if __name__ == "__main__":
    unittest.main()
