"""Synthetic wheel contracts; real downloaded artifacts are validated separately."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "offline_python", ROOT / "scripts/offline_python_wheelhouse.py")
wheelhouse = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wheelhouse)
NATIVE = (sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12)
          and sys.platform == "linux" and platform.machine() == "x86_64")


class OfflinePythonWheelhouseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.wheels = self.root / "wheels"
        self.wheels.mkdir()
        self.requirements = self.root / "requirements.txt"
        self.requirements.write_text("example[feature]==1.0\n")
        self.report = self.root / "report.json"
        self.manifest_path = self.root / "manifest.json"
        self.lock_path = self.root / "requirements.lock"
        self.data = {"version": "1", "pip_version": "26.2.2",
                     "environment": {"implementation_name": "cpython", "python_version": "3.12",
                                     "sys_platform": "linux", "platform_machine": "x86_64"}, "install": []}
        self.add_wheel("example", "1.0", ['helper>=2', 'optional==4.0; extra == "feature"'], ["feature"])
        self.add_wheel("helper", "2.0", ["leaf==3.0"])
        self.add_wheel("leaf", "3.0")
        self.add_wheel("optional", "4.0")
        self.write_report()
        self.manifest = wheelhouse.create_inventory(self.requirements, self.report, self.wheels)
        self.write_manifest()

    def add_wheel(self, name, version, dependencies=(), extras=(), tag="py3-none-any"):
        filename = f"{name}-{version}-{tag}.whl"
        path = self.wheels / filename
        prefix = f"{name}-{version}.dist-info/"
        metadata = f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\nRequires-Python: >=3.10\n"
        metadata += "".join(f"Requires-Dist: {dep}\n" for dep in dependencies)
        metadata += "".join(f"Provides-Extra: {extra}\n" for extra in extras)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(prefix + "METADATA", metadata + "\n")
            archive.writestr(prefix + "WHEEL", f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: {tag}\n\n")
            archive.writestr(prefix + "RECORD", "")
        self.data["install"].append({
            "download_info": {"url": "https://files.pythonhosted.org/packages/aa/bb/" + "c" * 60 + "/" + filename,
                              "archive_info": {"hashes": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}},
            "is_direct": False, "is_yanked": False, "requested": name == "example",
            "metadata": {"name": name, "version": version},
            **({"requested_extras": ["feature"]} if name == "example" else {})})
        return path

    def write_report(self):
        self.report.write_text(json.dumps(self.data))

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.lock_path.write_text(wheelhouse.lock_text(self.manifest))

    def verify(self):
        return wheelhouse.verify(self.requirements, self.manifest_path, self.lock_path, self.wheels)

    def cli(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = wheelhouse.main(["verify", "--requirements", str(self.requirements),
                "--manifest", str(self.manifest_path), "--lock", str(self.lock_path),
                "--wheelhouse", str(self.wheels)])
        return status, out.getvalue(), err.getvalue()

    def assert_rejected(self):
        self.assertEqual(self.cli(), (1, "", "offline python wheelhouse: validation failed\n"))

    def test_real_inventory_and_lock_match_original_requirements(self):
        requirements = (ROOT / "backend/requirements.txt").read_bytes()
        manifest, _ = wheelhouse.read_json(ROOT / "backend/offline-python-wheelhouse.json")
        wheelhouse.validate_manifest(manifest, requirements)
        self.assertEqual(len(manifest["artifacts"]), 30)
        self.assertEqual(len(manifest["direct_requirements"]), 7)
        self.assertEqual((ROOT / "backend/requirements-linux-cp312.lock").read_text(), wheelhouse.lock_text(manifest))
        roots = {p["name"]: p["extras"] for p in manifest["direct_requirements"]}
        self.assertEqual(roots["uvicorn"], ["standard"])
        self.assertEqual(roots["psycopg"], ["binary"])
        self.assertEqual(roots["pyjwt"], ["crypto"])

    def test_inventory_is_deterministic_and_byte_verified(self):
        self.data["install"].reverse()
        self.write_report()
        other = wheelhouse.create_inventory(self.requirements, self.report, self.wheels)
        self.assertEqual(other["artifacts"], self.manifest["artifacts"])
        self.assertEqual(wheelhouse.lock_text(other), wheelhouse.lock_text(self.manifest))
        self.assertIn("example[feature]==1.0 --hash=sha256:", wheelhouse.lock_text(other))
        self.assertEqual(wheelhouse.verify_artifacts(other, self.wheels),
                         sum(a["size_bytes"] for a in other["artifacts"]))

    @unittest.skipUnless(NATIVE, "pip closure requires Linux x86_64 / CPython 3.12")
    def test_actual_pip_offline_closure_without_installing(self):
        before = {p.name: p.read_bytes() for p in self.wheels.iterdir()}
        result = self.verify()
        self.assertEqual(result["status"], "OFFLINE_PIP_CLOSURE_VERIFIED")
        self.assertEqual(result["wheel_count"], 4)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.wheels.iterdir()})
        self.assertNotIn("example", sys.modules)

    @unittest.skipUnless(NATIVE, "pip closure requires Linux x86_64 / CPython 3.12")
    def test_actual_pip_rejects_missing_transitive_dependency(self):
        artifact = next(a for a in self.manifest["artifacts"] if a["name"] == "leaf")
        (self.wheels / artifact["filename"]).unlink()
        self.manifest["artifacts"].remove(artifact)
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "pip offline closure failed"):
            self.verify()

    @unittest.skipUnless(NATIVE, "pip closure requires Linux x86_64 / CPython 3.12")
    def test_actual_pip_rejects_missing_extra_dependency(self):
        artifact = next(a for a in self.manifest["artifacts"] if a["name"] == "optional")
        (self.wheels / artifact["filename"]).unlink()
        self.manifest["artifacts"].remove(artifact)
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "pip offline closure failed"):
            self.verify()

    def test_platform_accepts_abi3(self):
        name, version, tags = wheelhouse.wheel_identity("example-1.0-cp311-abi3-manylinux_2_34_x86_64.whl")
        self.assertEqual((name, version, tags), ("example", "1.0", ["cp311-abi3-manylinux_2_34_x86_64"]))

    def test_platform_rejections(self):
        for tag in ("cp312-cp312-manylinux_2_40_x86_64", "cp313-cp313-manylinux_2_17_x86_64",
                    "cp312-cp312-manylinux_2_17_aarch64", "cp312-cp312-musllinux_1_2_x86_64",
                    "cp312-cp312-linux_x86_64", "cp312-cp312-win_amd64", "cp312-cp312-macosx_11_0_arm64"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                wheelhouse.wheel_identity(f"example-1.0-{tag}.whl")

    def test_rejects_source_distribution(self):
        self.data["install"][0]["download_info"]["url"] = "https://files.pythonhosted.org/packages/example-1.0.tar.gz"
        self.write_report()
        with self.assertRaises(ValueError):
            wheelhouse.create_inventory(self.requirements, self.report, self.wheels)

    def test_rejects_missing_file(self):
        next(self.wheels.iterdir()).unlink()
        self.assert_rejected()

    def test_rejects_extra_file_or_source_archive(self):
        for filename in ("duplicate.whl", "example.tar.gz", "operator-secret.txt"):
            with self.subTest(filename=filename):
                path = self.wheels / filename
                path.write_text("not accepted")
                self.assert_rejected()
                path.unlink()

    def test_rejects_tampered_bytes(self):
        path = next(self.wheels.iterdir())
        path.write_bytes(path.read_bytes() + b"tamper")
        self.assert_rejected()

    def test_rejects_duplicate_distribution(self):
        self.manifest["artifacts"].append(copy.deepcopy(self.manifest["artifacts"][0]))
        self.write_manifest()
        self.assert_rejected()

    def test_rejects_source_host_credentials_query_and_traversal(self):
        original = self.manifest["artifacts"][0]["url"]
        for url in (original.replace("files.pythonhosted.org", "mirror.invalid"),
                    original.replace("https:", "http:"), original + "?token=secret", original + "#x",
                    original.replace("//files", "//user:secret@files"), original.replace("/packages/", "/packages/../")):
            with self.subTest(url=url):
                self.manifest["artifacts"][0]["url"] = url
                self.write_manifest()
                self.assert_rejected()

    def test_rejects_changed_input_and_lost_extras(self):
        self.requirements.write_text("example==1.0\n")
        self.assert_rejected()

    def test_rejects_lock_options_direct_urls_and_lost_extras(self):
        original = self.lock_path.read_text()
        for text in (original + "--extra-index-url https://example.invalid\n",
                     original.replace("[feature]", ""), original.replace("==1.0", " @ https://example.invalid/a.whl")):
            self.lock_path.write_text(text)
            self.assert_rejected()

    def test_rejects_requirements_urls_ranges_and_markers(self):
        for text in ("example>=1.0", "example @ https://example.invalid/a.whl", "example==1.*",
                     "example==1.0; python_version>'3'", "example==1.0\nexample==1.0"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                wheelhouse.roots(text.encode())

    def test_rejects_duplicate_json_keys(self):
        self.manifest_path.write_text('{"format":"x", "format":"y"}')
        self.assert_rejected()

    def test_rejects_wrong_size_digest_and_tags(self):
        original = copy.deepcopy(self.manifest)
        for key, value in (("size_bytes", 1), ("sha256", "f" * 64), ("tags", ["cp312-cp312-win_amd64"]),
                           ("filename", "../example.whl"), ("version", "9.0")):
            with self.subTest(key=key):
                self.manifest = copy.deepcopy(original)
                self.manifest["artifacts"][0][key] = value
                self.write_manifest()
                self.assert_rejected()

    def test_rejects_direct_dependency_url_before_pip(self):
        for path in self.wheels.iterdir():
            path.unlink()
        self.data["install"] = []
        self.add_wheel("example", "1.0", ["helper @ https://example.invalid/helper.whl"], ["feature"])
        self.write_report()
        with patch.object(subprocess, "run") as run, self.assertRaisesRegex(ValueError, "direct dependency URL"):
            wheelhouse.create_inventory(self.requirements, self.report, self.wheels)
        run.assert_not_called()

    def test_rejects_wheel_internal_metadata_disagreement(self):
        path = self.wheels / self.manifest["artifacts"][0]["filename"]
        with zipfile.ZipFile(path) as archive:
            contents = {entry.filename: archive.read(entry) for entry in archive.infolist()}
        key = next(k for k in contents if k.endswith("/METADATA"))
        contents[key] = contents[key].replace(b"Name: example", b"Name: impostor")
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in contents.items():
                archive.writestr(name, payload)
        artifact = self.manifest["artifacts"][0]
        artifact.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=path.stat().st_size)
        self.write_manifest()
        self.assert_rejected()

    def test_rejects_symlink_hardlink_and_fifo(self):
        artifact = self.manifest["artifacts"][0]
        path = self.wheels / artifact["filename"]
        original = self.root / "original.whl"
        path.rename(original)
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    path.symlink_to(original)
                elif kind == "hardlink":
                    os.link(original, path)
                else:
                    os.mkfifo(path)
                self.assert_rejected()
                path.unlink()

    def test_rejects_parent_symlink(self):
        link = self.root / "linked"
        link.symlink_to(self.wheels, target_is_directory=True)
        self.wheels = link
        self.assert_rejected()

    def test_rejects_changed_report_extras_and_host(self):
        original = copy.deepcopy(self.data)
        self.data["install"][0]["requested_extras"] = []
        self.write_report()
        with self.assertRaisesRegex(ValueError, "extras"):
            wheelhouse.create_inventory(self.requirements, self.report, self.wheels)
        self.data = original
        self.data["environment"]["sys_platform"] = "win32"
        self.write_report()
        with self.assertRaisesRegex(ValueError, "host"):
            wheelhouse.create_inventory(self.requirements, self.report, self.wheels)

    def test_rejects_yanked_or_nonregistry_resolution(self):
        for flag in ("is_yanked", "is_direct"):
            with self.subTest(flag=flag):
                self.data["install"][0][flag] = True
                self.write_report()
                with self.assertRaises(ValueError):
                    wheelhouse.create_inventory(self.requirements, self.report, self.wheels)
                self.data["install"][0][flag] = False

    def test_snapshot_protects_pip_from_later_input_change(self):
        with patch.object(wheelhouse, "pip_closure") as pip:
            def inspect_snapshot(manifest, snapshot, lock):
                path = self.wheels / manifest["artifacts"][0]["filename"]
                saved = path.read_bytes()
                path.write_bytes(b"changed after verification")
                self.assertEqual((snapshot / path.name).read_bytes(), saved)
                self.assertEqual(lock.decode(), wheelhouse.lock_text(manifest))
                return {"status": "TEST_SNAPSHOT_ONLY"}
            pip.side_effect = inspect_snapshot
            self.assertEqual(self.verify()["status"], "TEST_SNAPSHOT_ONLY")

    def test_pip_command_has_hash_binary_no_index_and_clean_config(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(subprocess, "run") as run:
            root = Path(temporary)
            snapshot = root / "wheels"
            snapshot.mkdir()
            def execute(cmd, **kwargs):
                for required in ("--no-index", "--require-hashes", "--only-binary=:all:", "--ignore-installed", "--no-cache-dir", "--dry-run"):
                    self.assertIn(required, cmd)
                self.assertNotIn("--no-deps", cmd)
                self.assertEqual(kwargs["env"]["PIP_CONFIG_FILE"], os.devnull)
                self.assertNotIn("PIP_EXTRA_INDEX_URL", kwargs["env"])
                report = {"install": [{"metadata": {"name": a["name"], "version": a["version"]}} for a in self.manifest["artifacts"]]}
                (root / "closure-report.json").write_text(json.dumps(report))
                return subprocess.CompletedProcess(cmd, 0)
            run.side_effect = execute
            with patch.object(wheelhouse.platform, "machine", return_value="x86_64"), patch.object(wheelhouse.sys, "platform", "linux"):
                if sys.version_info[:2] == (3, 12):
                    wheelhouse.pip_closure(self.manifest, snapshot, self.lock_path.read_bytes())

    def test_inventory_does_not_run_subprocess_or_install(self):
        with patch.object(subprocess, "run") as run:
            wheelhouse.create_inventory(self.requirements, self.report, self.wheels)
        run.assert_not_called()

    def test_rejects_size_and_package_limits(self):
        for limit, value in (("MAX_JSON", 1), ("MAX_WHEEL", 1), ("MAX_TOTAL", 1), ("MAX_PACKAGES", 1)):
            with self.subTest(limit=limit), patch.object(wheelhouse, limit, value):
                # MAX_JSON is a read_bytes default, so exercise that bound directly.
                if limit == "MAX_JSON":
                    with self.assertRaises(ValueError):
                        wheelhouse.read_bytes(self.manifest_path, limit=1)
                else:
                    self.assert_rejected()

    def test_rejects_malformed_report_schema(self):
        for report in ([], {"version": "1", "environment": []},
                       {**self.data, "install": [None]}):
            with self.subTest(report=report):
                self.report.write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    wheelhouse.create_inventory(self.requirements, self.report, self.wheels)

    def inventory_cli(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = wheelhouse.main(["inventory", "--requirements", str(self.requirements),
                "--report", str(self.report), "--wheelhouse", str(self.wheels)])
        return status, out.getvalue(), err.getvalue()

    def test_inventory_cli_rejects_report_url_types(self):
        for value in (123, True, None, [], {}, 1.5):
            with self.subTest(type=type(value).__name__):
                self.data["install"][0]["download_info"]["url"] = value
                self.write_report()
                with patch.object(wheelhouse, "urlsplit", wraps=wheelhouse.urlsplit) as split:
                    self.assertEqual(self.inventory_cli(),
                                     (1, "", "offline python wheelhouse: validation failed\n"))
                    split.assert_not_called()

    def test_inventory_cli_rejects_report_url_length_before_parse(self):
        for length in (2049, 4096):
            with self.subTest(length=length):
                self.data["install"][0]["download_info"]["url"] = "x" * length
                self.write_report()
                with patch.object(wheelhouse, "urlsplit", wraps=wheelhouse.urlsplit) as split:
                    self.assertEqual(self.inventory_cli(),
                                     (1, "", "offline python wheelhouse: validation failed\n"))
                    split.assert_not_called()

    def test_inventory_cli_rejects_report_url_syntax(self):
        for value in ("", "x" * 2048, "https://[invalid/", "https://files.pythonhosted.org/"):
            with self.subTest(length=len(value)):
                self.data["install"][0]["download_info"]["url"] = value
                self.write_report()
                self.assertEqual(self.inventory_cli(),
                                 (1, "", "offline python wheelhouse: validation failed\n"))

    def test_pip_timeout_is_fixed_failure_without_partial_output(self):
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 120)):
            self.assert_rejected()

    def test_rejects_invalid_zip_even_when_hash_matches(self):
        artifact = self.manifest["artifacts"][0]
        path = self.wheels / artifact["filename"]
        path.write_bytes(b"not a zip wheel")
        artifact.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=path.stat().st_size)
        self.write_manifest()
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
