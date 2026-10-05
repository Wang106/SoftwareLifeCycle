"""Candidate release evidence and append-only assessments for an issue.

A shared software product is a review lead, not proof of release impact.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.production import Deployment, ProductionBatch
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.impact import IssueImpactAssessment
from app.models.testing import IssueDvpItem, DvpItem, DvpExecution
from app.services.impact_assessment import AssessmentError, AssessmentInput, record_assessment
from app.authorization import authorize_issue_assessment
from app.actor import resolve_actor

router = APIRouter(prefix="/api/v1/issues", tags=["impact"])


def _assessment(row):
    return {'id': str(row.id), 'release_id': str(row.release_id), 'snapshot_id': str(row.snapshot_id),
            'decision': row.decision, 'reason': row.reason, 'evidence_ref': row.evidence_ref,
            'actor_name': row.actor_name, 'created_at': row.created_at}


def _contexts(db, issue_id, releases):
    ids = [row.id for row in releases]
    snapshots = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id.in_(ids), ReleaseSnapshot.status == 'FROZEN')
        .order_by(ReleaseSnapshot.snapshot_number.desc())).all() if ids else []
    latest = {}
    for snapshot in snapshots:
        latest.setdefault(snapshot.release_id, snapshot)
    snapshot_ids = [row.id for row in latest.values()]
    artifacts = db.scalars(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id.in_(snapshot_ids))
        .order_by(SnapshotArtifact.component_code, SnapshotArtifact.filename)).all() if snapshot_ids else []
    assessments = db.scalars(select(IssueImpactAssessment).where(IssueImpactAssessment.issue_id == issue_id,
        IssueImpactAssessment.release_id.in_(ids), IssueImpactAssessment.snapshot_id.in_(snapshot_ids))
        .order_by(IssueImpactAssessment.created_at.desc(), IssueImpactAssessment.id.desc())).all() if snapshot_ids else []
    reviews = {}
    for row in assessments:
        reviews.setdefault((row.release_id, row.snapshot_id), row)
    result = {}
    for release in releases:
        snapshot = latest.get(release.id)
        assessment = reviews.get((release.id, snapshot.id)) if snapshot else None
        result[release.id] = {'snapshot': {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no,
            'status': snapshot.status} if snapshot else None,
            'frozen_components': [{'code': code, 'version': version} for code, version in sorted({
                (row.component_code, row.component_version or '') for row in artifacts
                if snapshot and row.snapshot_id == snapshot.id})],
            'assessment': _assessment(assessment) if assessment else None}
    return result


def issue_impact(issue_no: str, db: Session = Depends(get_db)):
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no)).first()
    if issue is None:
        raise HTTPException(status_code=404, detail="issue not found")

    linked = db.execute(select(IssueChangeRequestRelation, SoftwareChangeRequest)
        .join(SoftwareChangeRequest, SoftwareChangeRequest.id == IssueChangeRequestRelation.change_request_id)
        .where(IssueChangeRequestRelation.issue_id == issue.id)).all()
    changes = [scr for _, scr in linked]
    software_ids = {scr.software_id for scr in changes}
    if not software_ids:
        return {"issue_no": issue.issue_no, "linked_changes": [], "candidate_releases": [],
                "truncated": False, "basis": "No linked SCR; release impact cannot be inferred."}

    products = {p.id: p for p in db.scalars(select(SoftwareProduct).where(SoftwareProduct.id.in_(software_ids))).all()}
    releases = db.scalars(select(Release).where(Release.software_id.in_(software_ids))
        .order_by(Release.created_at.desc(), Release.id.desc()).limit(201)).all()
    truncated = len(releases) > 200
    releases = releases[:200]
    release_ids = [release.id for release in releases]
    details = {d.release_id: d for d in db.scalars(select(ApplicationReleaseDetail)
        .where(ApplicationReleaseDetail.release_id.in_(release_ids))).all()} if release_ids else {}
    customer_ids = {d.customer_id for d in details.values()}
    project_ids = {d.project_id for d in details.values()}
    customers = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()} if customer_ids else {}
    projects = {p.id: p for p in db.scalars(select(Project).where(Project.id.in_(project_ids))).all()} if project_ids else {}
    deployments = db.scalars(select(Deployment).where(Deployment.actual_release_id.in_(release_ids))).all() if release_ids else []
    batches = db.scalars(select(ProductionBatch).where(ProductionBatch.release_id.in_(release_ids))).all() if release_ids else []
    deployment_count = {}
    batch_count = {}
    for deployment in deployments:
        deployment_count[deployment.actual_release_id] = deployment_count.get(deployment.actual_release_id, 0) + 1
    for batch in batches:
        batch_count[batch.release_id] = batch_count.get(batch.release_id, 0) + 1
    contexts = _contexts(db, issue.id, releases)

    return {
        "issue_no": issue.issue_no,
        "linked_changes": [{"request_no": scr.request_no, "title": scr.title,
                            "relation_type": relation.relation_type, "status": scr.status}
                           for relation, scr in linked],
        "candidate_releases": [{
            "id": str(release.id), "release_type": release.release_type,
            "version": release.version, "status": release.status,
            "software": {"code": products[release.software_id].code,
                         "name": products[release.software_id].name},
            "customer": customers[details[release.id].customer_id].name if release.id in details and details[release.id].customer_id in customers else None,
            "project": projects[details[release.id].project_id].name if release.id in details and details[release.id].project_id in projects else None,
            "customer_code": customers[details[release.id].customer_id].code if release.id in details and details[release.id].customer_id in customers else None,
            "project_id": str(details[release.id].project_id) if release.id in details else None,
            "deployment_count": deployment_count.get(release.id, 0),
            "batch_count": batch_count.get(release.id, 0),
            **contexts[release.id],
        } for release in releases if release.software_id in products],
        "truncated": truncated,
        "basis": "Candidate releases share a software product with a linked SCR. Actual issue impact requires review.",
    }


def impact_evidence(issue_no: str, release_id: uuid.UUID, db: Session = Depends(get_db)):
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no)).first()
    release = db.get(Release, release_id)
    if not issue or not release:
        raise HTTPException(status_code=404, detail='issue or release not found')
    software_ids = set(db.scalars(select(SoftwareChangeRequest.software_id)
        .join(IssueChangeRequestRelation, IssueChangeRequestRelation.change_request_id == SoftwareChangeRequest.id)
        .where(IssueChangeRequestRelation.issue_id == issue.id)).all())
    if release.software_id not in software_ids:
        raise HTTPException(status_code=409, detail='release is not a candidate from linked SCR software')
    context = _contexts(db, issue.id, [release])[release.id]
    item_ids = db.scalars(select(IssueDvpItem.dvp_item_id).where(IssueDvpItem.issue_id == issue.id)).all()
    items = db.scalars(select(DvpItem).where(DvpItem.id.in_(item_ids)).order_by(DvpItem.item_no, DvpItem.id)).all() if item_ids else []
    executions = db.scalars(select(DvpExecution).where(DvpExecution.dvp_item_id.in_(item_ids),
        DvpExecution.release_id == release.id, DvpExecution.snapshot_id == uuid.UUID(context['snapshot']['id']))
        .order_by(DvpExecution.execution_no.desc())).all() if context['snapshot'] and item_ids else []
    latest = {}
    for execution in executions:
        latest.setdefault(execution.dvp_item_id, execution)
    return {'issue_no': issue.issue_no, 'release': {'id': str(release.id), 'type': release.release_type,
            'version': release.version}, **context, 'verification': [{
                'id': str(item.id), 'item_no': item.item_no, 'title': item.title,
                'execution': {'execution_no': latest[item.id].execution_no, 'result': latest[item.id].result,
                    'actual_result': latest[item.id].actual_result, 'executed_at': latest[item.id].executed_at}
                if item.id in latest else None} for item in items]}


def assessment_history(issue_no: str, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no)).first()
    if not issue:
        raise HTTPException(status_code=404, detail='issue not found')
    rows = db.scalars(select(IssueImpactAssessment).where(IssueImpactAssessment.issue_id == issue.id)
        .order_by(IssueImpactAssessment.created_at.desc(), IssueImpactAssessment.id.desc()).limit(limit + 1)).all()
    page = rows[:limit]
    snapshots = {s.id: s for s in db.scalars(select(ReleaseSnapshot).where(
        ReleaseSnapshot.id.in_([r.snapshot_id for r in page]))).all()} if page else {}
    releases = {r.id: r for r in db.scalars(select(Release).where(
        Release.id.in_([r.release_id for r in page]))).all()} if page else {}
    return {'items': [{**_assessment(row), 'snapshot_no': snapshots[row.snapshot_id].snapshot_no,
                      'release_version': releases[row.release_id].version} for row in page],
            'truncated': len(rows) > limit}


@router.post('/{issue_no}/impact-assessments', status_code=201)
def create_assessment(
    issue_no: str,
    data: AssessmentInput,
    response: Response,
    db: Session = Depends(get_db),
    request: Request = None,
):
    authorize_issue_assessment(request, db, issue_no, data.release_id)
    actor = resolve_actor(request, data.actor_name)
    try:
        row, created = record_assessment(db, issue_no, data, actor_context=actor)
        db.commit()
        db.refresh(row)
        response.status_code = 201 if created else 200
        return _assessment(row)
    except AssessmentError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='assessment request conflict') from exc
    except Exception:
        db.rollback()
        raise
