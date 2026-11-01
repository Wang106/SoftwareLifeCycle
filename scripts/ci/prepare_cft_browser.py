"""One fixed, unrepaired official CfT candidate; no browser execution before trust checks.

Run from frontend on the approved macOS ARM64 CI runner. The internal download
child takes no URL/path arguments and is bounded by its parent's total timeout.
Importing this module does no I/O. Tests use synthetic archives and native mocks.
"""
import hashlib
import os
from pathlib import Path
import platform
import plistlib
import stat
import struct
import subprocess
import sys
import unicodedata
import urllib.request
import zipfile
import zlib

VERSION = '156.0.8078.80'
URL = ('https://storage.googleapis.com/chrome-for-testing-public/' + VERSION +
       '/mac-arm64/chrome-mac-arm64.zip')
ARCHIVE_ROOT = 'chrome-mac-arm64'
BUNDLE_PARTS = (ARCHIVE_ROOT, 'Google Chrome for Testing.app')
IDENTIFIER = 'com.google.chrome.for.testing'
REQUIREMENT = ('anchor apple generic and identifier "com.google.chrome.for.testing" '
               'and certificate 1[field.1.2.840.113635.100.6.2.6] exists '
               'and certificate leaf[field.1.2.840.113635.100.6.1.13] exists '
               'and certificate leaf[subject.OU] = "EQHXZ8M8AV"')
MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 20_000
DOWNLOAD_SECONDS = 120


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def official_url(value):
    require(value == URL, 'Only the approved exact CfT URL is allowed')
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('CfT download redirects are forbidden')


def paths():
    value = os.environ.get('RUNNER_TEMP', '')
    require(value and Path(value).is_absolute(), 'An absolute RUNNER_TEMP is required')
    root = Path(value).resolve(strict=True)
    require(root.is_dir(), 'Missing runner temporary directory')
    staging = root / 'slc-cft-chrome'
    return staging, staging / 'chrome-mac-arm64.zip', staging.joinpath(*BUNDLE_PARTS)


def download(archive):
    """Child-only transfer; parent process supplies the 120s total deadline."""
    opener = urllib.request.build_opener(NoRedirect())
    digest = hashlib.sha256()
    size = 0
    print('Official CfT download:', official_url(URL), flush=True)
    with opener.open(URL, timeout=DOWNLOAD_SECONDS) as response, archive.open('xb') as target:
        official_url(response.geturl())
        require(response.status == 200, 'Unexpected CfT download status')
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            require(size <= MAX_DOWNLOAD, 'CfT download exceeds limit')
            digest.update(chunk)
            target.write(chunk)
    require(size > 0, 'Empty CfT archive')
    print('Final download URL:', URL, flush=True)
    print('ZIP SHA256:', digest.hexdigest(), '; bytes:', size, flush=True)


def download_once():
    # subprocess.run kills and waits for this one child on TimeoutExpired.
    # A slow stream cannot reset this total deadline; no retries or fallback.
    subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--download'],
                   check=True, timeout=DOWNLOAD_SECONDS)


def normalized_parts(value):
    require(isinstance(value, str) and value and '\x00' not in value and '\\' not in value,
            'Invalid ZIP path')
    require(not value.startswith('/') and ':' not in value, 'Absolute or ambiguous ZIP path')
    parts = tuple(value.rstrip('/').split('/'))
    require(all(part and part not in ('.', '..') for part in parts), 'Unsafe ZIP path component')
    require(parts[0] == ARCHIVE_ROOT, 'Unexpected ZIP root')
    return parts


def link_parts(target):
    require(target and '\x00' not in target and '\\' not in target and ':' not in target
            and not target.startswith('/'), 'Invalid ZIP symlink target')
    # Preserve .. until symlinks have been expanded, matching filesystem
    # traversal rather than prematurely normalizing e.g. link/../target.
    return tuple(target.split('/'))


