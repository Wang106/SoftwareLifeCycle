from datetime import datetime, timezone
import uuid

from app.api.activity import _event_detail
from app.models.audit import AuditEvent


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
    assert result["payload"] == {"deployment_no": "DEP-0081"}
    assert result["occurred_at"] == timestamp
