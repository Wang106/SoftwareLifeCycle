#!/usr/bin/env python3
"""Explicit local canonical USTAR packaging; no build, network or upload.

Trusted local Linux filesystem only. Receipts are required: interrupted outputs
are retained for inspection, never overwritten, resumed or automatically deleted.
Outer SHA-256 is distinct from the independently trusted inner manifest digest.
"""
import argparse
import hashlib
import json
import os
import sys
import tarfile

import offline_image_bundle as bundle
import offline_media_retention as media
import offline_operator_assembly as assembly

NAMES = tuple(sorted(bundle.FILES | {'COMPLETE'}))
RESERVE_BYTES = 1024**3
MAX_MEMBER_BYTES = 8 * 1024**3 - 1  # USTAR octal size field; no PAX/base256 extension

class TransportError(ValueError):
    def __init__(self):
        super().__init__('MEDIA_TRANSPORT_REJECTED_OR_UNCONFIRMED')


def compatibility(commit, digest):
    bundle.require(commit == media.IMAGE_SOURCE and bundle.hexadecimal(commit, 40)
                   and bundle.hexadecimal(digest, 64)
                   and assembly.SOURCE_REVISIONS.get(commit) == bundle.preflight.REVISION)


def header(name, size):
    bundle.require(type(size) is int and 0 <= size <= MAX_MEMBER_BYTES)
    info = tarfile.TarInfo(name)
    info.size, info.mode = size, 0o600
    return info.tobuf(format=tarfile.USTAR_FORMAT)


def padding(size):
    return (-size) % 512


def length(files):
    return 1024 + sum(512 + v['size'] + padding(v['size']) for v in files.values())


def write(fd, raw):
    while raw:
        count = os.write(fd, raw)
        bundle.require(count > 0)
        raw = raw[count:]


def read(fd, size):
    raw = bytearray()
    while len(raw) < size:
        part = os.read(fd, size-len(raw))
        bundle.require(bool(part))
        raw.extend(part)
    return bytes(raw)


def parent_for(path, stack):
    parts = bundle.path_parts(path)
    bundle.require(len(parts) > 1)
    return bundle.Directory.open('/'+'/'.join(parts[:-1]), stack), parts[-1]


