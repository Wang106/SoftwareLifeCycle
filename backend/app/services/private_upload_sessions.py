"""Default-off, non-HTTP private upload coordination for trusted callers.

There is no production caller, environment switch, Artifact creation, download,
retry, takeover, cleanup or scan verdict. Tests supply synthetic finite streams.
A future HTTP adapter must enforce wall-clock deadlines/cancellation, admission,
approved policy and configuration before using this synchronous coordinator.

Each instance owns its database session and storage core exclusively. Calls are
serialized and non-reentrant; no authorization/parent locks span byte I/O. Durable
phase records precede I/O, and the same storage instance performs stage/commit.
Interrupted or unacknowledged phases are never resumed, even if bytes verify.
The operator's immutable storage_scope_id identifies one trusted local root; it
is not a path, secret or authorization. Changing that mapping is not supported.
"""
import copy
import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.models.audit import AuditEvent
from app.models.core import ReleaseComponent
from app.models.upload import PrivateUploadSession
from app.services.application_component_declaration import ApplicationComponentDeclarationService
from app.services.application_release_creation import (
    ApplicationReleaseCreationService, CreateApplicationRelease, digest, fail,
)
from app.services.audit import commit_with_audit
from app.services.local_artifact_storage import LocalArtifactStorage, Receipt


class ReservePrivateUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    component_id: uuid.UUID
    expected_bytes: int = Field(strict=True, ge=0, le=9223372036854775807)
    sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    expected_context_digest: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    reason: str = Field(strict=True, min_length=1, max_length=4000)

    @field_validator('request_id', 'component_id', mode='before')
    @classmethod
    def canonical_uuid(cls, value):
        return CreateApplicationRelease.canonical_uuid(value)

    @field_validator('reason')
    @classmethod
    def canonical_reason(cls, value, info):
        return CreateApplicationRelease.valid_unicode(
            CreateApplicationRelease.canonical_text(value), info)


TRANSITIONS = {
    'RESERVED': {'RECEIVING'},
    'RECEIVING': {'STAGED', 'RECONCILIATION_REQUIRED'},
    'STAGED': {'PUBLISHING', 'RECONCILIATION_REQUIRED'},
    'PUBLISHING': {'STORED_PRIVATE', 'RECONCILIATION_REQUIRED'},
    'STORED_PRIVATE': set(),
    'RECONCILIATION_REQUIRED': set(),
}
BINDINGS = ('component_id', 'release_id', 'project_id', 'customer_id', 'software_id',
            'standard_base_release_id', 'component_definition_id', 'base_component_id')


