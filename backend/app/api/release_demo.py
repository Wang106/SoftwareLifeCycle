"""Bounded read-only evidence for the explicitly installed synthetic sample family."""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import Release, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.api.dashboard import _readiness_for_release
from app.seed_release_evidence import key, VERSIONS, PRODUCT_CODE

router = APIRouter(prefix='/api/v1/demo', tags=['read-only sample evidence'])


@router.get('/release-evidence')
def evidence(db: Session = Depends(get_db)):
    product = db.get(SoftwareProduct, key('product'))
    if product is None or product.code != PRODUCT_CODE:
        return {'sample_only': True, 'initialized': False, 'items': []}
    items = []
    for version in VERSIONS:
        release = db.get(Release, key(version))
        if release is None or release.software_id != product.id:
            continue
        ready = _readiness_for_release(release, db, bounded=True)
        snapshot_id = ready['coverage']['snapshot_id']
        snapshot = db.get(ReleaseSnapshot, uuid.UUID(snapshot_id)) if snapshot_id else None
        decision = db.scalar(select(ReleaseDecision).where(ReleaseDecision.release_id == release.id)
            .order_by(ReleaseDecision.decided_at.desc(), ReleaseDecision.decision_no.desc(), ReleaseDecision.id.desc()).limit(1))
        approval = db.get(ApprovalRequest, decision.approval_request_id) if decision and decision.approval_request_id else None
        approval_bound = bool(approval and approval.target_type == 'RELEASE' and approval.target_id == release.id
            and snapshot and approval.snapshot_id == snapshot.id)
        decision_bound = bool(decision and snapshot and decision.snapshot_id == snapshot.id and approval_bound)
        confirmed = bool(decision_bound and approval.status == 'APPROVED' and decision.decision == 'RELEASE'
            and decision.readiness_status == 'READY' and ready['overall'] == 'READY')
        items.append({'release_id': str(release.id), 'version': release.version, 'release_type': release.release_type,
            'record_status': release.status, 'snapshot': {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no,
                'content_hash': snapshot.content_hash} if snapshot else None,
            'readiness': ready,
            'approval': {'approval_no': approval.approval_no, 'status': approval.status, 'current_snapshot_bound': approval_bound} if approval else None,
            'decision': {'decision_no': decision.decision_no, 'decision': decision.decision,
                'readiness_status': decision.readiness_status, 'snapshot_id': str(decision.snapshot_id),
                'current_evidence_bound': decision_bound} if decision else None,
            'current_release_confirmed': confirmed,
            'change_request_no': 'SCR-DEMO-EVIDENCE', 'dvp_items': [{'id': str(key(scope)), 'item_no': 'DVP-DEMO-' + scope} for scope in ('SOFTWARE','BATTERY','CUSTOMER')]})
    return {'sample_only': True, 'initialized': len(items) == len(VERSIONS), 'items': items}
