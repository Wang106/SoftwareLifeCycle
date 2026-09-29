from sqlalchemy.dialects import postgresql

from app.api.search import _pattern, global_search, search_records
from app.api.dashboard import dashboard_summary
from app.models.change import SoftwareChangeRequest
from app.models.core import Release
from app.models.production import Deployment, ProductionBatch
from app.models.audit import AuditEvent


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class SearchSession:
    def __init__(self):
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        model = statement.column_descriptions[0]["entity"]
        if model is SoftwareChangeRequest:
            return Rows([SoftwareChangeRequest(request_no="SCR-142", title="Charge timeout")])
        return Rows([])


def test_search_is_bounded_and_uses_literal_wildcards():
    db = SearchSession()
    result = search_records(db, "SCR%_142", 1)
    assert result == [{"type": "SCR", "label": "SCR-142", "description": "Charge timeout", "href": "/changes/SCR-142"}]
    assert len(db.statements) == 1
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert "%SCR\\%\\_142%" in compiled.params.values()
    assert "%(request_no_1)s" in str(compiled)
    assert _pattern("\\") == "%\\\\%"


def test_blank_query_does_not_scan_database():
    assert global_search(q="   ", limit=50, db=SearchSession()) == {"query": "   ", "results": []}


def test_search_audit_event_opens_its_formal_record():
    class AuditSession(SearchSession):
        def scalars(self, statement):
            self.statements.append(statement)
            if statement.column_descriptions[0]["entity"] is AuditEvent:
                return Rows([AuditEvent(event_no="EVT-0009", entity_ref="PB-1005-A", summary="Batch started")])
            return Rows([])

    results = search_records(AuditSession(), "EVT-0009", 50)
    assert results == [{"type": "Activity", "label": "EVT-0009", "description": "Batch started", "href": "/activity/EVT-0009"}]


class DashboardSession:
    def __init__(self):
        self.counts = iter([2, 3, 1, 1])

    def scalar(self, statement):
        return next(self.counts)

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is Release:
            return Rows([])
        if model is AuditEvent:
            return Rows([])
        raise AssertionError(model)


def test_dashboard_handles_empty_release_and_ledger():
    summary = dashboard_summary(db=DashboardSession())
    assert summary["active_changes"] == 2
    assert summary["high_open_issues"] == 1
    assert summary["current_release"] is None
    assert summary["recent_activity"] == []
