"""Independent retained synthetic package recovery; no company database access."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

from app.ops import postgresql_backup_restore as backup
from app.ops import retained_synthetic_restore as recovery

LOCAL_URL = "postgresql+psycopg://slc_ci:secret@127.0.0.1:5432/software_lifecycle_ci"
OLD_RUN = "0123456789ab"
NEW_RUN = "abcdef012345"


def package(tmp_path, monkeypatch):
    """A canonical metadata fixture; native acceptance below uses real pg_dump."""
    archive = tmp_path / f"postgresql-rehearsal-{OLD_RUN}.dump"
    archive.write_bytes(b"synthetic unit-test archive")
    manifest_path = tmp_path / f"postgresql-rehearsal-{OLD_RUN}-manifest.json"
    baseline_path = tmp_path / "postgresql-backup-restore-rehearsal.json"
    ids = backup.fixture_ids(OLD_RUN)
    inventory = {
        "revision": recovery.SUPPORTED_REVISION, "server_version": "16.15",
        "counts": {key: 1 for key in ("suppliers", "software_products", "customers", "projects", "releases", "audit_events")},
        "tables": sorted(["alembic_version", "suppliers", "software_products", "customers", "projects", "releases", "audit_events"]),
        "relationship_count": 1, "fixture": backup.canonical_fixture(OLD_RUN, ids),
        "append_only_trigger": ["trg_audit_events_append_only", "O"],
        "constraints": sorted(["suppliers_code_key", "software_products_supplier_id_fkey", "projects_customer_id_fkey"]),
        "indexes": ["ix_audit_events_entity", "uq_release_customer_version"],
    }
    manifest = {
        "schema_version": 1, "run_id": OLD_RUN, "synthetic_fixture": True,
        "source_commit": "1" * 40, "checkout_commit": "2" * 40,
        "owned_databases": {role: backup.owned_database_name(OLD_RUN, role) for role in ("source", "target")},
        "ownership_proof": backup.ownership_proof_path(Path(), OLD_RUN).name,
        "schema_revision": recovery.SUPPORTED_REVISION, "postgres_server_version": "16.15",
        "pg_dump_version": "pg_dump (PostgreSQL) 16.15", "pg_restore_version": "pg_restore (PostgreSQL) 16.15",
        "archive_file": archive.name, "archive_size": archive.stat().st_size,
        "archive_sha256": backup.archive_digest(archive), "fixture_ids": ids,
    }
    baseline = {key: manifest[key] for key in ("run_id", "source_commit", "checkout_commit", "owned_databases", "ownership_proof")}
    baseline.update(status="passed", manifest=manifest_path.name,
                    archive={"file": archive.name, "size": manifest["archive_size"], "sha256": manifest["archive_sha256"]},
                    source_inventory=inventory, target_inventory=copy.deepcopy(inventory),
                    append_only={"blocked": True, "source_unchanged": True, "target_unchanged": True})
    backup.write_manifest(manifest_path, manifest)
    backup.write_manifest(baseline_path, baseline)
    monkeypatch.setattr(backup, "native_version", lambda *_: "pg_restore (PostgreSQL) 16.15")
    monkeypatch.setattr(backup, "_native", lambda *_: subprocess.CompletedProcess([], 0, stdout="audit_events alembic_version releases", stderr=""))
    return archive, manifest_path, baseline_path


def args(paths, tmp_path):
    return dict(repo_root=tmp_path, admin_url=LOCAL_URL, archive=paths[0], manifest_path=paths[1],
                baseline_path=paths[2], evidence_dir=tmp_path / "recovery", run_id=NEW_RUN, trusted_own_synthetic=True)


@pytest.mark.parametrize("kind", ["checksum", "schema", "ids", "baseline", "version", "trust", "reuse-run", "existing-output"])
def test_invalid_retained_package_refused_before_database_access(tmp_path, monkeypatch, kind):
    paths = package(tmp_path, monkeypatch)
    options = args(paths, tmp_path)
    manifest = json.loads(paths[1].read_text())
    if kind == "checksum":
        paths[0].write_bytes(b"corrupt")
    elif kind == "schema":
        manifest["schema_version"] = 2
    elif kind == "ids":
        manifest["fixture_ids"]["audit"] = "0" * 36
    elif kind == "baseline":
        baseline = json.loads(paths[2].read_text())
        baseline["source_commit"] = "3" * 40
        backup.write_manifest(paths[2], baseline)
    elif kind == "version":
        manifest["pg_restore_version"] = "pg_restore (PostgreSQL) 15.0"
    elif kind == "trust":
        options["trusted_own_synthetic"] = False
    elif kind == "reuse-run":
        options["run_id"] = OLD_RUN
    elif kind == "existing-output":
        options["evidence_dir"].mkdir()
    backup.write_manifest(paths[1], manifest)
    before = [p.read_bytes() for p in paths]
    monkeypatch.setattr(backup, "connect", lambda *_a, **_k: pytest.fail("no database access permitted"))
    with pytest.raises(backup.RehearsalError):
        recovery.recover(**options)
    assert [p.read_bytes() for p in paths] == before
    assert not list(tmp_path.rglob("*ownership.json"))


def test_existing_recovery_target_refused_without_output_or_writes(tmp_path, monkeypatch):
    paths = package(tmp_path, monkeypatch)
    monkeypatch.setattr(backup, "database_metadata", lambda *_: (True, "slc_ci", "existing"))
    monkeypatch.setattr(backup, "create_owned_database", lambda *_: pytest.fail("must not create"))
    with pytest.raises(backup.RehearsalError, match="existing database"):
        recovery.recover(**args(paths, tmp_path))
    assert not (tmp_path / "recovery").exists()


def test_failed_restore_retains_new_proof_and_sanitized_diagnostic(tmp_path, monkeypatch):
    paths = package(tmp_path, monkeypatch)
    before = [p.read_bytes() for p in paths]
    class Control:
        def execute(self, query):
            assert query == "SHOW server_version"
            return self
        def fetchone(self):
            return ("16.15",)
    monkeypatch.setattr(backup, "connect", lambda *_a, **_k: nullcontext(Control()))
    monkeypatch.setattr(backup, "require_absent", lambda *_: None)
    monkeypatch.setattr(backup, "git_commits", lambda *_: ("3" * 40, "4" * 40))
    def create(admin, run_id, role, proof, proof_path):
        assert run_id == NEW_RUN and role == "target"
        proof["created_databases"][role] = {"name": backup.owned_database_name(run_id, role),
            "marker": backup.ownership_marker(run_id, role, proof["token"]), "created_at": backup.utc_now()}
        backup.write_manifest(proof_path, proof)
    monkeypatch.setattr(backup, "create_owned_database", create)
    def fail(*_):
        raise backup.RehearsalError("native failure secret " + LOCAL_URL)
    monkeypatch.setattr(backup, "restore_database", fail)
    monkeypatch.setattr(backup, "drop_owned_database", lambda *_: pytest.fail("no automatic failed cleanup"))
    with pytest.raises(backup.RehearsalError, match="native failure"):
        recovery.recover(**args(paths, tmp_path))
    report = json.loads((tmp_path / "recovery" / recovery.REPORT_NAME).read_text())
    assert report["status"] == "failed" and report["cleanup"] == "retained_for_diagnosis"
    assert "secret" not in report["error"] and LOCAL_URL not in report["error"]
    assert report["backup_source_commit"] == "1" * 40
    assert report["recovery_implementation_commit"] == "3" * 40
    proof = backup.load_ownership_proof(tmp_path / "recovery" / report["ownership_proof"], NEW_RUN, backup.PostgresAdmin.from_url(LOCAL_URL))
    assert set(proof["created_databases"]) == {"target"}
    assert proof["dropped_databases"] == []
    assert [p.read_bytes() for p in paths] == before


def test_native_postgresql_retained_package_new_process_recovery():
    admin_url = os.environ.get("TEST_POSTGRES_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_URL required for native retained recovery")
    root = Path(__file__).resolve().parents[2]
    directory = root / "ci-results" / "retained-synthetic-restore"
    backup_dir = directory / "original"
    # The producer exits before the recoverer starts; it cleans both original DBs.
    def cli(module, *arguments):
        return subprocess.run([sys.executable, "-m", module, *map(str, arguments)], cwd=root / "backend", text=True, capture_output=True, check=False)
    producer = cli("app.ops.postgresql_backup_restore", "--evidence-dir", backup_dir)
    assert producer.returncode == 0, producer.stderr
    baseline_path = backup_dir / "postgresql-backup-restore-rehearsal.json"
    baseline = json.loads(baseline_path.read_text())
    admin = backup.PostgresAdmin.from_url(admin_url)
    old_run = baseline["run_id"]
    old_proof_path = backup_dir / baseline["ownership_proof"]
    old_proof = backup.load_ownership_proof(old_proof_path, old_run, admin)
    assert {x["role"] for x in old_proof["dropped_databases"]} == {"source", "target"}
    for db in baseline["owned_databases"].values():
        assert backup.database_metadata(admin, db)[0] is False
    archive, manifest_path = backup_dir / baseline["archive"]["file"], backup_dir / baseline["manifest"]
    original_files = (archive, manifest_path, baseline_path, old_proof_path)
    original_hashes = {p.name: backup.archive_digest(p) for p in original_files}
    new_run = backup.new_run_id()
    target = backup.owned_database_name(new_run, "target")
    output = directory / "recovered"
    arguments = ["--archive", archive, "--manifest", manifest_path, "--baseline", baseline_path,
                 "--run-id", new_run, "--evidence-dir", output, "--trusted-own-synthetic"]
    result = cli("app.ops.retained_synthetic_restore", *arguments)
    assert result.returncode == 0, result.stderr
    report = json.loads((output / recovery.REPORT_NAME).read_text())
    assert report["status"] == "passed" and report["source_accessed"] is False
    assert report["backup_run_id"] == old_run and report["run_id"] != old_run
    assert report["backup_source_commit"] == baseline["source_commit"]
    assert (report["recovery_implementation_commit"], report["recovery_checkout_commit"]) == backup.git_commits(root)
    assert report["target_inventory"] == baseline["source_inventory"]
    assert report["append_only"] == {"blocked": True, "diagnostic": "audit_events are append-only", "target_unchanged": True, "source_accessed": False}
    proof_path = output / report["ownership_proof"]
    proof = backup.load_ownership_proof(proof_path, new_run, admin)
    assert set(proof["created_databases"]) == {"target"} and proof["token"] != old_proof["token"]
    with pytest.raises(backup.RehearsalError, match="exact run"):
        backup.drop_owned_database(admin, new_run, target, "target", old_proof, old_proof_path)
    # Real existing target: metadata read only, no proof/output created and no overwrite.
    before = backup.inventory(admin, target, old_run, backup.fixture_ids(old_run))
    existing_output = directory / "existing-rejected"
    existing_args = list(arguments)
    existing_args[existing_args.index(output)] = existing_output
    rejected = cli("app.ops.retained_synthetic_restore", *existing_args)
    assert rejected.returncode == 1 and not existing_output.exists()
    assert backup.inventory(admin, target, old_run, backup.fixture_ids(old_run)) == before
    scenarios = {"existing_target": "rejected_without_write", "old_proof": "rejected_new_target_preserved"}
    # Corrupt archive and mismatched baseline run through the actual CLI in new processes.
    for scenario in ("corrupt_archive", "mismatched_baseline"):
        case = directory / scenario
        case.mkdir()
        for path in (archive, manifest_path, baseline_path):
            (case / path.name).write_bytes(path.read_bytes())
        if scenario == "corrupt_archive":
            (case / archive.name).write_bytes(b"corrupt")
        else:
            changed = json.loads((case / baseline_path.name).read_text())
            changed["source_commit"] = "0" * 40
            backup.write_manifest(case / baseline_path.name, changed)
        rejected_run = backup.new_run_id()
        rejected_output = case / "recovery"
        rejected = cli("app.ops.retained_synthetic_restore", "--archive", case / archive.name,
                       "--manifest", case / manifest_path.name, "--baseline", case / baseline_path.name,
                       "--run-id", rejected_run, "--evidence-dir", rejected_output, "--trusted-own-synthetic")
        assert rejected.returncode == 1 and not rejected_output.exists()
        assert backup.database_metadata(admin, backup.owned_database_name(rejected_run, "target"))[0] is False
        scenarios[scenario] = "rejected_without_target_or_output"
    assert {p.name: backup.archive_digest(p) for p in original_files} == original_hashes
    cleanup = cli("app.ops.postgresql_backup_restore", "--evidence-dir", output, "--cleanup-run-id", new_run)
    assert cleanup.returncode == 0, cleanup.stderr
    assert backup.database_metadata(admin, target)[0] is False
    assert backup.database_metadata(admin, backup.owned_database_name(new_run, "source"))[0] is False
    for db in baseline["owned_databases"].values():
        assert backup.database_metadata(admin, db)[0] is False
    proof = backup.load_ownership_proof(proof_path, new_run, admin)
    assert [x["role"] for x in proof["dropped_databases"]] == ["target"]
    assert {p.name: backup.archive_digest(p) for p in original_files} == original_hashes
    backup.write_manifest(directory / "acceptance.json", {
        "status": "passed", "original_process_exited": True, "original_databases_absent_before_and_after": True,
        "backup_run_id": old_run, "recovery_run_id": new_run, "input_sha256": original_hashes,
        "backup_source_commit": baseline["source_commit"], "recovery_implementation_commit": report["recovery_implementation_commit"],
        "recovery_checkout_commit": report["recovery_checkout_commit"], "originals_unchanged": True,
        "scenarios": scenarios, "cleanup": "new_target_only_dropped_with_new_proof",
    })
