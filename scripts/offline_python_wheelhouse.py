#!/usr/bin/env python3
"""Inventory trusted PyPI wheels and ask pip to verify an offline hash-locked closure.

No downloader, installer, custom dependency resolver or package execution. pip's
vendored packaging supplies PEP 440/508/425 parsing. POSIX no-follow reads and a
private snapshot protect the bytes subsequently read by pip. See the scope doc.
"""
import argparse
import contextlib
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import zipfile

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import compatible_tags, cpython_tags, parse_tag
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import Version

FORMAT = "slc-python-wheelhouse-v1"
TARGET = {"implementation": "cpython", "python": "3.12", "os": "linux",
          "architecture": "x86_64", "max_glibc": "2.39"}
PLATFORMS = [f"manylinux_2_{minor}_x86_64" for minor in range(39, 4, -1)] + [
    "manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]
TAGS = set(cpython_tags((3, 12), abis=["cp312"], platforms=PLATFORMS)) | set(
    compatible_tags((3, 12), interpreter="cp312", platforms=PLATFORMS))
MAX_JSON = 4 * 1024 * 1024
MAX_WHEEL = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_PACKAGES = 256
SHA256 = re.compile(r"[0-9a-f]{64}")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


@contextlib.contextmanager
def directory(path):
    require(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and
            os.open in os.supports_dir_fd, "secure filesystem reads unsupported")
    path = Path(path)
    require(".." not in path.parts, "parent traversal forbidden")
    path = path if path.is_absolute() else Path.cwd() / path
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def regular_file(fd, name):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(handle)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "regular file required")
        with os.fdopen(handle, "rb", closefd=False) as stream:
            yield stream, before
            after = os.fstat(handle)
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    "file changed during read")
    finally:
        os.close(handle)


def read_bytes(path, limit=MAX_JSON):
    path = Path(path)
    with directory(path.parent) as fd, regular_file(fd, path.name) as (stream, info):
        require(info.st_size <= limit, "input size limit exceeded")
        raw = stream.read(limit + 1)
        require(len(raw) == info.st_size and len(raw) <= limit, "input size changed")
        return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    raw = read_bytes(path)
    result = json.loads(raw, object_pairs_hook=unique_object,
                        parse_constant=lambda _: require(False, "invalid JSON number"))
    return result, hashlib.sha256(raw).hexdigest()


