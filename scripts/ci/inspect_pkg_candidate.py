"""Static observation only. Never installs or executes content from a PKG.

This deliberately does not import/call the acceptance guard or update its pins.
Run only as a separately scoped macOS ARM64 diagnostic, never as acceptance.
"""
import hashlib
from itertools import chain
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

URL = ('https://dl.google.com/chrome/mac/stable/'
       'accept_tos%3Dhttps%253A%252F%252Fwww.google.com%252Fintl%252Fen_ph%252Fchrome%252Fterms%252F'
       '%26_and_accept_tos%3Dhttps%253A%252F%252Fpolicies.google.com%252Fterms/googlechrome.pkg')
MAX_BYTES = 1024 * 1024 * 1024
MAX_MEMBERS = 100000
MAX_EXPANDED_BYTES = 4 * 1024 * 1024 * 1024
MIN_FREE_BYTES = 1024 * 1024 * 1024
DOWNLOAD_SECONDS = 120
CHAIN = ('Developer ID Installer: Google LLC (EQHXZ8M8AV)',
         'Developer ID Certification Authority', 'Apple Root CA')
STATUSES = ('signed by a certificate trusted by macOS',
            'signed by a developer certificate issued by Apple for distribution')
REQUIREMENT = ('anchor apple generic and identifier "com.google.Chrome" '
               'and certificate 1[field.1.2.840.113635.100.6.2.6] exists '
               'and certificate leaf[field.1.2.840.113635.100.6.1.13] exists '
               'and certificate leaf[subject.OU] = "EQHXZ8M8AV"')
DISCLAIMER = 'Static candidate evidence only; no installation, browser execution, sandbox or acceptance proof.'


def require(value, message):
    if not value:
        raise RuntimeError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Candidate redirects forbidden')


def paths():
    raw = os.environ.get('RUNNER_TEMP', '')
    require(raw and Path(raw).is_absolute(), 'Absolute RUNNER_TEMP required')
    root = Path(raw).resolve(strict=True)
    require(root.is_dir(), 'Runner directory missing')
    stage = root / 'slc-pkg-static-inspection'
    return stage, stage / 'googlechrome.pkg'


def check_stage(stage):
    info = stage.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'Untrusted inspection directory')


def digest_file(package):
    info = package.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and not info.st_mode & 0o7022, 'Untrusted candidate file')
    require(0 < info.st_size <= MAX_BYTES, 'Candidate size out of bounds')
    digest = hashlib.sha256()
    count = 0
    with package.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            require(count <= MAX_BYTES, 'Candidate too large')
            digest.update(chunk)
    after = package.lstat()
    require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and count == info.st_size, 'Candidate changed while hashing')
    return {'bytes': count, 'sha256': digest.hexdigest()}


def download(package):
    check_stage(package.parent)
    opener = urllib.request.build_opener(NoRedirect())
    digest = hashlib.sha256()
    count = 0
    with opener.open(URL, timeout=DOWNLOAD_SECONDS) as response:
        require(response.status == 200 and response.geturl() == URL, 'Unexpected source/status')
        length = response.headers.get('Content-Length')
        require(isinstance(length, str) and re.fullmatch(r'[0-9]+', length), 'Missing or invalid Content-Length')
        expected = int(length)
        require(0 < expected <= MAX_BYTES, 'Declared candidate size out of bounds')
        with package.open('xb') as target:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                require(count <= MAX_BYTES, 'Candidate too large')
                digest.update(chunk)
                target.write(chunk)
    require(count == expected, 'Incomplete or oversized HTTP body')
    observed = digest_file(package)
    require(observed == {'bytes': count, 'sha256': digest.hexdigest()}, 'Transfer digest mismatch')
    print(json.dumps({'source': URL, 'observed': observed, 'acceptance': False}), flush=True)


