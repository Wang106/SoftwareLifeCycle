"""Negative evidence/lifecycle regressions; synthetic local files only."""
import hashlib
import uuid

import pytest
from private_upload_loopback import inspect_disk, remove_owned, RootIdentity

DATA = bytes(i % 251 for i in range(65539))


def test_closed_file_is_independently_rehashed(tmp_path):
    root = tmp_path / 'owned'; root.mkdir(mode=0o700)
    key = str(uuid.uuid4()); file = root / (key + '.blob')
    file.write_bytes(DATA); file.chmod(0o600)
    evidence = inspect_disk(root, key, len(DATA), hashlib.sha256(DATA).hexdigest())
    assert evidence['bytes'] == 65539 and evidence['closed_before_read']
    remove_owned(root, RootIdentity.capture(root), {file.name: evidence['identity']})
    assert not root.exists()


@pytest.mark.parametrize('bad', ['length', 'digest', 'symlink', 'hardlink'])
def test_invalid_disk_evidence_cannot_pass(tmp_path, bad):
    root = tmp_path / 'owned'; root.mkdir(mode=0o700)
    key = str(uuid.uuid4()); file = root / (key + '.blob')
    file.write_bytes(DATA); file.chmod(0o600)
    if bad == 'symlink':
        file.unlink(); file.symlink_to(tmp_path / 'absent')
    if bad == 'hardlink': (root / 'extra').hardlink_to(file)
    with pytest.raises((AssertionError, OSError)):
        inspect_disk(root, key, len(DATA) + (bad == 'length'), '0'*64 if bad == 'digest' else hashlib.sha256(DATA).hexdigest())


def test_cleanup_refuses_unrecorded_files_without_deleting(tmp_path):
    root = tmp_path / 'owned'; root.mkdir(mode=0o700)
    identity = RootIdentity.capture(root)
    sentinel = root / 'unrecorded'; sentinel.write_bytes(b'synthetic')
    with pytest.raises(AssertionError): remove_owned(root, identity, {})
    assert sentinel.read_bytes() == b'synthetic'


def test_owned_listener_stops_after_failure():
    import httpx
    from private_upload_loopback import LoopbackServer
    async def app(scope, receive, send):
        assert scope['server'][0] == '127.0.0.1'
        await send({'type':'http.response.start', 'status':200, 'headers':[]})
        await send({'type':'http.response.body', 'body':b'synthetic'})
    with pytest.raises(ValueError, match='synthetic failure'):
        with LoopbackServer(app) as server:
            with httpx.Client(trust_env=False, timeout=2) as client:
                assert client.get(server.origin).content == b'synthetic'
            raise ValueError('synthetic failure')
    assert not server.thread.is_alive() and server.socket.fileno() == -1


@pytest.mark.parametrize('query', ['host=example.invalid','hostaddr=192.0.2.1','service=foreign','options=-ctest=1'])
def test_pg_target_overrides_refused_before_connect(query):
    from private_upload_loopback import require_loopback_pg
    with pytest.raises(AssertionError):
        require_loopback_pg('postgresql://synthetic:synthetic@127.0.0.1:5432/test?'+query)


@pytest.mark.parametrize('failure', ['constructor','thread_start','startup'])
def test_partial_server_startup_closes_owned_socket(monkeypatch, failure):
    import threading
    import uvicorn
    from private_upload_loopback import LoopbackServer
    def broken(*args, **kwargs): raise RuntimeError('synthetic startup failure')
    if failure == 'constructor': monkeypatch.setattr(uvicorn, 'Server', broken)
    elif failure == 'thread_start': monkeypatch.setattr(threading.Thread, 'start', broken)
    else: monkeypatch.setattr(uvicorn.Server, 'run', broken)
    server = LoopbackServer(None)
    with pytest.raises((RuntimeError, AssertionError)): server.__enter__()
    assert server.socket.fileno() == -1
    assert server.thread is None or not server.thread.is_alive()


@pytest.mark.parametrize('busy', ['thread','connection','task','permit'])
def test_active_resources_never_mark_schema_safe(busy):
    import threading
    from types import SimpleNamespace as NS
    from private_upload_loopback import mark_quiescent
    engine = NS(loopback_cleanup_safe=False)
    state = NS(connections={1} if busy=='connection' else set(), tasks={1} if busy=='task' else set())
    server = NS(thread=NS(is_alive=lambda:busy=='thread'),server=NS(server_state=state))
    runtime = NS(permits=threading.BoundedSemaphore(1))
    if busy=='permit': runtime.permits.acquire()
    with pytest.raises(AssertionError): mark_quiescent(engine,server,runtime)
    assert engine.loopback_cleanup_safe is False


@pytest.mark.parametrize('unsafe', ['active','borrowed','none'])
def test_schema_cleanup_is_exact_and_quiescent(unsafe):
    from types import SimpleNamespace as NS
    from private_upload_loopback import cleanup_schema
    statements=[]
    class Admin:
        def begin(self): return self
        def connect(self): return self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql): statements.append(str(sql))
        def scalar(self,sql,params):
            assert params == {'name':'command_test_'+'a'*32}; return 0
    engine=NS(loopback_cleanup_safe=unsafe!='active',pool=NS(checkedout=lambda:1 if unsafe=='borrowed' else 0),dispose=lambda:None)
    if unsafe=='none':
        cleanup_schema(Admin(),engine,'command_test_'+'a'*32,True)
        assert statements == ['DROP SCHEMA "command_test_'+ 'a'*32 +'" CASCADE']
    else:
        with pytest.raises(AssertionError): cleanup_schema(Admin(),engine,'command_test_'+'a'*32,True)
        assert statements == []
