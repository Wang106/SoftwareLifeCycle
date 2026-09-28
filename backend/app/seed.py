import hashlib
import json
from datetime import datetime, timezone

from app.core.db import SessionLocal
from app.models.core import *
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.models.change import SoftwareChangeRequest, AcceptanceCriterion, ChangePoint, Issue, IssueChangeRequestRelation
from app.models.testing import DvpPlan, DvpItem, ChangePointDvpItem, IssueDvpItem, TestRelease, DvpExecution
from app.models.governance import PolicyException
from app.models.policy import ArtifactDistributionRule
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction, ReleaseDecision
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution, SoftwareAuthorization
from app.models.production import Deployment, ManufacturingSite, ProductionBatch, ProductionLine, SoftwareChangeover

def h(name):
    return hashlib.sha256(name.encode()).hexdigest()


def freeze_snapshot_artifacts(db, snapshot, release):
    """Materialize the demo release content and policy into an immutable snapshot."""
    rows = db.query(Artifact, ReleaseComponent, ComponentDefinition).join(
        ReleaseComponent, Artifact.release_component_id == ReleaseComponent.id
    ).join(
        ComponentDefinition,
        ReleaseComponent.component_definition_id == ComponentDefinition.id,
    ).filter(ReleaseComponent.release_id == release.id).all()

    payload = []
    frozen = {}
    for artifact, component, definition in rows:
        source_rules = db.query(ArtifactDistributionRule).filter_by(
            artifact_id=artifact.id
        ).all()
        rule_payload = sorted(
            [
                {
                    "recipient_type": rule.recipient_type,
                    "purpose": rule.purpose,
                    "decision": rule.decision,
                    "recipient_code": rule.recipient_code,
                }
                for rule in source_rules
            ],
            key=lambda item: (
                item["recipient_type"],
                item["purpose"],
                item["recipient_code"] or "",
                item["decision"],
            ),
        )
        payload.append(
            {
                "component": definition.code,
                "component_version": component.version,
                "filename": artifact.filename,
                "sha256": artifact.sha256,
                "classification": artifact.classification,
                "distribution_level": artifact.distribution_level,
                "ai_access_policy": artifact.ai_access_policy,
                "distribution_rules": rule_payload,
            }
        )

        row = db.query(SnapshotArtifact).filter_by(
            snapshot_id=snapshot.id,
            source_artifact_id=artifact.id,
        ).first()
        if not row:
            row = SnapshotArtifact(snapshot_id=snapshot.id, source_artifact_id=artifact.id)
            db.add(row)
        row.component_code = definition.code
        row.component_version = component.version
        row.filename = artifact.filename
        row.artifact_type = artifact.artifact_type
        row.sha256 = artifact.sha256
        row.classification = artifact.classification
        row.distribution_level = artifact.distribution_level
        row.ai_access_policy = artifact.ai_access_policy
        row.storage_reference = artifact.storage_reference
        db.flush()
        frozen[artifact.filename] = row

        for rule in source_rules:
            frozen_rule = db.query(SnapshotArtifactDistributionRule).filter_by(
                snapshot_artifact_id=row.id,
                recipient_type=rule.recipient_type,
                purpose=rule.purpose,
                recipient_code=rule.recipient_code,
            ).first()
            if not frozen_rule:
                frozen_rule = SnapshotArtifactDistributionRule(
                    snapshot_artifact_id=row.id,
                    recipient_type=rule.recipient_type,
                    purpose=rule.purpose,
                    recipient_code=rule.recipient_code,
                )
                db.add(frozen_rule)
            frozen_rule.decision = rule.decision

    payload.sort(key=lambda item: (item["component"], item["filename"]))
    snapshot.release_metadata_json = {
        "version": release.version,
        "release_type": release.release_type,
    }
    snapshot.content_hash = hashlib.sha256(
        json.dumps(
            {"release": release.version, "artifacts": payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    snapshot.status = "FROZEN"
    return frozen

def run():
    db = SessionLocal()

    supplier = db.query(Supplier).filter_by(code="SUP-001").first()
    if not supplier:
        supplier = Supplier(code="SUP-001", name="Supplier A", country="DE", status="ACTIVE")
        db.add(supplier)
    customer = db.query(Customer).filter_by(code="CUS-001").first()
    if not customer:
        customer = Customer(code="CUS-001", name="Customer A", status="ACTIVE")
        db.add(customer)
    db.flush()

    project = db.query(Project).filter_by(customer_id=customer.id, project_code="PRJ-X").first()
    if not project:
        project = Project(customer_id=customer.id, project_code="PRJ-X", name="Project X", vehicle_platform="EV Platform X", status="ACTIVE")
        db.add(project)
    software = db.query(SoftwareProduct).filter_by(code="SW-BMS-001").first()
    if not software:
        software = SoftwareProduct(supplier_id=supplier.id, code="SW-BMS-001", name="BMS Standard", software_type="BMS", status="ACTIVE")
        db.add(software)
    db.flush()

    ssr = db.query(Release).filter_by(software_id=software.id, release_type="STANDARD", version="5.1.12").first()
    if not ssr:
        ssr = Release(software_id=software.id, release_type="STANDARD", version="5.1.12", status="RELEASED")
        db.add(ssr)
        db.flush()
        db.add(StandardReleaseDetail(release_id=ssr.id, git_branch="main", git_commit="demo512"))

    asr = db.query(Release).filter_by(software_id=software.id, release_type="APPLICATION", version="2.3.4").first()
    if not asr:
        asr = Release(software_id=software.id, release_type="APPLICATION", version="2.3.4", status="READY")
        db.add(asr)
        db.flush()
        db.add(ApplicationReleaseDetail(release_id=asr.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=ssr.id))
    db.flush()

    previous_asr = db.query(Release).filter_by(
        software_id=software.id,
        release_type="APPLICATION",
        version="2.3.3",
    ).first()
    if not previous_asr:
        previous_asr = Release(
            software_id=software.id,
            release_type="APPLICATION",
            version="2.3.3",
            status="SUPERSEDED",
        )
        db.add(previous_asr)
        db.flush()
    if not db.get(ApplicationReleaseDetail, previous_asr.id):
        db.add(ApplicationReleaseDetail(
            release_id=previous_asr.id,
            customer_id=customer.id,
            project_id=project.id,
            standard_base_release_id=ssr.id,
        ))
    db.flush()

    main = db.query(ComponentDefinition).filter_by(code="MAIN_APPLICATION").first()
    if not main:
        main = ComponentDefinition(code="MAIN_APPLICATION", name="Main Application")
        db.add(main)
    cal = db.query(ComponentDefinition).filter_by(code="CALIBRATION").first()
    if not cal:
        cal = ComponentDefinition(code="CALIBRATION", name="Calibration")
        db.add(cal)
    db.flush()

    c1 = db.query(ReleaseComponent).filter_by(release_id=asr.id, component_definition_id=main.id).first()
    if not c1:
        c1 = ReleaseComponent(release_id=asr.id, component_definition_id=main.id, version="2.3.4", delta_type="MODIFIED")
        db.add(c1)
    c2 = db.query(ReleaseComponent).filter_by(release_id=asr.id, component_definition_id=cal.id).first()
    if not c2:
        c2 = ReleaseComponent(release_id=asr.id, component_definition_id=cal.id, version="CAL-32", delta_type="MODIFIED")
        db.add(c2)
    db.flush()

    artifact_specs = [
        (c1, "HEX", "CustomerA_BMS.hex", "hex", "CONFIDENTIAL", "EXTERNAL", "DENY"),
        (c1, "ELF", "BMS.elf", "elf", "STRICTLY_CONFIDENTIAL", "INTERNAL_ONLY", "LOCAL_ONLY"),
        (c1, "DBC", "CustomerA.dbc", "dbc", "CONFIDENTIAL", "EXTERNAL", "DENY"),
        (c2, "A2L", "CustomerA_BMS.a2l", "a2l", "CONFIDENTIAL", "CONTROLLED_EXTERNAL", "LOCAL_ONLY"),
    ]
    for component, artifact_type, filename, digest_name, classification, distribution_level, ai_policy in artifact_specs:
        artifact = db.query(Artifact).filter_by(
            release_component_id=component.id,
            filename=filename,
        ).first()
        if not artifact:
            artifact = Artifact(
                release_component_id=component.id,
                artifact_type=artifact_type,
                filename=filename,
                storage_reference=f"managed://{filename}",
                sha256=h(digest_name),
                controlled=True,
                classification=classification,
                distribution_level=distribution_level,
                ai_access_policy=ai_policy,
            )
            db.add(artifact)

    db.flush()
    artifacts = {a.filename: a for a in db.query(Artifact).join(ReleaseComponent, ReleaseComponent.id == Artifact.release_component_id).filter(ReleaseComponent.release_id == asr.id).all()}
    policy_specs = [
        ("CustomerA_BMS.hex", "CUSTOMER", "PRODUCTION", "ALLOW", "CUS-001"),
        ("CustomerA_BMS.a2l", "CUSTOMER", "PRODUCTION", "APPROVAL_REQUIRED", "CUS-001"),
        ("CustomerA.dbc", "CUSTOMER", "PRODUCTION", "ALLOW", "CUS-001"),
    ]
    for filename, recipient_type, purpose, decision, recipient_code in policy_specs:
        artifact = artifacts.get(filename)
        if artifact and not db.query(ArtifactDistributionRule).filter_by(
            artifact_id=artifact.id,
            recipient_type=recipient_type,
            purpose=purpose,
            recipient_code=recipient_code,
        ).first():
            db.add(ArtifactDistributionRule(
                artifact_id=artifact.id,
                recipient_type=recipient_type,
                purpose=purpose,
                decision=decision,
                recipient_code=recipient_code,
                notes="Demo recipient-specific production distribution policy.",
            ))

    snap7 = db.query(ReleaseSnapshot).filter_by(snapshot_no="SNAP-007").first()
    if not snap7:
        snap7 = ReleaseSnapshot(snapshot_no="SNAP-007", release_id=asr.id, snapshot_number=7, status="FROZEN", release_metadata_json={"version":"2.3.4"}, content_hash=h("snap7"))
        db.add(snap7)
    snap8 = db.query(ReleaseSnapshot).filter_by(snapshot_no="SNAP-008").first()
    if not snap8:
        snap8 = ReleaseSnapshot(snapshot_no="SNAP-008", release_id=asr.id, snapshot_number=8, status="FROZEN", release_metadata_json={"version":"2.3.4"}, content_hash=h("snap8"))
        db.add(snap8)
    db.flush()

    snapshot_artifacts = freeze_snapshot_artifacts(db, snap8, asr)
    db.flush()

    issue = db.query(Issue).filter_by(issue_no="310").first()
    if not issue:
        issue = Issue(issue_no="310", title="Low-temperature charging timeout", scope="STANDARD", severity="HIGH", status="FIX_VERIFIED", description="Charging timeout observed under low-temperature conditions.")
        db.add(issue)

    scr = db.query(SoftwareChangeRequest).filter_by(request_no="SCR-142").first()
    if not scr:
        scr = SoftwareChangeRequest(request_no="SCR-142", title="Charging timeout & low-temperature calibration", source="ISSUE", scope="STANDARD", change_type="BUG_FIX", software_id=software.id, customer_id=customer.id, project_id=project.id, status="IN_TEST", background="Issue #310", requirement="Improve timeout handling and calibration behavior.")
        db.add(scr)
    db.flush()

    if not db.query(IssueChangeRequestRelation).filter_by(issue_id=issue.id, change_request_id=scr.id, relation_type="FIXED_BY").first():
        db.add(IssueChangeRequestRelation(issue_id=issue.id, change_request_id=scr.id, relation_type="FIXED_BY"))
    if not db.query(AcceptanceCriterion).filter_by(change_request_id=scr.id, criterion_no="AC-001").first():
        db.add(AcceptanceCriterion(change_request_id=scr.id, criterion_no="AC-001", description="Low-temperature charging timeout behavior passes verification on current snapshot."))

    cp1 = db.query(ChangePoint).filter_by(change_request_id=scr.id, change_no="CP-001").first()
    if not cp1:
        cp1 = ChangePoint(change_request_id=scr.id, change_no="CP-001", title="Charging timeout algorithm", description="Update timeout state logic.", status="VERIFIED")
        db.add(cp1)
    cp2 = db.query(ChangePoint).filter_by(change_request_id=scr.id, change_no="CP-002").first()
    if not cp2:
        cp2 = ChangePoint(change_request_id=scr.id, change_no="CP-002", title="Low-temperature calibration", description="Update calibration thresholds.", status="IN_VERIFICATION")
        db.add(cp2)
    db.flush()

    plan = db.query(DvpPlan).filter_by(plan_no="DVP-PLAN-142").first()
    if not plan:
        plan = DvpPlan(change_request_id=scr.id, plan_no="DVP-PLAN-142", title="SCR-142 Verification Plan", status="IN_PROGRESS")
        db.add(plan)
    db.flush()

    items = {}
    specs = [
        ("DVP-031","Normal charging regression","SOFTWARE_TEST","COMPLETED"),
        ("DVP-032","Low-temp charging timeout","SOFTWARE_TEST","COMPLETED"),
        ("DVP-033","Calibration boundary verification","BATTERY_TEST","COMPLETED"),
        ("DVP-034","Low-temp endurance validation","BATTERY_TEST","IN_PROGRESS"),
    ]
    for no,title,scope,status in specs:
        item = db.query(DvpItem).filter_by(plan_id=plan.id, item_no=no).first()
        if not item:
            item = DvpItem(plan_id=plan.id, item_no=no, title=title, scope=scope, status=status)
            db.add(item)
            db.flush()
        items[no] = item

    for cp,item_no in [(cp1,"DVP-032"),(cp2,"DVP-033"),(cp2,"DVP-034")]:
        if not db.query(ChangePointDvpItem).filter_by(change_point_id=cp.id, dvp_item_id=items[item_no].id).first():
            db.add(ChangePointDvpItem(change_point_id=cp.id, dvp_item_id=items[item_no].id))
    if not db.query(IssueDvpItem).filter_by(issue_id=issue.id, dvp_item_id=items["DVP-032"].id).first():
        db.add(IssueDvpItem(issue_id=issue.id, dvp_item_id=items["DVP-032"].id))

    tr58 = db.query(TestRelease).filter_by(test_release_no="TR-0058").first()
    if not tr58:
        tr58 = TestRelease(test_release_no="TR-0058", release_id=asr.id, snapshot_id=snap7.id, purpose_scope="SOFTWARE_TEST", status="SUPERSEDED")
        db.add(tr58)
    tr61 = db.query(TestRelease).filter_by(test_release_no="TR-0061").first()
    if not tr61:
        tr61 = TestRelease(test_release_no="TR-0061", release_id=asr.id, snapshot_id=snap8.id, purpose_scope="SOFTWARE_TEST", status="ACTIVE")
        db.add(tr61)
    db.flush()

    executions = [
        (items["DVP-031"],1,snap8,tr61,"PASS","Normal charging regression passed."),
        (items["DVP-032"],1,snap7,tr58,"FAIL","Timeout reproduced on SNAP-007."),
        (items["DVP-032"],2,snap8,tr61,"PASS","Retest passed after CP-001 fix."),
        (items["DVP-033"],1,snap8,tr61,"PASS","Calibration boundary verification passed."),
    ]
    for item,no,snapshot,test_release,result,actual in executions:
        if not db.query(DvpExecution).filter_by(dvp_item_id=item.id, execution_no=no).first():
            db.add(DvpExecution(dvp_item_id=item.id, execution_no=no, release_id=asr.id, snapshot_id=snapshot.id, test_release_id=test_release.id, result=result, actual_result=actual))

    pex = db.query(PolicyException).filter_by(exception_no="PEX-0018").first()
    if not pex:
        pex = PolicyException(
            exception_no="PEX-0018",
            snapshot_id=snap8.id,
            rule_code="VERIFICATION_CURRENT_SNAPSHOT_COMPLETE",
            scope="Verification",
            status="APPROVED",
            reason="DVP-034 endurance test pending.",
            compensating_control="Restricted initial production authorization.",
            approved_by="Quality Manager",
        )
        db.add(pex)

    seeded_at = datetime.now(timezone.utc)
    approval = db.query(ApprovalRequest).filter_by(approval_no="APR-0121").first()
    if not approval:
        approval = ApprovalRequest(approval_no="APR-0121")
        db.add(approval)
    approval.target_type = "RELEASE"
    approval.target_id = asr.id
    approval.snapshot_id = snap8.id
    approval.status = "APPROVED"
    approval.submitted_by = "Release Manager"
    approval.submitted_at = approval.submitted_at or seeded_at
    db.flush()

    step_specs = [
        (1, "Software Lead", "Software Lead", "Change scope and release delta reviewed."),
        (2, "Test Lead", "Test Lead", "Current snapshot verification evidence confirmed."),
        (3, "Quality Manager", "Quality Manager", "PEX-0018 and compensating control approved."),
        (4, "Release Manager", "Release Manager", "Release approval completed for SNAP-008."),
    ]
    steps = {}
    for order, role, approver, comment in step_specs:
        step = db.query(ApprovalStep).filter_by(
            approval_request_id=approval.id,
            step_order=order,
        ).first()
        if not step:
            step = ApprovalStep(
                approval_request_id=approval.id,
                step_order=order,
                role_name=role,
            )
            db.add(step)
        step.role_name = role
        step.approver_name = approver
        step.status = "APPROVED"
        step.decided_at = step.decided_at or seeded_at
        db.flush()
        steps[order] = step
        if not db.query(ApprovalAction).filter_by(
            approval_request_id=approval.id,
            step_id=step.id,
            action="APPROVED",
        ).first():
            db.add(
                ApprovalAction(
                    approval_request_id=approval.id,
                    step_id=step.id,
                    actor_name=approver,
                    action="APPROVED",
                    comment=comment,
                )
            )

    decision = db.query(ReleaseDecision).filter_by(decision_no="RD-0081").first()
    if not decision:
        decision = ReleaseDecision(decision_no="RD-0081")
        db.add(decision)
    decision.release_id = asr.id
    decision.snapshot_id = snap8.id
    decision.approval_request_id = approval.id
    decision.readiness_status = "READY_WITH_EXCEPTION"
    decision.decision = "RELEASE"
    decision.decided_by = "Release Manager"
    decision.decision_notes = "Released with PEX-0018 controlled initial-production restriction."
    decision.decided_at = decision.decided_at or seeded_at
    asr.status = "RELEASED"
    db.flush()

    package = db.query(DeliveryPackage).filter_by(
        package_no="DP-0226",
        revision=1,
    ).first()
    if not package:
        package = DeliveryPackage(package_no="DP-0226", revision=1)
        db.add(package)
    package.release_id = asr.id
    package.snapshot_id = snap8.id
    package.recipient_type = "CUSTOMER"
    package.recipient_code = customer.code
    package.purpose = "PRODUCTION"
    package.status = "DISTRIBUTED"
    package.created_by = "Release Manager"
    db.flush()

    delivery_specs = [
        ("CustomerA_BMS.hex", "ALLOW", None),
        ("CustomerA_BMS.a2l", "APPROVAL_REQUIRED", approval.approval_no),
        ("CustomerA.dbc", "ALLOW", None),
    ]
    for filename, policy_decision, control_reference in delivery_specs:
        frozen_artifact = snapshot_artifacts[filename]
        package_item = db.query(DeliveryPackageItem).filter_by(
            delivery_package_id=package.id,
            snapshot_artifact_id=frozen_artifact.id,
        ).first()
        if not package_item:
            package_item = DeliveryPackageItem(
                delivery_package_id=package.id,
                snapshot_artifact_id=frozen_artifact.id,
                policy_decision=policy_decision,
            )
            db.add(package_item)
        package_item.policy_decision = policy_decision
        package_item.exception_reference = control_reference

    distribution = db.query(Distribution).filter_by(distribution_no="DIST-0326").first()
    if not distribution:
        distribution = Distribution(distribution_no="DIST-0326")
        db.add(distribution)
    distribution.delivery_package_id = package.id
    distribution.recipient_type = "CUSTOMER"
    distribution.recipient_code = customer.code
    distribution.status = "ACKNOWLEDGED"
    distribution.sent_at = distribution.sent_at or seeded_at
    distribution.acknowledged_at = distribution.acknowledged_at or seeded_at
    distribution.note = "DP-0226 Rev1 delivered and acknowledged by Customer A."
    db.flush()

    authorization = db.query(SoftwareAuthorization).filter_by(
        authorization_no="PA-0081"
    ).first()
    if not authorization:
        authorization = SoftwareAuthorization(authorization_no="PA-0081")
        db.add(authorization)
    authorization.distribution_id = distribution.id
    authorization.release_id = asr.id
    authorization.snapshot_id = snap8.id
    authorization.customer_id = customer.id
    authorization.project_id = project.id
    authorization.site_code = "FACTORY-A"
    authorization.line_code = "LINE-2"
    authorization.purpose = "PRODUCTION"
    authorization.status = "APPROVED"
    authorization.batch_limit = 1
    authorization.restriction_note = (
        "PEX-0018: controlled initial production batch only while DVP-034 remains incomplete."
    )
    authorization.approved_at = authorization.approved_at or seeded_at

    site = db.query(ManufacturingSite).filter_by(site_code="FACTORY-A").first()
    if not site:
        site = ManufacturingSite(site_code="FACTORY-A")
        db.add(site)
    site.customer_id = customer.id
    site.project_id = project.id
    site.name = "Factory A"
    site.region = "APAC"
    site.status = "ACTIVE"
    db.flush()

    line = db.query(ProductionLine).filter_by(
        site_id=site.id,
        line_code="LINE-2",
    ).first()
    if not line:
        line = ProductionLine(site_id=site.id, line_code="LINE-2")
        db.add(line)
    line.name = "Line 2"
    line.status = "ACTIVE"
    db.flush()

    deployment = db.query(Deployment).filter_by(deployment_no="DEP-0081").first()
    if not deployment:
        deployment = Deployment(deployment_no="DEP-0081")
        db.add(deployment)
    deployment.authorization_id = authorization.id
    deployment.production_line_id = line.id
    deployment.expected_release_id = asr.id
    deployment.expected_snapshot_id = snap8.id
    deployment.actual_release_id = asr.id
    deployment.actual_snapshot_id = snap8.id
    deployment.status = "MATCH"
    deployment.deployed_at = deployment.deployed_at or seeded_at
    db.flush()

    changeover = db.query(SoftwareChangeover).filter_by(
        changeover_no="CO-0032"
    ).first()
    if not changeover:
        changeover = SoftwareChangeover(changeover_no="CO-0032")
        db.add(changeover)
    changeover.deployment_id = deployment.id
    changeover.authorization_id = authorization.id
    changeover.from_release_id = previous_asr.id
    changeover.to_release_id = asr.id
    changeover.status = "COMPLETED"
    changeover.changed_at = changeover.changed_at or seeded_at
    changeover.note = "Controlled changeover from ASR 2.3.3 to authorized ASR 2.3.4."
    db.flush()

    batch = db.query(ProductionBatch).filter_by(batch_no="PB-1005-A").first()
    if not batch:
        batch = ProductionBatch(batch_no="PB-1005-A")
        db.add(batch)
    batch.deployment_id = deployment.id
    batch.changeover_id = changeover.id
    batch.authorization_id = authorization.id
    batch.release_id = asr.id
    batch.snapshot_id = snap8.id
    batch.status = "ACTIVE"
    batch.started_at = batch.started_at or seeded_at
    batch.note = "Initial controlled production batch under PEX-0018 restriction."

    db.commit()

if __name__ == "__main__":
    run()
