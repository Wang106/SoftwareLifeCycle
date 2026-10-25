"""Restore ONLY this operator's trusted synthetic rehearsal package, without its source.

A checksum binds files, it does not authenticate SQL. Never use untrusted archives.
This deliberately supports one fixture/schema and matching PostgreSQL versions,
not production recovery or arbitrary database imports.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import psycopg

from app.ops import postgresql_backup_restore as backup

SUPPORTED_REVISION = "0029_changeover_batch_history"
REPORT_NAME = "retained-synthetic-restore.json"


def read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise backup.RehearsalError("Package input must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise backup.RehearsalError("Package JSON cannot be read") from exc
    if not isinstance(value, dict):
        raise backup.RehearsalError("Package JSON must be an object")
    return value


def validate_package(
    admin: backup.PostgresAdmin, archive: Path, manifest_path: Path, baseline_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """No database connection/write, migrations or seed calls in this validation."""
    manifest, baseline = read_object(manifest_path), read_object(baseline_path)
    old_run = manifest.get("run_id")
    if not isinstance(old_run, str) or not backup.RUN_ID_PATTERN.fullmatch(old_run):
        raise backup.RehearsalError("Invalid backup run ID")
    if archive.is_symlink() or not archive.is_file():
        raise backup.RehearsalError("Archive must be a regular non-symlink file")
    ids = backup.fixture_ids(old_run)
    if (
        type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
        or manifest.get("synthetic_fixture") is not True
        or manifest.get("fixture_ids") != ids
        or manifest.get("schema_revision") != SUPPORTED_REVISION
        or manifest.get("archive_file") != archive.name
        or manifest.get("ownership_proof") != backup.ownership_proof_path(Path(), old_run).name
    ):
        raise backup.RehearsalError("Unsupported or inconsistent synthetic package manifest")
    for key in ("source_commit", "checkout_commit"):
        if not isinstance(manifest.get(key), str) or not re.fullmatch(r"[0-9a-f]{40}", manifest[key]):
            raise backup.RehearsalError("Invalid backup commit provenance")
    expected_archive = {"file": archive.name, "size": manifest.get("archive_size"), "sha256": manifest.get("archive_sha256")}
    if (
        baseline.get("status") != "passed"
        or baseline.get("run_id") != old_run
        or any(baseline.get(key) != manifest.get(key) for key in ("source_commit", "checkout_commit", "owned_databases", "ownership_proof"))
        or baseline.get("manifest") != manifest_path.name
        or baseline.get("archive") != expected_archive
        or baseline.get("source_inventory") != baseline.get("target_inventory")
    ):
        raise backup.RehearsalError("Backup manifest and baseline report do not match")
    inventory = baseline.get("source_inventory")
    counts = {table: 1 for table in ("suppliers", "software_products", "customers", "projects", "releases", "audit_events")}
    if (
        not isinstance(inventory, dict)
        or inventory.get("revision") != SUPPORTED_REVISION
        or inventory.get("server_version") != manifest.get("postgres_server_version")
        or inventory.get("fixture") != backup.canonical_fixture(old_run, ids)
        or inventory.get("counts") != counts
        or inventory.get("relationship_count") != 1
        or inventory.get("append_only_trigger") != ["trg_audit_events_append_only", "O"]
        or inventory.get("constraints") != sorted(["suppliers_code_key", "software_products_supplier_id_fkey", "projects_customer_id_fkey"])
        or inventory.get("indexes") != ["ix_audit_events_entity", "uq_release_customer_version"]
        or not isinstance(inventory.get("tables"), list)
        or not set(counts).union({"alembic_version"}).issubset(inventory["tables"])
        or baseline.get("append_only", {}).get("blocked") is not True
        or baseline.get("append_only", {}).get("source_unchanged") is not True
        or baseline.get("append_only", {}).get("target_unchanged") is not True
    ):
        raise backup.RehearsalError("Backup baseline is not the supported canonical fixture")
    # Compatibility is intentionally narrow: no cross-version conversion promise.
    current_restore = backup.native_version("pg_restore", admin)
    if current_restore != manifest.get("pg_restore_version"):
        raise backup.RehearsalError("Retained package pg_restore version is unsupported")
    dump_version = manifest.get("pg_dump_version")
    match = re.match(r"pg_restore \(PostgreSQL\) (\d+)\.", current_restore)
    if not match or not isinstance(dump_version, str) or not re.match(r"pg_dump \(PostgreSQL\) " + match[1] + r"\.", dump_version):
        raise backup.RehearsalError("Retained package pg_dump version is unsupported")
    backup.verify_archive(admin, archive, manifest, old_run)
    return manifest, baseline


def prove_target_append_only(admin: backup.PostgresAdmin, target: str, audit: dict[str, Any]) -> dict[str, Any]:
    expected = (audit["summary"], audit["payload"])
    with backup.connect(admin, target) as connection:
        before = connection.execute("SELECT summary, payload_json FROM audit_events WHERE id = %s", (audit["id"],)).fetchone()
    if before != expected:
        raise backup.RehearsalError("Restored target audit baseline differs")
    diagnostic = None
    try:
        with backup.connect(admin, target, autocommit=False) as connection:
            connection.execute("UPDATE audit_events SET summary = 'forbidden mutation' WHERE id = %s", (audit["id"],))
            # Always rollback, even if the guard is unexpectedly missing.
            connection.rollback()
    except psycopg.Error as exc:
        diagnostic = str(exc).splitlines()[0]
        if exc.sqlstate != "P0001" or diagnostic != "audit_events are append-only":
            raise backup.RehearsalError("Unexpected target audit verification error") from exc
    if diagnostic is None:
        raise backup.RehearsalError("Restored audit mutation was not blocked")
    with backup.connect(admin, target) as connection:
        after = connection.execute("SELECT summary, payload_json FROM audit_events WHERE id = %s", (audit["id"],)).fetchone()
    if after != expected:
        raise backup.RehearsalError("Restored audit changed during verification")
    return {"blocked": True, "diagnostic": diagnostic, "target_unchanged": True, "source_accessed": False}


def recover(
    *, repo_root: Path, admin_url: str, archive: Path, manifest_path: Path,
    baseline_path: Path, evidence_dir: Path, trusted_own_synthetic: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    if trusted_own_synthetic is not True:
        raise backup.RehearsalError("Explicit trusted-own-synthetic acknowledgement required; checksums are not authentication")
    admin = backup.PostgresAdmin.from_url(admin_url)
    backup.reject_inherited_libpq_environment()
    manifest, baseline = validate_package(admin, archive, manifest_path, baseline_path)
    run_id = run_id or backup.new_run_id()
    target = backup.owned_database_name(run_id, "target")
    if run_id == manifest["run_id"]:
        raise backup.RehearsalError("Recovery requires a new run ID, never the backup run")
    if evidence_dir.exists() or evidence_dir.is_symlink():
        raise backup.RehearsalError("Recovery evidence directory must be new")
    backup.require_absent(admin, target)
    with backup.connect(admin) as connection:
        if connection.execute("SHOW server_version").fetchone()[0] != manifest["postgres_server_version"]:
            raise backup.RehearsalError("Recovery server version differs from backup baseline")
    implementation, checkout = backup.git_commits(repo_root)
    inputs = {"archive": archive, "manifest": manifest_path, "baseline": baseline_path}
    fingerprints = {name: backup.archive_digest(path) for name, path in inputs.items()}
    # Exclusive new output directory is also a snapshot: restoration never reopens
    # the caller's archive after validation. Original backup inputs stay untouched.
    evidence_dir.mkdir(parents=True, exist_ok=False)
    snapshot = evidence_dir / "package"
    snapshot.mkdir()
    for path in inputs.values():
        (snapshot / path.name).write_bytes(path.read_bytes())
    manifest2, baseline2 = validate_package(admin, snapshot / archive.name, snapshot / manifest_path.name, snapshot / baseline_path.name)
    if manifest2 != manifest or baseline2 != baseline or any(backup.archive_digest(snapshot / path.name) != fingerprints[name] for name, path in inputs.items()):
        raise backup.RehearsalError("Package changed during snapshot; no target created")
    proof_path = backup.ownership_proof_path(evidence_dir, run_id)
    proof = backup.new_ownership_proof(run_id, admin)
    backup.write_manifest(proof_path, proof)
    report = {
        "schema_version": 1, "status": "running", "run_id": run_id,
        "backup_run_id": manifest["run_id"], "backup_source_commit": manifest["source_commit"],
        "backup_checkout_commit": manifest["checkout_commit"],
        "recovery_implementation_commit": implementation, "recovery_checkout_commit": checkout,
        "owned_databases": {"target": target}, "ownership_proof": proof_path.name,
        "input_sha256": fingerprints, "started_at": backup.utc_now(),
        "source_accessed": False, "cleanup": "retained_for_diagnosis",
    }
    report_path = evidence_dir / REPORT_NAME
    backup.write_manifest(report_path, report)
    try:
        backup.create_owned_database(admin, run_id, "target", proof, proof_path)
        backup.restore_database(admin, target, snapshot / archive.name)
        restored = backup.inventory(admin, target, manifest["run_id"], manifest["fixture_ids"])
        backup.assert_restored_inventory_matches(baseline["source_inventory"], restored)
        append_only = prove_target_append_only(admin, target, restored["fixture"]["audit"])
        if any(backup.archive_digest(path) != fingerprints[name] for name, path in inputs.items()):
            raise backup.RehearsalError("Original backup package changed during recovery")
        report.update(status="passed", target_inventory=restored, append_only=append_only,
                      originals_unchanged=True, cleanup="retained_for_explicit_cleanup")
    except Exception as exc:
        # Native errors are bounded; never print connection URLs/passwords.
        message = str(exc).replace(admin_url, "[redacted]")
        if admin.password:
            message = message.replace(admin.password, "[redacted]")
        report.update(status="failed", error_type=type(exc).__name__, error=message[:1000])
        raise
    finally:
        report["completed_at"] = backup.utc_now()
        backup.write_manifest(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", default=os.environ.get("TEST_POSTGRES_URL"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--trusted-own-synthetic", action="store_true")
    args = parser.parse_args()
    if not args.admin_url:
        parser.error("--admin-url or TEST_POSTGRES_URL is required")
    try:
        report = recover(repo_root=Path(__file__).resolve().parents[3], admin_url=args.admin_url,
                         archive=args.archive, manifest_path=args.manifest, baseline_path=args.baseline,
                         evidence_dir=args.evidence_dir, run_id=args.run_id,
                         trusted_own_synthetic=args.trusted_own_synthetic)
    except Exception as exc:
        # Full sanitized native diagnostic is in the new run report when created.
        print(f"Retained synthetic recovery failed ({type(exc).__name__}); inspect recovery evidence if created", file=sys.stderr)
        return 1
    print(json.dumps({key: report[key] for key in ("status", "run_id", "backup_run_id", "cleanup")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