def validate_extra(extra):
    """Only understood non-path ZIP metadata, in both central and local headers.

    In particular, no Unicode-name override, alternate link encoding or Apple
    archive metadata may make ditto interpret a different destination than us.
    Reject the archive rather than strip, rewrite or ignore such metadata.
    """
    seen, fields = set(), {}
    while extra:
        require(len(extra) >= 4, 'Truncated ZIP extra header')
        tag, size = struct.unpack('<HH', extra[:4])
        require(size <= len(extra) - 4 and tag not in seen, 'Invalid ZIP extra field')
        seen.add(tag)
        value, extra = extra[4:4 + size], extra[4 + size:]
        fields[tag] = value
        require(tag in (0x0001, 0x5455, 0x7875), 'Unsupported ZIP extra field')
        if tag == 0x0001:  # ZIP64 sizes/offset; no alternate path.
            require(size in (8, 16, 24, 28), 'Invalid ZIP64 extra field')
        elif tag == 0x5455:  # Extended timestamps; central header can omit atime/ctime.
            require(size in (5, 9, 13) and value[0] & ~7 == 0,
                    'Invalid ZIP timestamp field')
        else:  # Info-ZIP UNIX uid/gid, version 1, bounded integer encodings.
            require(size >= 5 and value[0] == 1, 'Invalid ZIP UID/GID field')
            uid_size = value[1]
            require(1 <= uid_size <= 8 and 2 + uid_size < size, 'Invalid ZIP UID size')
            gid_size = value[2 + uid_size]
            require(1 <= gid_size <= 8 and 3 + uid_size + gid_size == size,
                    'Invalid ZIP GID size')
    return fields


def validate_local_header(archive, info):
    archive.fp.seek(info.header_offset)
    raw = archive.fp.read(30)
    require(len(raw) == 30, 'Truncated ZIP local header')
    signature, _, flags, compression, _, _, crc, compressed, expanded, name_size, extra_size = struct.unpack('<4s5H3L2H', raw)
    require(signature == b'PK\x03\x04' and flags == info.flag_bits
            and compression == info.compress_type, 'ZIP local/central header mismatch')
    raw_name, extra = archive.fp.read(name_size), archive.fp.read(extra_size)
    require(len(raw_name) == name_size and len(extra) == extra_size, 'Truncated ZIP local metadata')
    name = raw_name.decode('utf-8' if flags & 0x800 else 'cp437', errors='strict')
    require(name == info.orig_filename, 'ZIP local/central filename mismatch')
    fields = validate_extra(extra)
    uses_zip64 = expanded == 0xffffffff or compressed == 0xffffffff
    if uses_zip64:
        value = fields.get(0x0001, b'')
        needed = 8 * ((expanded == 0xffffffff) + (compressed == 0xffffffff))
        require(len(value) == needed, 'Invalid local ZIP64 sizes')
        if expanded == 0xffffffff:
            expanded, = struct.unpack('<Q', value[:8])
            value = value[8:]
        if compressed == 0xffffffff:
            compressed, = struct.unpack('<Q', value[:8])
    else:
        require(0x0001 not in fields, 'Ambiguous unused local ZIP64 field')
    if flags & 8:
        require(crc in (0, info.CRC) and compressed in (0, info.compress_size)
                and expanded in (0, info.file_size), 'ZIP local/central sizes mismatch')
        archive.fp.seek(info.header_offset + 30 + name_size + extra_size + info.compress_size)
        first = archive.fp.read(4)
        if first == b'PK\x07\x08':
            first = archive.fp.read(4)
        rest = archive.fp.read(16 if uses_zip64 else 8)
        require(len(first) == 4 and len(rest) == (16 if uses_zip64 else 8),
                'Truncated ZIP data descriptor')
        values = struct.unpack('<LQQ' if uses_zip64 else '<LLL', first + rest)
        require(values == (info.CRC, info.compress_size, info.file_size),
                'ZIP descriptor/central sizes mismatch')
    else:
        require((crc, compressed, expanded) == (info.CRC, info.compress_size, info.file_size),
                'ZIP local/central sizes mismatch')
    data_start = info.header_offset + 30 + name_size + extra_size
    end = archive.fp.tell() if flags & 8 else data_start + info.compress_size
    return data_start, end


