"""Transport inventory tests only; fixtures are not installable npm packages."""
import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("offline_npm", ROOT / "scripts/offline_npm_inventory.py")
npm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(npm)


class OfflineNpmInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = self.root / "package-lock.json"
        self.cache = self.root / "artifacts"
        self.cache.mkdir()
        self.payload = b"synthetic transport bytes, not an npm archive"
        self.sri = "sha512-" + base64.b64encode(hashlib.sha512(self.payload).digest()).decode()
        self.package = {"version": "1.2.3", "resolved": "https://registry.npmjs.org/example/-/example-1.2.3.tgz",
                        "integrity": self.sri, "optional": True, "os": ["darwin"], "cpu": ["arm64"],
                        "hasInstallScript": True}
        self.data = {"lockfileVersion": 3, "packages": {"": {"name": "fixture"},
                                                      "node_modules/example": self.package}}
        self.write()
        self.artifact = self.cache / ("sha512-" + hashlib.sha512(self.payload).hexdigest() + ".tgz")
        self.artifact.write_bytes(self.payload)

    def write(self):
        self.lock.write_text(json.dumps(self.data))

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = npm.main([str(self.lock), *map(str, args)])
        return status, out.getvalue(), err.getvalue()

    def rejected(self, *args):
        code, out, err = self.run_cli(*args)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "offline npm inventory: validation failed\n")

    def test_real_lock_all_packages_and_deterministic_output(self):
        path = ROOT / "frontend/package-lock.json"
        lock, sha = npm.read_lock(path)
        result = npm.inventory(lock, sha)
        self.assertEqual(result["package_count"], len(lock["packages"]) - 1)
        occurrences = [p for a in result["artifacts"] for p in a["packages"]]
        self.assertEqual({p["location"] for p in occurrences}, set(lock["packages"]) - {""})
        self.assertTrue(any("darwin" in p["os"] for p in occurrences))
        self.assertTrue(any("win32" in p["os"] for p in occurrences))
        self.assertTrue(any(p["hasInstallScript"] for p in occurrences))
        reversed_lock = copy.deepcopy(lock)
        reversed_lock["packages"] = dict(reversed(list(lock["packages"].items())))
        self.assertEqual(result, npm.inventory(reversed_lock, sha))
        self.assertEqual(result["status"], "INVENTORY_ONLY")
        self.assertIn("No installation or runtime completeness", result["limitations"])

    def test_inventory_and_cache_success_read_only(self):
        before = self.lock.read_bytes(), self.artifact.read_bytes()
        code, out, err = self.run_cli()
        self.assertEqual((code, err), (0, "INVENTORY_ONLY\n"))
        self.assertNotIn("size_bytes", json.loads(out)["artifacts"][0])
        code, out, err = self.run_cli("--artifacts", self.cache)
        self.assertEqual((code, err), (0, "ARTIFACT_BYTES_VERIFIED\n"))
        self.assertEqual(json.loads(out)["artifacts"][0]["size_bytes"], len(self.payload))
        self.assertEqual(before, (self.lock.read_bytes(), self.artifact.read_bytes()))

    def test_dedup_preserves_occurrence_metadata(self):
        other = copy.deepcopy(self.package)
        other.update(optional=False, os=["linux"])
        self.data["packages"]["node_modules/parent/node_modules/example"] = other
        self.write()
        code, out, _ = self.run_cli("--artifacts", self.cache)
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((result["artifact_count"], result["package_count"]), (1, 2))
        self.assertEqual(len(result["artifacts"][0]["packages"]), 2)

    def test_conflicting_digest_or_source(self):
        for changes in ({"version": "1.2.4", "resolved": self.package["resolved"].replace("1.2.3", "1.2.4")},
                        {"integrity": "sha512-" + base64.b64encode(b"x" * 64).decode()}):
            with self.subTest(changes=changes):
                other = {**self.package, **changes}
                self.data["packages"]["node_modules/parent/node_modules/example"] = other
                self.write()
                self.rejected()

    def test_untrusted_sources(self):
        urls = ["http://registry.npmjs.org/example/-/example-1.2.3.tgz",
                "https://evil.test/example/-/example-1.2.3.tgz",
                "https://registry.npmjs.org.evil.test/example/-/example-1.2.3.tgz",
                "https://user:SECRET@registry.npmjs.org/example/-/example-1.2.3.tgz",
                "https://registry.npmjs.org:443/example/-/example-1.2.3.tgz",
                self.package["resolved"] + "?token=SECRET", self.package["resolved"] + "#SECRET",
                "file:../secret", "git+https://example.test/repo.git",
                self.package["resolved"].replace("example/-/", "example/../"),
                self.package["resolved"].replace("example/-/", "%65xample/-/"),
                self.package["resolved"] + "\n", self.package["resolved"].replace("1.2.3", "1.2.4")]
        for url in urls:
            with self.subTest(url=url):
                self.package["resolved"] = url
                self.write()
                self.rejected()

    def test_invalid_versions_integrities_flags_platforms(self):
        invalid = {"version": ["latest", "^1.2.3", "01.2.3", "1.2.3-01", "1.2", True, None],
                   "integrity": [None, "sha1-abc", self.sri + " " , self.sri + " " + self.sri,
                                 self.sri[:-3] + "B=="],
                   "optional": ["true", 1], "cpu": ["arm64", ["arm64", "arm64"], ["../secret"], [True]],
                   "link": [True, 0, ""], "inBundle": [True, None]}
        original = copy.deepcopy(self.package)
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.package.clear()
                    self.package.update(original)
                    self.package[field] = value
                    self.write()
                    self.rejected()

    def test_missing_required_and_invalid_structure(self):
        for field in ("version", "resolved", "integrity"):
            original = self.package.pop(field)
            self.write()
            self.rejected()
            self.package[field] = original
        for value in [None, [], {}, {"lockfileVersion": True}, {"lockfileVersion": 2, "packages": {}},
                      {"lockfileVersion": 3, "packages": {"": {}, "../escape": self.package}}]:
            self.lock.write_text(json.dumps(value))
            self.rejected()

    def test_malformed_duplicate_and_complex_json(self):
        for text in ["{", '{"lockfileVersion":3,"lockfileVersion":3}', '{"x":NaN}',
                     '{"x":Infinity}', '{"x":1e999}', '["\ud800"]'.encode("utf-8", errors="surrogatepass").decode("latin1"),
                     '[' * 2000 + '0' + ']' * 2000]:
            self.lock.write_text(text)
            self.rejected()
        self.write()
        with patch.object(npm, "MAX_LOCK_BYTES", 2):
            self.rejected()
        with patch.object(npm, "MAX_JSON_NODES", 2):
            self.rejected()
        with patch.object(npm, "MAX_PACKAGES", 0):
            self.rejected()

    def test_cache_missing_tampered_extra_directory_and_empty(self):
        self.artifact.unlink()
        self.rejected("--artifacts", self.cache)
        for payload in (b"tampered", b""):
            self.artifact.write_bytes(payload)
            self.rejected("--artifacts", self.cache)
        self.artifact.write_bytes(self.payload)
        extra = self.cache / "extra.tgz"
        extra.write_bytes(self.payload)
        self.rejected("--artifacts", self.cache)
        extra.unlink()
        self.artifact.unlink()
        self.artifact.mkdir()
        self.rejected("--artifacts", self.cache)

    def test_symlink_file_parent_and_traversal(self):
        real = self.root / "real"
        self.artifact.rename(real)
        self.artifact.symlink_to(real)
        self.rejected("--artifacts", self.cache)
        self.artifact.unlink()
        real.rename(self.artifact)
        link = self.root / "linked"
        link.symlink_to(self.cache, target_is_directory=True)
        self.rejected("--artifacts", link)
        self.rejected("--artifacts", self.cache / ".." / "artifacts")
        source = self.root / "source.json"
        self.lock.rename(source)
        self.lock.symlink_to(source)
        self.rejected()
        self.lock.unlink()
        source.rename(self.lock)
        parent_link = self.root / "parent-link"
        parent_link.symlink_to(self.root, target_is_directory=True)
        self.lock = parent_link / "package-lock.json"
        self.rejected()

    def test_hardlinks_fifo_and_bounds(self):
        duplicate = self.root / "hardlink"
        os.link(self.artifact, duplicate)
        self.rejected("--artifacts", self.cache)
        duplicate.unlink()
        with patch.object(npm, "MAX_ARTIFACT_BYTES", 2):
            self.rejected("--artifacts", self.cache)
        with patch.object(npm, "MAX_TOTAL_BYTES", 2):
            self.rejected("--artifacts", self.cache)
        self.artifact.unlink()
        os.mkfifo(self.artifact)
        result = subprocess.run([sys.executable, str(ROOT / "scripts/offline_npm_inventory.py"),
                                 str(self.lock), "--artifacts", str(self.cache)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.lock.unlink()
        os.mkfifo(self.lock)
        self.rejected()

    def test_late_failure_emits_no_partial_manifest(self):
        other = copy.deepcopy(self.package)
        other.update(version="2.0.0", resolved=other["resolved"].replace("1.2.3", "2.0.0"),
                     integrity="sha512-" + base64.b64encode(b"z" * 64).decode())
        self.data["packages"]["node_modules/other/node_modules/example"] = other
        self.write()
        (self.cache / ("sha512-" + (b"z" * 64).hex() + ".tgz")).write_bytes(b"wrong")
        self.rejected("--artifacts", self.cache)

    def test_scoped_prerelease_alias_and_canonical_zero_digest(self):
        self.package.update(version="1.2.3-rc.1+build.2",
                            resolved="https://registry.npmjs.org/@scope/example/-/example-1.2.3-rc.1+build.2.tgz",
                            integrity="sha512-" + base64.b64encode(bytes(64)).decode())
        self.write()
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["artifacts"][0]["name"], "@scope/example")

    def test_invalid_utf8_depth_and_file_mutation(self):
        self.lock.write_bytes(b"\xff")
        self.rejected()
        self.lock.write_text("[" * 65 + "0" + "]" * 65)
        self.rejected()
        self.write()
        with npm.directory(self.root) as fd:
            with self.assertRaises(npm.InventoryError):
                with npm.regular_file(fd, self.lock.name):
                    self.lock.write_bytes(b"changed")

    def test_argument_errors_are_redacted(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as result:
            npm.main(["--unknown=SECRET"])
        self.assertEqual(result.exception.code, 2)
        self.assertNotIn("SECRET", err.getvalue())


if __name__ == "__main__":
    unittest.main()
