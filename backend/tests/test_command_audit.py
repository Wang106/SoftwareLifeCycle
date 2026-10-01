import uuid

import pytest
from sqlalchemy import func, select

from test_distribution_catalog import chain
from test_impact_assessments import context
from app.actor import ActorContext
from app.models.audit import AuditEvent
from app.models.core import Artifact, ComponentDefinition, Release, ReleaseComponent
from app.models.production import (
    Deployment,
    ManufacturingSite,
    ProductionBatch,
    ProductionLine,
    SoftwareChangeover,
)
from app.models.security import SecurityPrincipal
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.services.audit import AuditEventService
from app.services.production import ProductionService
from app.services.snapshot import SnapshotService


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def trusted_actor(db, subject: str, display_name: str):
    principal = SecurityPrincipal(
        issuer="https://identity.example.com",
        subject=subject,
        principal_type="USER",
        display_name=display_name,
    )
    db.add(principal)
    db.commit()
    return ActorContext(
        name=display_name,
        principal_id=principal.id,
        display_name=display_name,
        declared_name=None,
        source="AUTHENTICATED_PRINCIPAL",
    )


def prepare_snapshot_source(db, release):
    definition = ComponentDefinition(
        code=f"APP-{uuid.uuid4().hex[:8]}", name="Application"
    )
    db.add(definition)
    db.flush()
    component = ReleaseComponent(
        release_id=release.id,
        component_definition_id=definition.id,
        version=release.version,
        delta_type="MODIFIED",
    )
    db.add(component)
    db.flush()
    artifact = Artifact(
        release_component_id=component.id,
        artifact_type="HEX",
        filename="application.hex",
        storage_reference="/controlled/application.hex",
        sha256="c" * 64,
        controlled=True,
        classification="CONFIDENTIAL",
        distribution_level="INTERNAL_ONLY",
        ai_access_policy="DENY",
    )
    db.add(artifact)
    db.commit()


def test_snapshot_creation_records_trusted_atomic_audit(context, monkeypatch):
    db, _, release, _, _ = context
    prepare_snapshot_source(db, release)
    actor = trusted_actor(db, "snapshot-maintainer", "Snapshot Maintainer")

    snapshot = SnapshotService().create(db, release.id, actor_context=actor)
    event = db.scalars(
        select(AuditEvent).where(AuditEvent.entity_id == snapshot.id)
    ).one()
    assert snapshot.snapshot_number == 2
    assert event.entity_type == "RELEASE_SNAPSHOT"
    assert event.action == "FROZEN"
    assert event.actor_principal_id == actor.principal_id
    assert event.payload_json["content_hash"] == snapshot.content_hash
    assert event.payload_json["artifact_count"] == 1

    before = {
        ReleaseSnapshot: count(db, ReleaseSnapshot),
        SnapshotArtifact: count(db, SnapshotArtifact),
        AuditEvent: count(db, AuditEvent),
    }

    def fail(*args, **kwargs):
        raise RuntimeError("Injected audit failure")

    monkeypatch.setattr(AuditEventService, "record", fail)
    with pytest.raises(RuntimeError):
        SnapshotService().create(db, release.id, actor_context=actor)
    assert {
        model: count(db, model) for model in before
    } == before


def test_production_commands_record_trusted_atomic_audit(chain, monkeypatch):
    db, release, _, old_snapshot, _, _, authorizations, customer, project = chain
    authorization = authorizations[1]
    site = ManufacturingSite(
        site_code=authorization.site_code,
        customer_id=customer.id,
        project_id=project.id,
        name="Manufacturing Site",
        status="ACTIVE",
    )
    db.add(site)
    db.flush()
    line = ProductionLine(
        site_id=site.id,
        line_code=authorization.line_code,
        name="Production Line",
        status="ACTIVE",
    )
    previous_release = Release(
        software_id=release.software_id,
        release_type=release.release_type,
        version="0",
        status="RELEASED",
    )
    db.add_all([line, previous_release])
    db.commit()
    actor = trusted_actor(db, "production-operator", "Production Operator")
    service = ProductionService(db)

    deployment = service.create_deployment(
        "DEP-AUDITED", authorization.id, line.id, actor_context=actor
    )
    service.report_actual(
        deployment.deployment_no,
        release.id,
        old_snapshot.id,
        actor_context=actor,
    )
    changeover = service.create_changeover(
        deployment.deployment_no,
        "CO-AUDITED",
        previous_release.id,
        actor_context=actor,
    )
    batch = service.create_batch(
        deployment.deployment_no,
        "BATCH-AUDITED",
        changeover_id=changeover.id,
        actor_context=actor,
    )

    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.actor_principal_id == actor.principal_id)
        .order_by(AuditEvent.created_at, AuditEvent.event_no)
    ).all()
    assert {(event.entity_type, event.action) for event in events} == {
        ("DEPLOYMENT", "CREATED"),
        ("DEPLOYMENT", "ACTUAL_REPORTED"),
        ("SOFTWARE_CHANGEOVER", "COMPLETED"),
        ("PRODUCTION_BATCH", "STARTED"),
    }
    assert all(event.actor_name == actor.name for event in events)
    assert batch.changeover_id == changeover.id

    before = {
        Deployment: count(db, Deployment),
        ProductionBatch: count(db, ProductionBatch),
        SoftwareChangeover: count(db, SoftwareChangeover),
        AuditEvent: count(db, AuditEvent),
    }

    def fail(*args, **kwargs):
        raise RuntimeError("Injected audit failure")

    monkeypatch.setattr(AuditEventService, "record", fail)
    with pytest.raises(RuntimeError):
        service.create_deployment(
            "DEP-ROLLBACK", authorization.id, line.id, actor_context=actor
        )
    assert {
        model: count(db, model) for model in before
    } == before
