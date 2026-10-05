"""Validate migrations in a disposable schema on the loopback CI database.

Run from backend with its development requirements installed. This deliberately
rejects remote databases and never runs migrations on the database's public schema.
"""
import io
import os
from pathlib import Path
import sys
import uuid

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Script execution does not otherwise put backend/app on the import path.
sys.path.insert(0, str(Path.cwd()))
from app.core.config import settings


def check_migrations():
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    if heads != [settings.required_db_revision]:
        raise ValueError(f"Expected single configured head {settings.required_db_revision}, got {heads}")
    head = scripts.get_revision(heads[0])
    if not isinstance(head.down_revision, str):
        raise ValueError("Head must have one predecessor for the round-trip check")
    url = make_url(os.environ["TEST_POSTGRES_URL"])
    if (url.get_backend_name() != "postgresql" or
            url.host not in {"localhost", "127.0.0.1", "::1"} or
            url.database != "software_lifecycle_ci" or url.query):
        raise ValueError("Use a loopback software_lifecycle_ci PostgreSQL database without URL options")
    url = url.set(drivername="postgresql+psycopg")
    settings.database_url = url.render_as_string(hide_password=False)
    evidence = Path("../ci-results")
    evidence.mkdir(exist_ok=True)
    for name, action in (
        ("upgrade.sql", lambda cfg: command.upgrade(cfg, "head", sql=True)),
        ("head-downgrade.sql", lambda cfg: command.downgrade(cfg, f"{head.revision}:{head.down_revision}", sql=True)),
    ):
        output = io.StringIO()
        action(Config("alembic.ini", output_buffer=output))
        sql = output.getvalue()
        if not sql.strip():
            raise ValueError(f"Empty generated migration SQL: {name}")
        (evidence / name).write_text(sql)

    engine = create_engine(url)
    schema = "ci_migration_" + uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = url.update_query_dict({"options": f"-csearch_path={schema}"})
    scoped_engine = create_engine(scoped)
    settings.database_url = scoped.render_as_string(hide_password=False)
    try:
        for target, migration in (("head", command.upgrade),
                                  (head.down_revision, command.downgrade),
                                  ("head", command.upgrade)):
            migration(config, target)
            expected = head.revision if target == "head" else target
            with scoped_engine.connect() as connection:
                actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
                if actual != expected:
                    raise ValueError(f"Migration revision mismatch: {actual}, expected {expected}")
        print(f"Migration evidence: single head {head.revision}, SQL and PostgreSQL round trip passed")
    finally:
        scoped_engine.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


if __name__ == "__main__":
    check_migrations()
