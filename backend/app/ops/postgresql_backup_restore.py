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
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
FORBIDDEN_DATABASES = {"software_lifecycle", "template0", "template1"}
RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
PROOF_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


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
        if not parsed.username or parsed.password is None or not parsed.database:
            raise RehearsalError("PostgreSQL user, password and control database are required")
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
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PG")}
        env["PGPASSFILE"] = os.devnull
        if self.password is not None:
            env["PGPASSWORD"] = self.password
        return env


def reject_inherited_libpq_environment() -> None:
    inherited = sorted(key for key in os.environ if key.upper().startswith("PG"))
    if inherited:
        raise RehearsalError(
            "Inherited libpq environment is not allowed: " + ", ".join(inherited)
        )


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
    reject_inherited_libpq_environment()
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


def _database_metadata(connection: psycopg.Connection, database: str) -> tuple[bool, str | None, str | None]:
    row = connection.execute(
        """SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = %s),
                  (SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s),
                  (SELECT pg_catalog.shobj_description(oid, 'pg_database')
                     FROM pg_database WHERE datname = %s)""",
        (database, database, database),
    ).fetchone()
    return bool(row[0]), row[1], row[2]


def database_metadata(admin: PostgresAdmin, database: str) -> tuple[bool, str | None, str | None]:
    with connect(admin) as connection:
        return _database_metadata(connection, database)


def require_absent(admin: PostgresAdmin, *databases: str) -> None:
    if len(set(databases)) != len(databases):
        raise RehearsalError("Source and target databases must be different")
    for database in databases:
        exists, _, _ = database_metadata(admin, database)
        if exists:
            raise RehearsalError(f"Refusing existing database: {database}")


def ownership_marker(run_id: str, role: str, token: str) -> str:
    owned_database_name(run_id, role)
    if not PROOF_TOKEN_PATTERN.fullmatch(token):
        raise RehearsalError("Ownership proof token must be exactly 32 lowercase hexadecimal characters")
    return f"softwarelifecycle-rehearsal:{run_id}:{role}:{token}"


def ownership_proof_path(evidence_dir: Path, run_id: str) -> Path:
    owned_database_name(run_id, "source")
    return evidence_dir / f"postgresql-rehearsal-{run_id}-ownership.json"


def new_ownership_proof(run_id: str, admin: PostgresAdmin) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "token": uuid.uuid4().hex,
        "control": {"host": admin.host, "port": admin.port, "user": admin.user, "database": admin.database},
        "created_databases": {},
        "dropped_databases": [],
        "created_at": utc_now(),
    }


def validate_ownership_proof(proof: dict[str, Any], run_id: str, admin: PostgresAdmin) -> None:
    expected_control = {"host": admin.host, "port": admin.port, "user": admin.user, "database": admin.database}
    if (
        proof.get("schema_version") != 1
        or proof.get("run_id") != run_id
        or not isinstance(proof.get("token"), str)
        or not PROOF_TOKEN_PATTERN.fullmatch(proof["token"])
        or proof.get("control") != expected_control
        or not isinstance(proof.get("created_databases"), dict)
        or not isinstance(proof.get("dropped_databases"), list)
    ):
        raise RehearsalError("Ownership proof is missing or does not match this exact run")


def load_ownership_proof(path: Path, run_id: str, admin: PostgresAdmin) -> dict[str, Any]:
    try:
        proof = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RehearsalError("Persisted ownership proof is required for cleanup") from exc
    if not isinstance(proof, dict):
        raise RehearsalError("Persisted ownership proof must be a JSON object")
    validate_ownership_proof(proof, run_id, admin)
    return proof


def create_owned_database(
    admin: PostgresAdmin,
    run_id: str,
    role: str,
    proof: dict[str, Any],
    proof_path: Path,
) -> str:
    validate_ownership_proof(proof, run_id, admin)
    database = owned_database_name(run_id, role)
    require_absent(admin, database)
    marker = ownership_marker(run_id, role, proof["token"])
    with connect(admin) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
                sql.Identifier(database), sql.Identifier(admin.user)
            )
        )
        connection.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(database), sql.Literal(marker))
        )
    exists, owner, observed_marker = database_metadata(admin, database)
    if not exists or owner != admin.user or observed_marker != marker:
        raise RehearsalError(f"Database ownership verification failed: {database}")
    proof["created_databases"][role] = {"name": database, "marker": marker, "created_at": utc_now()}
    write_manifest(proof_path, proof)
    return database