def native(*args, timeout=120):
    # Only Apple's static inspection tools. No shell or candidate executable.
    allowed = (args[:2] == ('/usr/sbin/pkgutil', '--check-signature')
               or args[:2] in [('/usr/bin/codesign', '--verify'),
                               ('/usr/bin/codesign', '--display')])
    require(allowed, 'Native command outside static inspection allowlist')
    result = subprocess.run(args, check=True, timeout=timeout, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C'})
    print(result.stdout, end='', flush=True)
    return result.stdout


def expansion_budget(expanded):
    count = size = 0
    if expanded.exists():
        for path in chain((expanded,), expanded.rglob('*')):
            info = path.lstat()
            count += 1
            if stat.S_ISREG(info.st_mode):
                size += info.st_size
            require(count <= MAX_MEMBERS and size <= MAX_EXPANDED_BYTES,
                    'Expansion resource budget exceeded')
    require(shutil.disk_usage(expanded.parent).free >= MIN_FREE_BYTES, 'Expansion free-space floor reached')


def expand_static(package, expanded):
    # A monitored native unpack only, never installer/Distribution/Scripts.
    # Sampling is a stop condition, not an OS-level hard disk quota.
    expansion_budget(expanded)
    command = ('/usr/sbin/pkgutil', '--expand-full', str(package), str(expanded))
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 180
    try:
        while process.poll() is None:
            require(time.monotonic() < deadline, 'Expansion deadline exceeded')
            expansion_budget(expanded)
            time.sleep(0.1)
        require(process.returncode == 0, 'Native static expansion failed')
        expansion_budget(expanded)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def check_expanded_tree(expanded):
    require(expanded.is_dir() and expanded.resolve(strict=True) == expanded, 'Indirect expansion root')
    expansion_budget(expanded)
    for path in chain((expanded,), expanded.rglob('*')):
        info = path.lstat()
        require(info.st_uid in (0, os.getuid()), 'Untrusted expanded member owner')
        if stat.S_ISLNK(info.st_mode):
            require(path.resolve(strict=True).is_relative_to(expanded), 'Expanded symlink escape')
        else:
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Special expanded member')
            require(not info.st_mode & 0o7022, 'Unsafe expanded member mode')


def verify_package_signature(package):
    report = native('/usr/sbin/pkgutil', '--check-signature', str(package))
    statuses = re.findall(r'^\s*Status:\s*(.*?)\s*$', report, re.MULTILINE)
    require(len(statuses) == 1 and statuses[0] in STATUSES, 'System trust missing')
    parts = re.split(r'^\s*Certificate Chain:\s*$', report, flags=re.MULTILINE)
    require(len(parts) == 2, 'Ambiguous package chain')
    chain = re.findall(r'^\s*(\d+)\.\s+(.*?)\s*$', parts[1], re.MULTILINE)
    require(chain == [(str(i), name) for i, name in enumerate(CHAIN, 1)], 'Wrong package signer')


def inspect_bundle(bundle):
    require(bundle.is_dir() and bundle.resolve(strict=True) == bundle, 'Unexpected bundle path')
    count = 0
    for path in chain((bundle,), bundle.rglob('*')):
        count += 1
        require(count <= MAX_MEMBERS, 'Too many bundle members')
        info = path.lstat()
        require(info.st_uid in (0, os.getuid()), 'Untrusted member owner')
        if stat.S_ISLNK(info.st_mode):
            require(path.resolve(strict=True).is_relative_to(bundle), 'Escaping symlink')
        else:
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Special member')
            require(not info.st_mode & 0o7022, 'Unsafe member mode')
    for relative in ('Contents/MacOS/Google Chrome', 'Contents/Info.plist',
                     'Contents/_CodeSignature/CodeResources'):
        path = bundle / relative
        require(path.is_file() and not path.is_symlink() and
                path.resolve(strict=True) == path, 'Missing or indirect required member')
    native('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2',
           '-R', '=' + REQUIREMENT, str(bundle))
    native('/usr/bin/codesign', '--display', '--verbose=4', str(bundle))
    plist = bundle / 'Contents/Info.plist'
    require(plist.stat().st_size <= 1024 * 1024, 'Oversized bundle metadata')
    with plist.open('rb') as stream:
        meta = plistlib.load(stream)
    require(meta.get('CFBundleIdentifier') == 'com.google.Chrome', 'Wrong bundle identity')
    version = meta.get('CFBundleShortVersionString')
    require(isinstance(version, str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}', version),
            'Unexpected version metadata')
    return {'identifier': meta['CFBundleIdentifier'], 'signed_plist_version': version,
            'version_not_executed': True, 'checked_members': count}


def inspect():
    stage, package = paths()
    stage.mkdir(mode=0o700)  # Never reuse a prior candidate.
    check_stage(stage)
    subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--download'],
                   check=True, timeout=DOWNLOAD_SECONDS)
    observed = digest_file(package)
    print(json.dumps({'observed': observed, 'acceptance': False}), flush=True)
    verify_package_signature(package)
    require(digest_file(package) == observed, 'Candidate changed after package trust check')
    expanded = stage / 'expanded'
    require(not expanded.exists() and not expanded.is_symlink(), 'Expansion path exists')
    expand_static(package, expanded)
    check_expanded_tree(expanded)
    metadata = inspect_bundle(expanded / 'GoogleChrome.pkg/Payload/Google Chrome.app')
    require(digest_file(package) == observed, 'Candidate changed during inspection')
    print(json.dumps({'observed': observed, 'bundle': metadata, 'acceptance': False}), flush=True)
    print(DISCLAIMER, flush=True)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    require(__debug__, 'Python optimization prohibited')
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'macOS ARM64 required')
    require(args in ([], ['--download']), 'Unexpected arguments')
    print(DISCLAIMER, flush=True)
    if args == ['--download']:
        _, package = paths()
        download(package)
    else:
        inspect()


if __name__ == '__main__':
    main()
