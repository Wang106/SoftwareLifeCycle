from alembic import context
from sqlalchemy import engine_from_config, pool, text
from app.core.config import settings
from app.core.db import Base
from app.models import core, snapshot, snapshot_policy, change, testing, governance, policy, approval, distribution, production, audit, impact

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    # Alembic defaults version_num to VARCHAR(32), but an existing revision ID
    # exceeds that length. Widen only Alembic's bookkeeping column before its
    # revision traversal; this also resumes databases halted at revision 0007.
    with connectable.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64) NOT NULL PRIMARY KEY)"))
        connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"))
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
