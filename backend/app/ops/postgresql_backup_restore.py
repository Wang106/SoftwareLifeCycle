"""Fail-closed PostgreSQL backup/restore rehearsal for disposable synthetic data.

This module deliberately accepts only loopback PostgreSQL and generates the two
database names itself.  It never restores over an existing database and cleanup
is restricted to names owned by the exact rehearsal run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

from app.core.config import settings


DATABASE_PREFIX = "slc_rehearsal_"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
FORBIDDEN_DATABASES = {"software_lifecycle", "template0", "template1"}
RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


class RehearsalError(RuntimeError):
    """An expected safety or verification failure."""


@dataclass(frozen=True)
class PostgresAdmin:
    host: str
    port: int
    user: str
    password: str | None
    database: str

    @classmethod
    def from_url(cls, raw_url: str) -> "PostgresAdmin":
        parsed = make_url(raw_url)
        if parsed.get_backend_name() != "postgresql":
            raise RehearsalError("A real PostgreSQL connection is required")
        if parsed.host not in LOOPBACK_HOSTS:
            raise RehearsalError("Only loopback PostgreSQL is allowed")
        if parsed.query:
            raise RehearsalError("Connection URL options are not allowed")
        if not parsed.username or not parsed.database:
            raise RehearsalError("PostgreSQL user and control database are required")
        if parsed.database in FORBIDDEN_DATABASES:
            raise RehearsalError("The application/default database cannot be the control database")
        return cls(
            host=parsed.host,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.database,
        )

    def sqlalchemy_url(self, database: str) -> str:
        from sqlalchemy.engine import URL

        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=database,
        ).render_as_string(hide_password=False)

    def client_args(self, database: str) -> list[str]:
        return [
            "--host", self.host,
            "--port", str(self.port),
            "--username", self.user,
            "--dbname", database,
        ]

    def client_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.password is not None:
            env["PGPASSWORD"] = self.password
        return env


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def owned_database_name(run_id: str, role: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise RehearsalError("Run ID must be exactly 12 lowercase hexadecimal characters")
    if role not in {"source", "target"}:
        raise RehearsalError("Database role must be source or target")
    return f"{DATABASE_PREFIX}{run_id}_{role}"


def assert_owned_database_name(run_id: str, database: str, role: str) -> None:
    expected = owned_database_name(run_id, role)
    if database != expected:
        raise RehearsalError(f"Refusing unowned database name; expected {expected}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(admin: PostgresAdmin, database: str | None = None, *, autocommit: bool = True) -> Iterator[psycopg.Connection]:
    with psycopg.connect(
        host=admin.host,
        port=admin.port,
        user=admin.user,
        password=admin.password,
        dbname=database or admin.database,
        connect_timeout=5,
        autocommit=autocommit,
    ) as connection:
        yield connection


def database_metadata(admin: PostgresAdmin, database: str) -> tuple[bool, str | None]:
    with connect(admin) as connection:
        row = connection.execute(
            """SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = %s),
                      (SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s)""",
            (database, database),
        ).fetchone()
    return bool(row[0]), row[1]


def require_absent(admin: PostgresAdmin, *databases: str) -> None:
    if len(set(databases)) != len(databases):
        raise RehearsalError("Source and target databases must be different")
    for database in databases:
        exists, _ = database_metadata(admin, database)
        if exists:
            raise RehearsalError(f"Refusing existing database: {database}")


def create_owned_database(admin: PostgresAdmin, run_id: str, role: str) -> str:
    database = owned_database_name(run_id, role)
    require_absent(admin, database)
    with connect(admin) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
                sql.Identifier(database), sql.Identifier(admin.user)
            )
        )
    exists, owner = database_metadata(admin, database)
    if not exists or owner != admin.user:
        raise RehearsalError(f"Database ownership verification failed: {database}")
    return database


def drop_owned_database(admin: PostgresAdmin, run_id: str, database: str, role: str) -> None:
    assert_owned_database_name(run_id, database, role)
    exists, owner = database_metadata(admin, database)
    if not exists:
        return
    if owner != admin.user:
        raise RehearsalError(f"Refusing database owned by {owner!r}: {database}")
    with connect(admin) as connection:
        connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))


def _native(command_line: list[str], admin: PostgresAdmin, *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    executable = command_line[0]
    if shutil.which(executable) is None:
        raise RehearsalError(f"Required PostgreSQL client is unavailable: {executable}")
    completed = subprocess.run(
        command_line,
        env=admin.client_env(),
        text=True,
        capture_output=capture_output,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "no diagnostic output").strip()
        raise RehearsalError(f"{executable} failed with exit {completed.returncode}: {detail[:800]}")
    return completed


def native_version(executable: str, admin: PostgresAdmin) -> str:
    return _native([executable, "--version"], admin).stdout.strip()


def migrate_source(repo_root: Path, admin: PostgresAdmin, source_database: str) -> None:
    backend = repo_root / "backend"
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    previous = settings.database_url
    settings.database_url = admin.sqlalchemy_url(source_database)
    try:
        command.upgrade(config, "head")
    finally:
        settings.database_url = previous


def fixture_ids(run_id: str) -> dict[str, str]:
    namespace = uuid.UUID("90d4dd3c-91ad-4a66-bfb5-8a203ba0aa4f")
    return {name: str(uuid.uuid5(namespace, f"{run_id}:{name}")) for name in (
        "supplier", "software", "customer", "project", "release", "audit"
    )}


def load_synthetic_fixture(admin: PostgresAdmin, database: str, run_id: str) -> dict[str, str]:
    ids = fixture_ids(run_id)
    with connect(admin, database, autocommit=False) as connection:
        connection.execute(
            "INSERT INTO suppliers (id, code, name, status) VALUES (%s, %s, %s, 'ACTIVE')",
            (ids["supplier"], f"SYN-{run_id}", "Synthetic rehearsal supplier"),
        )
        connection.execute(
            "INSERT INTO software_products (id, supplier_id, code, name, status) VALUES (%s, %s, %s, %s, 'ACTIVE')",
            (ids["software"], ids["supplier"], f"SW-{run_id}", "Synthetic rehearsal software"),
        )
        connection.execute(
            "INSERT INTO customers (id, code, name, region, status) VALUES (%s, %s, %s, 'OTHER', 'ACTIVE')",
            (ids["customer"], f"C-{run_id}", "Synthetic rehearsal customer"),
        )
        connection.execute(
            "INSERT INTO projects (id, customer_id, project_code, name, status) VALUES (%s, %s, %s, %s, 'ACTIVE')",
            (ids["project"], ids["customer"], f"P-{run_id}", "Synthetic rehearsal project"),
        )
        connection.execute(
            "INSERT INTO releases (id, software_id, release_type, version, status) VALUES (%s, %s, 'STANDARD', %s, 'DRAFT')",
            (ids["release"], ids["software"], f"rehearsal-{run_id}"),
        )
        connection.execute(
            """INSERT INTO audit_events
               (id, event_no, event_type, action, entity_type, entity_id, entity_ref,
                actor_name, summary, detail, payload_json, occurred_at, created_at)
               VALUES (%s, %s, 'REHEARSAL', 'SYNTHETIC_FIXTURE_CREATED', 'Release', %s, %s,
                       'synthetic-rehearsal', %s, 'No real company or customer data', %s, now(), now())""",
            (
                ids["audit"], f"REHEARSAL-{run_id}", ids["release"], f"release:{ids['release']}",
                f"Synthetic backup/restore fixture {run_id}",
                Jsonb({"run_id": run_id, "synthetic": True, "release_id": ids["release"]}),
            ),
        )
        connection.commit()
    return ids


def _one(connection: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise RehearsalError("Expected verification row is missing")
    return row[0]


def inventory(admin: PostgresAdmin, database: str, ids: dict[str, str]) -> dict[str, Any]:
    with connect(admin, database) as connection:
        revision = _one(connection, "SELECT version_num FROM alembic_version")
        server_version = _one(connection, "SHOW server_version")
        tables = sorted(row[0] for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall())
        counts = {
            table: _one(connection, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
            for table in ("suppliers", "software_products", "customers", "projects", "releases", "audit_events")
        }
        relationship_count = _one(
            connection,
            """SELECT count(*) FROM releases r
               JOIN software_products sw ON sw.id = r.software_id
               JOIN suppliers s ON s.id = sw.supplier_id
               WHERE r.id = %s AND sw.id = %s AND s.id = %s""",
            (ids["release"], ids["software"], ids["supplier"]),
        )
        audit = connection.execute(
            "SELECT id::text, event_no, entity_id::text, summary, payload_json FROM audit_events WHERE id = %s",
            (ids["audit"],),
        ).fetchone()
        if audit is None:
            raise RehearsalError("Synthetic audit event is missing")
        constraints = sorted(row[0] for row in connection.execute(
            """SELECT conname FROM pg_constraint
               WHERE connamespace = 'public'::regnamespace AND conname IN
               ('suppliers_code_key', 'software_products_supplier_id_fkey',
                'projects_customer_id_fkey', 'uq_release_customer_version')"""
        ).fetchall())
        indexes = sorted(row[0] for row in connection.execute(
            """SELECT indexname FROM pg_indexes WHERE schemaname = 'public'
               AND indexname IN ('ix_audit_events_entity', 'uq_release_customer_version')"""
        ).fetchall())
        trigger = connection.execute(
            """SELECT t.tgname, t.tgenabled FROM pg_trigger t
               WHERE t.tgrelid = 'public.audit_events'::regclass
                 AND t.tgname = 'trg_audit_events_append_only' AND NOT t.tgisinternal"""
        ).fetchone()
    required_tables = {"alembic_version", "suppliers", "software_products", "customers", "projects", "releases", "audit_events"}
    if not required_tables.issubset(tables):
        raise RehearsalError("Required migrated tables are missing")
    if relationship_count != 1:
        raise RehearsalError("Synthetic relationship verification failed")
    if trigger != ("trg_audit_events_append_only", "O"):
        raise RehearsalError("Append-only audit trigger is absent or disabled")
    if len(constraints) != 3 or len(indexes) != 2:
        raise RehearsalError("Expected constraints or indexes are missing")
    return {
        "revision": revision,
        "server_version": server_version,
        "tables": tables,
        "counts": counts,
        "relationship_count": relationship_count,
        "constraints": constraints,
        "indexes": indexes,
        "append_only_trigger": list(trigger),
        "fixture": {
            "ids": ids,
            "audit": {
                "id": audit[0], "event_no": audit[1], "entity_id": audit[2],
                "summary": audit[3], "payload": audit[4],
            },
        },
    }


def dump_database(admin: PostgresAdmin, database: str, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    _native([
        "pg_dump", *admin.client_args(database), "--format=custom", "--no-owner",
        "--no-privileges", "--file", str(archive),
    ], admin)
    if not archive.is_file() or archive.stat().st_size <= 0:
        raise RehearsalError("pg_dump did not create a nonempty archive")


def archive_digest(archive: Path) -> str:
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def verify_archive(admin: PostgresAdmin, archive: Path, manifest: dict[str, Any], run_id: str) -> None:
    if manifest.get("run_id") != run_id:
        raise RehearsalError("Manifest run ID does not match")
    expected = {
        "source": owned_database_name(run_id, "source"),
        "target": owned_database_name(run_id, "target"),
    }
    if manifest.get("owned_databases") != expected:
        raise RehearsalError("Manifest owned database names do not match")
    if not archive.is_file():
        raise RehearsalError("Backup archive is missing")
    if manifest.get("archive_size") != archive.stat().st_size:
        raise RehearsalError("Backup archive size does not match manifest")
    if manifest.get("archive_sha256") != archive_digest(archive):
        raise RehearsalError("Backup archive checksum does not match manifest")
    listing = _native(["pg_restore", "--list", str(archive)], admin).stdout
    for required in ("audit_events", "alembic_version", "releases"):
        if required not in listing:
            raise RehearsalError(f"Backup archive lacks required object: {required}")


def restore_database(admin: PostgresAdmin, database: str, archive: Path) -> None:
    _native([
        "pg_restore", *admin.client_args(database), "--exit-on-error", "--no-owner",
        "--no-privileges", str(archive),
    ], admin)


def prove_append_only(admin: PostgresAdmin, source: str, target: str, audit_id: str) -> dict[str, Any]:
    before_source: tuple[Any, ...]
    with connect(admin, source) as connection:
        before_source = connection.execute(
            "SELECT summary, payload_json FROM audit_events WHERE id = %s", (audit_id,)
        ).fetchone()
    if before_source is None:
        raise RehearsalError("Source audit evidence is missing")
    blocked = False
    diagnostic = ""
    try:
        with connect(admin, target, autocommit=False) as connection:
            connection.execute("UPDATE audit_events SET summary = 'forbidden mutation' WHERE id = %s", (audit_id,))
            connection.commit()
    except psycopg.Error as exc:
        blocked = True
        diagnostic = str(exc).splitlines()[0]
    if not blocked:
        raise RehearsalError("Restored audit event mutation was not blocked")
    with connect(admin, target) as connection:
        after_target = connection.execute(
            "SELECT summary, payload_json FROM audit_events WHERE id = %s", (audit_id,)
        ).fetchone()
    with connect(admin, source) as connection:
        after_source = connection.execute(
            "SELECT summary, payload_json FROM audit_events WHERE id = %s", (audit_id,)
        ).fetchone()
    if after_target != before_source or after_source != before_source:
        raise RehearsalError("Audit evidence changed during append-only verification")
    return {"blocked": True, "diagnostic": diagnostic, "source_unchanged": True, "target_unchanged": True}


def git_commits(repo_root: Path) -> tuple[str, str]:
    completed = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    parts = completed.stdout.strip().split()
    if completed.returncode or not parts or any(not re.fullmatch(r"[0-9a-f]{40}", item) for item in parts):
        raise RehearsalError("Unable to determine exact source commit")
    checkout_commit = parts[0]
    # actions/checkout tests a synthetic merge ref for pull_request events.  Its
    # second parent is the exact feature head whose bytes are under review.
    source_commit = parts[2] if os.environ.get("GITHUB_EVENT_NAME") == "pull_request" and len(parts) == 3 else checkout_commit
    return source_commit, checkout_commit


def run_rehearsal(
    *,
    repo_root: Path,
    admin_url: str,
    evidence_dir: Path,
    run_id: str | None = None,
    cleanup_on_success: bool = True,
) -> dict[str, Any]:
    run_id = run_id or new_run_id()
    source = owned_database_name(run_id, "source")
    target = owned_database_name(run_id, "target")
    admin = PostgresAdmin.from_url(admin_url)
    require_absent(admin, source, target)
    exact_commit, checkout_commit = git_commits(repo_root)
    archive = evidence_dir / f"postgresql-rehearsal-{run_id}.dump"
    manifest_path = evidence_dir / f"postgresql-rehearsal-{run_id}-manifest.json"
    report_path = evidence_dir / "postgresql-backup-restore-rehearsal.json"
    created: list[tuple[str, str]] = []
    report: dict[str, Any] = {
        "status": "running", "run_id": run_id, "source_commit": exact_commit,
        "checkout_commit": checkout_commit,
        "started_at": utc_now(), "owned_databases": {"source": source, "target": target},
    }
    try:
        create_owned_database(admin, run_id, "source")
        created.append((source, "source"))
        migrate_source(repo_root, admin, source)
        ids = load_synthetic_fixture(admin, source, run_id)
        source_inventory = inventory(admin, source, ids)
        dump_database(admin, source, archive)
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "source_commit": exact_commit,
            "checkout_commit": checkout_commit,
            "created_at": utc_now(),
            "synthetic_fixture": True,
            "owned_databases": {"source": source, "target": target},
            "schema_revision": source_inventory["revision"],
            "postgres_server_version": source_inventory["server_version"],
            "pg_dump_version": native_version("pg_dump", admin),
            "pg_restore_version": native_version("pg_restore", admin),
            "archive_file": archive.name,
            "archive_size": archive.stat().st_size,
            "archive_sha256": archive_digest(archive),
            "fixture_ids": ids,
        }
        write_manifest(manifest_path, manifest)
        verify_archive(admin, archive, manifest, run_id)
        require_absent(admin, target)
        create_owned_database(admin, run_id, "target")
        created.append((target, "target"))
        restore_database(admin, target, archive)
        target_inventory = inventory(admin, target, ids)
        if target_inventory != source_inventory:
            raise RehearsalError("Restored schema/data/audit inventory differs from source")
        append_only = prove_append_only(admin, source, target, ids["audit"])
        report.update({
            "status": "passed",
            "completed_at": utc_now(),
            "manifest": manifest_path.name,
            "archive": {"file": archive.name, "size": manifest["archive_size"], "sha256": manifest["archive_sha256"]},
            "source_inventory": source_inventory,
            "target_inventory": target_inventory,
            "append_only": append_only,
            "cleanup": "pending" if cleanup_on_success else "retained",
        })
        write_manifest(report_path, report)
        if cleanup_on_success:
            for database, role in reversed(created):
                drop_owned_database(admin, run_id, database, role)
            report["cleanup"] = "owned_databases_dropped"
            write_manifest(report_path, report)
        return report
    except Exception as exc:
        report.update({
            "status": "failed", "completed_at": utc_now(),
            "error_type": type(exc).__name__, "error": str(exc)[:1000],
            "cleanup": "retained_for_diagnosis",
        })
        write_manifest(report_path, report)
        raise


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", default=os.environ.get("TEST_POSTGRES_URL"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("ci-results"))
    parser.add_argument("--run-id")
    parser.add_argument(
        "--cleanup-run-id",
        help="After reviewing retained diagnostics, drop only this run's exact owned source/target databases",
    )
    parser.add_argument("--keep-on-success", action="store_true")
    args = parser.parse_args()
    if not args.admin_url:
        parser.error("--admin-url or TEST_POSTGRES_URL is required")
    if args.cleanup_run_id:
        if args.run_id or args.keep_on_success:
            parser.error("--cleanup-run-id cannot be combined with rehearsal options")
        try:
            admin = PostgresAdmin.from_url(args.admin_url)
            for role in ("target", "source"):
                database = owned_database_name(args.cleanup_run_id, role)
                drop_owned_database(admin, args.cleanup_run_id, database, role)
        except RehearsalError as exc:
            print(f"Owned-resource cleanup failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"cleanup": "owned_databases_dropped", "run_id": args.cleanup_run_id}, sort_keys=True))
        return 0
    repo_root = Path(__file__).resolve().parents[3]
    try:
        report = run_rehearsal(
            repo_root=repo_root,
            admin_url=args.admin_url,
            evidence_dir=args.evidence_dir,
            run_id=args.run_id,
            cleanup_on_success=not args.keep_on_success,
        )
    except RehearsalError as exc:
        print(f"Backup/restore rehearsal failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": report["status"], "run_id": report["run_id"],
        "source_commit": report["source_commit"], "cleanup": report["cleanup"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
