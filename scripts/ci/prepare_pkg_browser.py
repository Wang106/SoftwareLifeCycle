"""Prepare one pinned Google-signed Chrome PKG without installing its scripts.

Run from frontend on macOS ARM64. The package hash and native package trust
check precede native expansion; strict bundle verification precedes execution.
This is a fixed, inspected package, not a general-purpose package extractor.
Importing this module does no I/O. Tests use synthetic files and native mocks.
"""
import hashlib
import os
from pathlib import Path
import platform
import plistlib
import re
import stat
import subprocess
import sys
import urllib.request

# Static trust evidence (not browser acceptance):
# https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42753708819
# Signed plist version; no Chrome installation or execution in that inspection.
VERSION = '157.0.8103.51'
URL = ('https://dl.google.com/chrome/mac/stable/'
       'accept_tos%3Dhttps%253A%252F%252Fwww.google.com%252Fintl%252Fen_ph%252Fchrome%252Fterms%252F'
       '%26_and_accept_tos%3Dhttps%253A%252F%252Fpolicies.google.com%252Fterms/googlechrome.pkg')
SHA256 = '34b6cfbde780a236ec5c1c1a9300e231ad81acb454fc569f409513a7a6525bef'
PACKAGE_BYTES = 272444759
BUNDLE_PARTS = ('expanded', 'GoogleChrome.pkg', 'Payload', 'Google Chrome.app')
IDENTIFIER = 'com.google.Chrome'
REQUIREMENT = ('anchor apple generic and identifier "com.google.Chrome" '
               'and certificate 1[field.1.2.840.113635.100.6.2.6] exists '
               'and certificate leaf[field.1.2.840.113635.100.6.1.13] exists '
               'and certificate leaf[subject.OU] = "EQHXZ8M8AV"')
PACKAGE_CHAIN = ('Developer ID Installer: Google LLC (EQHXZ8M8AV)',
                 'Developer ID Certification Authority', 'Apple Root CA')
TRUSTED_STATUSES = ('signed by a certificate trusted by macOS',
                    'signed by a developer certificate issued by Apple for distribution')
MAX_DOWNLOAD = 1024 * 1024 * 1024
DOWNLOAD_SECONDS = 120


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def official_url(value):
    require(value == URL, 'Only the pinned exact Google PKG URL is allowed')
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Google PKG download redirects are forbidden')


def paths():
    value = os.environ.get('RUNNER_TEMP', '')
    require(value and Path(value).is_absolute(), 'An absolute RUNNER_TEMP is required')
    root = Path(value).resolve(strict=True)
    require(root.is_dir(), 'Missing runner temporary directory')
    staging = root / 'slc-pkg-chrome'
    return staging, staging / 'googlechrome.pkg', staging.joinpath(*BUNDLE_PARTS)


def verify_staging(staging):
    info = staging.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'Untrusted PKG staging directory')


def verify_pin(size, digest):
    if size != PACKAGE_BYTES or size > MAX_DOWNLOAD or digest != SHA256:
        # Only locally computed counts/hashes, never response bodies or headers.
        # Diagnostic evidence is not trust: the original checks still fail closed.
        print('PKG pin mismatch: actual bytes:', size, '; expected bytes:', PACKAGE_BYTES,
              '; actual SHA256:', digest, '; expected SHA256:', SHA256, flush=True)
    require(size == PACKAGE_BYTES and size <= MAX_DOWNLOAD, 'Pinned PKG byte count differs')
    require(digest == SHA256, 'Pinned PKG SHA256 differs')


def download(package):
    """Child-only transfer; the parent enforces one 120-second total deadline."""
    opener = urllib.request.build_opener(NoRedirect())
    digest = hashlib.sha256()
    size = 0
    print('Official PKG download:', official_url(URL), flush=True)
    with opener.open(URL, timeout=DOWNLOAD_SECONDS) as response, package.open('xb') as target:
        official_url(response.geturl())
        require(response.status == 200, 'Unexpected PKG download status')
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            require(size <= MAX_DOWNLOAD, 'PKG download exceeds limit')
            digest.update(chunk)
            target.write(chunk)
    verify_pin(size, digest.hexdigest())
    print('Final download URL:', URL, flush=True)
    print('PKG SHA256:', digest.hexdigest(), '; bytes:', size, flush=True)


def download_once():
    # run() kills and waits for its only child on TimeoutExpired. Slow reads
    # cannot reset this total deadline. There is no retry or alternate source.
    subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--download'],
                   check=True, timeout=DOWNLOAD_SECONDS)


def verify_package_bytes(package):
    """Recheck the child's saved bytes before allowing any native extraction."""
    info = package.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and not info.st_mode & 0o7022, 'Untrusted PKG file')
    require(info.st_size == PACKAGE_BYTES and info.st_size <= MAX_DOWNLOAD,
            'Pinned PKG byte count differs')
    digest = hashlib.sha256()
    size = 0
    with package.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            require(size <= MAX_DOWNLOAD, 'PKG exceeds limit')
            digest.update(chunk)
    verify_pin(size, digest.hexdigest())