def roots(raw):
    result = {}
    for line in raw.decode("utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        req = Requirement(line)
        specs = list(req.specifier)
        require(not req.url and not req.marker and len(specs) == 1 and
                specs[0].operator == "==" and "*" not in specs[0].version,
                "plain exact requirements required")
        name = canonicalize_name(req.name)
        require(name not in result, "duplicate direct dependency")
        result[name] = {"name": name, "version": str(Version(specs[0].version)),
                        "extras": sorted(req.extras)}
    require(0 < len(result) <= MAX_PACKAGES, "invalid direct dependency count")
    return [result[name] for name in sorted(result)]


def wheel_identity(filename):
    require(isinstance(filename, str) and len(filename) <= 255 and
            re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", filename), "wheel filename required")
    name, version, build, tags = parse_wheel_filename(filename)
    require(not build and bool(tags & TAGS), "unsupported wheel platform or build")
    # The selected wheel may have several equivalent tags, but no platform outside
    # the declared target is accepted (in particular linux_x86_64 lacks a glibc floor).
    require(all(tag.platform == "any" or tag.platform in PLATFORMS for tag in tags),
            "unapproved wheel platform")
    return name, str(version), sorted(str(tag) for tag in tags)


def official_source(url, filename):
    require(isinstance(url, str) and len(url) <= 2048, "invalid source")
    parts = urlsplit(url)
    require(parts.scheme == "https" and parts.netloc == "files.pythonhosted.org" and
            not parts.query and not parts.fragment and
            re.fullmatch(r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/" + re.escape(filename), parts.path),
            "official PyPI wheel source required")


def metadata(stream, artifact):
    with zipfile.ZipFile(stream) as archive:
        entries = archive.infolist()
        require(len(entries) <= 10000 and len({e.filename for e in entries}) == len(entries),
                "duplicate or excessive ZIP entries")
        prefix = None
        for suffix in ("METADATA", "WHEEL"):
            matches = [e for e in entries if re.fullmatch(r"[^/]+\.dist-info/" + suffix, e.filename)]
            require(len(matches) == 1 and matches[0].file_size <= MAX_JSON,
                    "wheel metadata missing or excessive")
            current = matches[0].filename.rsplit("/", 1)[0]
            require(prefix is None or prefix == current, "conflicting wheel metadata")
            prefix = current
            with archive.open(matches[0]) as source:
                raw = source.read(MAX_JSON + 1)
            require(len(raw) <= MAX_JSON, "wheel metadata excessive")
            parsed = BytesParser().parsebytes(raw)
            if suffix == "METADATA":
                require(len(parsed.get_all("Name", [])) == 1 and
                        len(parsed.get_all("Version", [])) == 1 and
                        canonicalize_name(parsed["Name"]) == artifact["name"] and
                        str(Version(parsed["Version"])) == artifact["version"],
                        "wheel metadata identity mismatch")
                for dep in parsed.get_all("Requires-Dist", []):
                    # --no-index alone does not stop direct URL dependencies.
                    require(Requirement(dep).url is None, "direct dependency URL forbidden")
            else:
                internal_tags = set()
                for tag in parsed.get_all("Tag", []):
                    internal_tags.update(parse_tag(tag))
                require(sorted(str(t) for t in internal_tags) == artifact["tags"],
                        "wheel internal tags mismatch")


def verify_artifacts(manifest, wheelhouse, snapshot=None):
    expected = {a["filename"] for a in manifest["artifacts"]}
    total = 0
    with directory(wheelhouse) as fd:
        def names():
            found = set()
            with os.scandir(fd) as entries:
                for entry in entries:
                    require(entry.name in expected, "unexpected artifact")
                    found.add(entry.name)
            require(found == expected, "missing artifact")
        names()
        for artifact in manifest["artifacts"]:
            with regular_file(fd, artifact["filename"]) as (stream, info):
                require(0 < info.st_size <= MAX_WHEEL, "wheel size limit exceeded")
                total += info.st_size
                require(total <= MAX_TOTAL, "wheelhouse size limit exceeded")
                digest = hashlib.sha256()
                with contextlib.ExitStack() as stack:
                    target = stack.enter_context((snapshot / artifact["filename"]).open("xb")) if snapshot else None
                    size = 0
                    while chunk := stream.read(1024 * 1024):
                        size += len(chunk)
                        require(size <= info.st_size, "wheel size changed")
                        digest.update(chunk)
                        if target:
                            target.write(chunk)
                require(size == info.st_size and digest.hexdigest() == artifact["sha256"],
                        "wheel hash mismatch")
                require(artifact.get("size_bytes", size) == size, "wheel size mismatch")
                stream.seek(0)
                metadata(stream, artifact)
                artifact["size_bytes"] = size
        names()
    return total


def lock_text(manifest):
    direct = {p["name"]: p for p in manifest["direct_requirements"]}
    lines = ["# Linux x86_64 / CPython 3.12; generated from the reviewed PyPI resolver report.",
             "# One selected wheel per package. Keep extras; do not use --no-deps to install."]
    for artifact in manifest["artifacts"]:
        extras = direct.get(artifact["name"], {}).get("extras", [])
        suffix = "[" + ",".join(extras) + "]" if extras else ""
        lines.append(f'{artifact["name"]}{suffix}=={artifact["version"]} --hash=sha256:{artifact["sha256"]}')
    return "\n".join(lines) + "\n"


def validate_manifest(manifest, requirements):
    require(isinstance(manifest, dict) and manifest.get("format") == FORMAT and
            manifest.get("target") == TARGET and manifest.get("index_url") == "https://pypi.org/simple",
            "invalid inventory target or source")
    require(manifest.get("requirements_sha256") == hashlib.sha256(requirements).hexdigest() and
            manifest.get("direct_requirements") == roots(requirements), "requirements changed")
    require(isinstance(manifest.get("resolver_report_sha256"), str) and
            SHA256.fullmatch(manifest["resolver_report_sha256"]), "resolver report digest required")
    require(isinstance(manifest.get("resolver_pip_version"), str) and
            re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", manifest["resolver_pip_version"]),
            "resolver pip version required")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list) and 0 < len(artifacts) <= MAX_PACKAGES, "invalid wheel count")
    seen = {}
    for artifact in artifacts:
        require(isinstance(artifact, dict), "invalid artifact")
        name, version, tags = wheel_identity(artifact.get("filename"))
        require((artifact.get("name"), artifact.get("version"), artifact.get("tags")) ==
                (name, version, tags), "wheel identity mismatch")
        require(name not in seen, "duplicate distribution")
        seen[name] = artifact
        official_source(artifact.get("url"), artifact["filename"])
        require(isinstance(artifact.get("sha256"), str) and SHA256.fullmatch(artifact["sha256"]),
                "invalid wheel digest")
        require(type(artifact.get("size_bytes")) is int and 0 < artifact["size_bytes"] <= MAX_WHEEL,
                "invalid wheel size")
    require([a["name"] for a in artifacts] == sorted(seen), "inventory order changed")
    require(sum(a["size_bytes"] for a in artifacts) <= MAX_TOTAL, "wheelhouse size limit exceeded")
    for direct in manifest["direct_requirements"]:
        require(direct["name"] in seen and seen[direct["name"]]["version"] == direct["version"],
                "missing or changed direct requirement")


def create_inventory(requirements_path, report_path, wheelhouse):
    requirements = read_bytes(requirements_path)
    direct = roots(requirements)
    report, report_sha = read_json(report_path)
    require(isinstance(report, dict) and report.get("version") == "1", "pip report version unsupported")
    env = report.get("environment", {})
    require(isinstance(env, dict) and all(env.get(k) == v for k, v in {"implementation_name": "cpython", "python_version": "3.12",
                "sys_platform": "linux", "platform_machine": "x86_64"}.items()), "resolver host incompatible")
    packages = report.get("install")
    require(isinstance(packages, list) and 0 < len(packages) <= MAX_PACKAGES, "invalid resolver report")
    expected_direct = {p["name"]: p for p in direct}
    artifacts = []
    for package in packages:
        require(isinstance(package, dict) and package.get("is_yanked") is False and package.get("is_direct") is False,
                "yanked or direct URL resolver input forbidden")
        info = package["download_info"]
        require(isinstance(info, dict) and set(info) == {"url", "archive_info"}, "nonarchive resolver input forbidden")
        require(isinstance(info["url"], str) and len(info["url"]) <= 2048, "invalid source")
        filename = urlsplit(info["url"]).path.rsplit("/", 1)[-1]
        name, version, tags = wheel_identity(filename)
        official_source(info["url"], filename)
        require(canonicalize_name(package["metadata"]["name"]) == name and
                str(Version(package["metadata"]["version"])) == version, "report identity mismatch")
        require(package.get("requested") is (name in expected_direct), "report direct roots mismatch")
        require(sorted(package.get("requested_extras", [])) == expected_direct.get(name, {}).get("extras", []),
                "report extras mismatch")
        artifacts.append({"name": name, "version": version, "filename": filename, "tags": tags,
                          "url": info["url"], "sha256": info["archive_info"]["hashes"]["sha256"]})
    manifest = {"format": FORMAT, "target": TARGET, "index_url": "https://pypi.org/simple",
                "requirements_sha256": hashlib.sha256(requirements).hexdigest(),
                "direct_requirements": direct, "resolver_report_sha256": report_sha,
                "resolver_pip_version": report["pip_version"],
                "artifacts": sorted(artifacts, key=lambda a: a["name"])}
    require(len({a["name"] for a in artifacts}) == len(artifacts), "duplicate distribution")
    verify_artifacts(manifest, wheelhouse)
    validate_manifest(manifest, requirements)
    return manifest


def pip_closure(manifest, snapshot, lock):
    require(sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12) and
            sys.platform == "linux" and platform.machine() == "x86_64", "closure host incompatible")
    lock_path = snapshot.parent / "requirements.lock"
    lock_path.write_bytes(lock)
    report_path = snapshot.parent / "closure-report.json"
    cmd = [sys.executable, "-I", "-m", "pip", "--isolated", "install", "--dry-run",
           "--ignore-installed", "--no-index", "--no-cache-dir", "--disable-pip-version-check",
           "--no-input", "--only-binary=:all:", "--require-hashes", "--find-links", str(snapshot),
           "--report", str(report_path), "-r", str(lock_path),
           "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312"]
    for tag in PLATFORMS:
        cmd.extend(["--platform", tag])
    env = {"PATH": os.environ.get("PATH", ""), "PIP_CONFIG_FILE": os.devnull,
           "HOME": str(snapshot.parent), "PYTHONNOUSERSITE": "1"}
    # Direct URLs were rejected in wheel METADATA. Use only the validated snapshot;
    # user config, pip cache and system packages cannot make an incomplete set pass.
    result = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=120, check=False)
    require(result.returncode == 0, "pip offline closure failed")
    report, digest = read_json(report_path)
    actual = [(canonicalize_name(p["metadata"]["name"]), str(Version(p["metadata"]["version"])))
              for p in report["install"]]
    expected = [(p["name"], p["version"]) for p in manifest["artifacts"]]
    require(sorted(actual) == expected, "pip closure inventory mismatch")
    return {"status": "OFFLINE_PIP_CLOSURE_VERIFIED", "wheel_count": len(actual),
            "closure_report_sha256": digest,
            "limitations": "No installation, physical network isolation or Ubuntu 24.04 runtime acceptance."}


