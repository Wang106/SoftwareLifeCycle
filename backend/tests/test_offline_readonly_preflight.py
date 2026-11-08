"""Offline format/config checks; synthetic tar fixtures are NOT runnable image evidence."""
import contextlib
import copy
import gzip
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

    def test_complete_compose_contract_with_fixed_local_log_retention(self):
        common = {
            "platform": "linux/amd64", "pull_policy": "never", "network_mode": "host",
            "read_only": True, "restart": "no", "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"], "user": "65532:65532",
            "working_dir": "/app", "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m"],
            "healthcheck": {"disable": True},
            "logging": {"driver": "local", "options": {
                "max-size": "10m", "max-file": "3", "compress": "true"}},
        }
        expected = {"name": "slc-offline-readonly", "services": {
            "api": {**copy.deepcopy(common), "image": self.manifest["images"]["api"]["image_id"],
                    "entrypoint": ["/usr/local/bin/python", "-m", "uvicorn"],
                    "command": ["app.main:app", "--host", "127.0.0.1", "--port", "8000"],
                    "env_file": [{"path": str(self.secret), "required": True, "format": "raw"}],
                    "environment": {
                        "READ_ONLY_MODE": "true", "AUTH_MODE": "disabled", "ADMIN_OPERATOR_ENABLED": "false",
                        "SEED_ON_STARTUP": "false", "SEED_ZFI_DEMO": "false", "REQUIRED_DB_REVISION": preflight.REVISION,
                        "CORS_ORIGINS": "http://127.0.0.1:3000", "PYTHONPATH": "/app", "PYTHONDONTWRITEBYTECODE": "1",
                        "PGOPTIONS": "-c default_transaction_read_only=on"}},
            "web": {**copy.deepcopy(common), "image": self.manifest["images"]["web"]["image_id"],
                    "entrypoint": ["/usr/local/bin/node", "node_modules/next/dist/bin/next"],
                    "command": ["start", "--hostname", "127.0.0.1", "--port", "3000"],
                    "environment": {
                        **dict.fromkeys(preflight.GATES, "disabled"), "API_BASE_URL": "http://127.0.0.1:8000",
                        "NEXT_PUBLIC_API_URL": "", "NEXT_PUBLIC_API_BASE_URL": "", "NEXT_TELEMETRY_DISABLED": "1",
                        "NODE_ENV": "production"}},
        }}
        self.assertEqual(preflight.validate(self.root), expected)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(preflight.main([str(self.root)]), 0)
        self.assertEqual(json.loads(out.getvalue()), expected)
        self.assertIn("CONFIGURATION_ONLY", err.getvalue())
        for service in json.loads(out.getvalue())["services"].values():
            self.assertIs(type(service["logging"]["driver"]), str)
            self.assertTrue(all(type(value) is str for value in service["logging"]["options"].values()))

    def test_logging_objects_are_independent_between_services_and_calls(self):
        expected = {"driver": "local", "options": {"max-size": "10m", "max-file": "3", "compress": "true"}}
        for changed, unchanged in (("api", "web"), ("web", "api")):
            with self.subTest(changed=changed):
                services = preflight.validate(self.root)["services"]
                self.assertEqual(services[changed]["logging"], expected)
                self.assertIsNot(services[changed]["logging"], services[unchanged]["logging"])
                self.assertIsNot(services[changed]["logging"]["options"], services[unchanged]["logging"]["options"])
                services[changed]["logging"]["driver"] = "none"
                services[changed]["logging"]["options"]["max-file"] = "999"
                self.assertEqual(services[unchanged]["logging"], expected)
                for service in preflight.validate(self.root)["services"].values():
                    self.assertEqual(service["logging"], expected)

    def test_log_overrides_rejected_by_exact_input_key_allowlists(self):
        original_manifest, original_operator = copy.deepcopy(self.manifest), copy.deepcopy(self.operator)
        for location in ("manifest", "operator", "images", "api", "web"):
            for field, value in (("logging", {"driver": "none"}), ("log_driver", "json-file"),
                                 ("log_opts", {"max-file": "999"})):
                with self.subTest(location=location, field=field):
                    self.manifest, self.operator = copy.deepcopy(original_manifest), copy.deepcopy(original_operator)
                    target = {"manifest": self.manifest, "operator": self.operator,
                              "images": self.manifest["images"], "api": self.manifest["images"]["api"],
                              "web": self.manifest["images"]["web"]}[location]
                    target[field] = value
                    self.blocked()

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


