#!/usr/bin/env python3
"""Read-only npm v3 transport inventory. Never fetch, extract or execute packages.

Cache layout is flat: sha512-<128 lowercase hex>.tgz, exactly one regular,
single-link file per unique artifact. POSIX no-follow directory handles are
required; unsupported hosts fail closed. This is not an npm cache or installer.
"""
import argparse
import base64
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

MAX_LOCK_BYTES = 16 * 1024 * 1024
MAX_PACKAGES = 20000
MAX_JSON_NODES = 500000
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
NAME = r"[a-z0-9_~][a-z0-9._~-]*"
PACKAGE = rf"(?:@{NAME}/)?{NAME}"
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
LOCATION = re.compile(rf"node_modules/{PACKAGE}(?:/node_modules/{PACKAGE})*")
URL = re.compile(rf"https://registry\.npmjs\.org/(?P<name>{PACKAGE})/-/(?P<file>[a-zA-Z0-9._~+-]+\.tgz)")
LIMITATION = ("Transport bytes only. No installation or runtime completeness is established: "
              "npm lifecycle scripts and transitive tooling may require additional inputs. "
              "Lockfile checksums do not authenticate provenance or package safety.")


class InventoryError(ValueError):
    """Safe, fixed diagnostic with no input values."""


def require(ok, message):
    if not ok:
        raise InventoryError(message)


@contextlib.contextmanager
def directory(path):
    """Walk every component with no-follow handles; do not resolve symlinks."""
    require(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and
            os.open in os.supports_dir_fd, "secure filesystem reads unsupported")
    path = Path(path)
    require(".." not in path.parts, "parent path components forbidden")
    absolute = path if path.is_absolute() else Path.cwd() / path
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def regular_file(parent_fd, name):
    # O_NONBLOCK prevents a hostile FIFO from blocking before fstat rejects it.
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                "expected single-link regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream, before
            after = os.fstat(fd)
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    "file changed during verification")
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(_value):
    raise InventoryError("invalid JSON number")


