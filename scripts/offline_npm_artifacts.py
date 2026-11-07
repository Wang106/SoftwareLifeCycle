#!/usr/bin/env python3
"""Read-only byte and package.json audit of a complete npm tarball collection.

Never downloads, extracts archives to disk, installs, or runs lifecycle scripts.
The existing inventory validator supplies lock/source/filesystem validation.
"""
import argparse
import gzip
import hashlib
import json
import math
import re
import sys
import tarfile
import zlib

import offline_npm_inventory as inventory

MAX_JSON_BYTES = 1024 * 1024
MAX_JSON_NODES = 50000
MAX_MEMBERS = 100000
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_TOTAL_EXPANDED_BYTES = 32 * 1024 * 1024 * 1024
MAX_EXTENSION_BYTES = 65536
LIFECYCLE = ("preinstall", "install", "postinstall", "prepare")
require = inventory.require


class BoundedTarInfo(tarfile.TarInfo):
    """Bound stdlib extension work before payload allocation (Python 3.12)."""
    @classmethod
    def _fromtarfile(cls, archive, *, dircheck=True):
        archive.audit_header_count = getattr(archive, "audit_header_count", 0) + 1
        require(archive.audit_header_count <= MAX_MEMBERS + 1, "archive header count exceeded")
        try:
            return super()._fromtarfile(archive, dircheck=dircheck)
        except (tarfile.InvalidHeaderError, tarfile.TruncatedHeaderError, tarfile.EmptyHeaderError):
            # TarFile.next otherwise tolerates these after the first member.
            # A genuine zero terminal block raises EOFHeaderError instead.
            raise inventory.InventoryError("invalid or missing terminal tar header") from None

    def _proc_pax(self, archive):
        require(0 <= self.size <= MAX_EXTENSION_BYTES, "PAX header limit exceeded")
        return super()._proc_pax(archive)

    def _proc_gnulong(self, archive):
        require(0 <= self.size <= MAX_EXTENSION_BYTES, "GNU long header limit exceeded")
        return super()._proc_gnulong(archive)

    def _proc_sparse(self, *_args):
        raise inventory.InventoryError("sparse archives unsupported")

    _proc_gnusparse_00 = _proc_sparse
    _proc_gnusparse_01 = _proc_sparse
    _proc_gnusparse_10 = _proc_sparse


class ExpandedReader:
    """Bound gzip output before tarfile parses even a hostile PAX header."""
    def __init__(self, stream):
        self.stream = stream
        self.size = 0

    def read(self, size):
        require(0 <= size <= MAX_EXPANDED_BYTES, "invalid expanded read")
        data = self.stream.read(min(size, MAX_EXPANDED_BYTES + 1 - self.size))
        self.size += len(data)
        require(self.size <= MAX_EXPANDED_BYTES, "expanded archive limit exceeded")
        return data


def package_json(raw):
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=inventory.unique_object,
                       parse_constant=inventory.invalid_constant)
    pending, count = [(value, 0)], 0
    while pending:
        child, depth = pending.pop()
        count += 1
        require(count <= MAX_JSON_NODES and depth <= 64, "package JSON complexity limit exceeded")
        require(not isinstance(child, float) or math.isfinite(child), "invalid JSON number")
        if isinstance(child, dict):
            pending.extend((v, depth + 1) for v in child.values())
        elif isinstance(child, list):
            pending.extend((v, depth + 1) for v in child)
    require(isinstance(value, dict), "package JSON object required")
    return value


def string_map(package, field, maximum):
    values = package.get(field, {})
    require(isinstance(values, dict) and len(values) <= 10000 and
            all(isinstance(k, str) and len(k) <= 256 and isinstance(v, str) and len(v) <= maximum
                for k, v in values.items()), "invalid package mapping")
    return values


def metadata(package, artifact, binding_gyp):
    require(package.get("name") == artifact["name"] and package.get("version") == artifact["version"],
            "archive identity mismatch")
    scripts = string_map(package, "scripts", 65536)
    result = {"name": package["name"], "version": package["version"],
              "lifecycle_scripts": {k: scripts[k] for k in LIFECYCLE if k in scripts},
              "binding_gyp": binding_gyp, "engines": string_map(package, "engines", 1024),
              "optional_dependencies": string_map(package, "optionalDependencies", 1024)}
    result["gypfile"] = package.get("gypfile")
    result["binding_gyp_default_candidate"] = bool(binding_gyp and package.get("gypfile") is not False
                                                  and not scripts.get("install") and not scripts.get("preinstall"))
    has_install = any(scripts.get(k) for k in LIFECYCLE[:3]) or result["binding_gyp_default_candidate"]
    result["has_install_script_evidence"] = has_install
    result["install_script_discrepancies"] = []
    for field in ("os", "cpu", "libc"):
        values = package.get(field, [])
        require(isinstance(values, list) and len(values) <= 128 and
                all(isinstance(v, str) and re.fullmatch(r"!?[a-z0-9][a-z0-9_-]{0,63}", v)
                    for v in values) and len(values) == len(set(values)), "invalid archive platform")
        result[field] = sorted(values)
    for occurrence in artifact["packages"]:
        if occurrence["hasInstallScript"] != has_install:
            result["install_script_discrepancies"].append({
                "location": occurrence["location"], "lock_has_install_script": occurrence["hasInstallScript"],
                "archive_has_install_script_evidence": has_install})
        for field in ("os", "cpu", "libc"):
            # npm lockfiles can omit libc. Preserve actual archive metadata;
            # compare every platform constraint that the lock does record.
            require(not occurrence[field] or occurrence[field] == result[field],
                    "archive platform mismatch")
    return result