class DockerSaveDescriptorTests(unittest.TestCase):
    """Synthetic classic-save variants only; no Docker/network/runtime acceptance."""
    MEDIA = "application/vnd.oci.image.layer.v1.tar"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "image.tar"
        self.fixture()

    def fixture(self):
        self.values = {}
        self.diff_ids = []
        self.layer_names = []
        self.sources = {}
        for index in range(2):
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w") as archive:
                payload = ("synthetic layer " + str(index)).encode()
                member = tarfile.TarInfo("synthetic-" + str(index))
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            value = raw.getvalue()
            identity = "sha256:" + hashlib.sha256(value).hexdigest()
            name = "blobs/sha256/" + identity[7:]
            self.values[name] = value
            self.diff_ids.append(identity)
            self.layer_names.append(name)
            self.sources[identity] = {"mediaType": self.MEDIA, "digest": identity, "size": len(value)}
        self.config = {"os": "linux", "architecture": "amd64", "config": {
            "Labels": {"org.opencontainers.image.revision": COMMIT}, "Env": ["PATH=/usr/bin"]},
            "rootfs": {"type": "layers", "diff_ids": self.diff_ids.copy()}}
        self.record = {"Config": "", "RepoTags": None, "Layers": self.layer_names.copy(), "LayerSources": self.sources}
        self.set_config()

    def set_config(self):
        self.values.pop(self.record["Config"], None)
        raw = json.dumps(self.config).encode()
        self.identity = "sha256:" + hashlib.sha256(raw).hexdigest()
        self.record["Config"] = "blobs/sha256/" + self.identity[7:]
        self.values[self.record["Config"]] = raw

    def write(self, *, manifest_raw=None, extra_members=()):
        values = {**self.values, "manifest.json": manifest_raw if manifest_raw is not None else json.dumps([self.record]).encode()}
        with tarfile.open(self.path, "w") as archive:
            for name, raw in values.items():
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
            for info, raw in extra_members:
                archive.addfile(info, io.BytesIO(raw))
        return {"archive": self.path.name, "size": self.path.stat().st_size,
                "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(), "image_id": self.identity,
                "platform": "linux/amd64", "source_commit": COMMIT}

    def check(self, **kwargs):
        preflight.archive_image(self.path, self.write(**kwargs), COMMIT)

    def rejected(self, reason, **kwargs):
        with self.assertRaises(preflight.Invalid) as caught:
            self.check(**kwargs)
        self.assertEqual(caught.exception.args, (reason,))

    def test_complete_two_layer_classic_sources_pass_without_mutation_or_network(self):
        # Moby may also emit OCI helper metadata, but only manifest.json is authority.
        self.values.update({"oci-layout": b'{"imageLayoutVersion":"1.0.0"}', "index.json": b'{"manifests":[]}'})
        item = self.write()
        before = self.path.read_bytes()
        with patch("subprocess.run", side_effect=AssertionError("must not spawn")), \
             patch("socket.create_connection", side_effect=AssertionError("must not connect")), \
             patch.object(tarfile.TarFile, "extractall", side_effect=AssertionError("must not extract")), \
             patch.object(tarfile.TarFile, "extract", side_effect=AssertionError("must not extract")):
            preflight.archive_image(self.path, item, COMMIT)
        self.assertEqual(self.path.read_bytes(), before)

    def test_original_three_field_format_and_noncanonical_names_remain_supported(self):
        self.record.pop("LayerSources")
        old = self.record["Config"]
        self.record["Config"] = "config.json"
        self.values["config.json"] = self.values.pop(old)
        for index, old in enumerate(self.layer_names):
            name = "layer-" + str(index) + ".tar"
            self.record["Layers"][index] = name
            self.values[name] = self.values.pop(old)
        self.check()

    def test_manifest_record_type_missing_and_unknown_fields_have_fixed_reasons(self):
        for record, reason in ((None, "invalid docker-save manifest record"),
                               ({"Config": "config.json"}, "missing docker-save manifest fields"),
                               ({**self.record, "Parent": "PRIVATE_SENTINEL"}, "unreviewed docker-save manifest fields"),
                               ({**self.record, "PRIVATE_SENTINEL": None}, "unreviewed docker-save manifest fields")):
            with self.subTest(reason=reason):
                self.rejected(reason, manifest_raw=json.dumps([record]).encode())

    def test_item_fields_are_distinguished_from_manifest_fields(self):
        item = self.write()
        item["PRIVATE_SENTINEL"] = "ignored"
        with self.assertRaises(preflight.Invalid) as caught:
            preflight.archive_image(self.path, item, COMMIT)
        self.assertEqual(caught.exception.args, ("unexpected or missing image item fields",))

    def test_sources_require_exact_complete_nonempty_diff_id_mapping(self):
        for bad in (None, [], {}, {self.diff_ids[0]: self.sources[self.diff_ids[0]]},
                    {**self.sources, "sha256:" + "0" * 64: self.sources[self.diff_ids[0]]}):
            with self.subTest(kind=type(bad).__name__):
                self.record["LayerSources"] = bad
                self.rejected("invalid LayerSources mapping")

    def test_sources_reject_malformed_or_repeated_diff_ids(self):
        for bad in (None, {}, "PRIVATE_SENTINEL", [None, self.diff_ids[1]],
                    [self.diff_ids[0].upper(), self.diff_ids[1]], [self.diff_ids[0]] * 2):
            with self.subTest(value=bad):
                self.config["rootfs"]["diff_ids"] = bad
                self.set_config()
                self.rejected("invalid LayerSources mapping")

    def test_descriptor_requires_only_exact_three_fields(self):
        base = self.sources[self.diff_ids[0]].copy()
        for bad in (None, [], {}, {k: v for k, v in base.items() if k != "size"},
                    *({**base, field: value} for field, value in (
                        ("urls", []), ("urls", ["https://PRIVATE_SENTINEL"]),
                        ("annotations", {}), ("platform", {}), ("data", ""), ("PRIVATE_SENTINEL", None)))):
            with self.subTest(descriptor=bad):
                self.sources[self.diff_ids[0]] = bad
                self.rejected("unreviewed LayerSources descriptor fields")

    def test_descriptor_media_type_accepts_only_uncompressed_oci_tar(self):
        for bad in (None, [], "", self.MEDIA + "+gzip", self.MEDIA + "+zstd",
                    "application/vnd.oci.image.layer.nondistributable.v1.tar",
                    "application/vnd.docker.image.rootfs.diff.tar.gzip",
                    "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip"):
            with self.subTest(media_type=bad):
                self.sources[self.diff_ids[0]]["mediaType"] = bad
                self.rejected("unreviewed LayerSources media type")

    def test_descriptor_digest_must_be_exact_diff_id_not_registry_compressed_digest(self):
        for bad in (None, [], "", "sha512:" + "a" * 128, self.diff_ids[0].upper(), self.diff_ids[1]):
            with self.subTest(digest=bad):
                self.sources[self.diff_ids[0]]["digest"] = bad
                self.rejected("LayerSources digest mismatch")

    def test_descriptor_size_is_positive_exact_integer_equal_to_member_bytes(self):
        for bad in (None, True, False, 0, -1, 10240.0, "10240", 10239, 10241):
            with self.subTest(size=bad):
                self.sources[self.diff_ids[0]]["size"] = bad
                self.rejected("LayerSources size mismatch")

    def test_crossed_descriptors_cannot_match_a_different_layer_in_the_archive(self):
        first, second = self.diff_ids
        self.sources[first], self.sources[second] = self.sources[second], self.sources[first]
        self.rejected("LayerSources digest mismatch")

    def test_layer_order_is_bound_to_diff_id_and_canonical_blob_path(self):
        self.record["Layers"].reverse()
        self.rejected("invalid LayerSources blob path")

    def test_new_variant_requires_canonical_config_and_layer_blob_paths(self):
        for field in ("Config", "Layers"):
            with self.subTest(field=field):
                self.fixture()
                old = self.record["Config"] if field == "Config" else self.record["Layers"][0]
                self.values["arbitrary.tar"] = self.values.pop(old)
                if field == "Config":
                    self.record["Config"] = "arbitrary.tar"
                else:
                    self.record["Layers"][0] = "arbitrary.tar"
                self.rejected("invalid LayerSources blob path")

    def test_new_variant_rejects_malformed_layer_containers(self):
        for bad in (None, {}, [], [None, self.layer_names[1]], [self.layer_names[0]] * 2):
            with self.subTest(layers=bad):
                self.record["Layers"] = bad
                self.rejected("invalid image layers")

    def replace_first_layer(self, raw):
        old = self.diff_ids[0]
        identity = "sha256:" + hashlib.sha256(raw).hexdigest()
        name = "blobs/sha256/" + identity[7:]
        self.values.pop(self.layer_names[0])
        self.values[name] = raw
        self.sources.pop(old)
        self.sources[identity] = {"mediaType": self.MEDIA, "digest": identity, "size": len(raw)}
        self.diff_ids[0] = identity
        self.layer_names[0] = name
        self.record["Layers"][0] = name
        self.config["rootfs"]["diff_ids"][0] = identity
        self.set_config()

    def test_consistent_gzip_or_nontar_bytes_cannot_claim_uncompressed_media_type(self):
        raw = self.values[self.layer_names[0]]
        for bad in (gzip.compress(raw), b"PRIVATE_SENTINEL not tar", raw[:600]):
            with self.subTest(size=len(bad)):
                self.fixture()
                self.replace_first_layer(bad)
                self.rejected("invalid LayerSources uncompressed tar")

    def test_oversized_inner_extension_headers_are_fixed_invalid_not_raw_cli_tracebacks(self):
        for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
            with self.subTest(kind=kind):
                self.fixture()
                info = tarfile.TarInfo("PRIVATE_SENTINEL")
                info.type = kind
                info.size = 2**80
                self.replace_first_layer(info.tobuf(format=tarfile.GNU_FORMAT) + b"\0" * 1024)
                self.rejected("invalid LayerSources uncompressed tar")
                out, err = io.StringIO(), io.StringIO()
                with patch.object(preflight, "validate", side_effect=lambda _bundle: self.check()), \
                     contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(preflight.main([str(self.path.parent)]), 2)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("BLOCKED", err.getvalue())
                self.assertNotIn("PRIVATE_SENTINEL", err.getvalue())
                self.assertNotIn("Traceback", err.getvalue())

    def test_recursive_inner_extension_headers_are_fixed_invalid_not_raw_cli_tracebacks(self):
        for kind in (tarfile.XHDTYPE, tarfile.GNUTYPE_LONGNAME):
            with self.subTest(kind=kind):
                self.fixture()
                info = tarfile.TarInfo("PRIVATE_SENTINEL")
                info.type = kind
                info.size = 0
                self.replace_first_layer(info.tobuf(format=tarfile.GNU_FORMAT) * 1200 + b"\0" * 1024)
                self.rejected("invalid LayerSources uncompressed tar")
                out, err = io.StringIO(), io.StringIO()
                with patch.object(preflight, "validate", side_effect=lambda _bundle: self.check()), \
                     contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(preflight.main([str(self.path.parent)]), 2)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("BLOCKED", err.getvalue())
                self.assertNotIn("PRIVATE_SENTINEL", err.getvalue())
                self.assertNotIn("Traceback", err.getvalue())

    def test_new_variant_requires_double_zero_end_blocks_alignment_and_zero_tail(self):
        raw = self.values[self.layer_names[0]]
        for bad in (raw[:1024], raw[:1536], raw + b"X" * 512, raw + b"\0",
                    raw[:1024] + b"X" * 512 + b"\0" * 1024):
            with self.subTest(size=len(bad)):
                self.fixture()
                self.replace_first_layer(bad)
                self.rejected("invalid LayerSources uncompressed tar")

    def test_huge_extension_read_is_rejected_before_underlying_allocation(self):
        for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
            with self.subTest(kind=kind):
                self.fixture()
                info = tarfile.TarInfo("PRIVATE_SENTINEL")
                info.type = kind
                info.size = 2**40
                self.replace_first_layer(info.tobuf(format=tarfile.GNU_FORMAT) + b"\0" * 1024)
                requests = []
                original = tarfile.ExFileObject.read
                def guard(stream, size=-1):
                    if size > 1024 * 1024:
                        requests.append(size)
                        raise OverflowError("test guard prevents large allocation")
                    return original(stream, size)
                with patch.object(tarfile.ExFileObject, "read", guard):
                    self.rejected("invalid LayerSources uncompressed tar")
                self.assertEqual(requests, [], "parser must reject before requesting huge reads")

    def test_extension_payload_budget_rejects_valid_but_oversized_metadata(self):
        for kind in (tarfile.PAX_FORMAT, tarfile.GNU_FORMAT):
            with self.subTest(format=kind):
                self.fixture()
                info = tarfile.TarInfo("n" * 66000)
                raw = info.tobuf(format=kind) + b"\0" * 1024
                self.replace_first_layer(raw)
                self.rejected("invalid LayerSources uncompressed tar")

    def test_regular_large_files_and_normal_pax_gnu_metadata_still_pass(self):
        for kind in (tarfile.PAX_FORMAT, tarfile.GNU_FORMAT):
            with self.subTest(format=kind):
                self.fixture()
                info = tarfile.TarInfo("synthetic/" + "n" * 200)
                info.size = 2 * 1024 * 1024
                if kind == tarfile.PAX_FORMAT:
                    info.pax_headers = {"comment": "synthetic metadata", "mtime": "1.25"}
                raw = info.tobuf(format=kind) + b"\0" * info.size + b"\0" * 1024
                self.replace_first_layer(raw)
                self.check()

    def test_flat_header_budget_accepts_exact_layer_limit_and_rejects_next_header(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as archive:
            for name in ("first", "second"):
                archive.addfile(tarfile.TarInfo(name))
        self.replace_first_layer(raw.getvalue())
        with patch.object(preflight, "MAX_LAYER_TAR_HEADERS", 2), \
             patch.object(preflight, "MAX_IMAGE_TAR_HEADERS", 3):
            self.check()
        with patch.object(preflight, "MAX_LAYER_TAR_HEADERS", 1):
            self.rejected("invalid LayerSources uncompressed tar")

    def test_image_header_budget_accumulates_across_layers(self):
        with patch.object(preflight, "MAX_LAYER_TAR_HEADERS", 1), \
             patch.object(preflight, "MAX_IMAGE_TAR_HEADERS", 2):
            self.check()
        with patch.object(preflight, "MAX_LAYER_TAR_HEADERS", 1), \
             patch.object(preflight, "MAX_IMAGE_TAR_HEADERS", 1):
            self.rejected("invalid LayerSources uncompressed tar")

    def test_pax_gnu_extension_headers_count_toward_layer_and_image_budgets(self):
        for kind in (tarfile.PAX_FORMAT, tarfile.GNU_FORMAT):
            with self.subTest(format=kind):
                self.fixture()
                info = tarfile.TarInfo("synthetic/" + "n" * 200)
                self.replace_first_layer(info.tobuf(format=kind) + b"\0" * 1024)
                with patch.object(preflight, "MAX_LAYER_TAR_HEADERS", 2), \
                     patch.object(preflight, "MAX_IMAGE_TAR_HEADERS", 3):
                    self.check()
                with patch.object(preflight, "MAX_LAYER_TAR_HEADERS", 1):
                    self.rejected("invalid LayerSources uncompressed tar")
                with patch.object(preflight, "MAX_IMAGE_TAR_HEADERS", 2):
                    self.rejected("invalid LayerSources uncompressed tar")

    def test_parser_metadata_budget_has_exact_layer_and_cross_layer_limits(self):
        # Each ordinary fixture reads a 512-byte header, a one-byte payload probe,
        # then a 512-byte zero terminator. File payload and zero-tail scans are not metadata.
        with patch.object(preflight, "MAX_LAYER_TAR_METADATA", 1025), \
             patch.object(preflight, "MAX_IMAGE_TAR_METADATA", 2050):
            self.check()
        with patch.object(preflight, "MAX_LAYER_TAR_METADATA", 1024):
            self.rejected("invalid LayerSources uncompressed tar")
        with patch.object(preflight, "MAX_IMAGE_TAR_METADATA", 2049):
            self.rejected("invalid LayerSources uncompressed tar")

    def test_extension_payload_bytes_count_toward_cumulative_metadata_budget(self):
        info = tarfile.TarInfo("synthetic/" + "n" * 200)
        self.replace_first_layer(info.tobuf(format=tarfile.GNU_FORMAT) + b"\0" * 1024)
        # GNU extension header + padded payload + ordinary header + first end block.
        with patch.object(preflight, "MAX_LAYER_TAR_METADATA", 2048), \
             patch.object(preflight, "MAX_IMAGE_TAR_METADATA", 3073):
            self.check()
        with patch.object(preflight, "MAX_LAYER_TAR_METADATA", 2047):
            self.rejected("invalid LayerSources uncompressed tar")

    def test_large_regular_payload_is_not_charged_to_metadata_budget(self):
        info = tarfile.TarInfo("large-synthetic-file")
        info.size = 2 * 1024 * 1024
        self.replace_first_layer(info.tobuf() + b"\0" * info.size + b"\0" * 1024)
        with patch.object(preflight, "MAX_LAYER_TAR_METADATA", 1025), \
             patch.object(preflight, "MAX_IMAGE_TAR_METADATA", 2050):
            self.check()

    def test_sequential_parser_does_not_retain_inherited_pax_entry_cache(self):
        raw = io.BytesIO()
        global_fields = {"custom_" + str(index): "synthetic-value" for index in range(30)}
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT, pax_headers=global_fields) as archive:
            for index in range(20):
                archive.addfile(tarfile.TarInfo("file-" + str(index)))
        self.replace_first_layer(raw.getvalue())
        original = tarfile.TarFile.next
        cached, observed = [], set()
        def inspect_next(archive):
            member = original(archive)
            if archive.tarinfo is preflight.LayerTarInfo:
                cached.append(len(archive.members))
                if member is not None and member.name.startswith("file-"):
                    self.assertEqual(member.pax_headers, global_fields)
                    observed.add(member.name)
            return member
        with patch.object(tarfile.TarFile, "next", inspect_next):
            self.check()
        self.assertEqual(len(observed), 20)
        self.assertLessEqual(max(cached), 1)

    def test_sequential_parser_preserves_global_pax_changes_without_prior_entries(self):
        raw = (tarfile.TarInfo.create_pax_global_header({"custom": "first", "uid": "123"})
               + tarfile.TarInfo("first-file").tobuf()
               + tarfile.TarInfo.create_pax_global_header({"custom": "second", "uid": "456"})
               + tarfile.TarInfo("second-file").tobuf() + b"\0" * 1024)
        self.replace_first_layer(raw)
        original = tarfile.TarFile.next
        observed = {}
        def inspect_next(archive):
            member = original(archive)
            if archive.tarinfo is preflight.LayerTarInfo and member is not None and member.name in ("first-file", "second-file"):
                observed[member.name] = (member.pax_headers["custom"], member.uid)
            return member
        with patch.object(tarfile.TarFile, "next", inspect_next):
            self.check()
        self.assertEqual(observed, {"first-file": ("first", 123), "second-file": ("second", 456)})

    @unittest.skipUnless(sys.platform == "linux", "Linux address-space budget regression")
    def test_global_pax_many_files_stays_within_bounded_child_address_space(self):
        code = r"""
import importlib.util, io, resource, sys, tarfile
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
spec = importlib.util.spec_from_file_location("preflight", sys.argv[1])
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
raw = io.BytesIO()
fields = {"custom_%04d" % index: "v" * 40 for index in range(1000)}
with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT, pax_headers=fields) as archive:
    for index in range(9000):
        archive.addfile(tarfile.TarInfo("file-%04d" % index))
size = raw.tell()
raw.seek(0)
try:
    preflight.layer_tar_format(raw, size)
except Exception:
    print("BOUNDED_PARSE_FAILED")
    sys.exit(2)
print("BOUNDED_PARSE_PASSED")
"""
        result = subprocess.run([sys.executable, "-c", code, str(ROOT / "scripts/offline_readonly_preflight.py")],
                                capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "BOUNDED_PARSE_PASSED\n")
        self.assertEqual(result.stderr, "")

    def test_layer_format_boundary_does_not_swallow_process_interrupts(self):
        for error in (KeyboardInterrupt(), SystemExit(17)):
            with self.subTest(error=type(error).__name__), \
                 patch.object(tarfile, "open", side_effect=error), self.assertRaises(type(error)):
                preflight.layer_tar_format(io.BytesIO(b"\0" * 1024), 1024)

    def test_uncompressed_tar_format_validation_keeps_empty_and_special_layer_members(self):
        for special in (False, True):
            with self.subTest(special=special):
                self.fixture()
                raw = io.BytesIO()
                with tarfile.open(fileobj=raw, mode="w") as archive:
                    if special:
                        for name, kind in ((".wh.removed", tarfile.CHRTYPE),
                                           ("symlink", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE)):
                            info = tarfile.TarInfo(name)
                            info.type = kind
                            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                                info.linkname = "synthetic"
                            archive.addfile(info)
                self.replace_first_layer(raw.getvalue() if special else b"\0" * 1024)
                self.check()

    def test_actual_bytes_are_still_hashed_after_descriptor_matches(self):
        name = self.layer_names[0]
        self.values[name] = b"X" + self.values[name][1:]
        self.rejected("image layer digest mismatch")

    def test_missing_layer_still_rejected(self):
        self.values.pop(self.layer_names[0])
        self.rejected("missing image layer")

    def test_duplicate_json_at_record_mapping_and_descriptor_levels_is_rejected(self):
        raw = json.dumps([self.record]).encode()
        replacements = ((b'"LayerSources":', b'"LayerSources": {}, "LayerSources":'),
                        ((json.dumps(self.diff_ids[0]) + ":").encode(),
                         (json.dumps(self.diff_ids[0]) + ": {}, " + json.dumps(self.diff_ids[0]) + ":").encode()),
                        (b'"size":', b'"size": 1, "size":'))
        for before, after in replacements:
            with self.subTest(before=before):
                self.rejected("duplicate JSON field", manifest_raw=raw.replace(before, after, 1))

    def test_new_variant_keeps_config_and_archive_identity_gates(self):
        for field, value, reason in (("sha256", "0" * 64, "archive checksum mismatch"),
                                     ("size", 1, "archive size mismatch"),
                                     ("image_id", "sha256:" + "0" * 64, "invalid LayerSources blob path"),
                                     ("platform", "linux/arm64", "image provenance mismatch")):
            with self.subTest(field=field):
                item = self.write()
                item[field] = value
                with self.assertRaises(preflight.Invalid) as caught:
                    preflight.archive_image(self.path, item, COMMIT)
                self.assertEqual(caught.exception.args, (reason,))
        self.values[self.record["Config"]] += b" "
        self.rejected("image config digest mismatch")

    def test_new_variant_keeps_platform_revision_environment_and_volume_gates(self):
        cases = (("os", "windows", "image platform mismatch"),
                 ("architecture", "arm64", "image platform mismatch"),
                 ("Labels", {}, "image revision label mismatch"),
                 ("Env", ["DATABASE_URL=PRIVATE_SENTINEL"], "unreviewed baked image environment"),
                 ("Volumes", {"/app": {}}, "image-declared writable volumes refused"))
        for field, value, reason in cases:
            with self.subTest(field=field):
                self.fixture()
                target = self.config if field in ("os", "architecture") else self.config["config"]
                target[field] = value
                self.set_config()
                self.rejected(reason)

    def test_new_variant_keeps_archive_path_duplicate_and_entry_type_gates(self):
        for name, kind, reason in (("../bad", tarfile.REGTYPE, "unsafe or duplicate archive path"),
                                   ("manifest.json", tarfile.REGTYPE, "unsafe or duplicate archive path"),
                                   ("link", tarfile.SYMTYPE, "archive links or special files refused"),
                                   ("hardlink", tarfile.LNKTYPE, "archive links or special files refused"),
                                   ("device", tarfile.CHRTYPE, "archive links or special files refused")):
            with self.subTest(name=name):
                info = tarfile.TarInfo(name)
                info.type = kind
                self.rejected(reason, extra_members=((info, b""),))

    def test_pure_oci_layout_without_docker_save_manifest_is_rejected(self):
        self.rejected("archive must contain exactly one image", manifest_raw=b'{"schemaVersion":2}')


if __name__ == "__main__":
    unittest.main()
