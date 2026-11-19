"""Finite HTTP ingress over the existing private upload coordinator.

No filesystem I/O occurs while waiting for network bytes. Every synchronous
operation owns and closes its Session in one worker. Cancellation waits for that
worker: it cannot stop disk/DB I/O and must not release admission early.
"""
import asyncio
import hashlib
import io
import json
import math
import threading
import time
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import ValidationError
from app.services.private_upload_sessions import PrivateUploadService, ReservePrivateUpload


def refuse(code, status=422):
    raise HTTPException(status, code)


@dataclass(frozen=True)
class UploadPolicy:
    root: str
    scope: uuid.UUID
    max_bytes: int
    total_seconds: float
    idle_seconds: float
    transfers: int

    def __post_init__(self):
        from app.core.config import validate_upload_policy
        validate_upload_policy(self.root,self.scope,self.max_bytes,self.total_seconds,
                               self.idle_seconds,self.transfers)


async def owned_worker(function):
    """Keep ownership until the worker finishes, including repeated cancellation."""
    task = asyncio.create_task(asyncio.to_thread(function))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # Observe, never publish an exception containing paths.
        raise


def length_header(request, media):
    headers = request.headers
    lengths = headers.getlist('content-length')
    if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal()
            or len(lengths[0]) > 10 or str(int(lengths[0])) != lengths[0]
            or headers.getlist('content-type') != [media]
            or headers.getlist('content-encoding') or headers.getlist('transfer-encoding')
            or headers.getlist('content-range')):
        refuse('invalid_private_upload_headers')
    return int(lengths[0])


class UploadHTTP:
    def __init__(self, policy, sessions):
        self.policy = policy
        self.sessions = sessions
        self.permits = threading.BoundedSemaphore(policy.transfers)

    @staticmethod
    def token_current(request):
        expiry = getattr(request.state, 'token_expires', None)
        if type(expiry) not in (int,float) or not math.isfinite(expiry) or expiry <= time.time():
            refuse('expired_private_upload_token',401)

    def call(self, operation, request, key=None, values=None, data=None):
        self.token_current(request)
        with self.sessions() as db:
            svc = PrivateUploadService(db, root=self.policy.root, storage_scope_id=self.policy.scope,
                                       max_bytes=self.policy.max_bytes, enabled=True)
            if operation == 'context': return svc.context(key,request)
            if operation == 'reserve': return svc.reserve(request=request,**values)
            if operation == 'receipt': return svc.receipt(key,request)
            if operation == 'receive':
                with io.BytesIO(data) as source:
                    return svc.receive(key,source,request)
            if operation == 'authorize':
                with svc._operation(): svc._actor(request,True)
                return None
            if operation == 'prepare':
                # Reuse coordinator evidence, exact binding and fresh authorization;
                # no new grant policy and no durable transition during preflight.
                with svc._operation():
                    actor = svc._actor(request,True)
                    row = svc._session(svc._key(key),actor,fresh=True)
                    if row.state != 'RESERVED': refuse('private_upload_attempt_consumed',409)
                    svc._storage._receipt(svc._descriptor(row))
                    return {'expected_bytes':row.expected_bytes,'sha256':row.sha256}
            raise RuntimeError('unknown upload operation')

    async def _read(self, request, size):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.policy.total_seconds
        idle_deadline = loop.time() + self.policy.idle_seconds
        result = bytearray()
        while True:
            left = min(deadline, idle_deadline) - loop.time()
            if left <= 0: refuse('private_upload_receive_timeout',408)
            try:
                message = await asyncio.wait_for(request.receive(), min(left,self.policy.idle_seconds))
            except TimeoutError:
                refuse('private_upload_receive_timeout',408)
            if loop.time() >= min(deadline,idle_deadline): refuse('private_upload_receive_timeout',408)
            if message['type'] == 'http.disconnect': refuse('private_upload_disconnected',400)
            if message['type'] != 'http.request': refuse('invalid_private_upload_body')
            chunk = message.get('body',b'')
            if type(chunk) is not bytes or len(chunk) > size-len(result):
                refuse('private_upload_length_mismatch')
            result.extend(chunk)
            if chunk: idle_deadline = loop.time() + self.policy.idle_seconds
            if not message.get('more_body',False): break
        if len(result) != size: refuse('private_upload_length_mismatch')
        return bytes(result)

    async def receive(self, key, request):
        if not self.permits.acquire(False): refuse('private_upload_busy',429)
        try:
            size = length_header(request,'application/octet-stream')
            if size > self.policy.max_bytes: refuse('private_upload_length_mismatch')
            expected = await owned_worker(lambda:self.call('prepare',request,key))
            if size != expected['expected_bytes']: refuse('private_upload_length_mismatch')
            data = await self._read(request,size)
            if hashlib.sha256(data).hexdigest() != expected['sha256']:
                refuse('private_upload_digest_mismatch')
            return await owned_worker(lambda:self.call('receive',request,key,data=data))
        finally:
            self.permits.release()

    async def reserve(self, request):
        if not self.permits.acquire(False): refuse('private_upload_busy',429)
        try:
            size = length_header(request,'application/json')
            if not 1 <= size <= 65536: refuse('invalid_private_upload_request')
            await owned_worker(lambda:self.call('authorize',request))
            raw = await self._read(request,size)
            try:
                def unique(pairs):
                    value = dict(pairs)
                    if len(value) != len(pairs): raise ValueError('duplicate')
                    return value
                value = json.loads(raw,object_pairs_hook=unique)
                values = ReservePrivateUpload.model_validate(value).model_dump()
            except (ValueError,TypeError,ValidationError,RecursionError):
                refuse('invalid_private_upload_request')
            return await owned_worker(lambda:self.call('reserve',request,values=values))
        finally:
            self.permits.release()
