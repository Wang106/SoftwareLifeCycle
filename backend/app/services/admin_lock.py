"""One transaction gate for API and offline administrative writers."""
from sqlalchemy import text


def admin_write_gate(db):
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(1397506887, 1)'))
