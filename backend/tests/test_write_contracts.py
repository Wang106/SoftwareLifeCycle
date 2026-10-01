from app.main import app
from app.security_roles import ALL_ROLES
from app.write_contracts import WRITE_CONTRACTS


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def registered_write_routes():
    return {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set()) - SAFE_METHODS
    }


def test_every_registered_write_route_has_exactly_one_reviewed_contract():
    assert set(WRITE_CONTRACTS) == registered_write_routes()


def test_current_write_contracts_remain_non_public_and_explicitly_unauthenticated():
    assert WRITE_CONTRACTS
    for contract in WRITE_CONTRACTS.values():
        assert contract.public_exposure == "READ_ONLY_BLOCKED"
        assert contract.authentication == "NONE"
        assert contract.authorization == "NONE"
        assert contract.actor_source in {"NONE", "DECLARED_OPTIONAL", "DECLARED_REQUIRED"}
        assert contract.audit in {"NONE", "ATOMIC_APPEND"}
        assert contract.idempotency in {"NONE", "REQUEST_ID"}
        assert contract.concurrency in {"NONE", "ROW_LOCK"}
        assert contract.planned_roles
        assert contract.planned_roles <= ALL_ROLES
        assert contract.known_gap.strip()
