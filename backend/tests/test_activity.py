from datetime import datetime, timezone
import uuid

from app.api.activity import _event_detail, _release_links, get_activity, list_activity
from app.models.audit import AuditEvent
from app.models.approval import ReleaseDecision
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot


def test_event_detail_preserves_formal_reference_and_payload():
    event_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    timestamp = datetime(2026, 9, 28, 10, 17, tzinfo=timezone.utc)
    event = AuditEvent(
        id=event_id,
        event_no="EVT-0009",
        event_type="BATCH",
        action="STARTED",
        entity_type="PRODUCTION_BATCH",
        entity_id=entity_id,
        entity_ref="PB-1005-A",
        actor_name="Production Operator",
        summary="PB-1005-A started",
        detail="Initial controlled production batch started.",
        payload_json={"deployment_no": "DEP-0081"},
        occurred_at=timestamp,
        created_at=timestamp,
    )

    result = _event_detail(event)

    assert result["id"] == str(event_id)
    assert result["entity_id"] == str(entity_id)
    assert result["entity_ref"] == "PB-1005-A"
    assert result["related_release_id"] is None
    assert result["payload"] == {"deployment_no": "DEP-0081"}
    assert result["occurred_at"] == timestamp


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class ActivitySession:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        return Rows(self.rows.get(entity, []))


def make_event(entity_type, entity_id, event_no):
    timestamp = datetime(2026, 9, 29, tzinfo=timezone.utc)
    return AuditEvent(id=uuid.uuid4(), event_no=event_no, event_type="RELEASE", action="RECORDED",
        entity_type=entity_type, entity_id=entity_id, entity_ref=event_no, actor_name="Release Manager",
        summary=event_no, payload_json={}, occurred_at=timestamp, created_at=timestamp)


def test_activity_links_only_recorded_application_release_relations():
    application = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    standard = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="STANDARD", version="5.1.12")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=application.id, snapshot_no="SNAP-008",
        snapshot_number=1, status="FROZEN", content_hash="a" * 64)
    standard_snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=standard.id, snapshot_no="SNAP-SSR",
        snapshot_number=1, status="FROZEN", content_hash="b" * 64)
    decision = ReleaseDecision(id=uuid.uuid4(), decision_no="RD-0081", release_id=application.id,
        snapshot_id=snapshot.id, approval_request_id=uuid.uuid4(), readiness_status="READY",
        decision="RELEASE", decided_by="Release Manager")
    events = [make_event("RELEASE_SNAPSHOT", snapshot.id, "EVT-0003"),
        make_event("RELEASE_DECISION", decision.id, "EVT-0005"),
        make_event("RELEASE_SNAPSHOT", standard_snapshot.id, "EVT-SSR"),
        make_event("RELEASE_DECISION", uuid.uuid4(), "EVT-MISSING")]
    db = ActivitySession({AuditEvent: events, ReleaseSnapshot: [snapshot, standard_snapshot],
        ReleaseDecision: [decision], Release: [application]})

    links = _release_links(db, events)
    assert links == {
        ("RELEASE_SNAPSHOT", snapshot.id): str(application.id),
        ("RELEASE_DECISION", decision.id): str(application.id),
    }
    rows = list_activity(limit=50, db=db)
    assert [row["related_release_id"] for row in rows] == [str(application.id), str(application.id), None, None]
    assert get_activity("EVT-0003", db=db)["related_release_id"] == str(application.id)