def read_lock(path):
    path = Path(path)
    with directory(path.parent) as fd, regular_file(fd, path.name) as (stream, info):
        require(info.st_size <= MAX_LOCK_BYTES, "lockfile size limit exceeded")
        raw = stream.read(MAX_LOCK_BYTES + 1)
        require(len(raw) <= MAX_LOCK_BYTES, "lockfile size limit exceeded")
    lock = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=invalid_constant)
    pending = [(lock, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        require(count <= MAX_JSON_NODES and depth <= 64, "JSON complexity limit exceeded")
        require(not isinstance(value, float) or math.isfinite(value), "invalid JSON number")
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
    return lock, hashlib.sha256(raw).hexdigest()


def integrity_digest(value):
    require(isinstance(value, str) and re.fullmatch(r"sha512-[A-Za-z0-9+/]{86}==", value),
            "canonical sha512 integrity required")
    decoded = base64.b64decode(value[7:], validate=True)
    require(len(decoded) == 64 and base64.b64encode(decoded).decode("ascii") == value[7:],
            "canonical sha512 integrity required")
    return decoded.hex()


def inventory(lock, lock_sha256):
    require(isinstance(lock, dict) and type(lock.get("lockfileVersion")) is int and
            lock["lockfileVersion"] == 3, "npm lockfile version 3 required")
    packages = lock.get("packages")
    require(isinstance(packages, dict) and "" in packages and
            isinstance(packages[""], dict) and 1 < len(packages) <= MAX_PACKAGES + 1,
            "invalid package inventory")
    artifacts = {}
    sources = {}
    for location, package in sorted(packages.items()):
        if location == "":
            continue
        require(LOCATION.fullmatch(location) is not None and len(location) <= 2048,
                "invalid package location")
        require(isinstance(package, dict), "invalid package metadata")
        require(all(flag not in package or type(package[flag]) is bool
                    for flag in ("link", "inBundle")), "invalid package flag")
        require(not package.get("link") and not package.get("inBundle"),
                "linked or bundled packages unsupported")
        version = package.get("version")
        require(isinstance(version, str) and len(version) <= 256 and VERSION.fullmatch(version),
                "exact package version required")
        # Numeric prerelease identifiers must have no leading zero (SemVer).
        prerelease = version.split("+", 1)[0].partition("-")[2]
        require(all(not (p.isdigit() and len(p) > 1 and p[0] == "0")
                    for p in prerelease.split(".")), "invalid exact package version")
        resolved = package.get("resolved")
        match = URL.fullmatch(resolved) if isinstance(resolved, str) and len(resolved) <= 2048 else None
        require(match is not None, "approved HTTPS npm tarball source required")
        name = match.group("name")
        require(match.group("file") == name.rsplit("/", 1)[-1] + "-" + version + ".tgz",
                "tarball source/version mismatch")
        digest = integrity_digest(package.get("integrity"))
        metadata = {"name": name, "version": version, "url": resolved,
                    "integrity": package["integrity"], "sha512": digest,
                    "filename": "sha512-" + digest + ".tgz"}
        require(resolved not in sources or sources[resolved] == digest,
                "conflicting artifact source")
        sources[resolved] = digest
        occurrence = {"location": location}
        for flag in ("optional", "dev", "devOptional", "hasInstallScript"):
            require(flag not in package or type(package[flag]) is bool, "invalid package flag")
            occurrence[flag] = package.get(flag, False)
        for platform in ("os", "cpu", "libc"):
            values = package.get(platform, [])
            require(isinstance(values, list) and len(values) <= 128 and
                    all(isinstance(v, str) and re.fullmatch(r"!?[a-z0-9][a-z0-9_-]{0,63}", v)
                        for v in values) and len(values) == len(set(values)),
                    "invalid package platform metadata")
            occurrence[platform] = sorted(values)
        if digest in artifacts:
            require(all(artifacts[digest][k] == v for k, v in metadata.items()),
                    "conflicting digest metadata")
            artifacts[digest]["packages"].append(occurrence)
        else:
            artifacts[digest] = {**metadata, "packages": [occurrence]}
    return {"format": "slc-offline-npm-inventory-v1", "lockfile_sha256": lock_sha256,
            "scope": "all-lockfile-packages-including-optional-and-all-platforms",
            "status": "INVENTORY_ONLY", "limitations": LIMITATION,
            "package_count": len(packages) - 1, "artifact_count": len(artifacts),
            "artifacts": [artifacts[k] for k in sorted(artifacts)]}


def verify_artifacts(manifest, path):
    expected = {a["filename"] for a in manifest["artifacts"]}
    sizes = []
    total = 0
    with directory(path) as fd:
        def scan_names():
            # Every accepted name is unique and expected, bounding both scans.
            with os.scandir(fd) as entries:
                names = set()
                for entry in entries:
                    require(entry.name in expected and entry.name not in names,
                            "unexpected or ambiguous artifact entry")
                    names.add(entry.name)
            require(names == expected, "missing artifact")

        scan_names()
        for artifact in manifest["artifacts"]:
            with regular_file(fd, artifact["filename"]) as (stream, info):
                require(0 < info.st_size <= MAX_ARTIFACT_BYTES, "artifact size limit exceeded")
                total += info.st_size
                require(total <= MAX_TOTAL_BYTES, "total artifact size limit exceeded")
                digest = hashlib.sha512()
                size = 0
                while True:
                    chunk = stream.read(min(1024 * 1024, MAX_ARTIFACT_BYTES + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    require(size <= MAX_ARTIFACT_BYTES and size <= info.st_size,
                            "artifact size changed or limit exceeded")
                    digest.update(chunk)
                require(size == info.st_size and digest.hexdigest() == artifact["sha512"],
                        "artifact digest mismatch")
                sizes.append(size)
        scan_names()
    for artifact, size in zip(manifest["artifacts"], sizes):
        artifact["size_bytes"] = size
    manifest["status"] = "ARTIFACT_BYTES_VERIFIED"


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "offline npm inventory: invalid arguments\n")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("lockfile")
    parser.add_argument("--artifacts", metavar="DIRECTORY")
    args = parser.parse_args(argv)
    try:
        lock, sha256 = read_lock(args.lockfile)
        manifest = inventory(lock, sha256)
        if args.artifacts is not None:
            verify_artifacts(manifest, args.artifacts)
        output = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    except (InventoryError, OSError, ValueError, TypeError, RecursionError, OverflowError):
        # Do not echo URLs, input data, local paths, exception details or credentials.
        print("offline npm inventory: validation failed", file=sys.stderr)
        return 1
    sys.stdout.write(output)
    print(manifest["status"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
