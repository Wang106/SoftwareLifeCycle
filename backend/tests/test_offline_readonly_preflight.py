"""Offline format/config checks; synthetic tar fixtures are NOT runnable image evidence."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("offline_preflight", ROOT / "scripts/offline_readonly_preflight.py")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)
COMMIT = "a" * 40


class OfflinePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"os": "linux", "architecture": "amd64", "config": {
            "Labels": {"org.opencontainers.image.revision": COMMIT}, "Env": ["PATH=/usr/local/bin:/usr/bin:/bin"]},
            "rootfs": {"type": "layers", "diff_ids": ["sha256:" + hashlib.sha256(b"synthetic layer bytes").hexdigest()]}}
        self.manifest = {"format": "slc-offline-readonly-v1", "source_commit": COMMIT,
                         "required_db_revision": preflight.REVISION, "images": {}}
        self.operator = {"profile": "linux-localhost-readonly", "database_env_file": "database.env",
                         "database_preprovisioned": True, "database_readonly_role": True, "data_classification": "synthetic-only"}
        self.secret = self.root / "database.env"
        self.secret.write_text("DATABASE_URL=postgresql+psycopg://readonly:unit_test_only_not_a_secret@127.0.0.1:5432/slc_synthetic\n")
        self.secret.chmod(0o600)
        self.make_images()
        self.write_inputs()

    def make_images(self, *, extra=None, config=None, layers=None):
        for service in ("api", "web"):
            config_bytes = json.dumps(config or self.config).encode()
            image_id = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
            values = {"config.json": config_bytes, "layer.tar": b"synthetic layer bytes",
                      "manifest.json": json.dumps([{"Config": "config.json", "RepoTags": [], "Layers": layers or ["layer.tar"]}]).encode()}
            target = self.root / f"{service}.tar"
            with tarfile.open(target, "w") as archive:
                for name, value in values.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(value)
                    archive.addfile(info, io.BytesIO(value))
                if extra:
                    info, value = extra
                    archive.addfile(info, io.BytesIO(value))
            self.manifest["images"][service] = {"archive": target.name, "size": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "image_id": image_id,
                "platform": "linux/amd64", "source_commit": COMMIT}

    def write_inputs(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        (self.root / "operator.json").write_text(json.dumps(self.operator))

    def blocked(self):
        self.write_inputs()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(preflight.main([str(self.root)]), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("unit_test_only", err.getvalue())
        self.assertIn("BLOCKED", err.getvalue())

    def test_fixed_compose_has_no_startup_migration_seed_pull_build_or_database_service(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch("subprocess.run", side_effect=AssertionError("must not spawn")), patch("socket.create_connection", side_effect=AssertionError("must not connect")):
            result = preflight.validate(self.root)
        self.assertEqual(set(result["services"]), {"api", "web"})
        api, web = result["services"].values()
        for service in (api, web):
            self.assertEqual(service["pull_policy"], "never")
            self.assertEqual(service["network_mode"], "host")
            self.assertEqual(service["platform"], "linux/amd64")
            self.assertTrue(service["read_only"])
            self.assertEqual(service["user"], "65532:65532")
            self.assertNotIn("build", service)
            self.assertNotIn("volumes", service)
            self.assertNotIn("ports", service)
            self.assertIn("127.0.0.1", service["command"])
        self.assertEqual(api["entrypoint"], ["/usr/local/bin/python", "-m", "uvicorn"])
        self.assertEqual(api["environment"]["READ_ONLY_MODE"], "true")
        self.assertEqual(api["environment"]["SEED_ON_STARTUP"], "false")
        self.assertEqual(api["environment"]["SEED_ZFI_DEMO"], "false")
        self.assertEqual(api["environment"]["PGOPTIONS"], "-c default_transaction_read_only=on")
        self.assertEqual(web["environment"]["API_BASE_URL"], "http://127.0.0.1:8000")
        for gate in preflight.GATES:
            self.assertEqual(web["environment"][gate], "disabled")
        serialized = json.dumps(result)
        self.assertNotIn("unit_test_only", serialized)
        self.assertNotIn("alembic", serialized)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_cli_success_is_configuration_only(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/offline_readonly_preflight.py"), str(self.root)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("CONFIGURATION_ONLY", proc.stderr)
        self.assertEqual(set(json.loads(proc.stdout)["services"]), {"api", "web"})

    def test_missing_input(self):
        self.secret.unlink()
        self.blocked()

    def test_archive_checksum(self):
        (self.root / "api.tar").write_bytes(b"corrupted")
        self.blocked()

    def test_declared_identity_platform_revision_schema_fail_closed(self):
        original = copy.deepcopy(self.manifest)
        for key, value in (("image_id", "latest"), ("image_id", "sha256:" + "b" * 64), ("source_commit", "b" * 40), ("platform", "linux/arm64"), ("size", True)):
            with self.subTest(key=key, value=value):
                self.manifest = copy.deepcopy(original)
                self.manifest["images"]["api"][key] = value
                self.blocked()
        self.manifest = original
        self.manifest["required_db_revision"] = "0020_global_role_status"
        self.blocked()

    def test_actual_config_platform_label_layer_or_environment_mismatch(self):
        for change in ("architecture", "label", "layer", "env"):
            with self.subTest(change=change):
                config = copy.deepcopy(self.config)
                if change == "architecture": config["architecture"] = "arm64"
                elif change == "label": config["config"]["Labels"]["org.opencontainers.image.revision"] = "b" * 40
                elif change == "layer": config["rootfs"]["diff_ids"] = ["sha256:" + "b" * 64]
                else: config["config"]["Env"] = ["AUTH_MODE=oidc"]
                self.make_images(config=config)
                self.blocked()

    def test_tar_traversal_symlink_duplicate_or_device_rejected_without_extraction(self):
        for name, kind in (("../outside", tarfile.REGTYPE), ("/outside", tarfile.REGTYPE), ("link", tarfile.SYMTYPE), ("config.json", tarfile.REGTYPE), ("device", tarfile.CHRTYPE)):
            with self.subTest(name=name):
                info = tarfile.TarInfo(name)
                info.type = kind
                self.make_images(extra=(info, b""))
                self.blocked()
        self.assertFalse((self.root.parent / "outside").exists())

    def test_symlink_input_rejected(self):
        source = self.root / "real.env"
        self.secret.rename(source)
        self.secret.symlink_to(source)
        self.blocked()

    def test_operator_unknown_or_unapproved_scope(self):
        original = self.operator.copy()
        for key, value in (("database_preprovisioned", False), ("database_readonly_role", False), ("data_classification", "company"), ("profile", "production"), ("extra", "anything"), ("database_env_file", "../secret")):
            with self.subTest(key=key):
                self.operator = {**original, key: value}
                self.blocked()

    def test_secret_permissions(self):
        self.secret.chmod(0o644)
        self.blocked()

    def test_database_input_rejects_remote_options_defaults_and_extra_environment(self):
        original = self.secret.read_text()
        for value in (original.replace("127.0.0.1", "localhost"), original.replace("127.0.0.1", "example.org"),
                      original.replace("unit_test_only_not_a_secret", "slc_dev_password"), original.rstrip() + "?options=unsafe\n",
                      original + "READ_ONLY_MODE=false\n", original.replace("unit_test_only", "$PASSWORD")):
            with self.subTest(value=value):
                self.secret.write_text(value)
                self.blocked()

    def test_duplicate_json_fields_and_malformed_json_are_redacted(self):
        for value in ('{"format":1,"format":2}', 'unit_test_only invalid secret'):
            (self.root / "manifest.json").write_text(value)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(preflight.main([str(self.root)]), 2)
            self.assertNotIn("unit_test_only", out.getvalue() + err.getvalue())

    def test_compose_interpolated_root_and_secret_paths_rejected(self):
        self.secret.rename(self.root / "$secret.env")
        self.operator["database_env_file"] = "$secret.env"
        self.blocked()
        self.operator["database_env_file"] = "database.env"
        (self.root / "$secret.env").rename(self.secret)
        child = self.root / "$bundle"
        child.mkdir()
        for path in list(self.root.iterdir()):
            if path != child:
                path.rename(child / path.name)
        self.root = child
        self.blocked()

    def test_baked_volumes_rejected_and_public_gpg_fingerprint_allowed(self):
        config = copy.deepcopy(self.config)
        config["config"]["Volumes"] = {"/app": {}}
        self.make_images(config=config)
        self.blocked()
        config["config"].pop("Volumes")
        config["config"]["Env"].append("GPG_KEY=" + "A" * 40)
        self.make_images(config=config)
        self.write_inputs()
        preflight.validate(self.root)
        config["config"]["Env"][-1] = "GPG_KEY=not_a_fingerprint"
        self.make_images(config=config)
        self.blocked()

    def test_all_frontend_submission_and_session_gates_explicitly_disabled(self):
        import re
        discovered = set()
        for path in (ROOT / "frontend/lib").glob("*.ts"):
            discovered.update(re.findall(r"\b[A-Z_]+_(?:SUBMISSION|SESSION|OIDC|SELECTION)_MODE\b", path.read_text()))
        self.assertEqual(discovered, set(preflight.GATES))


if __name__ == "__main__":
    unittest.main()