def absent(parent, name):
    try:
        os.stat(name, dir_fd=parent.fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise TransportError()


def capacity(parent, size):
    v = os.fstatvfs(parent.fd)
    bundle.require(v.f_bavail*v.f_frsize >= size + RESERVE_BYTES)


def scan(file, expected_digest=None, destination=None, stack=None, outputs=None):
    """Parse exactly five canonical regular members, never received paths.

    No generic tar extraction, links, PAX/GNU extensions, duplicate entries,
    arbitrary modes, hidden trailing bytes or compressed expansion are accepted.
    Bounded reads and total/metadata caps apply before any output copy.
    """
    file.check()
    bundle.require(0 < file.initial.st_size <= media.MAX_UPLOAD_BYTES)
    os.lseek(file.fd, 0, os.SEEK_SET)
    files = {}
    for name in NAMES:
        raw = read(file.fd,512)
        size = int(raw[124:136].rstrip(b'\0 '),8)
        bundle.require(size >= 0 and raw == header(name,size))
        limit = media.MAX_UPLOAD_BYTES if name.endswith('.tar') else bundle.MAX_JSON_BYTES
        bundle.require(size <= limit and (name != 'COMPLETE' or size == 0))
        bundle.require(os.lseek(file.fd,0,os.SEEK_CUR)+size+padding(size)+1024 <= file.initial.st_size)
        target = bundle.File(destination,name,stack,create=True) if destination and name != 'COMPLETE' else None
        if target is not None: outputs[name] = target
        digest = hashlib.sha256()
        remaining = size
        while remaining:
            data = read(file.fd,min(bundle.CHUNK,remaining))
            digest.update(data)
            if target: write(target.fd,data)
            remaining -= len(data)
        bundle.require(read(file.fd,padding(size)) == bytes(padding(size)))
        if target: target.written()
        files[name] = {'size':size,'sha256':digest.hexdigest()}
    bundle.require(read(file.fd,1024) == bytes(1024) and not os.read(file.fd,1))
    bundle.require(length(files) == file.initial.st_size)
    digest = media.stream_hash(file)
    if expected_digest is not None: bundle.require(digest == expected_digest)
    file.check()
    return files,digest


def receipt(inventory, size, digest):
    return {'status':'MEDIA_TRANSPORT_VERIFIED_NOT_UPLOAD_APPROVED',
            'transport_format':'canonical-ustar-v1', 'transport_bytes':size,
            'transport_sha256':digest, 'transport_bytes_verified':True,
            'handoff_manifest_sha256':inventory['handoff_manifest_sha256'],
            'inventory':inventory, 'upload_authorized':False,
            'limitations':['Exact local transport bytes only; stored remote bytes remain unverified',
                'Outer digest does not replace independently trusted inner manifest digest',
                'No public content clearance, free storage, retention, delivery or installation proof']}


def _pack(source, destination, commit, digest):
    compatibility(commit,digest)
    inventory = media.inspect_candidate(source,expected_commit=commit,expected_manifest_sha256=digest)
    for name, item in inventory['files'].items(): header(name,item['size'])
    size = length(inventory['files'])
    bundle.require(size <= media.MAX_UPLOAD_BYTES)
    # Reject lexical nesting before opening a destination; preserve the handoff.
    src, dst = bundle.path_parts(source), bundle.path_parts(destination)
    bundle.require(dst[:len(src)] != src)
    with assembly._ClosingStack() as stack:
        root = bundle.Directory.open(source,stack)
        root.names(NAMES)
        sources = {name:bundle.File(root,name,stack) for name in NAMES}
        bundle.verify_files(root,sources,commit,digest,completed=True)
        parent,name = parent_for(destination,stack)
        bundle.require(all(assembly._inode(os.fstat(d.fd)) != assembly._inode(os.fstat(root.fd))
                           for d in parent.descriptors))
        absent(parent,name)
        capacity(parent,size)
        output = bundle.File(parent,name,stack,create=True)
        for name in NAMES:
            source_file = sources[name]
            item = inventory['files'][name]
            bundle.require(source_file.initial.st_size == item['size'])
            write(output.fd,header(name,item['size']))
            os.lseek(source_file.fd,0,os.SEEK_SET)
            remaining = item['size']
            copied = hashlib.sha256()
            while remaining:
                raw = read(source_file.fd,min(bundle.CHUNK,remaining))
                copied.update(raw)
                write(output.fd,raw)
                remaining -= len(raw)
            bundle.require(copied.hexdigest() == item['sha256'] and not os.read(source_file.fd,1))
            source_file.check()
            write(output.fd,bytes(padding(item['size'])))
        write(output.fd,bytes(1024))
        output.written()
        # Re-read the actual archive, comparing every inner byte digest and size.
        extracted,outer_digest = scan(output)
        bundle.require(extracted == inventory['files'] and output.initial.st_size == size)
        bundle.verify_files(root,sources,commit,digest,completed=True)
        for f in sources.values(): f.check()
        root.names(NAMES)
        os.fsync(parent.fd)
    return receipt(inventory,size,outer_digest)


def _unpack(source,destination,commit,digest,outer_digest):
    compatibility(commit,digest)
    bundle.require(bundle.hexadecimal(outer_digest,64))
    with assembly._ClosingStack() as stack:
        parent,name = parent_for(source,stack)
        archive = bundle.File(parent,name,stack)
        # Strict entire outer-format and trusted outer-digest gate BEFORE mkdir.
        files,actual = scan(archive,outer_digest)
        bundle.require(files['manifest.json']['sha256'] == digest)
        dest_parent,dest_name = parent_for(destination,stack)
        absent(dest_parent,dest_name)
        capacity(dest_parent,sum(v['size'] for v in files.values()))
        os.mkdir(dest_name,mode=0o700,dir_fd=dest_parent.fd)
        root = dest_parent.child(dest_name,stack)
        root.names(set())
        outputs = {}
        copied,again = scan(archive,outer_digest,root,stack,outputs)
        bundle.require(copied == files and again == actual)
        # Validate and close every payload BEFORE creating completion marker.
        bundle.verify_files(root,outputs,commit,digest,completed=False)
        for file in outputs.values(): file.handle.close()
        root.names(bundle.FILES)
        archive.check()
        os.fsync(root.fd)
        marker = bundle.File(root,'COMPLETE',stack,create=True)
        marker.handle.close()
        # A later failure is completion-unconfirmed, never permission to retry.
        # Inner validation still independently checks source/schema and archives.
        inventory = media.inspect_candidate(destination,expected_commit=commit,expected_manifest_sha256=digest)
        bundle.require(inventory['files'] == files)
        archive.check()
        root.names(NAMES)
        os.fsync(root.fd)
        os.fsync(dest_parent.fd)
        size = archive.initial.st_size
    return receipt(inventory,size,actual)


def guarded(function,*args):
    try: return function(*args)
    except KeyboardInterrupt: raise KeyboardInterrupt('MEDIA_TRANSPORT_INTERRUPTED') from None
    except SystemExit: raise SystemExit(2) from None
    except Exception: raise TransportError() from None


def pack(source,destination,*,expected_commit,expected_manifest_sha256):
    return guarded(_pack,source,destination,expected_commit,expected_manifest_sha256)


def unpack(source,destination,*,expected_commit,expected_manifest_sha256,expected_transport_sha256):
    return guarded(_unpack,source,destination,expected_commit,expected_manifest_sha256,expected_transport_sha256)


class SafeParser(argparse.ArgumentParser):
    def error(self,_message): raise TransportError()


def main(argv=None):
    parser = SafeParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('mode',nargs='?',choices=['pack','unpack'])
    parser.add_argument('source',nargs='?')
    parser.add_argument('destination',nargs='?')
    parser.add_argument('--expected-commit')
    parser.add_argument('--expected-manifest-sha256')
    parser.add_argument('--expected-transport-sha256')
    try:
        args = parser.parse_args(argv)
        if args.mode is None:
            bundle.require(not any(vars(args).values()))
            assembly._emit(sys.stdout,'DISABLED: explicit pack/unpack required; no files read or created.')
            return 0
        bundle.require(all((args.source,args.destination,args.expected_commit,args.expected_manifest_sha256)))
        kw = dict(expected_commit=args.expected_commit,expected_manifest_sha256=args.expected_manifest_sha256)
        if args.mode == 'pack':
            bundle.require(args.expected_transport_sha256 is None)
            result = pack(args.source,args.destination,**kw)
        else:
            result = unpack(args.source,args.destination,expected_transport_sha256=args.expected_transport_sha256,**kw)
        assembly._emit(sys.stdout,json.dumps(result,sort_keys=True))
        return 0
    except KeyboardInterrupt: code = 130
    except SystemExit as error: return 0 if error.code == 0 else 2
    except Exception: code = 2
    try: assembly._emit(sys.stderr,'MEDIA_TRANSPORT_REJECTED_OR_UNCONFIRMED: inspect owned output; no automatic retry or deletion.')
    except (Exception,KeyboardInterrupt,SystemExit): pass
    return code

if __name__ == '__main__': raise SystemExit(main())
