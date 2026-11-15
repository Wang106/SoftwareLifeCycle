#!/usr/bin/env python3
"""Inventory an existing handoff for seven-day retention preparation only.

No builds, writes, uploads, extraction, billing access or content clearance.
A successful inventory NEVER grants permission to upload. Expected source/digest
must be independently trusted; payload hashes do not establish provenance.
"""
import argparse
import hashlib
import json
import os
import sys

import offline_image_bundle as bundle
import offline_operator_assembly as assembly

MAX_UPLOAD_BYTES = 16 * 1024**3
RETENTION_DAYS = 7
IMAGE_SOURCE = 'e2038a9462770a29254674dd86c0e7b26b26a221'
BLOCKERS = ('ZERO_INCREMENTAL_COST_UNVERIFIED', 'PUBLIC_CONTENT_CLEARANCE_UNVERIFIED',
            'STORED_ARTIFACT_SIZE_UNVERIFIED', 'UPLOAD_AND_EXPIRATION_UNVERIFIED')


class RetentionError(ValueError):
    def __init__(self):
        super().__init__('MEDIA_CANDIDATE_REJECTED')


def stream_hash(file):
    """Hash bounded bytes through the already pinned file, never reopen by name."""
    file.check()
    os.lseek(file.fd, 0, os.SEEK_SET)
    remaining = file.initial.st_size
    digest = hashlib.sha256()
    while remaining:
        raw = os.read(file.fd, min(bundle.CHUNK, remaining))
        bundle.require(bool(raw))
        digest.update(raw)
        remaining -= len(raw)
    bundle.require(not os.read(file.fd, 1))
    file.check()
    return digest.hexdigest()


def _inspect(directory, expected_commit, expected_manifest_sha256):
    bundle.require(bundle.hexadecimal(expected_commit, 40)
                   and expected_commit == IMAGE_SOURCE
                   and bundle.hexadecimal(expected_manifest_sha256, 64))
    revision = assembly.SOURCE_REVISIONS.get(expected_commit)
    bundle.require(revision is not None and revision == bundle.preflight.REVISION)
    names = bundle.FILES | {'COMPLETE'}
    # Reuse the reviewed close stack to attempt each owned close once and keep
    # interruptions visible even when a later close fails. No cleanup/retry.
    with assembly._ClosingStack() as stack:
        root = bundle.Directory.open(directory, stack)
        root.names(names)
        files = {name: bundle.File(root, name, stack) for name in sorted(names)}
        bundle.require(files['COMPLETE'].initial.st_size == 0)
        total = sum(file.initial.st_size for file in files.values())
        # Original bundle cap counts only archives. Retention counts metadata too.
        bundle.require(0 < total <= MAX_UPLOAD_BYTES)
        manifest = bundle.verify_files(root, files, expected_commit,
                                       expected_manifest_sha256, completed=True)
        inventory = {name: {'size': file.initial.st_size, 'sha256': stream_hash(file)}
                     for name, file in files.items()}
        bundle.require(inventory['manifest.json']['sha256'] == expected_manifest_sha256
                       and inventory['evidence.json']['sha256'] == manifest['evidence_sha256'])
        for role in ('api', 'web'):
            item = inventory[role + '.tar']
            bundle.require(item['sha256'] == manifest['images'][role]['sha256']
                           and item['size'] == manifest['images'][role]['size'])
        for file in files.values():
            file.check()
        root.names(names)
    # Publish only after verification, inventory and all descriptor closes succeed.
    return {'status': 'MEDIA_CANDIDATE_INVENTORIED_NOT_UPLOAD_APPROVED',
            'image_source_commit': expected_commit, 'required_db_revision': revision,
            'handoff_manifest_sha256': expected_manifest_sha256,
            'file_count': len(inventory), 'files': inventory, 'payload_bytes': total,
            'retention_days': RETENTION_DAYS,
            'payload_byte_hours': total * RETENTION_DAYS * 24,
            'artifact_size_limit_bytes': MAX_UPLOAD_BYTES,
            'maximum_artifact_gib_hours': 16 * RETENTION_DAYS * 24,
            'upload_authorized': False, 'zero_incremental_cost_verified': False,
            'content_clearance_verified': False, 'stored_artifact_size_verified': False,
            'artifact_expiration_verified': False, 'blockers': list(BLOCKERS),
            'limitations': ['Payload bytes are not stored ZIP size or billable usage',
                            'Hashes are not secret scanning or provenance',
                            'Tool checkout and image source commit are distinct',
                            'No runtime, retention, transfer or company acceptance']}


def inspect_candidate(directory, *, expected_commit, expected_manifest_sha256):
    try:
        return _inspect(directory, expected_commit, expected_manifest_sha256)
    except KeyboardInterrupt:
        raise KeyboardInterrupt('MEDIA_INVENTORY_INTERRUPTED') from None
    except SystemExit:
        raise SystemExit(2) from None
    except Exception:
        raise RetentionError() from None


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        raise RetentionError()


def main(argv=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('mode', nargs='?', choices=['inspect'])
    parser.add_argument('directory', nargs='?')
    parser.add_argument('--expected-commit')
    parser.add_argument('--expected-manifest-sha256')
    try:
        args = parser.parse_args(argv)
        if args.mode is None:
            bundle.require(not any((args.directory, args.expected_commit, args.expected_manifest_sha256)))
            print('DISABLED: explicit inspect mode required; no files read or uploads performed.')
            return 0
        bundle.require(all((args.directory, args.expected_commit, args.expected_manifest_sha256)))
        result = inspect_candidate(args.directory, expected_commit=args.expected_commit,
                                   expected_manifest_sha256=args.expected_manifest_sha256)
        assembly._emit(sys.stdout, json.dumps(result, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        return 130
    except SystemExit as error:
        return 0 if error.code == 0 else 2
    except Exception:
        try:
            assembly._emit(sys.stderr, 'MEDIA_CANDIDATE_REJECTED')
        except (Exception, KeyboardInterrupt, SystemExit):
            pass
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