def member_chunks(archive, info, data_start):
    """Independently decode raw data: ZipExtFile truncates at declared size.

    A forged small size/CRC must not hide the rest of a deflate stream from
    our resource budget while the native extractor expands all of it.
    """
    archive.fp.seek(data_start)
    remaining, produced, crc = info.compress_size, 0, 0
    inflater = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
    if inflater is None:
        require(info.compress_size == info.file_size, 'Stored ZIP sizes differ')
    while remaining:
        raw = archive.fp.read(min(1024 * 1024, remaining))
        require(raw, 'Truncated ZIP member data')
        remaining -= len(raw)
        pending = raw
        while pending:
            chunk = inflater.decompress(pending, 1024 * 1024) if inflater else pending
            produced += len(chunk)
            require(produced <= info.file_size and produced <= MAX_EXPANDED,
                    'Actual ZIP expansion exceeds declared limit')
            crc = zlib.crc32(chunk, crc)
            if chunk:
                yield chunk
            if inflater:
                require(not inflater.unused_data, 'Trailing data in ZIP deflate stream')
                tail = inflater.unconsumed_tail
                require(not tail or chunk or len(tail) < len(pending), 'Stalled ZIP decoder')
                pending = tail
                require(not inflater.eof or remaining == 0, 'Extra bytes after ZIP deflate stream')
            else:
                pending = b''
    if inflater:
        require(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail,
                'Incomplete ZIP deflate stream')
    require(produced == info.file_size and crc == info.CRC, 'ZIP data size or CRC mismatch')


def validate_directory_layout(archive, infos):
    """Reject hidden/unindexed records, spanning archives and trailing payloads.

    Our 1GiB/20,000-entry budget does not require a ZIP64 archive directory;
    forced ZIP64 *local* size headers remain supported above.
    """
    archive.fp.seek(0, 2)
    length = archive.fp.tell()
    tail_size = min(length, 22 + 65535)
    archive.fp.seek(length - tail_size)
    tail = archive.fp.read(tail_size)
    index = tail.rfind(b'PK\x05\x06')
    require(index >= 0 and index + 22 <= len(tail), 'Missing ZIP end record')
    _, disk, directory_disk, on_disk, total, size, offset, comment_size = struct.unpack(
        '<4s4H2LH', tail[index:index + 22])
    end_offset = length - tail_size + index
    require(disk == directory_disk == 0 and on_disk == total == len(infos),
            'Spanning or ZIP64 archive directory is unsupported')
    require(offset == archive.start_dir and offset + size == end_offset
            and end_offset + 22 + comment_size == length, 'Invalid ZIP directory layout')
    archive.fp.seek(offset)
    for info in infos:
        header = archive.fp.read(46)
        require(len(header) == 46, 'Truncated central ZIP header')
        values = struct.unpack('<4s6H3L5H2L', header)
        signature, _, _, flags, method, _, _, crc, compressed, expanded, name_size, extra_size, note_size, disk, _, mode, local = values
        require(signature == b'PK\x01\x02' and disk == 0, 'Invalid central ZIP record')
        require((flags, method, crc, compressed, expanded, mode, local) ==
                (info.flag_bits, info.compress_type, info.CRC, info.compress_size,
                 info.file_size, info.external_attr, info.header_offset),
                'Ambiguous central ZIP metadata')
        name, extra, note = archive.fp.read(name_size), archive.fp.read(extra_size), archive.fp.read(note_size)
        require(len(name) == name_size and len(extra) == extra_size and len(note) == note_size,
                'Truncated central ZIP metadata')
        require(name.decode('utf-8' if flags & 0x800 else 'cp437') == info.orig_filename
                and extra == info.extra, 'Central ZIP filename or extra mismatch')
        require(0x0001 not in validate_extra(extra), 'Unneeded central ZIP64 metadata')
    require(archive.fp.tell() == end_offset, 'Unindexed central ZIP data')