def timestamp(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


def exact_json(left, right):
    """JSON booleans/floats must not impersonate integer evidence fields."""
    options = dict(sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    return json.dumps(left, **options) == json.dumps(right, **options)


class PrivateUploadService:
    def __init__(self, db, *, root, storage_scope_id=None, max_bytes=None, enabled=False):
        # Constructing even an enabled service performs no database/filesystem I/O.
        self.db = db
        self.enabled = enabled
        self.storage_scope_id = storage_scope_id
        self._max_bytes = max_bytes
        self._storage = LocalArtifactStorage(root, enabled=enabled, max_bytes=max_bytes)
        self._configuration = (root, storage_scope_id, max_bytes, self._storage.chunk_bytes)
        self._busy = threading.Lock()

    def _gate(self):
        if self.enabled is not True:
            fail('private_upload_disabled', 403)
        if (type(self.storage_scope_id) is not uuid.UUID or not self.storage_scope_id.int or
                type(self._max_bytes) is not int or not 0 <= self._max_bytes <= 9223372036854775807 or
                self._storage.enabled is not True or
                (self._storage.root, self.storage_scope_id, self._storage.max_bytes,
                 self._storage.chunk_bytes) != self._configuration):
            fail('private_upload_configuration_conflict')

    @contextmanager
    def _operation(self):
        self._gate()
        if not self._busy.acquire(blocking=False):
            fail('private_upload_busy')
        try:
            yield
        finally:
            try:
                self.db.rollback()
            finally:
                self._busy.release()

    def _actor(self, request, write):
        self._gate()
        return ApplicationReleaseCreationService(self.db)._actor(request, write)

    @staticmethod
    def _key(value):
        try:
            return uuid.UUID(str(CreateApplicationRelease.canonical_uuid(value)))
        except (TypeError, ValueError, AttributeError):
            fail('invalid_private_upload_id', 422)

    def _component(self, key, actor, *, fresh):
        component = self.db.get(ReleaseComponent, key, populate_existing=True)
        if component is None:
            fail('private_upload_component_not_found', 404)
        event = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-ASRC-' + key.hex))
        if event is None:
            fail('private_upload_private_component_required')
        declaration = ApplicationComponentDeclarationService(self.db)
        declaration._evidence(event, key, actor, bound_actor=False)
        context = declaration._context(component.release_id, component.component_definition_id,
                                       component.base_component_id, actor, fresh=fresh)
        return {**context, 'component_id': str(key), 'component_version': component.version,
                'delta_type': component.delta_type, 'storage_scope_id': str(self.storage_scope_id),
                'admission_max_bytes': self._max_bytes}

    def context(self, component_id, request):
        with self._operation():
            actor = self._actor(request, False)
            context = self._component(self._key(component_id), actor, fresh=True)
            return {'version': 1, 'context': context, 'context_digest': digest(context)}

    @staticmethod
    def _event_no(key, revision):
        return 'EVT-UP-' + key.hex + '-' + str(revision)

    @staticmethod
    def _reservation(command, object_id, actor_id, scope_id, created_at):
        return {'version': 1, 'request_id': command['request_id'], 'component_id': command['component_id'],
                'object_id': str(object_id), 'storage_scope_id': str(scope_id),
                'expected_bytes': command['expected_bytes'], 'sha256': command['sha256'],
                'actor_principal_id': str(actor_id), 'state': 'RESERVED', 'created_at': created_at}

    @staticmethod
    def _stored(reservation, stored_at):
        return {**reservation, 'state': 'STORED_PRIVATE', 'revision': 4, 'stored_at': stored_at}

    @staticmethod
    def _payload(row, previous):
        return {'version': 1, 'request': row.request_json, 'context': row.context_json,
                'reservation': row.reservation_receipt_json, 'from_state': previous,
                'to_state': row.state, 'revision': row.revision,
                'stored_receipt': row.stored_receipt_json, 'actor_source': 'AUTHENTICATED_PRINCIPAL'}

    def _record(self, row, actor, previous):
        commit_with_audit(self.db, lambda: dict(
            event_no=self._event_no(row.id, row.revision), event_type='PRIVATE_UPLOAD_SESSION',
            action=row.state, entity_type='PRIVATE_UPLOAD_SESSION', entity_id=row.id, entity_ref=str(row.id),
            actor_name=actor.display_name[:120], actor_principal_id=actor.id,
            actor_display_name=actor.display_name, declared_actor_name=None,
            summary='Private upload session recorded', detail=row.request_json['reason'],
            occurred_at=row.updated_at, payload=copy.deepcopy(self._payload(row, previous))))

    def _validate(self, row):
        """An observation never invents a receipt from current mutable state."""
        try:
            command = ReservePrivateUpload.model_validate(row.request_json).model_dump(mode='json')
            if (not exact_json(command, row.request_json) or command['request_id'] != str(row.id) or
                    command['component_id'] != str(row.release_component_id) or
                    type(row.expected_bytes) is not int or command['expected_bytes'] != row.expected_bytes or
                    command['sha256'] != row.sha256 or row.object_id.version != 4 or
                    not isinstance(row.context_json, dict) or digest(row.context_json) != command['expected_context_digest'] or
                    row.context_json['component_id'] != command['component_id'] or
                    row.context_json['storage_scope_id'] != str(row.storage_scope_id) or
                    type(row.revision) is not int or not 0 <= row.revision <= 4 or row.state not in TRANSITIONS):
                fail('private_upload_evidence_conflict')
            reservation = self._reservation(command, row.object_id, row.actor_principal_id,
                                            row.storage_scope_id, row.reservation_receipt_json['created_at'])
            created = datetime.fromisoformat(reservation['created_at'])
            if (created.tzinfo is None or created != timestamp(row.created_at) or
                    not exact_json(reservation, row.reservation_receipt_json)):
                fail('private_upload_evidence_conflict')
            events = list(self.db.scalars(select(AuditEvent).where(AuditEvent.entity_id == row.id,
                or_(AuditEvent.event_type == 'PRIVATE_UPLOAD_SESSION', AuditEvent.event_no.like('EVT-UP-%')))))
            by_number = {event.event_no: event for event in events}
            if len(events) != row.revision + 1 or len(by_number) != len(events):
                fail('private_upload_evidence_conflict')
            previous, previous_time = None, created
            for revision in range(row.revision + 1):
                event = by_number[self._event_no(row.id, revision)]
                payload = event.payload_json
                state = payload['to_state']
                occurred = timestamp(event.occurred_at)
                stored = self._stored(reservation, occurred.isoformat()) if state == 'STORED_PRIVATE' else None
                if (event.event_type != 'PRIVATE_UPLOAD_SESSION' or event.entity_type != 'PRIVATE_UPLOAD_SESSION' or
                        event.entity_ref != str(row.id) or event.actor_principal_id != row.actor_principal_id or
                        event.declared_actor_name is not None or event.action != state or event.detail != command['reason'] or
                        state not in (TRANSITIONS[previous] if previous else {'RESERVED'}) or
                        occurred < previous_time or (revision == 0 and occurred != created) or
                        not exact_json(payload, {'version': 1, 'request': command, 'context': row.context_json,
                            'reservation': reservation, 'from_state': previous, 'to_state': state, 'revision': revision,
                            'stored_receipt': stored, 'actor_source': 'AUTHENTICATED_PRINCIPAL'})):
                    fail('private_upload_evidence_conflict')
                previous, previous_time = state, occurred
            if (previous != row.state or previous_time != timestamp(row.updated_at) or
                    not exact_json(row.stored_receipt_json, (self._stored(reservation, previous_time.isoformat())
                                                if row.state == 'STORED_PRIVATE' else None))):
                fail('private_upload_evidence_conflict')
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
            fail('private_upload_evidence_conflict')
        return command

    def _session(self, key, actor, *, fresh):
        candidate = self.db.get(PrivateUploadSession, key, populate_existing=True)
        if candidate is None:
            fail('private_upload_receipt_not_found', 404)
        if candidate.actor_principal_id != actor.id or candidate.storage_scope_id != self.storage_scope_id:
            fail('private_upload_binding_conflict')
        context = self._component(candidate.release_component_id, actor, fresh=fresh)
        row = self.db.scalar(select(PrivateUploadSession).where(PrivateUploadSession.id == key)
                             .with_for_update().execution_options(populate_existing=True))
        if row is None or row.actor_principal_id != actor.id or row.storage_scope_id != self.storage_scope_id:
            fail('private_upload_binding_conflict')
        self._validate(row)
        if any(context.get(name) != row.context_json.get(name) for name in BINDINGS):
            fail('private_upload_binding_conflict')
        if fresh and not exact_json(context, row.context_json):
            fail('private_upload_context_conflict')
        return row

    def reserve(self, *, request, **values):
        with self._operation():
            try:
                try:
                    command = ReservePrivateUpload.model_validate(values).model_dump(mode='json')
                except ValidationError:
                    fail('invalid_private_upload_request', 422)
                actor = self._actor(request, True)
                key, component_id = uuid.UUID(command['request_id']), uuid.UUID(command['component_id'])
                existing = self.db.get(PrivateUploadSession, key, populate_existing=True)
                if existing is not None:
                    row = self._session(key, actor, fresh=False)
                    if not exact_json(row.request_json, command):
                        fail('private_upload_request_conflict')
                    return copy.deepcopy(row.reservation_receipt_json), False
                context = self._component(component_id, actor, fresh=True)
                # A concurrent identical request may have committed while waiting
                # for the common principal/parent locks. Do not reserve a new ID.
                if self.db.get(PrivateUploadSession, key, populate_existing=True) is not None:
                    row = self._session(key, actor, fresh=False)
                    if not exact_json(row.request_json, command):
                        fail('private_upload_request_conflict')
                    return copy.deepcopy(row.reservation_receipt_json), False
                if digest(context) != command['expected_context_digest']:
                    fail('private_upload_context_conflict')
                if command['expected_bytes'] > self._max_bytes:
                    fail('invalid_private_upload_request', 422)
                descriptor = self._storage.reserve(expected_bytes=command['expected_bytes'], sha256=command['sha256'])
                now = datetime.now(timezone.utc)
                receipt = self._reservation(command, descriptor.object_id, actor.id, self.storage_scope_id, now.isoformat())
                row = PrivateUploadSession(id=key, object_id=uuid.UUID(descriptor.object_id), actor_principal_id=actor.id,
                    storage_scope_id=self.storage_scope_id, release_component_id=component_id,
                    expected_bytes=command['expected_bytes'], sha256=command['sha256'], state='RESERVED', revision=0,
                    request_json=command, context_json=context, reservation_receipt_json=receipt,
                    stored_receipt_json=None, created_at=now, updated_at=now)
                self.db.add(row)
                self._record(row, actor, None)
                return copy.deepcopy(receipt), True
            except IntegrityError:
                fail('private_upload_request_conflict')

    @staticmethod
    def _status(row):
        return {'version': 1, 'state': row.state, 'revision': row.revision,
                'reservation': copy.deepcopy(row.reservation_receipt_json),
                'stored_receipt': copy.deepcopy(row.stored_receipt_json)}

    @staticmethod
    def _descriptor(row):
        return Receipt(str(row.object_id), row.expected_bytes, row.sha256)

    def receipt(self, request_id, request):
        with self._operation():
            actor = self._actor(request, False)
            return self._status(self._session(self._key(request_id), actor, fresh=False))

    def _transition(self, key, request, expected, state, *, fresh=True):
        actor = self._actor(request, True)
        row = self._session(key, actor, fresh=fresh)
        if row.state != expected or state not in TRANSITIONS[expected]:
            fail('private_upload_attempt_consumed')
        descriptor = self._descriptor(row)
        # Check current bounds before consuming a RESERVED attempt or touching disk.
        self._storage._receipt(descriptor)
        row.state, row.revision = state, row.revision + 1
        row.updated_at = datetime.now(timezone.utc)
        if state == 'STORED_PRIVATE':
            row.stored_receipt_json = self._stored(row.reservation_receipt_json, row.updated_at.isoformat())
        result = copy.deepcopy(row.stored_receipt_json)
        self._record(row, actor, expected)
        return descriptor, result

    def _uncertain(self, key, request):
        # Best-effort *metadata only*, never retry a storage action. A lost final
        # DB acknowledgement may already have committed STORED_PRIVATE; preserve
        # that immutable success instead of downgrading it. Failure to record this
        # marker leaves the last durable in-progress phase for read-only recovery.
        self.db.rollback()
        try:
            actor = self._actor(request, True)
            row = self._session(key, actor, fresh=False)
            previous = row.state
            if previous in ('RECEIVING', 'STAGED', 'PUBLISHING'):
                row.state, row.revision = 'RECONCILIATION_REQUIRED', row.revision + 1
                row.updated_at = datetime.now(timezone.utc)
                self._record(row, actor, previous)
        except Exception:
            self.db.rollback()
        finally:
            self.db.rollback()

    def receive(self, request_id, source, request):
        with self._operation():
            key = self._key(request_id)
            descriptor, _ = self._transition(key, request, 'RESERVED', 'RECEIVING')
            try:
                self._gate()
                self._storage.stage(descriptor, source)
                self._transition(key, request, 'RECEIVING', 'STAGED')
                self._transition(key, request, 'STAGED', 'PUBLISHING')
                self._gate()
                self._storage.commit(descriptor)
                _, result = self._transition(key, request, 'PUBLISHING', 'STORED_PRIVATE')
                return result
            except Exception:
                self._uncertain(key, request)
                raise

    def inspect(self, request_id, request):
        with self._operation():
            key = self._key(request_id)
            actor = self._actor(request, False)
            row = self._session(key, actor, fresh=False)
            descriptor, revision = self._descriptor(row), row.revision
            self.db.rollback()
            self._gate()
            observation = self._storage.inspect(descriptor)
            observed_at = datetime.now(timezone.utc).isoformat()
            # Authorization may have changed during filesystem reads. The byte
            # observation and latest database state are explicitly independent.
            actor = self._actor(request, False)
            status = self._status(self._session(key, actor, fresh=False))
            return {'version': 1, 'status': status, 'bytes': observation,
                    'observed_for_revision': revision, 'observed_at': observed_at}
