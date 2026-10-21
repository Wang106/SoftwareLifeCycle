"""Bounded read-only evidence for the explicitly installed synthetic sample family."""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import Release, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot
from app.models.approval import ApprovalRequest, ApprovalStep, ReleaseDecision
from app.api.dashboard import _readiness_for_release
from app.seed_release_evidence import key, VERSIONS, PRODUCT_CODE
from app.services.release_decision import effective_release_decision

router = APIRouter(prefix='/api/v1/demo', tags=['read-only sample evidence'])


@router.get('/zfi-import')
def zfi_import(db: Session = Depends(get_db)):
    from app.seed_zfi_demo import key as identity, manifest, manifest_hash, MARKER
    from app.seed_release_demo import ASR_ROLES, SSR_ROLES
    from app.models.audit import AuditEvent
    data = manifest(); marker = db.get(AuditEvent, identity('import'))
    if marker is None or marker.event_no != MARKER or marker.payload_json.get('manifest_sha256') != manifest_hash(data):
        return {'sample_only':True,'initialized':False,'items':[]}
    refs = data['standards'] + data['applications']
    releases = {r.id:r for r in db.scalars(select(Release).where(Release.id.in_([identity(r['ref']) for r in refs])))}
    approvals = {a.id:a for a in db.scalars(select(ApprovalRequest).where(ApprovalRequest.id.in_([identity(r['ref']+'-approval') for r in refs])))}
    approval_ids = list(approvals)
    step_rows = db.scalars(select(ApprovalStep).where(ApprovalStep.approval_request_id.in_(approval_ids))
        .order_by(ApprovalStep.approval_request_id, ApprovalStep.step_order)).all() if approval_ids else []
    steps_by_approval = {approval_id: [] for approval_id in approval_ids}
    for step in step_rows:
        steps_by_approval[step.approval_request_id].append(step)

    def approval_progress(approval, expected_roles):
        if approval is None:
            return None
        steps = steps_by_approval.get(approval.id, [])
        if len(steps) != len(expected_roles) or any(
            step.step_order != index or step.role_name != expected_role
            for index, (step, expected_role) in enumerate(zip(steps, expected_roles), 1)
        ):
            return None
        closed = approval.status in ('APPROVED', 'RETURNED', 'REJECTED', 'CANCELLED')
        candidate = next((step for step in steps if step.status in ('PENDING', 'WAITING')), None)
        current = candidate if not closed and candidate is not None and candidate.status == 'PENDING' else None
        return {
            'approved_steps': sum(step.status == 'APPROVED' for step in steps),
            'total_steps': len(steps),
            'current_step_order': current.step_order if current else None,
            'current_role': current.role_name if current else None,
            'closed': closed,
        }
    items = []
    for row in refs:
        release = releases.get(identity(row['ref'])); approval = approvals.get(identity(row['ref']+'-approval'))
        if release is None: continue
        roles = SSR_ROLES if row['ref'].startswith('SSR') else ASR_ROLES
        items.append({'source_ref':row['ref'],'release_id':str(release.id),'version':release.version,
            'release_type':release.release_type,'product':row['product'],'customer':row.get('customer'),
            'project_code':row.get('project_code'),'record_status':release.status,
            'approval_no':approval.approval_no if approval else None,'approval_status':approval.status if approval else None,
            'approval_progress':approval_progress(approval, roles),
            'source_release_date':row.get('release_date'),'supplied_artifacts':0,'supplied_test_evidence':0})
    return {'sample_only':True,'initialized':len(items)==20 and len(approvals)==20,'import_event_no':MARKER,
        'corrections':data['corrections'],'synthetic_approvals':True,'release_decisions_created':0,
        'approval_routes':{'STANDARD':list(SSR_ROLES),'APPLICATION':list(ASR_ROLES)},'items':items}


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
        decision = effective_release_decision(db, release.id)
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
