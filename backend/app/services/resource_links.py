"""Validate references without fetching URLs, opening files or granting distribution rights."""
import re
import uuid
import hashlib
import json
from typing import Literal
from urllib.parse import quote, urlsplit, unquote
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.core import Supplier, Customer, Project, Release
from app.models.change import SoftwareChangeRequest, Issue
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpItem, TestRelease, DvpExecution
from app.models.resource import ResourceLink
from app.models.audit import AuditEvent
from app.actor import ActorContext, idempotent_actor_matches
from app.services.audit import AuditEventService

EntityType = Literal['SUPPLIER','CUSTOMER','PROJECT','RELEASE','SNAPSHOT','SCR','ISSUE','DVP_ITEM','TEST_RELEASE','DVP_EXECUTION']
LocationKind = Literal['WEB_URL','LOCAL_PATH','NETWORK_PATH']
TARGETS = {
    'SUPPLIER': (Supplier, 'code', '/suppliers/'), 'CUSTOMER': (Customer, 'code', '/customers/'),
    'PROJECT': (Project, 'project_code', '/projects/'), 'RELEASE': (Release, 'version', None),
    'SNAPSHOT': (ReleaseSnapshot, 'snapshot_no', '/snapshots/'), 'SCR': (SoftwareChangeRequest, 'request_no', '/changes/'),
    'ISSUE': (Issue, 'issue_no', '/issues/'), 'DVP_ITEM': (DvpItem, 'item_no', '/testing/dvp/'),
    'TEST_RELEASE': (TestRelease, 'test_release_no', '/testing/releases/'),
    'DVP_EXECUTION': (DvpExecution, 'execution_no', '/testing/dvp/')}

# Versioned, ordered normalized request digest. Keep resource locations/descriptions
# out of general activity history while allowing exact own-operation recovery.
REQUEST_DIGEST_FIELDS = ('request_id','entity_type','entity_id','title','location_kind',
                         'location','description','actor_name','reason')


def request_digest(data):
    values = data.model_dump(mode='json')
    encoded = json.dumps([values[k] for k in REQUEST_DIGEST_FIELDS],
                         ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class ResourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    entity_type: EntityType
    entity_id: uuid.UUID
    title: str = Field(min_length=1, max_length=240)
    location_kind: LocationKind
    location: str = Field(min_length=1, max_length=4000)
    description: str = Field(default='', max_length=4000)
    actor_name: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('title','location','description','actor_name','reason')
    @classmethod
    def clean_text(cls, value, info):
        value = value.strip()
        if not value and info.field_name != 'description': raise ValueError('blank value')
        if any(ord(c) < 32 or ord(c) == 127 for c in value): raise ValueError('control characters are not allowed')
        return value

    @model_validator(mode='after')
    def validate_location(self):
        value = self.location
        if self.location_kind == 'WEB_URL':
            if any(c.isspace() for c in value) or '\\' in value: raise ValueError('invalid web URL')
            parsed = urlsplit(value)
            if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
                raise ValueError('use an HTTP(S) URL without embedded credentials')
            # Validate port and reject encoded controls that can alter link handling.
            parsed.port
            if any(ord(c) < 32 or ord(c) == 127 for c in unquote(value)): raise ValueError('encoded control characters')
        elif self.location_kind == 'LOCAL_PATH':
            if not (value.startswith('/') and not value.startswith('//') or re.match(r'^[A-Za-z]:[\\/]',value)):
                raise ValueError('local path must be absolute POSIX or Windows drive path')
        else:
            if not re.match(r'^(?:\\\\|//)[^\\/]+[\\/][^\\/]+',value):
                raise ValueError('network path must contain a server and share')
        return self


class ResourceError(ValueError):
    def __init__(self, status_code, message):
        super().__init__(message); self.status_code = status_code


def register_link(
    db: Session,
    data: ResourceInput,
    actor_context: ActorContext | None = None,
):
    resolved_actor = actor_context or ActorContext.legacy(data.actor_name)
    fields = data.model_dump(exclude={'request_id', 'actor_name'})
    fields['actor_name'] = resolved_actor.name
    existing = db.get(ResourceLink, data.request_id)
    if existing:
        event = db.scalars(select(AuditEvent).where(
            AuditEvent.event_no == f'EVT-LK-{data.request_id}'
        )).first()
        if (any(getattr(existing,key) != value for key,value in fields.items())
            or not idempotent_actor_matches(event, resolved_actor)):
            raise ResourceError(409,'request ID already used with different content')
        return existing, False
    model, ref_attr, prefix = TARGETS[data.entity_type]
    target = db.scalars(select(model).where(model.id == data.entity_id).with_for_update()).first()
    if not target: raise ResourceError(404,'resource target not found')
    ref = str(getattr(target,ref_attr))
    if data.entity_type == 'RELEASE':
        href = f'/releases/{"application" if target.release_type == "APPLICATION" else "standard"}/{target.id}'
    elif data.entity_type == 'DVP_EXECUTION':
        href = f'/testing/dvp/{target.dvp_item_id}'; ref = f'Execution #{target.execution_no} ({target.id})'
    else:
        value = target.id if data.entity_type in {'PROJECT','DVP_ITEM'} else ref
        href = prefix + quote(str(value),safe='')
    row = ResourceLink(id=data.request_id, entity_ref=ref, entity_href=href, **fields)
    db.add(row); db.flush()
    AuditEventService(db).record(event_no=f'EVT-LK-{row.id}',event_type='RESOURCE_LINK',action='REGISTER',
        entity_type='RESOURCE_LINK',entity_id=row.id,entity_ref=str(row.id),
        **resolved_actor.audit_fields(),
        summary=f'Registered resource: {row.title}'[:240],detail=row.reason,
        payload={'target_type':row.entity_type,'target_id':str(row.entity_id),
            'target_ref':row.entity_ref,'location_kind':row.location_kind,
            'request_digest_version':1,'request_sha256':request_digest(data),
            'actor_source':resolved_actor.source})
    return row, True
