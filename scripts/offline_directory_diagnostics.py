#!/usr/bin/env python3
"""Observe explicitly selected directory filesystems without reading their contents."""
import contextlib
import errno
import json
import os
import re
import stat
import sys

ROLES = ('logs', 'backups', 'software')
MAX_INTEGER = 2**63 - 1
MAX_PATH_CHARS = 4096
MAX_COMPONENTS = 256
LIMITATIONS = (
    'Point-in-time observations of opened directories only; paths may later refer '
    'to different objects. No disk health, write permission, container mapping, '
    'backup recoverability or production acceptance is established. Shared '
    'filesystems are not independent capacity and must not be summed.'
)
HELP = ('Usage: offline_directory_diagnostics.py --logs ABSOLUTE_DIRECTORY '
        '--backups ABSOLUTE_DIRECTORY --software ABSOLUTE_DIRECTORY '
        '--minimum-free-bytes INTEGER\n'
        'Read-only observation; no content reads, directory listing or target writes.\n')


class InvalidInput(ValueError):
    """Input rejected without retaining input in a diagnostic."""


def supported():
    return (os.name == 'posix' and all(isinstance(getattr(os, name, None), int)
            and getattr(os, name) != 0 for name in ('O_DIRECTORY', 'O_NOFOLLOW'))
            and os.open in getattr(os, 'supports_dir_fd', ())
            and all(callable(getattr(os, name, None)) for name in ('fstat', 'fstatvfs')))


def valid_path(path):
    if not isinstance(path, str) or not 1 <= len(path) <= MAX_PATH_CHARS:
        return False
    if not path.startswith('/') or '\\' in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        return False
    if path == '/':
        return True
    parts = path[1:].split('/')
    return len(parts) <= MAX_COMPONENTS and all(p not in ('', '.', '..') for p in parts)


@contextlib.contextmanager
def directory(path):
    """Pin each parent before opening its child; never resolve or re-open a path."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    fd = os.open('/', flags)
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.ENOTDIR, 'directory required')
        for part in (() if path == '/' else path[1:].split('/')):
            child = os.open(part, flags, dir_fd=fd)
            try:
                if not stat.S_ISDIR(os.fstat(child).st_mode):
                    raise OSError(errno.ENOTDIR, 'directory required')
            except BaseException:
                os.close(child)
                raise
            old, fd = fd, child
            os.close(old)
        yield fd
    finally:
        os.close(fd)


def row(role, status, minimum, available=None):
    return {'role': role, 'status': status, 'available_bytes': available,
            'minimum_free_bytes': minimum}


def report(rows):
    return {'format': 'slc-offline-directory-diagnostics-v1',
            'status': 'OBSERVATION_ONLY' if all(r['status'] == 'DIRECTORY_OBSERVED' for r in rows) else 'BLOCKED',
            'directories': rows, 'limitations': LIMITATIONS}


def unavailable(role, minimum, error):
    unsupported = isinstance(error, NotImplementedError) or getattr(error, 'errno', None) in (
        errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP)
    return row(role, 'UNSUPPORTED' if unsupported else 'PATH_UNAVAILABLE', minimum)


def observe(role, path, minimum):
    try:
        with directory(path) as fd:
            try:
                capacity = os.fstatvfs(fd)
                blocks, fragment = capacity.f_bavail, capacity.f_frsize
                # Missing, sentinel, negative, fractional and unbounded values are unknown,
                # never silently zero. Do not substitute f_bfree (root-reserved blocks).
                if not (type(blocks) is int and type(fragment) is int
                        and 0 <= blocks <= MAX_INTEGER and 0 < fragment <= MAX_INTEGER
                        and blocks * fragment <= MAX_INTEGER):
                    return row(role, 'CAPACITY_UNKNOWN', minimum)
                available = blocks * fragment
            except (OSError, ValueError, TypeError, AttributeError, OverflowError, NotImplementedError) as error:
                if isinstance(error, NotImplementedError) or getattr(error, 'errno', None) in (errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP):
                    return row(role, 'UNSUPPORTED', minimum)
                return row(role, 'CAPACITY_UNKNOWN', minimum)
            return row(role, 'DIRECTORY_OBSERVED' if available >= minimum else 'BELOW_MINIMUM', minimum, available)
    except (OSError, ValueError, TypeError, OverflowError, NotImplementedError) as error:
        return unavailable(role, minimum, error)


def diagnose(paths, minimum):
    valid_minimum = type(minimum) is int and 0 <= minimum <= MAX_INTEGER
    if not (valid_minimum and isinstance(paths, dict) and set(paths) == set(ROLES)
            and all(valid_path(paths[role]) for role in ROLES)):
        return report([row(role, 'INVALID_INPUT', minimum if valid_minimum else None) for role in ROLES])
    if not supported():
        return report([row(role, 'UNSUPPORTED', minimum) for role in ROLES])
    return report([observe(role, paths[role], minimum) for role in ROLES])


def parse(argv):
    # Exactly four option/value pairs: no abbreviation, duplication, files, JSON,
    # positional arguments or parser errors that could echo private input.
    if len(argv) != 8:
        raise InvalidInput()
    values = {}
    expected = {'--' + role for role in ROLES} | {'--minimum-free-bytes'}
    for option, value in zip(argv[::2], argv[1::2]):
        if option not in expected or option in values or not isinstance(value, str):
            raise InvalidInput()
        values[option] = value
    number = values['--minimum-free-bytes']
    if len(number) > 19 or re.fullmatch(r'0|[1-9][0-9]*', number) is None:
        raise InvalidInput()
    minimum = int(number)
    paths = {role: values['--' + role] for role in ROLES}
    if minimum > MAX_INTEGER or not all(valid_path(path) for path in paths.values()):
        raise InvalidInput()
    return paths, minimum


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--help']:
        sys.stdout.write(HELP)
        return 0
    try:
        paths, minimum = parse(argv)
    except InvalidInput:
        result = report([row(role, 'INVALID_INPUT', None) for role in ROLES])
        code = 2
    else:
        result = diagnose(paths, minimum)
        code = 0 if result['status'] == 'OBSERVATION_ONLY' else 1
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
