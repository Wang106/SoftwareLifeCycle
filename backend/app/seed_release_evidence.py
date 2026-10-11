"""Opt-in synthetic release evidence; caller controls the complete transaction."""
import argparse
import hashlib
import uuid
from datetime import timedelta
from sqlalchemy import select
from app.seed_release_demo import SSR_ROLES, ASR_ROLES, STAMP
from app.seed import freeze_snapshot_artifacts
from app.models.core import (Supplier, SoftwareProduct, Customer, Project, Release,
    StandardReleaseDetail, ApplicationReleaseDetail, ComponentDefinition, ReleaseComponent, Artifact)
from app.models.snapshot import ReleaseSnapshot
from app.models.change import SoftwareChangeRequest, ChangePoint, AcceptanceCriterion, Issue, IssueChangeRequestRelation
from app.models.acceptance import AcceptanceDvpLink
from app.models.testing import DvpPlan, DvpItem, ChangePointDvpItem, IssueDvpItem, DvpExecution
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction, ReleaseDecision
from app.models.audit import AuditEvent

VERSIONS = ('DEMO-EVIDENCE-SSR-2.0', 'DEMO-EVIDENCE-ASR-A-2.0', 'DEMO-EVIDENCE-ASR-B-2.0')
PRODUCT_CODE = 'DEMO-RELEASE-EVIDENCE'


def key(name):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'softwarelifecycle/release-evidence/v1/' + name)


