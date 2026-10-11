"""SQLite test schemas preserve UUID hex strings without numeric coercion.

Production PostgreSQL compilation and mapped UUID processors remain unchanged.
"""
from sqlalchemy import UUID, Uuid
from sqlalchemy.ext.compiler import compiles


@compiles(Uuid, 'sqlite')
@compiles(UUID, 'sqlite')
def sqlite_uuid_text(type_, compiler, **kw):
    return 'CHAR(32)'
