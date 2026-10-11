"""Opt-in, isolated SSR/ASR demonstration data; never rewrites existing history."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from sqlalchemy import select

from app.models.core import (Supplier, SoftwareProduct, Customer, Project, Release,
    StandardReleaseDetail, ApplicationReleaseDetail, ComponentDefinition, ReleaseComponent, Artifact)
from app.models.snapshot import ReleaseSnapshot
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction
from app.models.audit import AuditEvent
from app.seed import freeze_snapshot_artifacts

SSR_ROLES = ("电子工程师", "电子经理", "系统工程师", "研发总监")
ASR_ROLES = ("应用工程师", "应用经理", "系统工程师", "项目经理")
PRODUCT_CODE = "DEMO-RELEASE-BMS"
STAMP = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)


def key(name):
    return uuid.uuid5(uuid.NAMESPACE_URL, "softwarelifecycle/release-demo/v1/" + name)


def seed_release_demo(db):
    """Flush only; caller atomically commits the complete new sample family.

    Product UUID is the versioned manifest marker. Existing samples are untouched,
    including any later approvals performed in a private test environment.
    """
    existing = db.scalar(select(SoftwareProduct).where(SoftwareProduct.code == PRODUCT_CODE))
    if existing:
        if existing.id != key("product"):
            raise ValueError("Demo product code is owned by another record")
        return existing.id
    supplier = Supplier(id=key("supplier"), code="DEMO-RELEASE-SUP", name="Demo BMS Supplier")
    db.add(supplier); db.flush()
    product = SoftwareProduct(id=key("product"), supplier_id=supplier.id, code=PRODUCT_CODE,
                              name="SSR / ASR demonstration BMS")
    db.add(product); db.flush()
    definitions = []
    for code, name in (("DEMO-APPLICATION", "Application"), ("DEMO-BOOTLOADER", "Bootloader"),
                       ("DEMO-CALIBRATION", "Calibration")):
        row = ComponentDefinition(id=key(code), code=code, name=name)
        db.add(row); definitions.append(row)
    db.flush()
    releases = []
    components = {}
    for version in ("DEMO-SSR-1.0", "DEMO-SSR-1.1", "DEMO-ASR-A-1.0", "DEMO-ASR-B-1.0"):
        standard = "SSR" in version
        release = Release(id=key(version), software_id=product.id,
            release_type="STANDARD" if standard else "APPLICATION", version=version, status="DRAFT",
            release_notes="Synthetic demonstration only; approval is not a formal release decision.")
        db.add(release); db.flush(); releases.append(release)
        if standard:
            db.add(StandardReleaseDetail(release_id=release.id,
                previous_release_id=releases[0].id if version.endswith("1.1") else None,
                git_branch="demo", git_commit="sample-source-reference"))
        else:
            letter = "A" if "-A-" in version else "B"
            customer = Customer(id=key("customer-" + letter), code="DEMO-RELEASE-" + letter,
                name="Demo Customer " + letter, region="APAC" if letter == "A" else "EUROPE")
            db.add(customer); db.flush()
            project = Project(id=key("project-" + letter), customer_id=customer.id,
                project_code="DEMO-BMS-" + letter, name="Demo BMS Project " + letter)
            db.add(project); db.flush()
            db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=customer.id,
                project_id=project.id, standard_base_release_id=releases[1].id))
        for index, definition in enumerate(definitions):
            base = components.get((releases[1].id, definition.id)) if not standard else None
            unchanged = not standard and index < 2
            component = ReleaseComponent(id=key(version + definition.code), release_id=release.id,
                component_definition_id=definition.id, version=("1.0" if version.endswith("SSR-1.0") else "1.1") if standard or unchanged else version,
                base_component_id=base.id if base else None,
                delta_type="UNCHANGED" if unchanged else "MODIFIED")
            db.add(component); db.flush(); components[(release.id, definition.id)] = component
            filename = version + "_" + definition.name + ".hex"
            db.add(Artifact(id=key(filename), release_component_id=component.id, artifact_type="HEX",
                filename=filename, storage_reference="demo://" + filename,
                sha256=hashlib.sha256(("sample:" + ("DEMO-SSR-1.1" if unchanged else version) + definition.code).encode()).hexdigest(),
                controlled=True, classification="CONFIDENTIAL", distribution_level="INTERNAL_ONLY", ai_access_policy="DENY"))
        db.flush()
        snapshot = ReleaseSnapshot(id=key(version + "snapshot"), snapshot_no="SNAP-" + version,
            release_id=release.id, snapshot_number=1, status="FROZEN", content_hash="0" * 64,
            release_metadata_json={"version": version, "release_type": release.release_type, "sample_only": True})
        db.add(snapshot); db.flush()
        freeze_snapshot_artifacts(db, snapshot, release)
        roles = SSR_ROLES if standard else ASR_ROLES
        scenario = ("PENDING", "APPROVED", "RETURNED", "REJECTED")[len(releases)-1]
        approval = ApprovalRequest(id=key(version + "approval"), approval_no="APR-" + version,
            target_type="RELEASE", target_id=release.id, snapshot_id=snapshot.id, status=scenario,
            submitted_by="Demo submitter", submitted_at=STAMP)
        db.add(approval); db.flush()
        for order, role in enumerate(roles, 1):
            status = "APPROVED" if scenario == "APPROVED" or order == 1 else (
                scenario if order == 2 else "WAITING")
            decided = status in ("APPROVED", "RETURNED", "REJECTED")
            time = STAMP + timedelta(minutes=order)
            step = ApprovalStep(id=key(version + str(order)), approval_request_id=approval.id,
                step_order=order, role_name=role, status=status,
                approver_name="Demo " + role if decided else None, decided_at=time if decided else None)
            db.add(step); db.flush()
            if decided:
                action = ApprovalAction(id=key(version + str(order) + "action"), approval_request_id=approval.id,
                    step_id=step.id, actor_name=step.approver_name, action=status,
                    comment="Synthetic demonstration approval record.", created_at=time)
                db.add(action)
                db.add(AuditEvent(id=key(version + str(order) + "audit"),
                    event_no="EVT-DEMO-" + str(action.id)[:24], event_type="APPROVAL", action=status,
                    entity_type="APPROVAL_REQUEST", entity_id=approval.id, entity_ref=approval.approval_no,
                    actor_name=step.approver_name, summary="Synthetic demonstration approval " + status,
                    detail=action.comment, occurred_at=time,
                    payload_json={"sample_only": True, "approval_action_id": str(action.id),
                        "step_id": str(step.id), "step_order": order, "role_name": role,
                        "snapshot_id": str(snapshot.id), "target_id": str(release.id)}))
    db.flush()
    return product.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-only", action="store_true", required=True,
                        help="Acknowledge this is a dedicated test/demo database")
    parser.parse_args()
    from app.core.db import SessionLocal
    with SessionLocal.begin() as db:
        seed_release_demo(db)
    print("SSR/ASR sample family is present; no identities or submission gates enabled.")


if __name__ == "__main__":
    main()
