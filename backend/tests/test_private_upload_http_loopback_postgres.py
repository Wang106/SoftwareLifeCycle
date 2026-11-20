"""Real loopback HTTP + migrated disposable PG + Linux files, not browser/OIDC/TLS."""
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.core import Artifact
from app.models.security import BrowserSession, ProjectMembership
from app.models.upload import PrivateUploadSession
from app.services.local_artifact_storage import LocalArtifactStorage
from app.services.private_upload_http import UploadHTTP, UploadPolicy
from private_upload_loopback import LoopbackServer, RootIdentity, inspect_disk, remove_owned, require_loopback_pg, mark_quiescent, cleanup_schema
from test_application_component_declaration_postgres import component_pg
from test_private_upload_sessions_postgres import upload_pg
from test_private_upload_sessions import SCOPE
from test_application_release_creation import ISSUER
from test_auth import AUDIENCE, signed_token

DATA = bytes(i % 251 for i in range(65539))
DIGEST = hashlib.sha256(DATA).hexdigest()
BASE = '/api/v1/private-uploads'


@pytest.fixture
def pg(monkeypatch):
    value = os.environ.get('TEST_POSTGRES_URL')
    if not value:
        pytest.skip('TEST_POSTGRES_URL required for real PostgreSQL lock tests')
    parsed = require_loopback_pg(value).set(drivername='postgresql+psycopg')
    schema = 'command_test_' + uuid.uuid4().hex
    assert re.fullmatch(r'command_test_[0-9a-f]{32}', schema)
    admin = create_engine(parsed)
    engine = None; created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        scoped = parsed.update_query_dict({'options':f'-csearch_path={schema} -cstatement_timeout=10000'})
        engine = create_engine(scoped, pool_size=5)
        engine.loopback_cleanup_safe = True
        monkeypatch.setattr(settings, 'database_url', scoped.render_as_string(hide_password=False))
        command.upgrade(Config('alembic.ini'), 'head')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == settings.required_db_revision
            assert connection.scalar(text('SELECT current_schema()')) == schema
        yield engine, {}
    finally:
        try:
            cleanup_schema(admin, engine, schema, created)
        finally: admin.dispose()


@pytest.fixture
def real_http(upload_pg, monkeypatch):
    from app import auth, main
    from app.api.private_uploads import get_upload_runtime
    from app.core.db import get_db
    engine, ids, root = upload_pg
    root_id = RootIdentity.capture(root)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = signed_token(key, iss=ISSUER, sub='creator')
    sid = uuid.uuid4(); now = datetime.now(timezone.utc)
    with sessions() as db:
        db.add(BrowserSession(id=sid, principal_id=ids['actor'], token_digest=hashlib.sha256(token.encode()).hexdigest(), created_at=now, expires_at=now+timedelta(minutes=5)))
        db.commit()
    monkeypatch.setattr(auth, 'jwks_client', lambda *_:SimpleNamespace(get_signing_key_from_jwt=lambda _:SimpleNamespace(key=key.public_key())))
    monkeypatch.setattr(auth, 'SessionLocal', sessions)
    for name, value in {'oidc_audience':AUDIENCE, 'oidc_jwks_url':ISSUER+'/keys', 'oidc_leeway_seconds':0, 'private_upload_http_enabled':True}.items():
        monkeypatch.setattr(settings, name, value)
    runtime = UploadHTTP(UploadPolicy(str(root), SCOPE, 65539, 3, 1, 1), sessions)
    previous = dict(main.app.dependency_overrides)
    def route_db():
        with sessions() as db: yield db
    witness = server = None
    engine.loopback_cleanup_safe = False
    try:
        main.app.dependency_overrides[get_db] = route_db
        main.app.dependency_overrides[get_upload_runtime] = lambda:runtime
        witness = Witness(main.app, engine, ids, root)
        original_commit = LocalArtifactStorage.commit
        def commit(storage, receipt):
            result = original_commit(storage, receipt)
            witness.commits += 1
            return result
        monkeypatch.setattr(LocalArtifactStorage, 'commit', commit)
        server = LoopbackServer(witness)
        with server:
            yield server, witness, {'Authorization':'Bearer '+token,'X-Browser-Session':str(sid)}
        assert not witness.errors, 'response witness failed'
    finally:
        main.app.dependency_overrides.clear(); main.app.dependency_overrides.update(previous)
        mark_quiescent(engine, server, runtime)
        remove_owned(root, root_id, witness.files if witness is not None else {})


