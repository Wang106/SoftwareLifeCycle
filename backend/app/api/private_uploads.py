"""Default-off private ingress. Never creates Artifact or serves file bytes."""
import threading
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.core.config import settings
from app.core.db import SessionLocal
from app.services.private_upload_http import UploadHTTP, UploadPolicy, owned_worker
from app.services.private_upload_sessions import PrivateUploadService

router = APIRouter(prefix='/api/v1/private-uploads', tags=['private upload'])
_runtime = None
_runtime_lock = threading.Lock()


def get_upload_runtime():
    if not settings.private_upload_http_enabled:
        raise HTTPException(403,'private_upload_disabled')
    try:
        policy = UploadPolicy(settings.private_upload_root, settings.private_upload_scope_id,
            settings.private_upload_max_bytes, settings.private_upload_total_seconds,
            settings.private_upload_idle_seconds, settings.private_upload_transfers)
    except (ValueError,TypeError):
        raise HTTPException(503,'private_upload_configuration_invalid') from None
    global _runtime
    with _runtime_lock:
        if _runtime is None: _runtime = UploadHTTP(policy,SessionLocal)
        # Hot configuration replacement must not reset admission or scope bindings.
        if _runtime.policy != policy: raise HTTPException(503,'private_upload_configuration_changed')
        return _runtime


def key(value):
    return PrivateUploadService._key(value)


def no_query(request):
    if request.query_params: raise HTTPException(422,'unexpected_private_upload_query')


async def safe(operation):
    try:
        return await operation()
    except HTTPException:
        raise
    except Exception:
        # Do not return filesystem paths, SQL details, original bytes or reasons.
        raise HTTPException(503,'private_upload_outcome_unavailable_use_receipt') from None


@router.get('/context')
async def context(request: Request, runtime: UploadHTTP = Depends(get_upload_runtime)):
    pairs = list(request.query_params.multi_items())
    if len(pairs) != 1 or pairs[0][0] != 'component_id':
        raise HTTPException(422,'invalid_private_upload_context_query')
    identifier = key(pairs[0][1])
    return await safe(lambda:owned_worker(lambda:runtime.call('context',request,identifier)))


@router.post('/reservations')
async def reserve(request: Request, response: Response, runtime: UploadHTTP = Depends(get_upload_runtime)):
    no_query(request)
    result, created = await safe(lambda:runtime.reserve(request))
    response.status_code = 201 if created else 200
    return result


@router.put('/{request_id}/content')
async def receive(request_id: str, request: Request, runtime: UploadHTTP = Depends(get_upload_runtime)):
    no_query(request)
    identifier = key(request_id)
    return await safe(lambda:runtime.receive(identifier,request))


@router.get('/receipts/{request_id}')
async def receipt(request_id: str, request: Request, runtime: UploadHTTP = Depends(get_upload_runtime)):
    no_query(request)
    identifier = key(request_id)
    return await safe(lambda:owned_worker(lambda:runtime.call('receipt',request,identifier)))
