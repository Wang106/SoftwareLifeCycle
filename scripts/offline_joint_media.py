#!/usr/bin/env python3
"""Verify three actual handoffs together; no installation or runtime operations.

Explicit verify only. Trusted local Linux filesystem/no concurrent mutation;
retained descriptors and identity checks are not hostile-UID snapshots.
Never writes inputs, extracts, invokes subprocesses, connects or uploads.
"""
import argparse
import os
import sys

import offline_image_bundle as bundle
import offline_operator_assembly as assembly
import offline_postgres_image_bundle as postgres
import offline_migration_image_bundle as migration

IMAGE_SOURCE = 'e2038a9462770a29254674dd86c0e7b26b26a221'
REVISION = '0030_private_upload_sessions'
MAX_PAYLOAD_BYTES = 16 * 1024**3
VERIFY_SECONDS = 600
ROLES = ('api_web', 'postgres', 'migration')
FORMAT = 'slc-joint-media-index-v1'
STATUS = 'MEDIA_SET_VERIFIED_NOT_INSTALLATION_READY'
LIMITATIONS = (
    'Independently trusted manifest digests are required; hashes are not signatures',
    'Trusted local Linux filesystem; no hostile same-UID or concurrent-writer isolation',
    'Payload bytes are local files, not compressed transport size or remote billable storage',
    'No image load, database migration, role setup, runtime or company acceptance',
    'Index is a point-in-time report; later consumers must reverify original bytes',
)


class MediaError(ValueError):
    def __init__(self):
        super().__init__('JOINT_MEDIA_REJECTED_OR_UNCONFIRMED')


def require(value):
    if not value:
        raise MediaError()


def inode(info):
    return info.st_dev, info.st_ino


def inputs_checked(inputs):
    require(type(inputs) is dict and set(inputs) == set(ROLES))
    result = {}
    for role in ROLES:
        item = inputs[role]
        require(type(item) is dict and set(item) == {'directory','expected_commit','manifest_sha256'})
        require(bundle.hexadecimal(item['expected_commit'],40)
                and bundle.hexadecimal(item['manifest_sha256'],64))
        parts = bundle.path_parts(item['directory'])
        result[role] = {**item, 'parts':parts}
    require(result['api_web']['expected_commit'] == IMAGE_SOURCE)
    # These are reviewed source bindings, not declarations supplied by a package.
    require(assembly.SOURCE_REVISIONS == {IMAGE_SOURCE:REVISION}
            and migration.SOURCE_REVISIONS == {IMAGE_SOURCE:REVISION}
            and migration.IMAGE_SOURCE == IMAGE_SOURCE and migration.REVISION == REVISION
            and bundle.preflight.REVISION == REVISION)
    for index, left in enumerate(ROLES):
        for right in ROLES[index+1:]:
            a, b = result[left]['parts'], result[right]['parts']
            require(a[:min(len(a),len(b))] != b[:min(len(a),len(b))])
    return result


def open_set(inputs, stack):
    modules = {'api_web':bundle, 'postgres':postgres, 'migration':migration}
    roots = {role:bundle.Directory.open(inputs[role]['directory'],stack) for role in ROLES}
    # Reject aliases/bind-mounted ancestors as well as lexical nesting.
    for left in ROLES:
        own = inode(os.fstat(roots[left].fd))
        for right in ROLES:
            if left != right:
                require(all(own != inode(os.fstat(fd.fd)) for fd in roots[right].descriptors))
    opened, total = {}, 0
    for role in ROLES:
        root = roots[role]; names = modules[role].FILES | {'COMPLETE'}
        root.names(names)
        files = {name:bundle.File(root,name,stack) for name in sorted(names)}
        require(files['COMPLETE'].initial.st_size == 0)
        total += sum(file.initial.st_size for file in files.values())
        require(total <= MAX_PAYLOAD_BYTES)
        opened[role] = {'root':root, 'files':files, 'names':names}
    return opened, total


def verify_pinned(opened, inputs):
    app, pg, mig = (opened[role] for role in ROLES)
    def files(item):
        return {name:file for name,file in item['files'].items() if name != 'COMPLETE'}
    app_manifest = bundle.verify_files(app['root'],files(app),IMAGE_SOURCE,
                                       inputs['api_web']['manifest_sha256'],completed=True)
    postgres.verify_files(pg['root'],files(pg),inputs['postgres']['expected_commit'],
                          inputs['postgres']['manifest_sha256'],True)
    migration.verify_files(mig['root'],files(mig),IMAGE_SOURCE,
                           inputs['migration']['manifest_sha256'],True)
    # Read only from the retained, already-validated descriptors. Later final
    # identity checks also cover earlier handoffs and all completion markers.
    pg_manifest = bundle.parse_json(bundle.read_bytes(pg['files']['manifest.json'],bundle.MAX_JSON_BYTES))
    mig_manifest = bundle.parse_json(bundle.read_bytes(mig['files']['manifest.json'],bundle.MAX_JSON_BYTES))
    require(mig_manifest['tool_commit'] == inputs['migration']['expected_commit'])
    return app_manifest, pg_manifest, mig_manifest


