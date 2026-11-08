#!/usr/bin/env python3
"""Optional local image handoff export and read-only integrity verification.

Linux/Python standard library only. No Docker, network, extraction or DB access.
Hashes require independently trusted expected values; they are not signatures.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import re
import stat
import sys

import offline_readonly_preflight as preflight

CHUNK = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024**3
RESERVE_BYTES = 1024**3
MAX_JSON_BYTES = 64 * 1024
MAX_OUTER_HEADERS = 10000
MAX_OUTER_METADATA = 16 * 1024 * 1024
MAX_OUTER_PAX_ITEMS = 10000
MAX_OUTER_PAX_CHARS = 4 * 1024 * 1024
MAX_OUTER_NAME_CHARS = 4 * 1024 * 1024
FILES = frozenset({'api.tar', 'web.tar', 'manifest.json', 'evidence.json'})
REHEARSAL_STATUS = 'IMAGE_REHEARSAL_PASSED_NOT_OFFLINE_ACCEPTANCE'
FORMAT = 'slc-image-handoff-v1'
CODES = frozenset({'BUNDLE_POLICY_REJECTED', 'BUNDLE_PATH_REJECTED', 'BUNDLE_CHANGED',
                   'BUNDLE_CAPACITY_REJECTED', 'BUNDLE_IO_FAILED', 'BUNDLE_ARCHIVE_REJECTED',
                   'BUNDLE_COMPLETION_UNCERTAIN'})


class BundleError(ValueError):
    def __init__(self, code='BUNDLE_POLICY_REJECTED', *, receipt=None):
        self.code = code if type(code) is str and code in CODES else 'BUNDLE_POLICY_REJECTED'
        self.receipt = safe_receipt(receipt)
        super().__init__(self.code)


class CompletionInterrupted(KeyboardInterrupt):
    """Interrupt semantics retained, but no raw text and no false incomplete claim."""
    def __init__(self, receipt):
        self.code = 'BUNDLE_COMPLETION_UNCERTAIN'
        self.receipt = safe_receipt(receipt)
        super().__init__(self.code)


def safe_receipt(value):
    if (type(value) is dict and set(value) == {'source_commit', 'manifest_sha256'}
            and hexadecimal(value['source_commit'], 40) and hexadecimal(value['manifest_sha256'], 64)):
        return dict(value)
    return None


def require(value, code='BUNDLE_POLICY_REJECTED'):
    if not value:
        raise BundleError(code)


def exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(exact(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def hexadecimal(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


def parse_json(raw):
    def reject(_value):
        raise BundleError()
    return json.loads(raw, object_pairs_hook=preflight.object_pairs, parse_constant=reject)


def check_images(images, commit):
    require(type(images) is dict and set(images) == {'api', 'web'})
    for role in ('api', 'web'):
        item = images[role]
        require(type(item) is dict and set(item) == {'archive', 'size', 'sha256', 'image_id', 'platform', 'source_commit'})
        require(type(item['archive']) is str and item['archive'] == role + '.tar')
        require(type(item['size']) is int and 0 < item['size'] <= MAX_TOTAL_BYTES)
        require(hexadecimal(item['sha256'], 64) and type(item['image_id']) is str
                and re.fullmatch('sha256:[0-9a-f]{64}', item['image_id']) is not None)
        require(type(item['source_commit']) is str and item['source_commit'] == commit
                and type(item['platform']) is str and item['platform'] == 'linux/amd64')
    require(sum(item['size'] for item in images.values()) <= MAX_TOTAL_BYTES)


def safe_evidence(commit):
    return {'format': 'slc-image-handoff-evidence-v1', 'source_commit': commit,
            'status': REHEARSAL_STATUS,
            'checks': {'strict_archives': True, 'dependency_only_native_smoke': True,
                       'compose_project_and_model': True},
            'limitations': ['No application or database startup', 'No physical network isolation',
                            'No operator or deployment approval', 'No signature or security clearance']}


def export_inputs(manifest, evidence):
    require(type(manifest) is dict and set(manifest) == {'format', 'source_commit', 'required_db_revision', 'images'})
    require(exact(manifest['format'], 'slc-offline-readonly-v1')
            and exact(manifest['required_db_revision'], preflight.REVISION)
            and hexadecimal(manifest['source_commit'], 40))
    commit = manifest['source_commit']
    check_images(manifest['images'], commit)
    require(type(evidence) is dict and exact(evidence.get('status'), REHEARSAL_STATUS)
            and exact(evidence.get('source_commit'), commit) and exact(evidence.get('images'), manifest['images'])
            and exact(evidence.get('compose'), {'status': 'COMPOSE_PARSED_ONLY', 'operator_approval': False,
                                              'application_started': False}))
    native = evidence.get('native_smoke')
    require(type(native) is dict and set(native) == {'api', 'web'}
            and all(type(value) is str and bool(value) for value in native.values()))
    # Project fresh data, never serialize raw evidence, paths, logs or host state.
    safe = canonical(safe_evidence(commit))
    result = {'format': FORMAT, 'source_commit': commit,
              'images': {role: dict(manifest['images'][role]) for role in ('api', 'web')},
              'evidence_sha256': hashlib.sha256(safe).hexdigest()}
    return result, safe


def identity(value):
    return (value.st_dev, value.st_ino, value.st_mode)


def file_identity(value):
    return identity(value) + (value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)


class Descriptor:
    def __init__(self, fd):
        self.fd = fd

    def close(self):
        fd, self.fd = self.fd, None
        if fd is not None:
            # A failed close can already have released the number. Never retry it.
            os.close(fd)


def own(stack, fd):
    result = Descriptor(fd)
    stack.callback(result.close)
    return result


def path_parts(value):
    raw = os.fspath(value)
    require(type(raw) is str and raw.startswith('/') and '\\' not in raw
            and all(part not in ('', '.', '..') for part in raw[1:].split('/')), 'BUNDLE_PATH_REJECTED')
    return raw[1:].split('/')


class Directory:
    """Retain every ancestor FD; names are never resolved again for file IO."""
    def __init__(self, descriptors, links):
        self.descriptors, self.links = descriptors, links
        self.fd = descriptors[-1].fd

    @classmethod
    def open(cls, path, stack):
        require(sys.platform == 'linux' and hasattr(os, 'O_NOFOLLOW'), 'BUNDLE_PATH_REJECTED')
        parts = path_parts(path)
        descriptors = [own(stack, os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC))]
        links = []
        for name in parts:
            parent = descriptors[-1].fd
            child = own(stack, os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                      dir_fd=parent))
            links.append((parent, name, child.fd, identity(os.fstat(child.fd))))
            descriptors.append(child)
        result = cls(descriptors, links)
        result.check()
        return result

    def child(self, name, stack):
        child = own(stack, os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=self.fd))
        return Directory(self.descriptors + [child], self.links + [
            (self.fd, name, child.fd, identity(os.fstat(child.fd)))])

    def check(self):
        for parent, name, fd, expected in self.links:
            require(identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected
                    and identity(os.fstat(fd)) == expected, 'BUNDLE_CHANGED')

    def names(self, expected):
        self.check()
        seen, expected = set(), set(expected)
        with os.scandir(self.fd) as entries:
            for entry in entries:
                require(entry.name in expected and entry.name not in seen, 'BUNDLE_POLICY_REJECTED')
                seen.add(entry.name)
        require(seen == expected, 'BUNDLE_POLICY_REJECTED')


class File:
    def __init__(self, directory, name, stack, *, create=False):
        self.directory, self.name = directory, name
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY
        # O_NONBLOCK refuses a substituted FIFO without hanging before fstat.
        self.handle = own(stack, os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                                         0o600, dir_fd=directory.fd))
        self.fd = self.handle.fd
        self.initial = os.fstat(self.fd)
        require(stat.S_ISREG(self.initial.st_mode) and self.initial.st_nlink == 1, 'BUNDLE_PATH_REJECTED')
        self.check()

    def check(self):
        self.directory.check()
        current = os.fstat(self.fd)
        named = os.stat(self.name, dir_fd=self.directory.fd, follow_symlinks=False)
        require(file_identity(current) == file_identity(self.initial)
                and file_identity(named) == file_identity(self.initial), 'BUNDLE_CHANGED')

    def written(self):
        os.fsync(self.fd)
        self.initial = os.fstat(self.fd)
        self.check()


class PinnedArchive(os.PathLike):
    """Adapt the unchanged validator's repeated stat/open/tar opens to one inode.

    /proc/self/fd reopens this retained descriptor, never the untrusted file name.
    It is NOT a snapshot of a concurrently writable inode; identity checks before
    and after validation reject observable changes. Run under a trusted local UID.
    """
    def __init__(self, file):
        self.file = file
        self.path = '/proc/self/fd/' + str(file.fd)
        require(identity(os.stat(self.path)) == identity(os.fstat(file.fd)), 'BUNDLE_CHANGED')

    def __fspath__(self):
        return self.path

    def stat(self):
        return os.fstat(self.file.fd)

    def open(self, mode):
        require(mode == 'rb')
        return open(self.path, mode)


def read_bytes(file, limit):
    file.check()
    require(file.initial.st_size <= limit)
    os.lseek(file.fd, 0, os.SEEK_SET)
    chunks, remaining = [], file.initial.st_size
    while remaining:
        value = os.read(file.fd, min(CHUNK, remaining))
        require(bool(value), 'BUNDLE_CHANGED')
        chunks.append(value)
        remaining -= len(value)
    require(not os.read(file.fd, 1), 'BUNDLE_CHANGED')
    file.check()
    return b''.join(chunks)


def write_bytes(file, raw):
    view = memoryview(raw)
    for offset in range(0, len(view), CHUNK):
        block = view[offset:offset + CHUNK]
        while block:
            count = os.write(file.fd, block)
            require(type(count) is int and 0 < count <= len(block), 'BUNDLE_IO_FAILED')
            block = block[count:]


def copy_archive(source, target, item):
    source.check()
    require(source.initial.st_size == item['size'], 'BUNDLE_CHANGED')
    os.lseek(source.fd, 0, os.SEEK_SET)
    remaining, digest = item['size'], hashlib.sha256()
    while remaining:
        value = os.read(source.fd, min(CHUNK, remaining))
        require(bool(value), 'BUNDLE_CHANGED')
        digest.update(value)
        write_bytes(target, value)
        remaining -= len(value)
    require(not os.read(source.fd, 1) and digest.hexdigest() == item['sha256'], 'BUNDLE_CHANGED')
    source.check()
    target.written()


class OuterTarInfo(preflight.LayerTarInfo):
    """Docker-save envelope entries cannot expand sparse logical data or maps."""
    def _reject_sparse(self, *_args):
        raise BundleError('BUNDLE_ARCHIVE_REJECTED')

    _proc_sparse = _reject_sparse
    _proc_gnusparse_00 = _reject_sparse
    _proc_gnusparse_01 = _reject_sparse
    _proc_gnusparse_10 = _reject_sparse


def bounded_outer_scan(path, size):
    """Bound the legacy gate's outer-header/PAX cache input before invoking it.

    This is an additional support limit, not a replacement for archive_image.
    Reuse its already bounded structural reader without changing that validator.
    """
    require(size >= 1024 and size % 512 == 0, 'BUNDLE_ARCHIVE_REJECTED')
    budget = preflight.LayerTarBudget(MAX_OUTER_HEADERS, MAX_OUTER_METADATA)
    with path.open('rb') as stream:
        reader = preflight.LayerTarReader(stream, size, budget)
        with preflight.tarfile.open(fileobj=reader, mode='r:', tarinfo=OuterTarInfo) as archive:
            pax_items = pax_chars = name_chars = 0
            while (member := archive.next()) is not None:
                # Account effective inherited PAX state for every ordinary member:
                # the unchanged second parser retains those dictionaries in cache.
                require(not member.issparse() and not any(key.startswith('GNU.sparse.')
                        for key in member.pax_headers), 'BUNDLE_ARCHIVE_REJECTED')
                pax_items += len(member.pax_headers)
                pax_chars += sum(len(key) + len(value) for key, value in member.pax_headers.items())
                name_chars += len(member.name) + len(member.linkname)
                require(pax_items <= MAX_OUTER_PAX_ITEMS and pax_chars <= MAX_OUTER_PAX_CHARS
                        and name_chars <= MAX_OUTER_NAME_CHARS, 'BUNDLE_ARCHIVE_REJECTED')
                archive.members.clear()
            end = archive.offset
        require(end % 512 == 0 and size - end >= 1024, 'BUNDLE_ARCHIVE_REJECTED')
        reader.parsing = False
        reader.seek(end)
        while reader.tell() < size:
            require(not reader.read(min(CHUNK, size - reader.tell())).strip(b'\0'), 'BUNDLE_ARCHIVE_REJECTED')


def archive_gate(file, item, commit):
    file.check()
    require(type(item['size']) is int and 0 < item['size'] <= MAX_TOTAL_BYTES
            and file.initial.st_size == item['size'], 'BUNDLE_ARCHIVE_REJECTED')
    try:
        path = PinnedArchive(file)
        bounded_outer_scan(path, file.initial.st_size)
        file.check()
        preflight.archive_image(path, item, commit)
    except BundleError:
        raise
    except Exception:
        raise BundleError('BUNDLE_ARCHIVE_REJECTED') from None
    file.check()


def verify_files(directory, files, expected_commit, expected_hash, *, completed=False):
    names = FILES | ({'COMPLETE'} if completed else set())
    directory.names(names)
    raw = read_bytes(files['manifest.json'], MAX_JSON_BYTES)
    require(hashlib.sha256(raw).hexdigest() == expected_hash)
    manifest = parse_json(raw)
    require(type(manifest) is dict and set(manifest) == {'format', 'source_commit', 'images', 'evidence_sha256'})
    require(exact(manifest['format'], FORMAT) and exact(manifest['source_commit'], expected_commit)
            and hexadecimal(manifest['evidence_sha256'], 64))
    check_images(manifest['images'], expected_commit)
    evidence = read_bytes(files['evidence.json'], MAX_JSON_BYTES)
    require(hashlib.sha256(evidence).hexdigest() == manifest['evidence_sha256']
            and exact(parse_json(evidence), safe_evidence(expected_commit)))
    for role in ('api', 'web'):
        archive_gate(files[role + '.tar'], manifest['images'][role], expected_commit)
    for file in files.values():
        file.check()
    directory.names(names)
    return manifest


def check_destination(destination):
    """Read-only early rejection; export repeats checks and exclusively creates later."""
    try:
        parts = path_parts(destination)
        require(len(parts) > 1, 'BUNDLE_PATH_REJECTED')
        with ExitStack() as stack:
            parent = Directory.open('/' + '/'.join(parts[:-1]), stack)
            try:
                os.stat(parts[-1], dir_fd=parent.fd, follow_symlinks=False)
            except FileNotFoundError:
                parent.check()
            else:
                raise BundleError('BUNDLE_PATH_REJECTED')
    except BundleError:
        raise
    except Exception:
        raise BundleError('BUNDLE_PATH_REJECTED') from None


def _export_bundle(source, manifest, evidence, destination, state):
    manifest, safe = export_inputs(manifest, evidence)
    raw = canonical(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    state['receipt'] = {'source_commit': manifest['source_commit'], 'manifest_sha256': digest}
    parts = path_parts(destination)
    require(len(parts) > 1, 'BUNDLE_PATH_REJECTED')
    with ExitStack() as stack:
        source_dir = Directory.open(source, stack)
        sources = {role: File(source_dir, role + '.tar', stack) for role in ('api', 'web')}
        for role, file in sources.items():
            require(file.initial.st_size == manifest['images'][role]['size'], 'BUNDLE_CHANGED')
        parent = Directory.open('/' + '/'.join(parts[:-1]), stack)
        required = sum(item['size'] for item in manifest['images'].values()) + len(raw) + len(safe) + RESERVE_BYTES
        available = os.fstatvfs(parent.fd)
        require(available.f_bavail * available.f_frsize >= required, 'BUNDLE_CAPACITY_REJECTED')
        parent.check()
        os.mkdir(parts[-1], mode=0o700, dir_fd=parent.fd)  # Atomic exclusive reservation.
        directory = parent.child(parts[-1], stack)
        directory.names(set())
        files = {}
        for role in ('api', 'web'):
            files[role + '.tar'] = File(directory, role + '.tar', stack, create=True)
            copy_archive(sources[role], files[role + '.tar'], manifest['images'][role])
        for name, value in (('evidence.json', safe), ('manifest.json', raw)):
            files[name] = File(directory, name, stack, create=True)
            write_bytes(files[name], value)
            files[name].written()
        verify_files(directory, files, manifest['source_commit'], digest)
        for file in sources.values():
            file.check()
        # Close every payload first. A failed/uncertain close is never retried.
        for file in files.values():
            file.handle.close()
        directory.names(FILES)
        os.fsync(directory.fd)
        # Empty regular marker: O_EXCL creates it atomically, no partial JSON can
        # resemble completion. No success is claimed until its close returns.
        state['completion_attempted'] = True
        marker = File(directory, 'COMPLETE', stack, create=True)
        marker.handle.close()
    return {'status': 'IMAGE_BUNDLE_EXPORTED_NOT_OFFLINE_ACCEPTANCE',
            'source_commit': manifest['source_commit'], 'manifest_sha256': digest}


def export_bundle(source, manifest, evidence, destination):
    """Internal success-only handoff. No export-from-old-logs CLI or automatic retry."""
    state = {'completion_attempted': False}
    try:
        return _export_bundle(source, manifest, evidence, destination, state)
    except (KeyboardInterrupt, SystemExit):
        if state['completion_attempted']:
            raise CompletionInterrupted(state.get('receipt')) from None
        raise
    except Exception as error:
        if state['completion_attempted']:
            raise BundleError('BUNDLE_COMPLETION_UNCERTAIN', receipt=state.get('receipt')) from None
        if isinstance(error, BundleError):
            raise
        raise BundleError('BUNDLE_IO_FAILED') from None


def verify_bundle(directory, *, expected_commit, expected_manifest_sha256):
    """Independent read-only recheck; both expectations must come from trusted context."""
    try:
        require(hexadecimal(expected_commit, 40) and hexadecimal(expected_manifest_sha256, 64))
        with ExitStack() as stack:
            root = Directory.open(directory, stack)
            root.names(FILES | {'COMPLETE'})
            marker = File(root, 'COMPLETE', stack)
            require(marker.initial.st_size == 0)
            files = {name: File(root, name, stack) for name in sorted(FILES)}
            verify_files(root, files, expected_commit, expected_manifest_sha256, completed=True)
            marker.check()
            root.names(FILES | {'COMPLETE'})
        return {'status': 'IMAGE_BUNDLE_VERIFIED_NOT_OFFLINE_ACCEPTANCE',
                'source_commit': expected_commit, 'manifest_sha256': expected_manifest_sha256}
    except BundleError:
        raise
    except Exception:
        raise BundleError('BUNDLE_IO_FAILED') from None


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, 'offline image bundle: invalid arguments\n')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('mode', choices=['verify'])
    parser.add_argument('directory')
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(args.directory, expected_commit=args.expected_commit,
                               expected_manifest_sha256=args.expected_manifest_sha256)
    except Exception:
        print('BLOCKED: image bundle verification failed; no offline or deployment acceptance claimed.', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
