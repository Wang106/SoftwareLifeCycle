"""Safety gates plus a native PostgreSQL dump/restore acceptance rehearsal."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from app.ops import postgresql_backup_restore as rehearsal


LOCAL_URL = "postgresql+psycopg://slc_ci:secret@127.0.0.1:5432/software_lifecycle_ci"


@pytest.mark.parametrize(
    "url, message",
    [
        ("sqlite:///local.db", "real PostgreSQL"),
        ("postgresql://user:secret@db.example/company", "loopback"),
        ("postgresql://user:secret@127.0.0.1/software_lifecycle", "application/default"),
        ("postgresql://user:secret@127.0.0.1/postgres?sslmode=disable", "options"),
    ],
)
def test_rehearsal_rejects_nonisolated_admin_connections(url, message):
    with pytest.raises(rehearsal.RehearsalError, match=message):
        rehearsal.PostgresAdmin.from_url(url)


def test_rehearsal_database_names_are_exactly_run_owned():
    run_id = "0123456789ab"
    source = rehearsal.owned_database_name(run_id, "source")
    target = rehearsal.owned_database_name(run_id, "target")
    assert source == "slc_rehearsal_0123456789ab_source"
    assert target == "slc_rehearsal_0123456789ab_target"
    rehearsal.assert_owned_database_name(run_id, source, "source")
    with pytest.raises(rehearsal.RehearsalError, match="unowned"):
        rehearsal.assert_owned_database_name(run_id, "software_lifecycle_ci", "source")
    with pytest.raises(rehearsal.RehearsalError, match="12 lowercase"):
        rehearsal.owned_database_name("BAD", "source")
    with pytest.raises(rehearsal.RehearsalError, match="source or target"):
        rehearsal.owned_database_name(run_id, "other")


def test_rehearsal_refuses_equal_or_existing_database(monkeypatch):
    admin = rehearsal.PostgresAdmin.from_url(LOCAL_URL)
    with pytest.raises(rehearsal.RehearsalError, match="must be different"):
        rehearsal.require_absent(admin, "same", "same")
    monkeypatch.setattr(rehearsal, "database_metadata", lambda *_: (True, "slc_ci"))
    with pytest.raises(rehearsal.RehearsalError, match="existing database"):
        rehearsal.require_absent(admin, "slc_rehearsal_0123456789ab_target")


def test_cleanup_refuses_wrong_name_before_database_access(monkeypatch):
    admin = rehearsal.PostgresAdmin.from_url(LOCAL_URL)
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        return False, None

    monkeypatch.setattr(rehearsal, "database_metadata", unexpected)
    with pytest.raises(rehearsal.RehearsalError, match="unowned"):
        rehearsal.drop_owned_database(admin, "0123456789ab", "postgres", "source")
    assert called is False


def test_native_client_password_is_environment_only(monkeypatch):
    admin = rehearsal.PostgresAdmin.from_url(LOCAL_URL)
    observed = {}
    monkeypatch.setattr(rehearsal.shutil, "which", lambda executable: f"/usr/bin/{executable}")

    def fake_run(command_line, **kwargs):
        observed["command"] = command_line
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command_line, 0, stdout="pg_dump 16.0\n", stderr="")

    monkeypatch.setattr(rehearsal.subprocess, "run", fake_run)
    assert rehearsal.native_version("pg_dump", admin) == "pg_dump 16.0"
    assert "secret" not in " ".join(observed["command"])
    assert observed["env"]["PGPASSWORD"] == "secret"


def manifest_for(path: Path, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "owned_databases": {
            "source": rehearsal.owned_database_name(run_id, "source"),
            "target": rehearsal.owned_database_name(run_id, "target"),
        },
        "archive_size": path.stat().st_size,
        "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_corrupt_or_mismatched_archive_fails_before_restore(tmp_path, monkeypatch):
    admin = rehearsal.PostgresAdmin.from_url(LOCAL_URL)
    archive = tmp_path / "fixture.dump"
    archive.write_bytes(b"synthetic archive")
    manifest = manifest_for(archive, "0123456789ab")
    archive.write_bytes(b"corrupt")
    monkeypatch.setattr(rehearsal, "_native", lambda *_args, **_kwargs: pytest.fail("must not inspect corrupt archive"))
    with pytest.raises(rehearsal.RehearsalError, match="size|checksum"):
        rehearsal.verify_archive(admin, archive, manifest, "0123456789ab")
    archive.write_bytes(b"synthetic archive")
    manifest = manifest_for(archive, "0123456789ab")
    with pytest.raises(rehearsal.RehearsalError, match="run ID"):
        rehearsal.verify_archive(admin, archive, manifest, "abcdef012345")


def test_archive_catalog_must_contain_schema_data_and_audit_objects(tmp_path, monkeypatch):
    admin = rehearsal.PostgresAdmin.from_url(LOCAL_URL)
    archive = tmp_path / "fixture.dump"
    archive.write_bytes(b"valid checksum but invalid catalog")
    manifest = manifest_for(archive, "0123456789ab")
    completed = subprocess.CompletedProcess(["pg_restore"], 0, stdout="TABLE public suppliers\n", stderr="")
    monkeypatch.setattr(rehearsal, "_native", lambda *_args, **_kwargs: completed)
    with pytest.raises(rehearsal.RehearsalError, match="audit_events"):
        rehearsal.verify_archive(admin, archive, manifest, "0123456789ab")


def test_native_restore_failure_is_not_silenced(monkeypatch):
    admin = rehearsal.PostgresAdmin.from_url(LOCAL_URL)
    monkeypatch.setattr(rehearsal.shutil, "which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        rehearsal.subprocess,
        "run",
        lambda command_line, **_kwargs: subprocess.CompletedProcess(
            command_line, 1, stdout="", stderr="synthetic restore failure"
        ),
    )
    with pytest.raises(rehearsal.RehearsalError, match="exit 1.*synthetic restore failure"):
        rehearsal.restore_database(admin, "slc_rehearsal_0123456789ab_target", Path("archive.dump"))


def test_pull_request_manifest_uses_exact_feature_parent(tmp_path, monkeypatch):
    feature = "2" * 40
    merge = "3" * 40
    base = "1" * 40
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setattr(
        rehearsal.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["git"], 0, stdout=f"{merge} {base} {feature}\n", stderr=""
        ),
    )
    assert rehearsal.git_commits(tmp_path) == (feature, merge)


def test_native_postgresql_backup_restore_rehearsal(tmp_path):
    admin_url = os.environ.get("TEST_POSTGRES_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_URL required for native PostgreSQL backup/restore rehearsal")
    repo_root = Path(__file__).resolve().parents[2]
    evidence_dir = repo_root / "ci-results"
    report = rehearsal.run_rehearsal(
        repo_root=repo_root,
        admin_url=admin_url,
        evidence_dir=evidence_dir,
        cleanup_on_success=True,
    )
    assert report["status"] == "passed"
    assert report["source_inventory"] == report["target_inventory"]
    assert report["append_only"] == {
        "blocked": True,
        "diagnostic": "audit_events are append-only",
        "source_unchanged": True,
        "target_unchanged": True,
    }
    assert report["cleanup"] == "owned_databases_dropped"
    assert (evidence_dir / "postgresql-backup-restore-rehearsal.json").is_file()
