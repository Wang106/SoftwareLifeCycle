"""Minimal, explicitly authorized evidence preparation reads; never write authority."""
from sqlalchemy import select
from app.models.security import ProjectMembership
from app.models.core import Release, ApplicationReleaseDetail, Project
from app.models.change import SoftwareChangeRequest, AcceptanceCriterion, Issue, IssueChangeRequestRelation
from app.models.approval import ApprovalRequest, ApprovalStep
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpPlan, DvpItem, TestRelease, DvpExecution
from app.services.private_distribution_selection import PrivateDistributionSelection, deny


class PrivateEvidenceSelection(PrivateDistributionSelection):
    """Reuse current USER/session locking, not the distribution eligibility policy."""
    def role(self, actor, projects, role):
        projects = sorted(set(projects), key=str)
        if not projects or any(p is None for p in projects): deny()
        for project in projects:
            member = self.db.scalar(select(ProjectMembership).where(
                ProjectMembership.principal_id == actor.id, ProjectMembership.project_id == project,
                ProjectMembership.role == role, ProjectMembership.status == 'ACTIVE').with_for_update()
                .execution_options(populate_existing=True))
            if member is None: deny()
        return projects

    def release_project(self, release_id):
        detail = self.db.get(ApplicationReleaseDetail, release_id, populate_existing=True)
        release = self.db.get(Release, release_id, populate_existing=True)
        if not detail or not release or release.release_type != 'APPLICATION': deny()
        return detail.project_id

    def change(self, request_no):
        row = self.db.scalar(select(SoftwareChangeRequest).where(SoftwareChangeRequest.request_no == request_no))
        if not row or row.project_id is None: deny()
        return row

    def linked(self, issue_id):
        return self.db.execute(select(SoftwareChangeRequest.project_id, SoftwareChangeRequest.software_id)
            .join(IssueChangeRequestRelation, IssueChangeRequestRelation.change_request_id == SoftwareChangeRequest.id)
            .where(IssueChangeRequestRelation.issue_id == issue_id)).all()

    def approval(self, request, approval_no):
        try:
            actor = self.principal(request)
            approval = self.db.scalar(select(ApprovalRequest).where(ApprovalRequest.approval_no == approval_no))
            if not approval: deny()
            if approval.target_type == 'RELEASE': project = self.release_project(approval.target_id)
            elif approval.target_type == 'SCR':
                change = self.db.get(SoftwareChangeRequest, approval.target_id)
                if not change: deny()
                project = change.project_id
            else: deny()
            target = (approval.target_type, approval.target_id)
            self.role(actor, [project], 'REVIEWER')
            # Match the existing approval writer's parent -> step order.
            approval = self.lock(ApprovalRequest, approval.id)
            if not approval or (approval.target_type, approval.target_id) != target: deny()
            if approval.target_type == 'RELEASE': current = self.release_project(approval.target_id)
            else:
                change = self.db.get(SoftwareChangeRequest, approval.target_id, populate_existing=True)
                current = change.project_id if change else None
            if current != project: deny()
            if approval.status in ('APPROVED','REJECTED','RETURNED','CANCELLED'): deny('selection_context_ineligible',409)
            step = self.db.scalar(select(ApprovalStep).where(ApprovalStep.approval_request_id == approval.id,
                ApprovalStep.status.in_(['PENDING','WAITING'])).order_by(ApprovalStep.step_order)
                .limit(1).with_for_update().execution_options(populate_existing=True))
            if not step: deny()
            return {'context':{'approval_id':str(approval.id),'approval_no':approval.approval_no,
                'project_id':str(project),'target_type':approval.target_type,'target_id':str(approval.target_id),
                'snapshot_id':str(approval.snapshot_id) if approval.snapshot_id else None,'status':approval.status},
                'step':{'step_id':str(step.id),'step_order':step.step_order,'role_name':step.role_name,'status':step.status}}
        finally: self.db.rollback()

    def changes(self, request, request_no, kind, limit=20, offset=0):
        try:
            actor = self.principal(request); change = self.change(request_no)
            project = change.project_id; self.role(actor,[project],'CONTRIBUTOR')
            change = self.lock(SoftwareChangeRequest,change.id)
            if not change or change.project_id != project: deny()
            context = {'change_request_id':str(change.id),'request_no':change.request_no,'project_id':str(project)}
            if kind == 'criteria':
                stmt = select(AcceptanceCriterion.id.label('criterion_id'),AcceptanceCriterion.criterion_no,
                    AcceptanceCriterion.description).where(AcceptanceCriterion.change_request_id == change.id).order_by(AcceptanceCriterion.id)
            else:
                stmt = select(DvpItem.id.label('dvp_item_id'),DvpItem.item_no,DvpItem.title,
                    DvpPlan.id.label('plan_id'),DvpPlan.plan_no).join(DvpPlan,DvpPlan.id == DvpItem.plan_id
                    ).where(DvpPlan.change_request_id == change.id).order_by(DvpItem.id)
            return self.page(context,[dict(r) for r in self.db.execute(stmt.offset(offset).limit(limit+1)).mappings()],limit,offset)
        finally: self.db.rollback()

    def snapshots(self, request, issue_no, release_id, limit=20, offset=0):
        try:
            actor = self.principal(request)
            issue = self.db.scalar(select(Issue).where(Issue.issue_no == issue_no))
            if not issue: deny()
            project = self.release_project(release_id); self.role(actor,[project],'REVIEWER')
            issue = self.lock(Issue,issue.id); release = self.lock(Release,release_id)
            links = self.linked(issue.id)
            if (self.release_project(release.id) != project or project not in {r.project_id for r in links}
                    or release.software_id not in {r.software_id for r in links}): deny()
            stmt = select(ReleaseSnapshot.id.label('snapshot_id'),ReleaseSnapshot.snapshot_no,
                ReleaseSnapshot.snapshot_number,ReleaseSnapshot.status).where(ReleaseSnapshot.release_id == release.id,
                ReleaseSnapshot.status == 'FROZEN').order_by(ReleaseSnapshot.id).offset(offset).limit(limit+1)
            context = {'issue_id':str(issue.id),'issue_no':issue.issue_no,'release_id':str(release.id),'project_id':str(project)}
            return self.page(context,[dict(r) for r in self.db.execute(stmt).mappings()],limit,offset)
        finally: self.db.rollback()

    def resource_target(self, kind, identifier):
        models = {'PROJECT':(Project,'project_code'),'RELEASE':(Release,'version'),
            'SNAPSHOT':(ReleaseSnapshot,'snapshot_no'),'SCR':(SoftwareChangeRequest,'request_no'),
            'DVP_ITEM':(DvpItem,'item_no'),'TEST_RELEASE':(TestRelease,'test_release_no'),
            'DVP_EXECUTION':(DvpExecution,'execution_no'),'ISSUE':(Issue,'issue_no')}
        if kind not in models: deny()
        model, ref = models[kind]; row = self.db.get(model,identifier,populate_existing=True)
        if not row: deny()
        if kind == 'PROJECT': projects = [row.id]
        elif kind == 'RELEASE': projects = [self.release_project(row.id)]
        elif kind in ('SNAPSHOT','TEST_RELEASE','DVP_EXECUTION'): projects = [self.release_project(row.release_id)]
        elif kind == 'SCR': projects = [row.project_id]
        elif kind == 'DVP_ITEM':
            plan = self.db.get(DvpPlan,row.plan_id,populate_existing=True)
            change = self.db.get(SoftwareChangeRequest,plan.change_request_id,populate_existing=True) if plan else None
            projects = [change.project_id] if change else []
        else: projects = [r.project_id for r in self.linked(row.id) if r.project_id is not None]
        return model,row,str(getattr(row,ref)),sorted(set(projects),key=str)

    def resource(self, request, entity_type, entity_id):
        try:
            actor = self.principal(request)
            model,row,ref,projects = self.resource_target(entity_type,entity_id)
            self.role(actor,projects,'CONTRIBUTOR'); self.lock(model,row.id)
            _,row,ref,current = self.resource_target(entity_type,entity_id)
            if current != projects: deny()
            return {'context':{'entity_type':entity_type,'entity_id':str(row.id),'entity_ref':ref,
                'project_ids':[str(p) for p in projects]}}
        finally: self.db.rollback()