def output(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT,
                                       timeout=120,
                                       env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C'}).strip()
    except subprocess.CalledProcessError as error:
        print(error.output or '', end='', flush=True)
        raise


def verify_package_signature(package):
    # Embedded certificate names alone are not trust evidence: pkgutil must
    # first exit successfully and explicitly report system-trusted signing.
    report = output('/usr/sbin/pkgutil', '--check-signature', str(package))
    print(report, flush=True)
    statuses = re.findall(r'^\s*Status:\s*(.*?)\s*$', report, flags=re.MULTILINE)
    require(len(statuses) == 1 and statuses[0] in TRUSTED_STATUSES,
            'PKG is not signed by a macOS-trusted certificate')
    sections = re.split(r'^\s*Certificate Chain:\s*$', report, flags=re.MULTILINE)
    require(len(sections) == 2, 'Missing or ambiguous PKG certificate chain')
    chain = re.findall(r'^\s*(\d+)\.\s+(.*?)\s*$', sections[1], flags=re.MULTILINE)
    require(chain == [(str(index), name) for index, name in enumerate(PACKAGE_CHAIN, 1)],
            'PKG does not have the pinned Google Developer ID Installer chain')


def verify_bundle(bundle):
    binary = bundle / 'Contents/MacOS/Google Chrome'
    require(bundle.resolve(strict=True) == bundle and bundle.is_dir(), 'Unexpected Chrome bundle path')
    require(binary.resolve(strict=True) == binary and binary.is_file(), 'Unexpected Chrome executable path')
    require(os.access(binary, os.X_OK), 'Chrome is not executable')
    owners = {0, os.getuid()}
    count = 0
    for path in (bundle, *bundle.rglob('*')):
        info = path.lstat()
        require(info.st_uid in owners, 'Untrusted Chrome member owner')
        if stat.S_ISLNK(info.st_mode):
            require(path.resolve(strict=True).is_relative_to(bundle), 'Chrome symlink escapes bundle')
            continue
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Special Chrome member')
        require(not info.st_mode & 0o7022, 'Unsafe Chrome member mode')
        count += 1
    resources = bundle / 'Contents/_CodeSignature/CodeResources'
    require(resources.is_file() and not resources.is_symlink()
            and resources.resolve(strict=True).is_relative_to(bundle)
            and os.access(resources, os.R_OK), 'Missing regular readable Chrome CodeResources')
    print('Checked bundle members:', count, '; allowed owners:', sorted(owners), flush=True)
    # Strict recursive verification checks nested seals; do not repair missing
    # resources, attributes, modes or signatures to make the candidate pass.
    print(output('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2',
                 '-R', '=' + REQUIREMENT, str(bundle)), flush=True)
    print(output('/usr/bin/codesign', '--display', '--verbose=4', str(bundle)), flush=True)
    with (bundle / 'Contents/Info.plist').open('rb') as stream:
        metadata = plistlib.load(stream)
    require(metadata.get('CFBundleIdentifier') == IDENTIFIER, 'Unexpected Chrome bundle identifier')
    require(metadata.get('CFBundleShortVersionString') == VERSION, 'Unexpected Chrome bundle version')
    configured = output('node', '-e',
                        "process.stdout.write(require('./e2e/playwright.config.cjs').use.launchOptions.executablePath)")
    require(configured == str(binary), 'Guard and Playwright executable paths differ')
    # First execution of any content from the package. Installer, Distribution
    # and package Scripts are never executed, including in failure handling.
    actual = output(str(binary), '--version')
    require(actual == 'Google Chrome ' + VERSION, 'Chrome bundle/binary version mismatch')
    print('Verified candidate:', actual, '; chromiumSandbox: true; retries: 0', flush=True)


def prepare():
    staging, package, bundle = paths()
    staging.mkdir(mode=0o700)  # An existing candidate is an error, never reused.
    verify_staging(staging)
    download_once()
    verify_package_bytes(package)
    verify_package_signature(package)
    expanded = staging / 'expanded'
    require(not expanded.exists() and not expanded.is_symlink(), 'PKG expansion destination exists')
    # Only native expansion of the exact pinned, system-trusted package.
    # --expand-full does not install or run package Scripts/Distribution.
    subprocess.run(('/usr/sbin/pkgutil', '--expand-full', str(package), str(expanded)),
                   check=True, timeout=180)
    verify_bundle(bundle)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    require(__debug__, 'Browser guard requires Python without -O')
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64',
            'Expected macOS ARM64 runner')
    require(args in ([], ['--download']), 'Unexpected browser guard arguments')
    if args == ['--download']:
        staging, package, _ = paths()
        verify_staging(staging)
        download(package)
        return
    print('Runner image:', os.environ.get('ImageOS', 'unknown'),
          os.environ.get('ImageVersion', 'unknown'), flush=True)
    print('OS:', output('/usr/bin/sw_vers', '-productVersion'), '; architecture:', platform.machine(), flush=True)
    for command in (('/usr/bin/csrutil', 'status'), ('/usr/sbin/spctl', '--status')):
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=20)
        print('Existing security state:', command, 'exit:', result.returncode,
              result.stdout.strip(), flush=True)
    prepare()


if __name__ == '__main__':
    main()