def drop_owned_database(
    admin: PostgresAdmin,
    run_id: str,
    database: str,
    role: str,
    proof: dict[str, Any],
    proof_path: Path,
) -> None:
    assert_owned_database_name(run_id, database, role)
    validate_ownership_proof(proof, run_id, admin)
    expected_marker = ownership_marker(run_id, role, proof["token"])
    recorded = proof["created_databases"].get(role)
    if (
        not isinstance(recorded, dict)
        or recorded.get("name") != database
        or recorded.get("marker") != expected_marker
        or not isinstance(recorded.get("created_at"), str)
    ):
        raise RehearsalError(f"Persisted ownership proof does not cover {database}")
    with connect(admin) as connection:
        exists, owner, observed_marker = _database_metadata(connection, database)
        if not exists:
            return
        if owner != admin.user:
            raise RehearsalError(f"Refusing database owned by {owner!r}: {database}")
        if observed_marker != expected_marker:
            raise RehearsalError(f"Refusing database without exact run-created marker: {database}")
        connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
    proof["dropped_databases"].append({"role": role, "name": database, "dropped_at": utc_now()})
    write_manifest(proof_path, proof)


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
    reject_inherited_libpq_environment()
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


def canonical_fixture(run_id: str, ids: dict[str, str]) -> dict[str, Any]:
    return {
        "supplier": {
            "id": ids["supplier"], "code": f"SYN-{run_id}",
            "name": "Synthetic rehearsal supplier", "status": "ACTIVE",
        },
        "software": {
            "id": ids["software"], "supplier_id": ids["supplier"],
            "code": f"SW-{run_id}", "name": "Synthetic rehearsal software", "status": "ACTIVE",
        },
        "customer": {
            "id": ids["customer"], "code": f"C-{run_id}",
            "name": "Synthetic rehearsal customer", "region": "OTHER", "status": "ACTIVE",
        },
        "project": {
            "id": ids["project"], "customer_id": ids["customer"],
            "project_code": f"P-{run_id}", "name": "Synthetic rehearsal project", "status": "ACTIVE",
        },
        "release": {
            "id": ids["release"], "software_id": ids["software"],
            "release_type": "STANDARD", "version": f"rehearsal-{run_id}", "status": "DRAFT",
        },
        "audit": {
            "id": ids["audit"], "event_no": f"REHEARSAL-{run_id}", "event_type": "REHEARSAL",
            "action": "SYNTHETIC_FIXTURE_CREATED", "entity_type": "Release",
            "entity_id": ids["release"], "entity_ref": f"release:{ids['release']}",
            "actor_name": "synthetic-rehearsal",
            "summary": f"Synthetic backup/restore fixture {run_id}",
            "detail": "No real company or customer data",
            "payload": {"run_id": run_id, "synthetic": True, "release_id": ids["release"]},
        },
    }