def validate_archive(archive_path):
    """Validate all paths/data before ditto; return content-preservation manifest."""
    require(archive_path.is_file() and not archive_path.is_symlink(), 'Missing regular ZIP')
    require(0 < archive_path.stat().st_size <= MAX_DOWNLOAD, 'Invalid ZIP size')
    entries, directories, folded, locations = {}, set(), {}, {}
    total = actual_total = 0
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= MAX_ENTRIES, 'Invalid ZIP entry count')
        validate_directory_layout(archive, infos)
        for info in infos:
            require(info.orig_filename == info.filename, 'Truncated ZIP filename')
            validate_extra(info.extra)
            name = normalized_parts(info.filename)
            require(name not in entries, 'Duplicate ZIP entry')
            for count in range(1, len(name) + 1):
                prefix = name[:count]
                key = tuple(unicodedata.normalize('NFD', part).casefold() for part in prefix)
                require(key not in folded or folded[key] == prefix, 'ZIP case or Unicode collision')
                folded[key] = prefix
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            require(kind in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK), 'Special ZIP member')
            require(kind == stat.S_IFLNK or not mode & 0o7022, 'Unsafe ZIP member mode')
            require(not info.flag_bits & 1, 'Encrypted ZIP is forbidden')
            require(not info.flag_bits & ~(0x800 | 8 | 6), 'Unsupported ZIP flags')
            require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    'Unsupported ZIP compression')
            is_directory = info.is_dir()
            require((kind == stat.S_IFDIR) == is_directory if kind else True,
                    'ZIP directory/type mismatch')
            require(info.file_size >= 0 and info.compress_size >= 0, 'Invalid ZIP member size')
            total += info.file_size
            require(total <= MAX_EXPANDED, 'ZIP expanded size exceeds limit')
            if is_directory:
                require(info.file_size == 0, 'Nonempty ZIP directory')
                directories.add(name)
            directories.update(name[:count] for count in range(1, len(name)))
            entries[name] = {'kind': 'directory' if is_directory else
                             'symlink' if kind == stat.S_IFLNK else 'file',
                             'size': info.file_size}
            locations[name] = validate_local_header(archive, info)
        ordered = sorted(infos, key=lambda info: info.header_offset)
        require(ordered[0].header_offset == 0, 'Unexpected ZIP prefix')
        for index, info in enumerate(ordered):
            name = normalized_parts(info.filename)
            following = ordered[index + 1].header_offset if index + 1 < len(ordered) else archive.start_dir
            require(info.header_offset < locations[name][0] <= locations[name][1] == following,
                    'Overlapping or unindexed ZIP member data')
        for name, entry in entries.items():
            require(not (name in directories and entry['kind'] != 'directory'),
                    'ZIP member is also an ancestor')
        for info in infos:
            name = normalized_parts(info.filename)
            entry = entries[name]
            digest, size, target = hashlib.sha256(), 0, bytearray()
            for chunk in member_chunks(archive, info, locations[name][0]):
                size += len(chunk)
                actual_total += len(chunk)
                require(size <= entry['size'] and actual_total <= MAX_EXPANDED,
                        'ZIP data exceeds declared limits')
                digest.update(chunk)
                if entry['kind'] == 'symlink':
                    require(size <= 4096, 'Oversized ZIP symlink')
                    target.extend(chunk)
            require(size == entry['size'], 'ZIP member size mismatch')
            entry['sha256'] = digest.hexdigest()
            if entry['kind'] == 'symlink':
                entry['target'] = target.decode('utf-8', errors='strict')

    def resolve_link(name, seen):
        require(len(seen) <= 64, 'Excessive ZIP symlink chain')
        resolved = []
        for index, part in enumerate(name):
            if part in ('', '.'):
                continue
            if part == '..':
                require(resolved, 'ZIP symlink escapes archive')
                resolved.pop()
                continue
            resolved.append(part)
            prefix = tuple(resolved)
            entry = entries.get(prefix)
            if entry and entry['kind'] == 'symlink':
                require(prefix not in seen, 'Cyclic ZIP symlink')
                destination = prefix[:-1] + link_parts(entry['target']) + name[index + 1:]
                return resolve_link(destination, seen | {prefix})
            require(prefix in entries or prefix in directories, 'Dangling ZIP symlink')
            require(index == len(name) - 1 or prefix in directories,
                    'ZIP symlink traverses a nondirectory')
        result = tuple(resolved)
        require(result in entries or result in directories, 'Dangling ZIP symlink')
        return result

    require(BUNDLE_PARTS in directories, 'Missing CfT bundle')
    for name, entry in entries.items():
        if entry['kind'] == 'symlink':
            require(name[:len(BUNDLE_PARTS)] == BUNDLE_PARTS, 'Symlink outside CfT bundle')
            destination = resolve_link(name, set())
            require(destination[:len(BUNDLE_PARTS)] == BUNDLE_PARTS,
                    'ZIP symlink escapes CfT bundle')
    for directory in directories:
        entries.setdefault(directory, {'kind': 'directory', 'size': 0})
    print('Validated ZIP entries:', len(infos), '; expanded bytes:', total, flush=True)
    return entries


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_extraction(staging, manifest):
    root = staging / ARCHIVE_ROOT
    require(root.is_dir() and not root.is_symlink(), 'Missing extracted root')
    actual = {tuple(path.relative_to(staging).parts): path
              for path in (root, *root.rglob('*'))}
    require(set(actual) == set(manifest), 'Extraction added or omitted ZIP members')
    for name, entry in manifest.items():
        path = actual[name]
        mode = path.lstat().st_mode
        if entry['kind'] == 'symlink':
            require(stat.S_ISLNK(mode) and os.readlink(path) == entry['target'],
                    'Extraction altered symlink')
        elif entry['kind'] == 'directory':
            require(stat.S_ISDIR(mode), 'Extraction altered directory')
        else:
            require(stat.S_ISREG(mode) and path.stat().st_size == entry['size']
                    and file_digest(path) == entry['sha256'], 'Extraction altered file bytes')


