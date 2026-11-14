#!/usr/bin/env python3
"""Validate trusted offline inputs and print a fixed localhost-only Compose document.

Standard library only. Never runs Docker, extracts archives, connects to a database,
creates credentials, installs packages, or modifies inputs. Not deployment approval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
from urllib.parse import unquote, urlsplit

REVISION = "0030_private_upload_sessions"
MAX_LAYER_TAR_HEADERS = 100000
MAX_IMAGE_TAR_HEADERS = 500000
MAX_LAYER_TAR_METADATA = 64 * 1024 * 1024
MAX_IMAGE_TAR_METADATA = 256 * 1024 * 1024
GATES = (
    "BROWSER_OIDC_MODE", "BROWSER_SESSION_MODE", "ADMIN_REGISTRATION_SUBMISSION_MODE",
    "GRANT_STATUS_SUBMISSION_MODE", "PRINCIPAL_STATUS_SUBMISSION_MODE",
    "FIRST_COMMAND_SUBMISSION_MODE", "GOVERNANCE_COMMAND_SUBMISSION_MODE",
    "DISTRIBUTION_COMMAND_SUBMISSION_MODE", "PRODUCTION_COMMAND_SUBMISSION_MODE",
    "RESOURCE_COMMAND_SUBMISSION_MODE", "EVIDENCE_COMMAND_SUBMISSION_MODE",
    "ACCEPTANCE_CORRECTION_SUBMISSION_MODE", "IMPACT_CORRECTION_SUBMISSION_MODE",
    "IMPACT_WITHDRAWAL_SUBMISSION_MODE", "RELEASE_CHAIN_REVOCATION_SUBMISSION_MODE",
    "RELEASE_DECISION_SUPERSESSION_SUBMISSION_MODE",
    "BATCH_CORRECTION_SUBMISSION_MODE",
    "CHANGEOVER_CORRECTION_SUBMISSION_MODE",
    "AUTHORIZATION_APPROVAL_SUBMISSION_MODE",
    "PRIVATE_DISTRIBUTION_SELECTION_MODE",
    "PRIVATE_EVIDENCE_SELECTION_MODE",
)


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def read_json(value):
    return json.loads(value, object_pairs_hook=object_pairs)


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected), "unexpected or missing fields")


def hex_value(value, length):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def safe_file(root, name):
    require(isinstance(name, str) and name and "\\" not in name, "invalid input path")
    parts = PurePosixPath(name)
    require(not parts.is_absolute() and all(p not in (".", "..") for p in name.split("/")), "input path escapes bundle")
    path = root
    for part in parts.parts:
        path = path / part
        require(not path.is_symlink(), "symlink input refused")
    require(path.is_file(), "required input file is missing")
    require(path.resolve().is_relative_to(root.resolve()), "input path escapes bundle")
    return path


def digest(stream):
    h = hashlib.sha256()
    while block := stream.read(1024 * 1024):
        h.update(block)
    return h.hexdigest()


class LayerTarBudget:
    def __init__(self, header_limit, metadata_limit):
        self.headers, self.metadata = 0, 0
        self.header_limit, self.metadata_limit = header_limit, metadata_limit

    def charge(self, *, headers=0, metadata=0):
        require(self.headers + headers <= self.header_limit and self.metadata + metadata <= self.metadata_limit,
                "invalid LayerSources uncompressed tar")
        self.headers += headers
        self.metadata += metadata


class LayerTarReader:
    """Bound parser reads/seeks before allocation; large regular files use seek."""
    def __init__(self, stream, size, image_budget):
        self.stream, self.size = stream, size
        self.layer_budget = LayerTarBudget(MAX_LAYER_TAR_HEADERS, MAX_LAYER_TAR_METADATA)
        self.image_budget = image_budget
        self.parsing = True

    def charge(self, **amount):
        self.layer_budget.charge(**amount)
        self.image_budget.charge(**amount)

    def tell(self):
        return self.stream.tell()

    def seek(self, offset, whence=0):
        require(type(offset) is int and whence in (0, 1, 2), "invalid LayerSources uncompressed tar")
        target = offset + (0 if whence == 0 else self.tell() if whence == 1 else self.size)
        require(0 <= target <= self.size, "invalid LayerSources uncompressed tar")
        return self.stream.seek(target)

    def read(self, size):
        require(type(size) is int and 0 <= size <= min(1024 * 1024, self.size - self.tell()),
                "invalid LayerSources uncompressed tar")
        if self.parsing:
            self.charge(metadata=size)
        value = self.stream.read(size)
        require(len(value) == size, "invalid LayerSources uncompressed tar")
        return value


class LayerTarInfo(tarfile.TarInfo):
    """Bound stdlib GNU/PAX metadata and recursive extension chains (Python 3.12)."""
    @classmethod
    def _fromtarfile(cls, archive, *, dircheck=True):
        depth = getattr(archive, "layer_header_depth", 0)
        archive.layer_header_depth = depth + 1
        try:
            require(depth < 64, "invalid LayerSources uncompressed tar")
            return super()._fromtarfile(archive, dircheck=dircheck)
        finally:
            archive.layer_header_depth = depth

    def _proc_pax(self, archive):
        require(0 <= self.size <= 65536, "invalid LayerSources uncompressed tar")
        return super()._proc_pax(archive)

    def _proc_gnulong(self, archive):
        require(0 <= self.size <= 65536, "invalid LayerSources uncompressed tar")
        return super()._proc_gnulong(archive)

    def _proc_member(self, archive):
        # Includes every ordinary and GNU/PAX header before processing its payload.
        archive.fileobj.charge(headers=1)
        return super()._proc_member(archive)


def layer_tar_format(stream, size, image_budget=None):
    """Structural read only: no decompression, extraction or inner path/type policy."""
    try:
        require(size >= 1024 and size % 512 == 0
                and callable(getattr(tarfile.TarInfo, "_fromtarfile", None)), "invalid LayerSources uncompressed tar")
        if image_budget is None:
            image_budget = LayerTarBudget(MAX_IMAGE_TAR_HEADERS, MAX_IMAGE_TAR_METADATA)
        reader = LayerTarReader(stream, size, image_budget)
        with tarfile.open(fileobj=reader, mode="r:", tarinfo=LayerTarInfo) as layer:
            # No extraction/link resolution needs historical TarInfo objects. Use
            # next(), not the index-based iterator, while releasing inherited PAX
            # dictionaries so their per-entry copies cannot accumulate in memory.
            while layer.next() is not None:
                layer.members.clear()
            end = layer.offset
        # Stdlib alone tolerates missing terminators or garbage after a zero block.
        require(end % 512 == 0 and size - end >= 1024, "invalid LayerSources uncompressed tar")
        reader.parsing = False
        reader.seek(end)
        while reader.tell() < size:
            require(not reader.read(min(1024 * 1024, size - reader.tell())).strip(b"\0"),
                    "invalid LayerSources uncompressed tar")
    except Exception:
        # Covers numeric/recursive parser failures, never KeyboardInterrupt/SystemExit.
        raise Invalid("invalid LayerSources uncompressed tar") from None


def archive_image(path, item, commit):
    require(isinstance(item, dict) and set(item) == {"archive", "size", "sha256", "image_id", "platform", "source_commit"},
            "unexpected or missing image item fields")
    require(item["platform"] == "linux/amd64" and item["source_commit"] == commit, "image provenance mismatch")
    require(hex_value(item["sha256"], 64), "invalid archive checksum")
    require(isinstance(item["image_id"], str) and re.fullmatch(r"sha256:[0-9a-f]{64}", item["image_id"]), "image must use immutable ID")
    require(type(item["size"]) is int and item["size"] > 0 and path.stat().st_size == item["size"], "archive size mismatch")
    with path.open("rb") as stream:
        require(digest(stream) == item["sha256"], "archive checksum mismatch")
    # Only uncompressed docker-save archives, not arbitrary OCI/multi-platform exports.
    # No extract/extractall call; links, devices, duplicate/traversal entries refused.
    with tarfile.open(path, mode="r:") as archive:
        members = {}
        for member in archive:
            name = member.name
            require(name not in members and name and not name.startswith("/") and "\\" not in name
                    and all(p not in ("", ".", "..") for p in name.rstrip("/").split("/")), "unsafe or duplicate archive path")
            require(member.isfile() or member.isdir(), "archive links or special files refused")
            members[name] = member
        def data(name):
            require(name in members and members[name].isfile() and members[name].size <= 8 * 1024 * 1024, "missing or oversized image metadata")
            with archive.extractfile(members[name]) as stream:
                return stream.read()
        manifest = read_json(data("manifest.json"))
        require(isinstance(manifest, list) and len(manifest) == 1, "archive must contain exactly one image")
        record = manifest[0]
        require(isinstance(record, dict), "invalid docker-save manifest record")
        required = {"Config", "RepoTags", "Layers"}
        require(required <= set(record), "missing docker-save manifest fields")
        require(set(record) in (required, required | {"LayerSources"}), "unreviewed docker-save manifest fields")
        has_sources = "LayerSources" in record
        if has_sources:
            require(record["Config"] == "blobs/sha256/" + item["image_id"][7:], "invalid LayerSources blob path")
            image_budget = LayerTarBudget(MAX_IMAGE_TAR_HEADERS, MAX_IMAGE_TAR_METADATA)
        config_bytes = data(record["Config"])
        require("sha256:" + hashlib.sha256(config_bytes).hexdigest() == item["image_id"], "image config digest mismatch")
        config = read_json(config_bytes)
        require(config.get("os") == "linux" and config.get("architecture") == "amd64" and not config.get("variant"), "image platform mismatch")
        require(config.get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision") == commit, "image revision label mismatch")
        # Image-baked env must not smuggle remote endpoints/identity/credentials into this profile.
        baked_env = config.get("config", {}).get("Env", [])
        require(isinstance(baked_env, list), "invalid image environment")
        safe_env = {"PATH", "LANG", "PYTHON_VERSION", "PYTHON_SHA256", "PYTHON_PIP_VERSION", "PYTHON_SETUPTOOLS_VERSION", "NODE_VERSION", "YARN_VERSION", "GPG_KEY"}
        require(all(isinstance(value, str) and "=" in value and value.split("=", 1)[0] in safe_env
                    and "\n" not in value and "\r" not in value for value in baked_env), "unreviewed baked image environment")
        require(all(not value.startswith("GPG_KEY=") or re.fullmatch(r"GPG_KEY=[0-9A-Fa-f]{40}", value)
                    for value in baked_env), "invalid public GPG fingerprint")
        require(not config.get("config", {}).get("Volumes"), "image-declared writable volumes refused")
        layers = record["Layers"]
        roots = config.get("rootfs", {})
        if has_sources:
            require(isinstance(roots, dict) and roots.get("type") == "layers"
                    and isinstance(layers, list) and layers and all(isinstance(name, str) for name in layers)
                    and len(set(layers)) == len(layers), "invalid image layers")
            diff_ids = roots.get("diff_ids")
            require(isinstance(diff_ids, list) and diff_ids
                    and all(isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in diff_ids)
                    and len(set(diff_ids)) == len(diff_ids), "invalid LayerSources mapping")
            sources = record["LayerSources"]
            require(isinstance(sources, dict) and set(sources) == set(diff_ids), "invalid LayerSources mapping")
        require(roots.get("type") == "layers" and isinstance(layers, list) and layers and len(set(layers)) == len(layers)
                and len(layers) == len(roots.get("diff_ids", [])), "invalid image layers")
        for name, expected in zip(layers, roots["diff_ids"]):
            if has_sources:
                require(name == "blobs/sha256/" + expected[7:], "invalid LayerSources blob path")
            require(name in members and members[name].isfile(), "missing image layer")
            if has_sources:
                source = sources[expected]
                require(isinstance(source, dict) and set(source) == {"mediaType", "digest", "size"},
                        "unreviewed LayerSources descriptor fields")
                # Moby's Linux classic exporter describes the uncompressed local tar.
                # Registry gzip/foreign descriptors are not interchangeable with diff_ids.
                require(source["mediaType"] == "application/vnd.oci.image.layer.v1.tar", "unreviewed LayerSources media type")
                require(source["digest"] == expected, "LayerSources digest mismatch")
                require(type(source["size"]) is int and source["size"] > 0
                        and source["size"] == members[name].size, "LayerSources size mismatch")
            with archive.extractfile(members[name]) as stream:
                require("sha256:" + digest(stream) == expected, "image layer digest mismatch")
            if has_sources:
                # Header/length validation without decompression or filesystem extraction.
                # Inner whiteouts, devices and links are legal layer contents, not outer
                # archive entries. This does not certify the safety of image contents.
                with archive.extractfile(members[name]) as stream:
                    layer_tar_format(stream, members[name].size, image_budget)


def validate(bundle):
    root = Path(bundle).resolve()
    manifest = read_json(safe_file(root, "manifest.json").read_text())
    keys(manifest, ("format", "source_commit", "required_db_revision", "images"))
    require(manifest["format"] == "slc-offline-readonly-v1", "unsupported bundle format")
    require(hex_value(manifest["source_commit"], 40), "exact source commit required")
    require(manifest["required_db_revision"] == REVISION, "database revision mismatch")
    keys(manifest["images"], ("api", "web"))
    for item in manifest["images"].values():
        require(isinstance(item, dict), "invalid image entry")
        archive_image(safe_file(root, item.get("archive")), item, manifest["source_commit"])
    operator = read_json(safe_file(root, "operator.json").read_text())
    keys(operator, ("profile", "database_env_file", "database_preprovisioned", "database_readonly_role", "data_classification"))
    require(operator["profile"] == "linux-localhost-readonly" and operator["database_preprovisioned"] is True
            and operator["database_readonly_role"] is True and operator["data_classification"] == "synthetic-only", "operator scope must be pre-provisioned synthetic localhost")
    secret = safe_file(root, operator["database_env_file"])
    require("$" not in str(secret), "Compose-interpolated secret paths refused")
    require(os.name == "posix" and not stat.S_IMODE(secret.stat().st_mode) & 0o077, "database env file must be private (mode 0600 or stricter)")
    raw = secret.read_text()
    require(re.fullmatch(r"DATABASE_URL=[^\s\x00-\x1f\x7f$#'\"\\]+\n?", raw) is not None, "database env must contain only a literal DATABASE_URL")
    url = urlsplit(raw.strip().split("=", 1)[1])
    require(url.scheme == "postgresql+psycopg" and url.hostname == "127.0.0.1" and url.port == 5432
            and url.username and url.password and re.fullmatch(r"/[a-z][a-z0-9_]{2,62}", url.path)
            and not url.query and not url.fragment, "database must be explicit local PostgreSQL without URL options")
    require(unquote(url.password).lower() not in ("slc_dev_password", "password", "changeme", "replace_me")
            and len(unquote(url.password)) >= 16, "operator-managed non-default database password required")
    # Deliberately no database connection: this does not prove server version, grants or schema.
    return compose(manifest, secret)


def compose(manifest, secret):
    common = {"platform": "linux/amd64", "pull_policy": "never", "network_mode": "host",
              "read_only": True, "restart": "no", "cap_drop": ["ALL"],
              "security_opt": ["no-new-privileges:true"], "user": "65532:65532",
              "working_dir": "/app", "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m"],
              "healthcheck": {"disable": True}}
    api = {**common, "image": manifest["images"]["api"]["image_id"],
           "entrypoint": ["/usr/local/bin/python", "-m", "uvicorn"],
           "command": ["app.main:app", "--host", "127.0.0.1", "--port", "8000"],
           "env_file": [{"path": str(secret), "required": True, "format": "raw"}],
           "environment": {"READ_ONLY_MODE": "true", "AUTH_MODE": "disabled", "ADMIN_OPERATOR_ENABLED": "false",
                           "SEED_ON_STARTUP": "false", "SEED_ZFI_DEMO": "false", "REQUIRED_DB_REVISION": REVISION,
                           "CORS_ORIGINS": "http://127.0.0.1:3000", "PYTHONPATH": "/app", "PYTHONDONTWRITEBYTECODE": "1",
                           "PGOPTIONS": "-c default_transaction_read_only=on"}}
    web = {**common, "image": manifest["images"]["web"]["image_id"],
           "entrypoint": ["/usr/local/bin/node", "node_modules/next/dist/bin/next"],
           "command": ["start", "--hostname", "127.0.0.1", "--port", "3000"],
           "environment": {**dict.fromkeys(GATES, "disabled"), "API_BASE_URL": "http://127.0.0.1:8000",
                           "NEXT_PUBLIC_API_URL": "", "NEXT_PUBLIC_API_BASE_URL": "", "NEXT_TELEMETRY_DISABLED": "1",
                           "NODE_ENV": "production"}}
    # Fresh nested dictionaries per service: fixed policy, never operator overrides.
    for service in (api, web):
        service["logging"] = {"driver": "local", "options": {
            "max-size": "10m", "max-file": "3", "compress": "true"}}
    return {"name": "slc-offline-readonly", "services": {"api": api, "web": web}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate(args.bundle)
    except (Invalid, OSError, ValueError, TypeError, KeyError, AttributeError, tarfile.TarError):
        # Do not print malformed input, filesystem paths, URL/password or library exception text.
        print("BLOCKED: offline inputs invalid or incomplete; no deployment or network action performed.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    print("CONFIGURATION_ONLY: archive integrity checked, not image trust/runtime/DB/schema/network/company acceptance.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
