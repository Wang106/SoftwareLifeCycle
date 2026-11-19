"""Synthetic ASGI streams; no network service, real files or database required."""
import asyncio
import hashlib
import threading
import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

DATA = b'synthetic finite content'
KEY = str(uuid.uuid4())


def runtime(**options):
    from app.services.private_upload_http import UploadHTTP, UploadPolicy
    class Fake(UploadHTTP):
        def call(self, operation, request, key=None, values=None, data=None):
            self.calls.append(operation)
            if operation == 'prepare':
                return {'expected_bytes': len(DATA), 'sha256': hashlib.sha256(DATA).hexdigest()}
            assert operation == 'receive' and data == DATA
            return {'state': 'STORED_PRIVATE', 'request_id': key}
    value = Fake(UploadPolicy('/synthetic/not/accessed', uuid.uuid4(), 1024, .12, .04, 1), None)
    value.calls = []
    return value


def req(events, headers=None):
    count = []
    async def receive():
        count.append(True)
        event = events.pop(0)
        if isinstance(event, tuple):
            delay, event = event
            await asyncio.sleep(delay)
        return event
    request = Request({'type':'http', 'method':'PUT', 'path':'/', 'headers': headers or [
        (b'content-type', b'application/octet-stream'), (b'content-length', str(len(DATA)).encode())]}, receive)
    return request, count


def body(data=DATA, more=False):
    return {'type':'http.request', 'body':data, 'more_body':more}


def test_finite_receive_exact_once_and_releases_permit():
    async def run():
        value = runtime()
        request, count = req([body()])
        result = await value.receive(KEY, request)
        assert result['state'] == 'STORED_PRIVATE' and len(count) == 1
        assert value.calls == ['prepare', 'receive']
        assert value.permits.acquire(False)
        value.permits.release()
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['stalled', 'slow', 'disconnect', 'length', 'digest', 'oversize'])
def test_incomplete_or_invalid_body_never_enters_storage(kind):
    async def run():
        value = runtime()
        events = {'stalled':[(10,body())],
            'slow':[(.025,body(b'x',True)) for _ in range(20)],
            'disconnect':[{'type':'http.disconnect'}],
            'length':[body(DATA[:-1])], 'digest':[body(b'x'*len(DATA))],
            'oversize':[body(DATA+b'x')]}[kind]
        request, _ = req(events)
        with pytest.raises(HTTPException) as error:
            await value.receive(KEY, request)
        assert error.value.status_code == (408 if kind in {'stalled','slow'} else 400 if kind == 'disconnect' else 422)
        assert value.calls == ['prepare']
        assert value.permits.acquire(False)
        value.permits.release()
    asyncio.run(run())


@pytest.mark.parametrize('headers', [[], [(b'content-type',b'multipart/form-data')],
    [(b'content-type',b'application/octet-stream'),(b'content-length',b'023')],
    [(b'content-type',b'application/octet-stream'),(b'content-length',b'1'),(b'content-length',b'2')],
    [(b'content-type',b'application/octet-stream'),(b'content-length',str(len(DATA)).encode()),(b'content-encoding',b'gzip')]])
def test_bad_headers_do_not_read_body(headers):
    async def run():
        value = runtime(); request, reads = req([body()])
        request.scope['headers'] = headers
        with pytest.raises(HTTPException): await value.receive(KEY, request)
        assert reads == [] and 'receive' not in value.calls
    asyncio.run(run())


def test_authority_refusal_does_not_read_body():
    async def run():
        value = runtime(); request, reads = req([body()])
        def denied(*args, **kwargs): raise HTTPException(403,'synthetic_denial')
        value.call = denied
        with pytest.raises(HTTPException): await value.receive(KEY, request)
        assert reads == [] and value.permits.acquire(False)
        value.permits.release()
    asyncio.run(run())


def test_busy_refuses_without_read_or_wait():
    async def run():
        value = runtime(); value.permits.acquire()
        request, reads = req([body()])
        try:
            with pytest.raises(HTTPException) as error: await value.receive(KEY, request)
            assert error.value.status_code == 429 and reads == [] and value.calls == []
        finally: value.permits.release()
    asyncio.run(run())


def test_cancelled_storage_keeps_permit_until_actual_worker_completion():
    async def run():
        value = runtime(); started, finish = threading.Event(), threading.Event()
        original = value.call
        def blocked(operation, *args, **kwargs):
            if operation == 'receive':
                started.set()
                assert finish.wait(2)
            return original(operation, *args, **kwargs)
        value.call = blocked
        request, _ = req([body()]); task = asyncio.create_task(value.receive(KEY,request))
        try:
            for _ in range(200):
                if started.is_set(): break
                await asyncio.sleep(.001)
            assert started.is_set()
            task.cancel(); await asyncio.sleep(.01)
            assert not task.done() and not value.permits.acquire(False)
            task.cancel(); await asyncio.sleep(.01)
            assert not task.done() and not value.permits.acquire(False)
        finally: finish.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert value.calls == ['prepare','receive'] and value.permits.acquire(False)
        value.permits.release()
    asyncio.run(run())


def test_cancelled_ingress_releases_permit_without_storage():
    async def run():
        value = runtime(); request, reads = req([(10,body())])
        task = asyncio.create_task(value.receive(KEY,request))
        for _ in range(100):
            if reads: break
            await asyncio.sleep(.001)
        assert reads
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert value.calls == ['prepare'] and value.permits.acquire(False)
        value.permits.release()
    asyncio.run(run())


@pytest.mark.parametrize('operation,broken',[('prepare',False),('prepare',True),('receive',True)])
def test_cancelled_worker_ownership_also_covers_prepare_and_failure(operation,broken):
    async def run():
        value=runtime(); started,finish=threading.Event(),threading.Event(); original=value.call
        def blocked(name,*args,**kwargs):
            if name==operation:
                started.set(); assert finish.wait(2)
                if broken: raise OSError('synthetic private error')
            return original(name,*args,**kwargs)
        value.call=blocked; request,reads=req([body()])
        task=asyncio.create_task(value.receive(KEY,request))
        try:
            for _ in range(200):
                if started.is_set(): break
                await asyncio.sleep(.001)
            assert started.is_set(); task.cancel(); await asyncio.sleep(.01)
            assert not task.done() and not value.permits.acquire(False)
            if operation=='prepare': assert reads==[]
        finally: finish.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert value.permits.acquire(False); value.permits.release()
    asyncio.run(run())


def test_empty_messages_do_not_renew_byte_progress_idle_deadline():
    async def run():
        value=runtime()
        request,_=req([(.015,body(b'',True)) for _ in range(5)]+[body()])
        with pytest.raises(HTTPException) as error:
            await value.receive(KEY,request)
        assert error.value.status_code==408
        assert value.calls==['prepare']
        assert value.permits.acquire(False)
        value.permits.release()
    asyncio.run(run())


def test_late_receive_completion_cannot_renew_elapsed_idle_deadline():
    import time
    async def run():
        value=runtime(); request,_=req([])
        async def late():
            time.sleep(.06)  # Synthetic delayed scheduling, below total but beyond idle.
            return body()
        request._receive=late
        with pytest.raises(HTTPException) as error: await value.receive(KEY,request)
        assert error.value.status_code==408 and value.calls==['prepare']
        assert value.permits.acquire(False);value.permits.release()
    asyncio.run(run())