def audit_archive(stream, artifact):
    digest = hashlib.sha512()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        require(size <= inventory.MAX_ARTIFACT_BYTES, "artifact size limit exceeded")
        digest.update(chunk)
    require(size == artifact["size_bytes"] and digest.hexdigest() == artifact["sha512"],
            "artifact changed before archive audit")
    stream.seek(0)
    package, binding_gyp, count, seen, root = None, False, 0, set(), None
    with gzip.GzipFile(fileobj=stream, mode="rb") as compressed:
        expanded = ExpandedReader(compressed)
        with tarfile.open(fileobj=expanded, mode="r|", tarinfo=BoundedTarInfo) as archive:
            for member in archive:
                count += 1
                require(count <= MAX_MEMBERS, "archive member count exceeded")
                parts = member.name.rstrip("/").split("/")
                require(all(p not in ("", ".", "..") for p in parts)
                        and "\\" not in member.name and "\x00" not in member.name,
                        "noncanonical archive path")
                root = parts[0] if root is None else root
                require(parts[0] == root and (len(parts) > 1 or member.isdir()),
                        "single archive root directory required")
                require(member.isfile() or member.isdir(), "unsupported archive member")
                require(not member.isfile() or not member.name.endswith("/"), "regular file path alias")
                canonical = member.name.rstrip("/")
                require(canonical not in seen, "duplicate archive path")
                seen.add(canonical)
                require(0 <= member.size <= MAX_EXPANDED_BYTES, "archive member size limit exceeded")
                if member.name == root + "/binding.gyp":
                    require(member.isfile(), "binding.gyp must be regular")
                    binding_gyp = True
                if member.name == root + "/package.json":
                    require(package is None and member.isfile() and 0 < member.size <= MAX_JSON_BYTES,
                            "invalid package JSON entry")
                    with archive.extractfile(member) as source:
                        raw = source.read(MAX_JSON_BYTES + 1)
                    require(len(raw) == member.size, "truncated package JSON")
                    package = package_json(raw)
            # Streaming tarfile can read past its terminal zero block. Check its
            # buffered bytes too, not just unread gzip output below.
            require(not archive.fileobj.buf.strip(b"\0"), "nonzero trailing tar data")
        # Read through gzip EOF to validate CRC/truncation and account for padding.
        while chunk := expanded.read(1024 * 1024):
            require(not chunk.strip(b"\0"), "nonzero trailing tar data")
    require(package is not None, "package JSON missing")
    result = metadata(package, artifact, binding_gyp)
    result["archive_root"] = root
    return result, expanded.size


def audit_artifacts(lockfile, path):
    require(callable(getattr(tarfile.TarInfo, "_fromtarfile", None)), "supported tarfile hook required")
    lock, sha256 = inventory.read_lock(lockfile)
    manifest = inventory.inventory(lock, sha256)
    inventory.verify_artifacts(manifest, path)
    expanded_size = 0
    with inventory.directory(path) as fd:
        for artifact in manifest["artifacts"]:
            with inventory.regular_file(fd, artifact["filename"]) as (stream, _info):
                artifact["archive_metadata"], expanded = audit_archive(stream, artifact)
                expanded_size += expanded
                require(expanded_size <= MAX_TOTAL_EXPANDED_BYTES, "total expanded limit exceeded")
    manifest.update(format="slc-offline-npm-artifacts-v1", status="ARTIFACT_BYTES_VERIFIED_METADATA_RECORDED",
                    total_size_bytes=sum(a["size_bytes"] for a in manifest["artifacts"]),
                    total_expanded_bytes=expanded_size,
                    limitations="Verified lock-matching bytes and recorded archive metadata, including lock flag discrepancies; not an installation, "
                    "lifecycle execution, vulnerability audit, source signature or physical-egress acceptance.")
    return manifest


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "offline npm artifacts: invalid arguments\n")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("lockfile")
    parser.add_argument("artifacts")
    args = parser.parse_args(argv)
    try:
        result = audit_artifacts(args.lockfile, args.artifacts)
        output = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    except (inventory.InventoryError, OSError, ValueError, TypeError, RecursionError,
            OverflowError, tarfile.TarError, EOFError, zlib.error):
        print("offline npm artifacts: validation failed", file=sys.stderr)
        return 1
    sys.stdout.write(output)
    print(result["status"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
