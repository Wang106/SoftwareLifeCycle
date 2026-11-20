"""Test-only Linux disk witnesses and owned Uvicorn listener; no deployment entry."""
import hashlib
import os
import socket
import stat
import threading
import time
import uuid
from dataclasses import dataclass


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@dataclass(frozen=True)
class RootIdentity:
    device: int
    inode: int

    @classmethod
    def capture(cls, root):
        info = root.lstat()
        assert stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
        assert info.st_uid == os.geteuid()
        return cls(info.st_dev, info.st_ino)


def inspect_disk(root, object_id, size, digest):
    assert str(uuid.UUID(object_id)) == object_id
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        file = os.open(object_id + '.blob', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(file)
            assert stat.S_ISREG(before.st_mode) and before.st_nlink in (1, 2)
            if before.st_nlink == 2:
                staged = os.stat(object_id + '.part', dir_fd=fd, follow_symlinks=False)
                assert identity(staged) == identity(before)
            assert stat.S_IMODE(before.st_mode) == 0o600 and before.st_uid == os.geteuid()
            assert before.st_size == size and 0 <= size <= 65539
            data = b''
            while len(data) <= size:
                chunk = os.read(file, min(8192, size + 1 - len(data)))
                if not chunk: break
                data += chunk
            assert len(data) == size and hashlib.sha256(data).hexdigest() == digest
            assert identity(os.fstat(file)) == identity(before)
            return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                        identity=identity(before), closed_before_read=True)
        finally: os.close(file)
    finally: os.close(fd)


def remove_owned(root, expected_root, files):
    assert RootIdentity.capture(root) == expected_root
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        assert (info.st_dev, info.st_ino) == (expected_root.device, expected_root.inode)
        assert set(os.listdir(fd)) == set(files), 'unknown file: cleanup refused'
        for name, expected in files.items():
            assert '/' not in name and name.endswith(('.blob', '.part'))
            assert str(uuid.UUID(name[:-5])) == name[:-5]
            actual = os.stat(name, dir_fd=fd, follow_symlinks=False)
            assert stat.S_ISREG(actual.st_mode) and actual.st_nlink in (1, 2)
            peers = [other for other, stamp in files.items() if stamp[:2] == expected[:2]]
            assert len(peers) == actual.st_nlink
            if actual.st_nlink == 2:
                assert set(peers) == {name[:-5]+'.part', name[:-5]+'.blob'}
            assert identity(actual) == expected, 'changed file: cleanup refused'
        for name in files: os.unlink(name, dir_fd=fd)
    finally: os.close(fd)
    assert RootIdentity.capture(root) == expected_root
    root.rmdir()
    assert not root.exists()


def require_loopback_pg(value):
    from sqlalchemy.engine import make_url
    parsed = make_url(value)
    assert parsed.get_backend_name() == 'postgresql' and parsed.host == '127.0.0.1'
    assert not parsed.query, 'connection target overrides are forbidden'
    return parsed


class LoopbackServer:
    """Prebind a single owned IPv4 loopback socket; never kill foreign processes."""
    def __init__(self, app):
        self.app = app
        self.errors = []
        self.socket = self.server = self.thread = None

    def __enter__(self):
        import uvicorn
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.bind(('127.0.0.1', 0))
            self.socket.listen(16)
            self.port = self.socket.getsockname()[1]
            self.origin = f'http://127.0.0.1:{self.port}'
            self.server = uvicorn.Server(uvicorn.Config(self.app, host='127.0.0.1', port=self.port,
                lifespan='off', loop='asyncio', http='h11', access_log=False,
                log_level='critical', timeout_graceful_shutdown=3))
            def run():
                try: self.server.run(sockets=[self.socket])
                except BaseException as error: self.errors.append(error)
            self.thread = threading.Thread(target=run, daemon=True)
            self.thread.start()
            deadline = time.monotonic() + 5
            while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.01)
            assert self.server.started, 'owned server did not start'
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.server is not None: self.server.should_exit = True
        if self.thread is not None and self.thread.ident is not None:
            self.thread.join(5)
            assert not self.thread.is_alive(), 'owned server failed to stop; cleanup refused'
        if self.socket is not None:
            self.socket.close()
            assert self.socket.fileno() == -1
        if self.server is not None:
            assert not self.server.server_state.connections
            assert not self.server.server_state.tasks

    def __exit__(self, *_):
        self.close()
        assert not self.errors, 'owned server thread failed'


def mark_quiescent(engine, server, runtime):
    if server is not None:
        assert server.thread is None or not server.thread.is_alive(), 'active server: cleanup refused'
        if server.server is not None:
            assert not server.server.server_state.connections
            assert not server.server.server_state.tasks
    assert runtime.permits.acquire(blocking=False), 'storage permit still held'
    runtime.permits.release()
    engine.loopback_cleanup_safe = True


def cleanup_schema(admin, engine, schema, created):
    import re
    from sqlalchemy import text
    assert re.fullmatch(r'command_test_[0-9a-f]{32}', schema)
    if engine is not None:
        assert engine.loopback_cleanup_safe, 'active HTTP/storage work: schema cleanup refused'
        assert engine.pool.checkedout() == 0, 'active DB work: schema cleanup refused'
        engine.dispose()
    if created:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        with admin.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname=:name'), {'name':schema}) == 0