def verify(requirements_path, manifest_path, lock_path, wheelhouse):
    requirements = read_bytes(requirements_path)
    manifest, _ = read_json(manifest_path)
    validate_manifest(manifest, requirements)
    lock = read_bytes(lock_path)
    require(lock == lock_text(manifest).encode(), "lock content mismatch")
    with tempfile.TemporaryDirectory(prefix="slc-python-check-") as temporary:
        snapshot = Path(temporary) / "wheels"
        snapshot.mkdir()
        verify_artifacts(manifest, wheelhouse, snapshot)
        return pip_closure(manifest, snapshot, lock)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    generate = sub.add_parser("inventory", help="emit manifest after checking a pip report and wheel bytes")
    generate.add_argument("--requirements", required=True, type=Path)
    generate.add_argument("--report", required=True, type=Path)
    generate.add_argument("--wheelhouse", required=True, type=Path)
    lock = sub.add_parser("lock", help="emit a canonical pinned/hash lock from a validated inventory")
    lock.add_argument("--requirements", required=True, type=Path)
    lock.add_argument("--manifest", required=True, type=Path)
    check = sub.add_parser("verify", help="verify bytes and full extras closure with pip, without installing")
    for flag in ("requirements", "manifest", "lock", "wheelhouse"):
        check.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "inventory":
            result = create_inventory(args.requirements, args.report, args.wheelhouse)
        elif args.action == "lock":
            manifest, _ = read_json(args.manifest)
            validate_manifest(manifest, read_bytes(args.requirements))
            print(lock_text(manifest), end="")
            return 0
        else:
            result = verify(args.requirements, args.manifest, args.lock, args.wheelhouse)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, EOFError, zipfile.BadZipFile,
            subprocess.SubprocessError):
        print("offline python wheelhouse: validation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
