import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api import distribution
from app.models.distribution import DeliveryPackage


class Rows:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class Session:
    def __init__(self, row=None):
        self.row = row
        self.statement = None

    def scalars(self, statement):
        self.statement = statement
        return Rows(self.row)


def test_delivery_revision_selects_exact_record(monkeypatch):
    package = DeliveryPackage(id=uuid.uuid4(), package_no="DP-0226", revision=1)
    db = Session(package)
    monkeypatch.setattr(distribution, "_delivery_detail", lambda session, row: (session, row))

    assert distribution.get_delivery_revision("DP-0226", 1, db=db) == (db, package)
    compiled = db.statement.compile(dialect=postgresql.dialect())
    assert "delivery_packages.package_no =" in str(compiled)
    assert "delivery_packages.revision =" in str(compiled)
    assert "DP-0226" in compiled.params.values() and 1 in compiled.params.values()


def test_delivery_revision_rejects_missing_or_invalid_revision():
    with pytest.raises(HTTPException) as missing:
        distribution.get_delivery_revision("DP-0226", 2, db=Session())
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as invalid:
        distribution.get_delivery_revision("DP-0226", 0, db=Session())
    assert invalid.value.status_code == 422