class Witness:
    def __init__(self, app, engine, ids, root):
        self.app, self.engine, self.ids, self.root = app, engine, ids, root
        self.counts = {'reserve':0,'put':0,'receipt':0}
        with Session(engine) as db:
            self.artifacts_before = db.scalar(select(func.count()).select_from(Artifact))
        self.commits = 0; self.files = {}; self.errors = []; self.lost = False
        self.drop = False; self.request_id = None; self.evidence = None

    def inspect(self):
        with Session(self.engine) as db:
            row = db.get(PrivateUploadSession, self.request_id)
            assert row and row.release_component_id == self.ids['component']
            assert row.actor_principal_id == self.ids['actor'] and row.state == 'STORED_PRIVATE'
            assert row.revision == 4 and row.expected_bytes == 65539 and row.sha256 == DIGEST
            assert row.stored_receipt_json['request_id'] == str(self.request_id)
            assert row.stored_receipt_json['component_id'] == str(self.ids['component'])
            events = db.scalars(select(AuditEvent).where(AuditEvent.event_type == 'PRIVATE_UPLOAD_SESSION')).all()
            assert len(events) == 5
            assert {e.event_no for e in events} == {f'EVT-UP-{self.request_id.hex}-{i}' for i in range(5)}
            assert db.scalar(select(func.count()).select_from(Artifact)) == self.artifacts_before
            object_id = str(row.object_id)
        result = inspect_disk(self.root, object_id, 65539, DIGEST)
        assert set(p.name for p in self.root.iterdir()) == {object_id+'.part', object_id+'.blob'}
        self.files.update({object_id+suffix:result['identity'] for suffix in ('.part','.blob')})
        return result

    async def __call__(self, scope, receive, send):
        assert scope['type'] == 'http' and scope['server'][0] == '127.0.0.1'
        path, method = scope['path'], scope['method']
        assert path.startswith(BASE+'/')
        if path == BASE+'/reservations' and method == 'POST': self.counts['reserve'] += 1
        if path.endswith('/content') and method == 'PUT': self.counts['put'] += 1
        if path.startswith(BASE+'/receipts/') and method == 'GET': self.counts['receipt'] += 1
        if not (method == 'PUT' and self.drop):
            return await self.app(scope, receive, send)
        messages = []
        async def capture(message): messages.append(message)
        try:
            await self.app(scope, receive, capture)
            assert messages[0]['type'] == 'http.response.start' and messages[0]['status'] == 200
            body = b''.join(m.get('body', b'') for m in messages[1:])
            receipt = json.loads(body)
            assert receipt['state'] == 'STORED_PRIVATE' and receipt['request_id'] == str(self.request_id)
            self.evidence = self.inspect()  # Independent DB connection and disk read AFTER app completion.
            assert self.commits == 1
            self.lost = True
            await send(messages[0])
            # Intentionally incomplete HTTP body, not a substitute success response.
            # Uvicorn closes it; httpx must report RemoteProtocolError.
            await send({'type':'http.response.body','body':b'', 'more_body':True})
        except BaseException as error:
            self.errors.append(type(error).__name__)
            raise


def client(server, headers):
    return httpx.Client(base_url=server.origin, headers=headers, trust_env=False,
                        follow_redirects=False, timeout=5, transport=httpx.HTTPTransport(retries=0))


def reserve(c, witness):
    context = c.get(BASE+'/context', params={'component_id':str(witness.ids['component'])})
    assert context.status_code == 200
    witness.request_id = uuid.uuid4()
    body = dict(request_id=str(witness.request_id), component_id=str(witness.ids['component']), expected_bytes=65539,
                sha256=DIGEST, expected_context_digest=context.json()['context_digest'], reason='Synthetic loopback evidence')
    response = c.post(BASE+'/reservations', json=body)
    assert response.status_code == 201
    return body


@pytest.mark.parametrize('drop', [False, True])
def test_real_http_committed_file_and_original_receipt_once(real_http, drop):
    server, witness, headers = real_http
    with client(server, headers) as c:
        body = reserve(c, witness); witness.drop = drop
        if drop:
            with pytest.raises(httpx.RemoteProtocolError):
                c.put(BASE+'/'+body['request_id']+'/content', content=DATA, headers={'Content-Type':'application/octet-stream'})
            assert witness.lost and witness.evidence
        else:
            response = c.put(BASE+'/'+body['request_id']+'/content', content=DATA, headers={'Content-Type':'application/octet-stream'})
            assert response.status_code == 200 and response.json()['state'] == 'STORED_PRIVATE'
        before = witness.inspect()
    # Fresh connection only reads the original receipt. No reservation/PUT retry.
    with client(server, headers) as recovered:
        response = recovered.get(BASE+'/receipts/'+body['request_id'])
        assert response.status_code == 200 and response.json()['state'] == 'STORED_PRIVATE'
        assert response.json()['stored_receipt']['request_id'] == body['request_id']
        assert response.headers['cache-control'] == 'private, no-store'
        assert str(witness.root) not in response.text
    assert witness.inspect() == before
    assert witness.counts == {'reserve':1,'put':1,'receipt':1} and witness.commits == 1


@pytest.mark.parametrize('denial', ['disabled','unsigned','revoked'])
def test_real_http_refusal_has_no_storage(real_http, monkeypatch, denial):
    server, witness, headers = real_http
    if denial == 'disabled': monkeypatch.setattr(settings, 'private_upload_http_enabled', False)
    if denial == 'unsigned': headers = {}
    if denial == 'revoked':
        with Session(witness.engine) as db:
            db.get(ProjectMembership, witness.ids['pm']).status = 'SUSPENDED'; db.commit()
    with client(server, headers) as c:
        response = c.get(BASE+'/context', params={'component_id':str(witness.ids['component'])})
        assert response.status_code == (401 if denial == 'unsigned' else 403)
        assert response.headers['cache-control'] == 'private, no-store'
    assert not list(witness.root.iterdir()) and witness.commits == 0
    assert witness.counts == {'reserve':0,'put':0,'receipt':0}
