"""Smoke-check a sample-only, read-only API deployment (standard library only)."""
import json
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check(base: str) -> None:
    origin = base.rstrip("/")
    for path in ("/health/ready", "/api/v1/releases/application",
                 "/api/v1/issues/310/impact", "/api/v1/activity"):
        with urlopen(origin + path, timeout=10) as response:
            payload = json.load(response)
        if path == "/health/ready" and (payload.get("status") != "ready" or payload.get("database_revision") != "0017_deployment_actual_version"):
            raise RuntimeError(f"API or migration not ready: {payload}")
        print(f"OK {path}")

    # A random release ID cannot modify a real record even if the read-only guard is misconfigured.
    path = f"/api/v1/releases/{uuid.uuid4()}/create-snapshot"
    try:
        urlopen(Request(origin + path, data=b"", method="POST"), timeout=10)
    except HTTPError as exc:
        if exc.code != 403 or json.load(exc).get("detail") != "read_only_mode":
            raise RuntimeError(f"Expected read-only 403, got {exc.code}") from exc
        print("OK read-only write guard")
    else:
        raise RuntimeError("Unexpected write request success")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        raise SystemExit("Usage: python scripts/check_staging.py https://public-api-host")
    try:
        check(sys.argv[1])
    except (HTTPError, URLError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Staging check failed: {exc}") from exc
