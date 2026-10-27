"""Bounded private selectors; observations never replace command authorization."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select, case, func
from app.auth import AuthenticatedPrincipal
from app.api.browser_sessions import require_browser_session
from app.core.config import settings
from app.models.security import SecurityPrincipal, ProjectMembership, BrowserSession
from app.models.core import Release, ApplicationReleaseDetail, Customer, Project
from app.models.approval import ApprovalRequest
from app.models.distribution import DeliveryPackage, Distribution, DeliveryPackageItem
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule as Rule
from app.models.production import ManufacturingSite, ProductionLine
from app.services.admin_lock import admin_write_gate
from app.services.release_decision import effective_release_decision
from app.services.revocation import ensure_chain_active


def deny(code='selection_target_not_found', status=404):
    raise HTTPException(status, code)


class PrivateDistributionSelection:
    def __init__(self, db): self.db = db

    def lock(self, model, identifier):
        return self.db.scalar(select(model).where(model.id == identifier).with_for_update()
                              .execution_options(populate_existing=True))

    def principal(self, request):
        if settings.auth_mode != 'oidc': deny('oidc_not_enabled',401)
        principal = getattr(request.state,'principal',None)
        if not isinstance(principal,AuthenticatedPrincipal): deny('authenticated_principal_required',401)
        admin_write_gate(self.db)
        row = self.lock(SecurityPrincipal,principal.id)
        if row is None or row.issuer != principal.issuer or row.subject != principal.subject or row.status != 'ACTIVE':
            deny('inactive_principal',401)
        if row.principal_type != 'USER': deny('user_principal_required',403)
        sid = require_browser_session(request,self.db,row.id)
        if sid is not None:
            self.lock(BrowserSession,sid)
            require_browser_session(request,self.db,row.id)
        return row

    def source(self, request, kind, identifier, role, expected_snapshot_id=None, expected_decision_id=None):
        actor = self.principal(request)
        package = distribution = None
        if kind == 'distribution':
            distribution = self.db.get(Distribution,identifier)
            if distribution is None: deny()
            package = self.db.get(DeliveryPackage,distribution.delivery_package_id)
        elif kind == 'package': package = self.db.get(DeliveryPackage,identifier)
        if kind != 'release' and package is None: deny()
        release_id = identifier if kind == 'release' else package.release_id
        detail = self.db.get(ApplicationReleaseDetail,release_id)
        if detail is None: deny()  # No invented SSR/software visibility policy.
        project_id = detail.project_id
        membership = self.db.scalar(select(ProjectMembership).where(ProjectMembership.principal_id == actor.id,
            ProjectMembership.project_id == project_id,ProjectMembership.role == role,ProjectMembership.status == 'ACTIVE')
            .with_for_update().execution_options(populate_existing=True))
        if membership is None: deny()
        release = self.lock(Release,release_id)
        package = self.lock(DeliveryPackage,package.id) if package else None
        distribution = self.lock(Distribution,distribution.id) if distribution else None
        detail = self.db.scalar(select(ApplicationReleaseDetail).where(ApplicationReleaseDetail.release_id == release_id)
                                .execution_options(populate_existing=True))
        if release is None or detail is None or detail.project_id != project_id or release.release_type != 'APPLICATION': deny()
        if package and (package.release_id != release.id or (kind == 'package' and package.status not in ('READY','APPROVED'))): deny('selection_context_ineligible',409)
        if distribution and (distribution.delivery_package_id != package.id or distribution.status not in ('READY','SENT','ACKNOWLEDGED')):
            deny('selection_context_ineligible',409)
        kind_name={'release':'RELEASE','package':'DELIVERY_PACKAGE','distribution':'DISTRIBUTION'}[kind]
        try: ensure_chain_active(self.db,kind_name,identifier)
        except ValueError: deny('selection_context_ineligible',409)
        if kind == 'package':
            if self.db.scalar(select(DeliveryPackageItem.id).where(DeliveryPackageItem.delivery_package_id==package.id).limit(1)) is None:
                deny('selection_context_ineligible',409)
            return {'release_id':str(release.id),'snapshot_id':str(package.snapshot_id),
                    'release_decision_id':None,'project_id':str(project_id)},detail,package,distribution
        decision = effective_release_decision(self.db,release.id)
        if not decision or decision.decision != 'RELEASE': deny('selection_context_ineligible',409)
        snapshot = self.lock(ReleaseSnapshot,decision.snapshot_id)
        if not snapshot or snapshot.release_id != release.id or (package and package.snapshot_id != snapshot.id):
            deny('selection_context_ineligible',409)
        if kind == 'release':
            approval = self.lock(ApprovalRequest,decision.approval_request_id)
            if (snapshot.status != 'FROZEN' or not approval or approval.status != 'APPROVED' or approval.snapshot_id != snapshot.id):
                deny('selection_context_ineligible',409)
        if ((expected_snapshot_id is not None and expected_snapshot_id != snapshot.id) or
                (expected_decision_id is not None and expected_decision_id != decision.id)):
            deny('selection_context_changed',409)
        context={'release_id':str(release.id),'snapshot_id':str(snapshot.id),
                 'release_decision_id':str(decision.id),'project_id':str(project_id)}
        return context,detail,package,distribution

    @staticmethod
    def page(context, items, limit, offset):
        more=len(items)>limit
        return {'context':context,'items':items[:limit],'limit':limit,'offset':offset,
                'next_offset':offset+limit if more and offset+limit<=100000 else None}

    def artifacts(self, request, release_id, recipient_type, recipient_code, purpose, limit=20, offset=0,
                  expected_snapshot_id=None, expected_decision_id=None):
        try:
            context,_,_,_=self.source(request,'release',release_id,'DISTRIBUTION_AUTHORITY',expected_snapshot_id,expected_decision_id)
            context.update(recipient_type=recipient_type,recipient_code=recipient_code,purpose=purpose)
            # Aggregate each tier in SQL. Duplicate nullable generic rules fail closed unless
            # every rule agrees; specific rules always take precedence over generic rules.
            def tier(code):
                return select(Rule.snapshot_artifact_id.label('artifact_id'),func.min(Rule.decision).label('lo'),
                    func.max(Rule.decision).label('hi')).where(Rule.recipient_type==recipient_type,
                    Rule.purpose==purpose,Rule.recipient_code.is_(None) if code is None else Rule.recipient_code==code
                    ).group_by(Rule.snapshot_artifact_id).subquery()
            specific,generic=tier(recipient_code),tier(None)
            selected=case((specific.c.artifact_id.is_not(None),case((specific.c.lo==specific.c.hi,specific.c.lo),else_='DENY')),
                else_=case((generic.c.lo==generic.c.hi,generic.c.lo),else_='DENY'))
            stmt=select(SnapshotArtifact.id.label('snapshot_artifact_id'),SnapshotArtifact.filename,
                SnapshotArtifact.artifact_type,SnapshotArtifact.component_code,SnapshotArtifact.component_version,
                SnapshotArtifact.sha256,selected.label('policy_decision')).outerjoin(specific,specific.c.artifact_id==SnapshotArtifact.id
                ).outerjoin(generic,generic.c.artifact_id==SnapshotArtifact.id).where(
                SnapshotArtifact.snapshot_id==uuid.UUID(context['snapshot_id']),SnapshotArtifact.distribution_level!='INTERNAL_ONLY',
                selected.in_(['ALLOW','APPROVAL_REQUIRED'])).order_by(SnapshotArtifact.id).offset(offset).limit(limit+1)
            items=[dict(row) for row in self.db.execute(stmt).mappings()]
            return self.page(context,items,limit,offset)
        finally:self.db.rollback()

    def package(self, request, package_id, expected_snapshot_id=None, expected_decision_id=None):
        try:
            context,_,package,_=self.source(request,'package',package_id,'DISTRIBUTION_AUTHORITY',expected_snapshot_id,expected_decision_id)
            context.update(delivery_package_id=str(package.id),package_no=package.package_no,revision=package.revision,
                recipient_type=package.recipient_type,recipient_code=package.recipient_code,purpose=package.purpose,status=package.status)
            return {'context':context}
        finally:self.db.rollback()

    def scope(self, request, distribution_id, limit=20, offset=0, expected_snapshot_id=None, expected_decision_id=None):
        try:
            context,detail,package,distribution=self.source(request,'distribution',distribution_id,'PRODUCTION_AUTHORITY',expected_snapshot_id,expected_decision_id)
            customer=self.db.get(Customer,detail.customer_id);project=self.db.get(Project,detail.project_id)
            if (not customer or not project or project.customer_id!=customer.id or distribution.recipient_type!='CUSTOMER' or
                    distribution.recipient_code!=customer.code or package.recipient_type!=distribution.recipient_type or
                    package.recipient_code!=distribution.recipient_code): deny('selection_context_ineligible',409)
            context.update(distribution_id=str(distribution.id),distribution_no=distribution.distribution_no,
                delivery_package_id=str(package.id),package_no=package.package_no,revision=package.revision,
                customer_id=str(customer.id),purpose=package.purpose,recipient_type=distribution.recipient_type,
                recipient_code=distribution.recipient_code)
            stmt=select(ManufacturingSite.id.label('site_id'),ManufacturingSite.site_code,ManufacturingSite.name.label('site_name'),
                ProductionLine.id.label('line_id'),ProductionLine.line_code,ProductionLine.name.label('line_name')).join(
                ProductionLine,ProductionLine.site_id==ManufacturingSite.id).where(ManufacturingSite.customer_id==customer.id,
                ManufacturingSite.project_id==detail.project_id,ManufacturingSite.status=='ACTIVE',ProductionLine.status=='ACTIVE'
                ).order_by(ManufacturingSite.id,ProductionLine.id).offset(offset).limit(limit+1)
            return self.page(context,[dict(row) for row in self.db.execute(stmt).mappings()],limit,offset)
        finally:self.db.rollback()