def seed_release_evidence(db):
    existing = db.scalar(select(SoftwareProduct).where(SoftwareProduct.code == PRODUCT_CODE))
    if existing:
        if existing.id != key('product'):
            raise ValueError('Evidence sample product code belongs to another record')
        return existing.id
    supplier = Supplier(id=key('supplier'), code='DEMO-EVIDENCE-SUP', name='Demo Evidence Supplier')
    db.add(supplier); db.flush()
    product = SoftwareProduct(id=key('product'), supplier_id=supplier.id, code=PRODUCT_CODE, name='Release evidence demonstration BMS')
    db.add(product); db.flush()
    scr = SoftwareChangeRequest(id=key('scr'), request_no='SCR-DEMO-EVIDENCE', title='Synthetic baseline verification',
        source='INTERNAL', scope='STANDARD', change_type='IMPROVEMENT', software_id=product.id, status='IN_TEST')
    db.add(scr); db.flush()
    cp = ChangePoint(id=key('cp'), change_request_id=scr.id, change_no='CP-DEMO-EVIDENCE', title='Synthetic release validation', status='VERIFIED')
    criterion = AcceptanceCriterion(id=key('criterion'), change_request_id=scr.id, criterion_no='AC-DEMO-EVIDENCE', description='Verify this exact frozen snapshot in all three test scopes.')
    issue = Issue(id=key('issue'), issue_no='DEMO-EVIDENCE', title='Synthetic release verification issue', scope='STANDARD', severity='LOW', status='FIX_VERIFIED')
    db.add_all([cp, criterion, issue]); db.flush()
    db.add(IssueChangeRequestRelation(id=key('issue-scr'), issue_id=issue.id, change_request_id=scr.id, relation_type='FIXES'))
    plan = DvpPlan(id=key('plan'), change_request_id=scr.id, plan_no='DVP-DEMO-EVIDENCE', title='Synthetic Software / Battery / Customer verification', status='IN_PROGRESS')
    db.add(plan); db.flush()
    tests = []
    for i, scope in enumerate(('SOFTWARE', 'BATTERY', 'CUSTOMER'), 1):
        item = DvpItem(id=key(scope), plan_id=plan.id, item_no='DVP-DEMO-' + scope, title='Synthetic ' + scope + ' validation', scope=scope, status='PASS')
        db.add(item); db.flush(); tests.append(item)
        db.add(ChangePointDvpItem(change_point_id=cp.id, dvp_item_id=item.id))
        db.add(IssueDvpItem(issue_id=issue.id, dvp_item_id=item.id))
        db.add(AcceptanceDvpLink(id=key(scope + '-acceptance'), criterion_id=criterion.id, dvp_item_id=item.id, action='ASSIGN', actor_name='Demo evidence seed', reason='Synthetic demonstration assignment.'))
    definitions = []
    for code, name in (('APP', 'Application'), ('BOOT', 'Bootloader'), ('CAL', 'Calibration')):
        d = ComponentDefinition(id=key(code), code='DEMO-EVIDENCE-' + code, name=name)
        db.add(d); definitions.append(d)
    db.flush()
    base_components = {}
    for index, version in enumerate(VERSIONS):
        standard = index == 0
        release = Release(id=key(version), software_id=product.id, release_type='STANDARD' if standard else 'APPLICATION', version=version, status='READY' if index < 2 else 'DRAFT', release_notes='Synthetic evidence only; no actual firmware or personnel approval.')
        db.add(release); db.flush()
        if standard:
            db.add(StandardReleaseDetail(release_id=release.id, git_branch='demo-evidence', git_commit='synthetic-source'))
        else:
            customer = Customer(id=key('customer-' + str(index)), code='DEMO-EVIDENCE-' + str(index), name='Demo Evidence Customer ' + str(index), region='APAC' if index == 1 else 'EUROPE')
            db.add(customer); db.flush()
            project = Project(id=key('project-' + str(index)), customer_id=customer.id, project_code='DEMO-EVIDENCE-' + str(index), name='Demo Evidence Project ' + str(index))
            db.add(project); db.flush()
            db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=key(VERSIONS[0])))
        for n, definition in enumerate(definitions):
            inherited = not standard and n < 2
            component = ReleaseComponent(id=key(version + definition.code), release_id=release.id, component_definition_id=definition.id,
                version='2.0' if standard or inherited else version, base_component_id=base_components.get(definition.id), delta_type='UNCHANGED' if inherited else 'MODIFIED')
            db.add(component); db.flush()
            if standard: base_components[definition.id] = component.id
            content = (VERSIONS[0] if inherited else version) + definition.code
            db.add(Artifact(id=key(version + definition.code + '-file'), release_component_id=component.id, filename=version + '_' + definition.name + '.hex', artifact_type='HEX', storage_reference='demo://' + content,
                sha256=hashlib.sha256(('sample:' + content).encode()).hexdigest(), controlled=True, classification='INTERNAL', distribution_level='INTERNAL_ONLY', ai_access_policy='DENY'))
        db.flush()
        snapshots = []
        for number in range(1, 3 if index == 2 else 2):
            snapshot = ReleaseSnapshot(id=key(version + '-snapshot-' + str(number)), snapshot_no='SNAP-DEMO-EVIDENCE-' + str(index) + '-' + str(number), release_id=release.id, snapshot_number=number,
                status='FROZEN', content_hash='0' * 64, release_metadata_json={'version':version, 'release_type':release.release_type, 'sample_only':True}, created_at=STAMP + timedelta(minutes=number))
            db.add(snapshot); db.flush(); freeze_snapshot_artifacts(db, snapshot, release); snapshots.append(snapshot)
        current = snapshots[-1]
        for item in tests:
            db.add(DvpExecution(id=key(version + item.scope + '-execution'), dvp_item_id=item.id, execution_no=index+1, release_id=release.id, snapshot_id=snapshots[0].id, result='PASS', actual_result='Synthetic PASS on the specified snapshot only.', executed_at=STAMP + timedelta(minutes=3)))
        approval = ApprovalRequest(id=key(version + '-approval'), approval_no='APR-DEMO-EVIDENCE-' + str(index), target_type='RELEASE', target_id=release.id, snapshot_id=current.id, status='APPROVED', submitted_by='Demo submitter', submitted_at=STAMP)
        db.add(approval); db.flush()
        for order, role in enumerate(SSR_ROLES if standard else ASR_ROLES, 1):
            step = ApprovalStep(id=key(version + '-step-' + str(order)), approval_request_id=approval.id, step_order=order, role_name=role, approver_name='Demo ' + role, status='APPROVED', decided_at=STAMP + timedelta(minutes=3+order))
            db.add(step); db.flush()
            action = ApprovalAction(id=key(version + '-action-' + str(order)), approval_request_id=approval.id, step_id=step.id, actor_name=step.approver_name, action='APPROVED', comment='Synthetic review record; not real job-role authorization.', created_at=step.decided_at)
            db.add(action)
            db.add(AuditEvent(id=key(version + '-audit-' + str(order)), event_no='EVT-DEMO-EVID-' + str(index) + '-' + str(order), event_type='APPROVAL', action='APPROVED', entity_type='APPROVAL_REQUEST', entity_id=approval.id, entity_ref=approval.approval_no, actor_name=step.approver_name, summary='Synthetic approval stage', occurred_at=step.decided_at, payload_json={'sample_only':True,'approval_action_id':str(action.id),'step_id':str(step.id),'snapshot_id':str(current.id),'role_name':role}))
        db.flush()
        from app.api.dashboard import _readiness_for_release
        observed = _readiness_for_release(release, db, bounded=True)
        expected = 'NOT_READY' if index == 2 else 'READY'
        if observed['overall'] != expected:
            raise ValueError('Synthetic evidence does not satisfy the actual readiness rules')
        decision = ReleaseDecision(id=key(version + '-decision'), decision_no='RD-DEMO-EVIDENCE-' + str(index), release_id=release.id, snapshot_id=current.id, approval_request_id=approval.id,
            readiness_status=observed['overall'], decision='HOLD' if index == 2 else 'RELEASE', decided_by='Demo release authority', decision_notes='Synthetic declaration based on calculated readiness; not actual production authorization.', decided_at=STAMP + timedelta(minutes=9))
        db.add(decision)
        db.add(AuditEvent(id=key(version + '-decision-audit'), event_no='EVT-DEMO-EVID-RD-' + str(index), event_type='RELEASE', action='DECISION_RECORDED', entity_type='RELEASE_DECISION', entity_id=decision.id, entity_ref=decision.decision_no, actor_name=decision.decided_by, summary='Synthetic release evidence decision', occurred_at=decision.decided_at,
            payload_json={'sample_only':True,'release_id':str(release.id),'snapshot_id':str(current.id),'content_hash':current.content_hash,'approval_no':approval.approval_no,'decision':decision.decision,'readiness_status':decision.readiness_status}))
    db.flush()
    return product.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample-only', action='store_true', required=True)
    parser.parse_args()
    from app.core.db import SessionLocal
    with SessionLocal.begin() as db: seed_release_evidence(db)
    print('Synthetic release evidence seeded; no actual submissions enabled.')


if __name__ == '__main__': main()
