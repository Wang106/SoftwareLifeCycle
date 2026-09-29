import json

from sqlalchemy.exc import SQLAlchemyError

from app import main


class FakeResult:
    def __init__(self, revision):
        self.revision = revision

    def scalar_one(self):
        return self.revision


class FakeConnection:
    def __init__(self, revision):
        self.revision = revision

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        return FakeResult(self.revision)


class FakeEngine:
    def __init__(self, revision):
        self.revision = revision

    def connect(self):
        return FakeConnection(self.revision)


class UnavailableEngine:
    def connect(self):
        raise SQLAlchemyError("database unavailable")


def test_liveness_does_not_require_database():
    assert main.liveness() == {"status": "ok", "version": main.APP_VERSION}


def test_readiness_reports_current_database_revision(monkeypatch):
    monkeypatch.setattr(main, "engine", FakeEngine(main.settings.required_db_revision))

    response = main.readiness()

    assert response == {
        "status": "ready",
        "version": main.APP_VERSION,
        "database_revision": main.settings.required_db_revision,
    }


def test_readiness_rejects_stale_database_revision(monkeypatch):
    monkeypatch.setattr(main, "engine", FakeEngine("0008_authorization_distribution_link"))

    response = main.readiness()
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["reason"] == "database_revision_mismatch"
    assert payload["required_revision"] == main.settings.required_db_revision


def test_readiness_rejects_unavailable_database(monkeypatch):
    monkeypatch.setattr(main, "engine", UnavailableEngine())

    response = main.readiness()
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload == {"status": "not_ready", "reason": "database_unavailable"}
