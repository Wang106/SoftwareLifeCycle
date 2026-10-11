"""Opt-in desensitized Excel sample family. Never repairs or rewrites history."""
import argparse
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select, text
from app.models.core import Supplier, SoftwareProduct, Customer, Project, Release, StandardReleaseDetail, ApplicationReleaseDetail
from app.models.snapshot import ReleaseSnapshot
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction
from app.models.audit import AuditEvent
from app.seed_release_demo import SSR_ROLES, ASR_ROLES

STAMP = datetime(2026, 10, 11, 16, 44, tzinfo=timezone.utc)
MARKER = 'EVT-ZFI-IMPORT-V1'


def key(name):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'softwarelifecycle/zfi-excel-demo/v1/' + name)


def manifest():
    return json.loads(Path(__file__).with_name('demo_data').joinpath('zfi_v1.json').read_text())


def manifest_hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def seed_zfi_demo(db):
    """Flush only; caller atomically commits all objects plus append-only audit."""
    data = manifest(); fingerprint = manifest_hash(data)
    refs = data['standards'] + data['applications']
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(106, 20261012)'))
    marker = db.get(AuditEvent, key('import'))
    if marker:
        if marker.event_no != MARKER or marker.payload_json.get('manifest_sha256') != fingerprint:
            raise ValueError('Import marker differs from reviewed manifest')
        if any(db.get(Release, key(r['ref'])) is None for r in refs):
            raise ValueError('Incomplete family; refuse historical repair')
        return {'releases': 20, 'already_present': True}
    for model, field, codes in ((Supplier, Supplier.code, ['1','2']),
        (SoftwareProduct, SoftwareProduct.code, ['cBMS-24x','go6']), (Customer, Customer.code, ['KUBO','VOL'])):
        if db.scalar(select(model.id).where(field.in_(codes)).limit(1)):
            raise ValueError('Import namespace contains unowned records')
    products = {}; customers = {}; projects = {}
    for row in data['suppliers']:
        supplier = Supplier(id=key('supplier-' + row['code']), code=row['code'], name=row['name'], description=row['description'])
        db.add(supplier); db.flush()
        product = SoftwareProduct(id=key('product-' + row['product']), supplier_id=supplier.id,
            code=row['product'], name=row['bms_model'], software_type='BMS')
        db.add(product); db.flush(); products[row['product']] = product
    for name, region in (('KUBO','APAC'),('VOL','EUROPE')):
        customer = Customer(id=key('customer-' + name), code=name, name=name, region=region)
        db.add(customer); db.flush(); customers[name] = customer
    for row in data['projects']:
        project = Project(id=key('project-' + row['code']), customer_id=customers[row['customer']].id,
            project_code=row['code'], name=row['name'], vehicle_platform=row['description'])
        db.add(project); db.flush(); projects[row['code']] = project
    scenarios = {r['ref']: r for r in data['approvals']}
    for row in refs:
        ref = row['ref']; standard = ref.startswith('SSR'); scenario = scenarios[ref]
        if scenario['generation'] != '允许生成演示资料':
            raise ValueError('Synthetic approval is not authorized')
        customer = customers[row['customer']] if not standard else None
        product_data = next(p for p in data['suppliers'] if p['product'] == row['product'])
        notes = ('脱敏演示 / Desensitized demo. 合成审批 / Synthetic approvals. '
            '未提供组件和测试，无正式发布决策 / No supplied artifacts/tests or release decision.\n'
            + f"ZFI · {product_data['bms_model']} · {product_data['hardware']}\n"
            + (row['description'] if standard else row['purpose']) + '\n' + row['changes']
            + ('\n' + row['configuration'] if not standard else ''))
        release = Release(id=key(ref), software_id=products[row['product']].id,
            customer_scope_id=customer.id if customer else None, release_type='STANDARD' if standard else 'APPLICATION',
            version=row['version'], status='DRAFT', release_notes=notes, created_at=STAMP)
        db.add(release); db.flush()
        if standard:
            db.add(StandardReleaseDetail(release_id=release.id))
        else:
            project = projects[row['project_code']]
            if project.customer_id != customer.id: raise ValueError('Customer/project mismatch')
            db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=customer.id, project_id=project.id,
                standard_base_release_id=key(row['base_ref'])))
        db.flush()
        metadata = {'sample_only': True, 'source_ref': ref, 'version': row['version'],
            'customer': row.get('customer'), 'supplied_artifacts': 0, 'supplied_test_evidence': 0,
            'desired_evidence_scenario': scenario['evidence_scenario'], 'desired_release_scenario': scenario['release_scenario'],
            'source_release_date': row.get('release_date'), 'product_metadata': product_data}
        snapshot = ReleaseSnapshot(id=key(ref + '-snapshot'), snapshot_no='SNAP-ZFI-' + ref,
            release_id=release.id, snapshot_number=1, status='FROZEN', content_hash=manifest_hash(metadata),
            release_metadata_json=metadata, created_at=STAMP)
        db.add(snapshot); db.flush()
        status = {'审批通过':'APPROVED','审批中':'PENDING','退回':'RETURNED','拒绝':'REJECTED'}[scenario['scenario']]
        approval = ApprovalRequest(id=key(ref + '-approval'), approval_no='APR-ZFI-' + ref, target_type='RELEASE',
            target_id=release.id, snapshot_id=snapshot.id, status=status, submitted_by='演示 / Demo submitter', submitted_at=STAMP)
        db.add(approval); db.flush()
        roles = SSR_ROLES if standard else ASR_ROLES
        current = roles.index(scenario['node']) + 1 if scenario['node'] else 4
        for order, role in enumerate(roles, 1):
            step_status = 'APPROVED' if status == 'APPROVED' or order < current else ('WAITING' if order > current else status)
            decided = step_status in ('APPROVED','RETURNED','REJECTED'); at = STAMP + timedelta(minutes=order)
            actor = '演示 / Demo ' + role if decided else None
            step = ApprovalStep(id=key(ref + f'-step-{order}'), approval_request_id=approval.id,
                step_order=order, role_name=role, status=step_status, approver_name=actor, decided_at=at if decided else None)
            db.add(step); db.flush()
            if decided:
                action = ApprovalAction(id=key(ref + f'-action-{order}'), approval_request_id=approval.id, step_id=step.id,
                    actor_name=actor, action=step_status, comment='合成演示审批 / Synthetic demo approval, not an actual sign-off.', created_at=at)
                db.add(action)
                db.add(AuditEvent(id=key(ref + f'-audit-{order}'), event_no=f'EVT-ZFI-{ref}-{order}', event_type='APPROVAL',
                    action=step_status, entity_type='APPROVAL_REQUEST', entity_id=approval.id, entity_ref=approval.approval_no,
                    actor_name=actor, summary=action.comment, occurred_at=at, payload_json={'sample_only':True,
                    'source_ref':ref,'approval_action_id':str(action.id),'step_id':str(step.id),'snapshot_id':str(snapshot.id)}))
    db.add(AuditEvent(id=key('import'), event_no=MARKER, event_type='DEMO_IMPORT', action='IMPORT',
        entity_type='DEMO_DATASET', entity_id=key('dataset'), entity_ref='ZFI-EXCEL-V1', actor_name='Excel demo importer',
        summary='Desensitized Excel intake; synthetic approvals; no test results or release decisions.', occurred_at=STAMP,
        payload_json={'sample_only':True,'manifest_sha256':fingerprint,'suppliers':2,'projects':4,'standards':4,
                      'applications':16,'corrections':data['corrections'],'supplied_artifacts':0,'supplied_test_evidence':0}))
    db.flush(); return {'releases':20,'already_present':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample-only', action='store_true', required=True)
    parser.parse_args()
    from app.core.db import SessionLocal
    with SessionLocal.begin() as db: result = seed_zfi_demo(db)
    print(json.dumps(result))


if __name__ == '__main__': main()