def _fixture_row(
    connection: psycopg.Connection,
    query: str,
    params: tuple[Any, ...],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise RehearsalError("Canonical synthetic fixture row is missing")
    return dict(zip(fields, row, strict=True))


def _one(connection: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise RehearsalError("Expected verification row is missing")
    return row[0]


def inventory(admin: PostgresAdmin, database: str, run_id: str, ids: dict[str, str]) -> dict[str, Any]:
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
        fixture = {
            "supplier": _fixture_row(
                connection,
                "SELECT id::text, code, name, status FROM suppliers WHERE id = %s",
                (ids["supplier"],), ("id", "code", "name", "status"),
            ),
            "software": _fixture_row(
                connection,
                "SELECT id::text, supplier_id::text, code, name, status FROM software_products WHERE id = %s",
                (ids["software"],), ("id", "supplier_id", "code", "name", "status"),
            ),
            "customer": _fixture_row(
                connection,
                "SELECT id::text, code, name, region, status FROM customers WHERE id = %s",
                (ids["customer"],), ("id", "code", "name", "region", "status"),
            ),
            "project": _fixture_row(
                connection,
                "SELECT id::text, customer_id::text, project_code, name, status FROM projects WHERE id = %s",
                (ids["project"],), ("id", "customer_id", "project_code", "name", "status"),
            ),
            "release": _fixture_row(
                connection,
                "SELECT id::text, software_id::text, release_type, version, status FROM releases WHERE id = %s",
                (ids["release"],), ("id", "software_id", "release_type", "version", "status"),
            ),
            "audit": _fixture_row(
                connection,
                """SELECT id::text, event_no, event_type, action, entity_type, entity_id::text,
                          entity_ref, actor_name, summary, detail, payload_json
                     FROM audit_events WHERE id = %s""",
                (ids["audit"],),
                ("id", "event_no", "event_type", "action", "entity_type", "entity_id",
                 "entity_ref", "actor_name", "summary", "detail", "payload"),
            ),
        }
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
    if counts != {table: 1 for table in counts}:
        raise RehearsalError("Synthetic fixture row counts are not canonical")
    if fixture != canonical_fixture(run_id, ids):
        raise RehearsalError("Canonical synthetic fixture data or relationships differ")
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
        "fixture": fixture,
    }


def assert_restored_inventory_matches(source: dict[str, Any], target: dict[str, Any]) -> None:
    if source != target:
        raise RehearsalError("Restored schema/data/audit inventory differs from source")


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
        ["git", "cat-file", "-p", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    checkout = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    checkout_commit = checkout.stdout.strip()
    parents = [line.split()[1] for line in completed.stdout.splitlines() if line.startswith("parent ")]
    if (
        completed.returncode
        or checkout.returncode
        or not re.fullmatch(r"[0-9a-f]{40}", checkout_commit)
        or any(not re.fullmatch(r"[0-9a-f]{40}", item) for item in parents)
    ):
        raise RehearsalError("Unable to determine exact source commit")
    # actions/checkout tests a synthetic merge ref for pull_request events.  Its
    # commit object retains both parent SHAs even in a depth-one clone.  The
    # second parent is the exact feature head whose bytes are under review.
    source_commit = parents[1] if os.environ.get("GITHUB_EVENT_NAME") == "pull_request" and len(parents) == 2 else checkout_commit
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
    proof_path = ownership_proof_path(evidence_dir, run_id)
    report_path = evidence_dir / "postgresql-backup-restore-rehearsal.json"
    proof = new_ownership_proof(run_id, admin)
    write_manifest(proof_path, proof)
    created: list[tuple[str, str]] = []
    report: dict[str, Any] = {
        "status": "running", "run_id": run_id, "source_commit": exact_commit,
        "checkout_commit": checkout_commit,
        "started_at": utc_now(), "owned_databases": {"source": source, "target": target},
    }
    try:
        create_owned_database(admin, run_id, "source", proof, proof_path)
        created.append((source, "source"))
        migrate_source(repo_root, admin, source)
        ids = load_synthetic_fixture(admin, source, run_id)
        source_inventory = inventory(admin, source, run_id, ids)
        dump_database(admin, source, archive)
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "source_commit": exact_commit,
            "checkout_commit": checkout_commit,
            "created_at": utc_now(),
            "synthetic_fixture": True,
            "owned_databases": {"source": source, "target": target},
            "ownership_proof": proof_path.name,
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
        create_owned_database(admin, run_id, "target", proof, proof_path)
        created.append((target, "target"))
        restore_database(admin, target, archive)
        target_inventory = inventory(admin, target, run_id, ids)
        assert_restored_inventory_matches(source_inventory, target_inventory)
        append_only = prove_append_only(admin, source, target, ids["audit"])
        report.update({
            "status": "passed",
            "completed_at": utc_now(),
            "manifest": manifest_path.name,
            "ownership_proof": proof_path.name,
            "archive": {"file": archive.name, "size": manifest["archive_size"], "sha256": manifest["archive_sha256"]},
            "source_inventory": source_inventory,
            "target_inventory": target_inventory,
            "append_only": append_only,
            "cleanup": "pending" if cleanup_on_success else "retained",
        })
        write_manifest(report_path, report)
        if cleanup_on_success:
            for database, role in reversed(created):
                drop_owned_database(admin, run_id, database, role, proof, proof_path)
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
            proof_path = ownership_proof_path(args.evidence_dir, args.cleanup_run_id)
            proof = load_ownership_proof(proof_path, args.cleanup_run_id, admin)
            for role in ("target", "source"):
                if role not in proof["created_databases"]:
                    continue
                database = owned_database_name(args.cleanup_run_id, role)
                drop_owned_database(admin, args.cleanup_run_id, database, role, proof, proof_path)
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