def output(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT,
                                       timeout=120).strip()
    except subprocess.CalledProcessError as error:
        print(error.output or '', end='', flush=True)
        raise


def verify_bundle(bundle):
    binary = bundle / 'Contents/MacOS/Google Chrome for Testing'
    require(bundle.resolve(strict=True) == bundle, 'Unexpected CfT bundle symlink')
    require(binary.resolve(strict=True) == binary and binary.is_file(), 'Unexpected CfT executable path')
    require(os.access(binary, os.X_OK), 'CfT is not executable')
    owners = {0, os.getuid()}
    count = 0
    for path in (bundle, *bundle.rglob('*')):
        info = path.lstat()
        require(info.st_uid in owners, 'Untrusted CfT member owner')
        if stat.S_ISLNK(info.st_mode):
            require(path.resolve(strict=True).is_relative_to(bundle), 'CfT symlink escapes bundle')
            continue
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Special CfT member')
        require(not info.st_mode & 0o7022, 'Unsafe CfT member mode')
        count += 1
    print('Checked bundle members:', count, '; allowed owners:', sorted(owners), flush=True)
    print(output('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2',
                 '-R', '=' + REQUIREMENT, str(bundle)), flush=True)
    print(output('/usr/bin/codesign', '--display', '--verbose=4', str(bundle)), flush=True)
    with (bundle / 'Contents/Info.plist').open('rb') as stream:
        metadata = plistlib.load(stream)
    require(metadata.get('CFBundleIdentifier') == IDENTIFIER, 'Unexpected CfT bundle identifier')
    require(metadata.get('CFBundleShortVersionString') == VERSION, 'Unexpected CfT bundle version')
    configured = output('node', '-e',
                        "process.stdout.write(require('./e2e/playwright.config.cjs').use.launchOptions.executablePath)")
    require(configured == str(binary), 'Guard and Playwright executable paths differ')
    # This is the first execution of anything from the candidate.
    actual = output(str(binary), '--version')
    require(actual == 'Google Chrome for Testing ' + VERSION, 'CfT bundle/binary version mismatch')
    print('Verified candidate:', actual, '; chromiumSandbox: true; retries: 0', flush=True)


def prepare():
    staging, archive, bundle = paths()
    staging.mkdir(mode=0o700)  # Existing candidate is an error, never reused or repaired.
    download_once()
    manifest = validate_archive(archive)
    subprocess.run(('/usr/bin/ditto', '-x', '-k', '--rsrc', '--extattr', str(archive), str(staging)),
                   check=True, timeout=180)
    verify_extraction(staging, manifest)
    verify_bundle(bundle)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    require(__debug__, 'Browser guard requires Python without -O')
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64',
            'Expected macOS ARM64 runner')
    require(args in ([], ['--download']), 'Unexpected browser guard arguments')
    if args == ['--download']:
        staging, archive, _ = paths()
        info = staging.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700, 'Untrusted CfT staging directory')
        download(archive)
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
