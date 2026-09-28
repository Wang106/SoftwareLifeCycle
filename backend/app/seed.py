import hashlib
from app.core.db import SessionLocal
from app.models.core import *
from app.models.snapshot import ReleaseSnapshot
from app.models.change import SoftwareChangeRequest, AcceptanceCriterion, ChangePoint, Issue, IssueChangeRequestRelation
from app.models.testing import DvpPlan, DvpItem, ChangePointDvpItem, IssueDvpItem, TestRelease, DvpExecution
from app.models.governance import PolicyException
from app.models.policy import ArtifactDistributionRule
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction, ReleaseDecision

def h(name):
    return hashlib.sha256(name.encode()).hexdigest()

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

    if not db.query(Artifact).filter_by(filename="CustomerA_BMS.hex").first():
        db.add_all([
            Artifact(release_component_id=c1.id, artifact_type="HEX", filename="CustomerA_BMS.hex", storage_reference="managed://CustomerA_BMS.hex", sha256=h("hex"), controlled=True, classification="CONFIDENTIAL", distribution_level="EXTERNAL", ai_access_policy="DENY"),
            Artifact(release_component_id=c1.id, artifact_type="ELF", filename="BMS.elf", storage_reference="managed://BMS.elf", sha256=h("elf"), controlled=True, classification="STRICTLY_CONFIDENTIAL", distribution_level="INTERNAL_ONLY", ai_access_policy="LOCAL_ONLY"),
            Artifact(release_component_id=c2.id, artifact_type="A2L", filename="CustomerA_BMS.a2l", storage_reference="managed://CustomerA_BMS.a2l", sha256=h("a2l"), controlled=True, classification="CONFIDENTIAL", distribution_level="CONTROLLED_EXTERNAL", ai_access_policy="LOCAL_ONLY"),
        ])

    db.flush()
    artifacts = {a.filename: a for a in db.query(Artifact).join(ReleaseComponent, ReleaseComponent.id == Artifact.release_component_id).filter(ReleaseComponent.release_id == asr.id).all()}
    policy_specs = [
        ("CustomerA_BMS.hex", "CUSTOMER", "PRODUCTION", "ALLOW", "CUS-001"),
        ("CustomerA_BMS.a2l", "CUSTOMER", "PRODUCTION", "APPROVAL_REQUIRED", "CUS-001"),
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

    approval = db.query(ApprovalRequest).filter_by(approval_no="APR-0121").first()
    if not approval:
        approval = ApprovalRequest(
            approval_no="APR-0121",
            target_type="RELEASE",
            target_id=asr.id,
            snapshot_id=snap8.id,
            status="PENDING",
            submitted_by="Release Manager",
        )
        db.add(approval)
        db.flush()

        step_specs = [
            (1, "Software Lead", "Software Lead", "APPROVED"),
            (2, "Test Lead", "Test Lead", "APPROVED"),
            (3, "Quality Manager", "Quality Manager", "PENDING"),
            (4, "Release Manager", "Release Manager", "WAITING"),
        ]
        steps = {}
        for order, role, approver, status in step_specs:
            step = ApprovalStep(
                approval_request_id=approval.id,
                step_order=order,
                role_name=role,
                approver_name=approver,
                status=status,
            )
            db.add(step)
            db.flush()
            steps[order] = step

        db.add_all([
            ApprovalAction(
                approval_request_id=approval.id,
                step_id=steps[1].id,
                actor_name="Software Lead",
                action="APPROVED",
                comment="Change scope and release delta reviewed.",
            ),
            ApprovalAction(
                approval_request_id=approval.id,
                step_id=steps[2].id,
                actor_name="Test Lead",
                action="APPROVED",
                comment="Current snapshot verification evidence confirmed.",
            ),
        ])

    db.commit()

if __name__ == "__main__":
    run()