def make_index(manifests, inputs, total):
    app, pg, mig = manifests
    images = {}
    for role, handoff, item in (
            ('api','api_web',app['images']['api']),('web','api_web',app['images']['web']),
            ('postgres','postgres',{**pg['image'], **{key:pg['contract'][key] for key in ('image_id','platform')}}),('migration','migration',mig['image'])):
        # Project only fields that the corresponding strict validator checked.
        images[role] = {key:item[key] for key in ('archive','size','sha256','image_id','platform')}
        images[role]['handoff'] = handoff
    require(len({item['image_id'] for item in images.values()}) == 4)
    images['api']['image_source_commit'] = app['source_commit']
    images['web']['image_source_commit'] = app['source_commit']
    images['migration']['image_source_commit'] = mig['source_commit']
    images['postgres']['repository_digest'] = pg['contract']['repository_digest']
    return {'format':FORMAT, 'status':STATUS, 'image_source_commit':IMAGE_SOURCE,
            'required_db_revision':REVISION, 'images':images,
            'handoffs':{
                'api_web':{'image_source_commit':app['source_commit'],
                           'manifest_sha256':inputs['api_web']['manifest_sha256']},
                'postgres':{'tool_commit':pg['source_commit'],
                            'manifest_sha256':inputs['postgres']['manifest_sha256']},
                'migration':{'tool_commit':mig['tool_commit'], 'image_source_commit':mig['source_commit'],
                             'manifest_sha256':inputs['migration']['manifest_sha256']}},
            'file_count':13, 'payload_bytes':total, 'payload_limit_bytes':MAX_PAYLOAD_BYTES,
            'installation_ready':False, 'database_migrated':False, 'database_readonly_role':False,
            'runtime_verified':False, 'company_acceptance':False,
            'content_clearance_verified':False, 'upload_authorized':False,
            'limitations':list(LIMITATIONS)}


def verify(inputs):
    try:
        # No per-handoff wrapper timers: a single non-extending deadline covers
        # opening, all three existing gates, final rechecks and descriptor close.
        with migration.bounded(VERIFY_SECONDS):
            checked = inputs_checked(inputs)
            with assembly._ClosingStack() as stack:
                opened, total = open_set(checked,stack)
                manifests = verify_pinned(opened,checked)
                result = make_index(manifests,checked,total)
                for item in opened.values():
                    item['root'].names(item['names'])
                    for file in item['files'].values():
                        file.check()
        return result
    except (Exception,KeyboardInterrupt,SystemExit):
        raise MediaError() from None


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise MediaError()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    parsed_arguments = False
    try:
        if not args:
            postgres.emit(sys.stdout,'DISABLED: explicit verify and three independent trusted receipts required.')
            return 0
        parser = Parser(description=__doc__,allow_abbrev=False)
        parser.add_argument('mode',choices=['verify'])
        for role in ROLES:
            name = role.replace('_','-')
            parser.add_argument('--'+name+'-directory',required=True)
            parser.add_argument('--'+name+'-expected-commit',required=True)
            parser.add_argument('--'+name+'-manifest-sha256',required=True)
        parsed = vars(parser.parse_args(args))
        parsed_arguments = True
        inputs = {role:{'directory':parsed[role+'_directory'],
                        'expected_commit':parsed[role+'_expected_commit'],
                        'manifest_sha256':parsed[role+'_manifest_sha256']} for role in ROLES}
        result = verify(inputs)
        postgres.emit(sys.stdout,bundle.canonical(result).decode('ascii').rstrip('\n'))
        return 0
    except (Exception,KeyboardInterrupt,SystemExit) as error:
        if isinstance(error,SystemExit) and not parsed_arguments:
            raise
        try:
            postgres.emit(sys.stderr,'JOINT_MEDIA_REJECTED_OR_UNCONFIRMED; no installation or runtime action.')
        except (Exception,KeyboardInterrupt,SystemExit):
            pass
        return 2


if __name__ == '__main__':
    sys.exit(main())
