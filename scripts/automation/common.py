"""Fail-closed policy shared by the trusted scheduler and clean publisher."""
import base64
import fnmatch
import json
import re
from pathlib import PurePosixPath

# GitHub outputs travel through an env var on the clean publisher. Linux limits
# an individual environment string to ~128 KiB; keep base64 + JSON below it.
MAX_PATCH = 49152
REQUIRED_JOBS = {
    "Backend, PostgreSQL and migrations",
    "Frontend tests and Cloudflare production build",
    "CI acceptance",
}
PROTECTED = (
    ".github/", ".git", ".agents/", ".codex/", "scripts/automation/",
    "scripts/ci/", "docs/automation/", "AGENTS.md", "START_HERE.md",
    "frontend/scripts/", "frontend/package", "frontend/wrangler",
    "frontend/open-next", "backend/requirements", "backend/alembic/",
    "backend/alembic.ini", "backend/tests/conftest.py", "backend/pytest.ini",
    "frontend/tests/", "backend/tests/", "docs/development-plan-progress.json",
)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Invalid commit SHA")
    return value


def task_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
        raise ValueError("Invalid task ID")
    return value


def validate_path(path, task, added=False):
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_./()\[\]-]+", path):
        raise ValueError("Unsafe path")
    parts = PurePosixPath(path).parts
    if path.startswith("/") or ".." in parts or "." in parts or "//" in path:
        raise ValueError("Unsafe path")
    # Existing tests cannot be edited/deleted by unattended development. New tests
    # are permitted under explicitly scoped paths; weakening a baseline is manual.
    if path == "backend/tests/conftest.py":
        raise ValueError("Protected fixture bootstrap")
    if path.startswith(("frontend/tests/", "backend/tests/")) and added:
        pass
    elif any(path.startswith(prefix) for prefix in PROTECTED):
        raise ValueError("Protected path: " + path)
    if not any(fnmatch.fnmatchcase(path, pattern) for pattern in task["allowed_paths"]):
        raise ValueError("Outside task scope: " + path)


def validate_tasks(data):
    if data.get("schema") != 1 or not isinstance(data.get("tasks"), list):
        raise ValueError("Invalid task queue")
    known = set()
    for task in data["tasks"]:
        tid = task_id(task["id"])
        if tid in known or not task.get("acceptance") or not task.get("allowed_paths"):
            raise ValueError("Duplicate or incomplete task")
        if task.get("enabled") not in (True, False) or task.get("auto_merge") not in (True, False):
            raise ValueError("Explicit task gates required")
        if not set(task.get("depends_on", [])).issubset(known):
            raise ValueError("Dependencies must precede task")
        if task["auto_merge"] and not task.get("enabled"):
            raise ValueError("Disabled tasks cannot auto-merge")
        known.add(tid)
    return data["tasks"]


def validate_candidate(text, expected_task, expected_base):
    if len(text.encode()) > MAX_PATCH * 2:
        raise ValueError("Oversize candidate")
    data = strict_json(text)
    if set(data) != {"task_id", "base_sha", "status", "summary", "patch_b64"}:
        raise ValueError("Unexpected candidate fields")
    if data["task_id"] != expected_task or sha(data["base_sha"]) != expected_base:
        raise ValueError("Candidate identity mismatch")
    if data["status"] not in ("ready", "checkpoint", "blocked"):
        raise ValueError("Invalid candidate status")
    if not isinstance(data["summary"], str) or len(data["summary"]) > 2000:
        raise ValueError("Invalid summary")
    patch = base64.b64decode(data["patch_b64"], validate=True)
    if len(patch) > MAX_PATCH:
        raise ValueError("Oversize patch")
    if data["status"] == "blocked" and patch:
        raise ValueError("Blocked candidate must not contain a patch")
    if data["status"] != "blocked" and not patch:
        raise ValueError("Empty candidate patch")
    return data, patch


def successful_ci(run, jobs, expected_sha, branch):
    """A run's green conclusion alone never authorizes merge."""
    if not run or run.get("head_sha") != expected_sha or run.get("head_branch") != branch:
        return False
    if run.get("event") not in ("pull_request", "push", "workflow_dispatch"):
        return False
    if run.get("path") != ".github/workflows/ci.yml" or run.get("conclusion") != "success":
        return False
    by_name = {job["name"]: job for job in jobs}
    if any(sum(job["name"] == name for job in jobs) != 1 for name in REQUIRED_JOBS):
        return False
    return all(name in by_name and by_name[name].get("conclusion") == "success"
               and by_name[name].get("status") == "completed" for name in REQUIRED_JOBS)
