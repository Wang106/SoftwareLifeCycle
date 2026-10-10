"""Offline behavior regressions: no API keys, network, paid calls or provider writes."""
import base64
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/automation"))
from common import MAX_PATCH, REQUIRED_JOBS, strict_json, successful_ci, validate_candidate, validate_path, validate_tasks
from github_api import APIError, StateStore
from orchestrator import reconcile, select, tick, validate_remote_diff
from publish import apply_and_read, publish

MAIN = "a" * 40
HEAD = "b" * 40
MERGE = "c" * 40
TASK = {"id": "sample", "title": "Sample", "enabled": True, "auto_merge": True,
        "depends_on": [], "allowed_paths": ["frontend/components/sample.tsx", "frontend/tests/new.test.cjs"],
        "acceptance": ["Behavior is verified"]}


def state():
    return {"schema": 1, "tasks": {}, "daily": {}, "events": []}


def record(status="waiting_ci"):
    return {"status": status, "branch": "codex/auto/sample", "work_sha": MAIN,
            "head_sha": HEAD, "base_main_sha": MAIN, "attempts": 1, "run_id": "42", "pr": 1}


def run(head=HEAD, branch="codex/auto/sample", conclusion="success"):
    return {"id": 100, "path": ".github/workflows/ci.yml", "head_sha": head, "head_branch": branch,
            "event": "pull_request", "conclusion": conclusion, "status": "completed"}


def jobs():
    return [{"name": name, "status": "completed", "conclusion": "success"} for name in REQUIRED_JOBS]


class MemoryStore:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.saves = 0

    def load(self, main):
        return copy.deepcopy(self.value)

    def save(self, value):
        self.value = copy.deepcopy(value)
        self.saves += 1


class FakeAPI:
    repo = "Wang106/SoftwareLifeCycle"

    def __init__(self):
        self.refs = {"main": MAIN}
        self.running = False
        self.calls = []
        self.ci = run()
        self.ci_jobs = jobs()
        self.remote_files = [{"filename": "frontend/components/sample.tsx", "status": "added", "additions": 1, "deletions": 0}]
        self.pr = {"number": 1, "state": "open", "merged": False,
                   "base": {"ref": "main"}, "head": {"ref": "codex/auto/sample", "sha": HEAD,
                   "repo": {"full_name": self.repo}}}
        self.commit_message = "codex-auto sample run 42 ready\n\nSample"
        self.merge_error = None
        self.open_prs = []

    def ref(self, branch):
        if branch not in self.refs:
            raise APIError(404, "ref")
        return self.refs[branch]

    def get(self, suffix, **params):
        self.calls.append(("GET", suffix))
        if suffix.startswith("actions/runs/"):
            return {"status": "in_progress" if self.running else "completed"}
        if suffix == "actions/workflows/ci.yml/runs":
            if params.get("head_sha") == MERGE:
                return {"workflow_runs": [run(MERGE, "main")]}
            if params.get("head_sha") == MAIN:
                return {"workflow_runs": [run(MAIN, "main")]}
            return {"workflow_runs": [self.ci] if self.ci else []}
        if suffix.startswith("compare/"):
            return {"files": self.remote_files}
        if suffix == "pulls/1":
            return self.pr
        if suffix == "pulls":
            return []
        if suffix.startswith("git/commits/"):
            return {"message": self.commit_message, "tree": {"sha": MAIN}}
        raise AssertionError(suffix)

    def pages(self, suffix, key=None, **params):
        if suffix == "pulls":
            return self.open_prs
        return self.ci_jobs

    def mutate(self, suffix, method, data):
        self.calls.append((method, suffix, copy.deepcopy(data)))
        if suffix == "git/refs":
            self.refs[data["ref"].removeprefix("refs/heads/")] = data["sha"]
            return {}
        if suffix == "pulls":
            return self.pr
        if suffix.endswith("/merge"):
            if self.merge_error:
                raise APIError(self.merge_error, suffix)
            return {"merged": True, "sha": MERGE}
        if suffix == "merges":
            return {"sha": HEAD}
        if suffix == "git/blobs":
            return {"sha": HEAD}
        if suffix == "git/trees":
            return {"sha": HEAD}
        if suffix == "git/commits":
            return {"sha": HEAD}
        if suffix.startswith("git/refs/heads/"):
            self.refs[suffix.removeprefix("git/refs/heads/")] = data["sha"]
            return {}
        raise AssertionError(suffix)


class GateTests(unittest.TestCase):
    def test_queue_matches_approved_dependency_order(self):
        queue = validate_tasks(json.loads((ROOT / "docs/automation/tasks.json").read_text()))
        self.assertEqual(queue[0]["id"], "acceptance-correction-ui")
        self.assertEqual(sum(task["enabled"] for task in queue), 2)

    def test_duplicate_and_forward_dependencies_rejected(self):
        for tasks in ([TASK, TASK], [{**TASK, "depends_on": ["missing"]}]):
            with self.assertRaises(ValueError):
                validate_tasks({"schema": 1, "tasks": tasks})

    def test_duplicate_json_and_nonfinite_rejected(self):
        for data in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                strict_json(data)

    def test_candidate_identity_and_fields(self):
        obj = {"task_id": "sample", "base_sha": MAIN, "status": "ready", "summary": "ok",
               "patch_b64": base64.b64encode(b"diff").decode()}
        self.assertEqual(validate_candidate(json.dumps(obj), "sample", MAIN)[1], b"diff")
        for change in ({"base_sha": HEAD}, {"task_id": "other"}, {"extra": True}, {"patch_b64": "@@"},
                       {"status": "blocked"}, {"patch_b64": ""}):
            with self.assertRaises((ValueError, TypeError)):
                validate_candidate(json.dumps({**obj, **change}), "sample", MAIN)

    def test_size_limit_and_blocked_without_patch(self):
        obj = {"task_id": "sample", "base_sha": MAIN, "status": "blocked", "summary": "needs review", "patch_b64": ""}
        self.assertEqual(validate_candidate(json.dumps(obj), "sample", MAIN)[1], b"")
        obj.update(status="ready", patch_b64=base64.b64encode(b"a" * (MAX_PATCH + 1)).decode())
        with self.assertRaises(ValueError):
            validate_candidate(json.dumps(obj), "sample", MAIN)

    def test_path_protection_even_when_scope_is_wide(self):
        broad = {**TASK, "allowed_paths": ["*"]}
        for path in ("../escape", "/escape", "frontend//components/a", ".github/workflows/ci.yml",
                     "AGENTS.md", "scripts/automation/common.py", "frontend/package-lock.json",
                     "backend/alembic/versions/9999.py", "backend/tests/conftest.py"):
            with self.assertRaises(ValueError, msg=path):
                validate_path(path, broad)

    def test_existing_tests_protected_but_new_scoped_tests_allowed(self):
        validate_path("frontend/tests/new.test.cjs", TASK, added=True)
        with self.assertRaises(ValueError):
            validate_path("frontend/tests/new.test.cjs", TASK)
        with self.assertRaises(ValueError):
            validate_path("frontend/components/other.tsx", TASK)
        with self.assertRaises(ValueError):
            validate_path("backend/tests/conftest.py", {**TASK, "allowed_paths": ["*"]}, added=True)

    def test_exact_sha_jobs_and_event_all_required(self):
        self.assertTrue(successful_ci(run(), jobs(), HEAD, "codex/auto/sample"))
        for candidate in (run(MAIN), {**run(), "event": "workflow_run"}, {**run(), "path": "other.yml"}, run(conclusion="cancelled")):
            self.assertFalse(successful_ci(candidate, jobs(), HEAD, "codex/auto/sample"))
        self.assertFalse(successful_ci(run(), jobs()[:-1], HEAD, "codex/auto/sample"))
        self.assertFalse(successful_ci(run(), jobs() + [jobs()[0]], HEAD, "codex/auto/sample"))
        skipped = [{**item, "conclusion": "skipped"} for item in jobs()]
        self.assertFalse(successful_ci(run(), skipped, HEAD, "codex/auto/sample"))

    def test_remote_diff_rejects_truncation_deletion_and_scope(self):
        api = FakeAPI()
        for files in ([], api.remote_files * 300, [{"filename": "AGENTS.md", "status": "modified"}],
                      [{"filename": "frontend/components/sample.tsx", "status": "removed"}]):
            api.remote_files = files
            with self.assertRaises(ValueError):
                validate_remote_diff(api, TASK, MAIN, HEAD)


class RecoveryTests(unittest.TestCase):
    def test_dependency_budget_and_blocked_stop_queue(self):
        value = state()
        self.assertEqual(select([TASK], value, "2026-10-10"), TASK)
        value["daily"]["2026-10-10"] = 6
        self.assertIsNone(select([TASK], value, "2026-10-10"))
        value["daily"].clear()
        value["tasks"]["other"] = {"status": "blocked"}
        self.assertIsNone(select([TASK], value, "2026-10-10"))
        self.assertIsNone(select([{**TASK, "depends_on": ["other"]}], state(), "2026-10-10"))

    def test_reservation_persists_before_execution_and_counts_budget(self):
        api, store = FakeAPI(), MemoryStore(state())
        result = tick(api, store, [TASK], MAIN, "42")
        self.assertEqual(result["execute"], "true")
        self.assertEqual(store.value["tasks"]["sample"]["status"], "developing")
        self.assertEqual(sum(store.value["daily"].values()), 1)
        self.assertEqual(store.value["tasks"]["sample"]["attempts"], 1)

    def test_superseded_controller_has_no_writes(self):
        api, store = FakeAPI(), MemoryStore(state())
        self.assertEqual(tick(api, store, [TASK], HEAD, "42")["execute"], "false")
        self.assertEqual(store.saves, 0)
        self.assertFalse(any(call[0] != "GET" for call in api.calls))

    def test_unowned_branch_blocks_instead_of_overwriting(self):
        api, store = FakeAPI(), MemoryStore(state())
        api.refs["codex/auto/sample"] = HEAD
        self.assertEqual(tick(api, store, [TASK], MAIN, "42")["execute"], "false")
        self.assertEqual(store.value["tasks"]["sample"]["status"], "blocked")

    def test_other_open_pr_prevents_duplicate_development(self):
        api, store = FakeAPI(), MemoryStore(state())
        api.open_prs = [{"number": 99}]
        self.assertEqual(tick(api, store, [TASK], MAIN, "42")["execute"], "false")
        self.assertEqual(store.value["tasks"], {})

    def test_live_execution_never_reclaimed_by_timer(self):
        api, value = FakeAPI(), state()
        api.running = True
        value["tasks"]["sample"] = record("developing")
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["status"], "developing")

    def test_duplicate_tick_does_not_reserve_second_execution(self):
        api, store = FakeAPI(), MemoryStore(state())
        self.assertEqual(tick(api, store, [TASK], MAIN, "42")["execute"], "true")
        api.running = True
        self.assertEqual(tick(api, store, [TASK], MAIN, "43")["execute"], "false")
        self.assertEqual(sum(store.value["daily"].values()), 1)
        self.assertEqual(store.value["tasks"]["sample"]["run_id"], "42")

    def test_terminal_execution_without_patch_resumes_but_budget_is_bounded(self):
        for attempts, expected in ((1, "ready"), (3, "blocked")):
            api, value = FakeAPI(), state()
            api.refs["codex/auto/sample"] = MAIN
            value["tasks"]["sample"] = {**record("developing"), "attempts": attempts}
            reconcile(api, [TASK], value, MAIN)
            self.assertEqual(value["tasks"]["sample"]["status"], expected)

    def test_crash_after_push_recovers_pr_without_another_model_call(self):
        api, value = FakeAPI(), state()
        api.refs["codex/auto/sample"] = HEAD
        api.ci = None
        value["tasks"]["sample"] = record("developing")
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["status"], "waiting_ci")
        self.assertTrue(any(call[:2] == ("POST", "pulls") for call in api.calls))

    def test_checkpoint_recovery_resumes_same_branch(self):
        api, value = FakeAPI(), state()
        api.refs["codex/auto/sample"] = HEAD
        api.commit_message = "codex-auto sample run 42 checkpoint"
        value["tasks"]["sample"] = record("developing")
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["status"], "ready")
        self.assertFalse(any(call[:2] == ("POST", "pulls") for call in api.calls))

    def test_unexpected_branch_update_blocks_recovery(self):
        api, value = FakeAPI(), state()
        api.refs["codex/auto/sample"] = HEAD
        api.commit_message = "unrelated writer"
        value["tasks"]["sample"] = record("developing")
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["status"], "blocked")

    def test_failed_and_missing_ci_do_not_merge(self):
        for candidate, expected in ((run(conclusion="failure"), "ready"), (None, "waiting_ci")):
            api, value = FakeAPI(), state()
            api.ci = candidate
            value["tasks"]["sample"] = record()
            reconcile(api, [TASK], value, MAIN)
            self.assertEqual(value["tasks"]["sample"]["status"], expected)
            self.assertFalse(any(call[0] == "PUT" for call in api.calls))

    def test_changed_pr_and_fork_heads_never_merge(self):
        for change in ("sha", "repo"):
            api, value = FakeAPI(), state()
            if change == "sha":
                api.pr["head"]["sha"] = MAIN
            else:
                api.pr["head"]["repo"]["full_name"] = "fork/SoftwareLifeCycle"
            value["tasks"]["sample"] = record()
            reconcile(api, [TASK], value, MAIN)
            self.assertEqual(value["tasks"]["sample"]["status"], "blocked")

    def test_main_change_synchronizes_without_force_and_requires_fresh_ci(self):
        api, value = FakeAPI(), state()
        value["tasks"]["sample"] = record()
        reconcile(api, [TASK], value, MERGE)
        self.assertEqual(value["tasks"]["sample"]["base_main_sha"], MERGE)
        self.assertTrue(any(call[:2] == ("POST", "merges") for call in api.calls))
        self.assertFalse(any(call[0] == "PUT" for call in api.calls))

    def test_successful_pr_and_main_ci_accept_code_without_claiming_deployment(self):
        api, value = FakeAPI(), state()
        value["tasks"]["sample"] = record()
        reconcile(api, [TASK], value, MAIN)
        result = value["tasks"]["sample"]
        self.assertEqual(result["status"], "done_code")
        self.assertEqual(result["deployment"], "unverified")
        self.assertEqual(result["main_ci"]["sha"], MERGE)

    def test_strict_deployment_gate_holds_queue(self):
        api, value = FakeAPI(), state()
        value["tasks"]["sample"] = record()
        reconcile(api, [TASK], value, MAIN, require_deployment=True)
        self.assertEqual(value["tasks"]["sample"]["status"], "merged_pending")
        self.assertIsNone(select([TASK], value, "2026-10-10"))

    def test_merge_response_lost_recovers_from_actual_pr_without_remerge(self):
        api, value = FakeAPI(), state()
        api.pr.update(merged=True, merge_commit_sha=MERGE)
        value["tasks"]["sample"] = record()
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["merge_sha"], MERGE)
        self.assertFalse(any(call[0] == "PUT" for call in api.calls))
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["status"], "done_code")

    def test_main_ci_failure_blocks_even_after_pr_success(self):
        api, value = FakeAPI(), state()
        value["tasks"]["sample"] = {**record("merged_pending"), "merge_sha": HEAD}
        api.ci = run(HEAD, "main", "failure")
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["status"], "blocked")

    def test_branch_protection_denial_is_persisted_without_bypass(self):
        api, value = FakeAPI(), state()
        api.merge_error = 403
        value["tasks"]["sample"] = record()
        reconcile(api, [TASK], value, MAIN)
        self.assertEqual(value["tasks"]["sample"]["status"], "blocked")
        self.assertIn("no bypass", value["tasks"]["sample"]["reason"])


class PublicationTests(unittest.TestCase):
    def repo(self, directory):
        work = Path(directory)
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "--allow-empty", "-qm", "base"], check=True)
        base = subprocess.check_output(["git", "-C", str(work), "rev-parse", "HEAD"], text=True).strip()
        return work, base

    def make_patch(self, work, path, content, executable=False):
        file = work / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        if executable:
            file.chmod(0o755)
        subprocess.run(["git", "-C", str(work), "add", path], check=True)
        data = subprocess.check_output(["git", "-C", str(work), "diff", "--cached", "--binary"])
        subprocess.run(["git", "-C", str(work), "reset", "--hard", "-q"], check=True)
        return data

    def test_real_git_patch_applies_and_reads_only_scoped_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            work, base = self.repo(directory)
            data = self.make_patch(work, "frontend/components/sample.tsx", "export const x = 1;\n")
            self.assertEqual(apply_and_read(work, data, TASK, base),
                             [("frontend/components/sample.tsx", b"export const x = 1;\n")])

    def test_executable_and_credentials_rejected_before_publication(self):
        for content, executable in (("plain\n", True), ("-----BEGIN PRIVATE KEY-----\n", False)):
            with tempfile.TemporaryDirectory() as directory:
                work, base = self.repo(directory)
                data = self.make_patch(work, "frontend/components/sample.tsx", content, executable)
                with self.assertRaises(ValueError):
                    apply_and_read(work, data, TASK, base)

    def test_partial_task_test_can_be_completed_but_main_baseline_test_cannot(self):
        with tempfile.TemporaryDirectory() as directory:
            work, _ = self.repo(directory)
            file = work / "frontend/tests/new.test.cjs"
            file.parent.mkdir(parents=True)
            file.write_text("// checkpoint\n")
            subprocess.run(["git", "-C", str(work), "add", "."], check=True)
            subprocess.run(["git", "-C", str(work), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "commit", "-qm", "checkpoint"], check=True)
            base = subprocess.check_output(["git", "-C", str(work), "rev-parse", "HEAD"], text=True).strip()
            data = self.make_patch(work, "frontend/tests/new.test.cjs", "// completed regression\n")
            self.assertEqual(apply_and_read(work, data, TASK, base, {"frontend/tests/new.test.cjs"})[0][0],
                             "frontend/tests/new.test.cjs")
            subprocess.run(["git", "-C", str(work), "reset", "--hard", "-q"], check=True)
            with self.assertRaises(ValueError):
                apply_and_read(work, data, TASK, base)

    def test_outside_scope_and_stale_output_do_not_write_github(self):
        with tempfile.TemporaryDirectory() as directory:
            work, base = self.repo(directory)
            data = self.make_patch(work, "AGENTS.md", "change\n")
            api, value = FakeAPI(), state()
            value["tasks"]["sample"] = {**record("developing"), "work_sha": base}
            store = MemoryStore(value)
            payload = json.dumps({"task_id": "sample", "base_sha": base, "status": "ready",
                                  "summary": "test", "patch_b64": base64.b64encode(data).decode()})
            for run_id in ("other", "42"):
                with self.assertRaises(ValueError):
                    publish(api, store, [TASK], payload, "sample", base, run_id, work)
            self.assertFalse(any(call[0] != "GET" for call in api.calls))

    def test_state_cas_includes_old_blob_sha_and_does_not_force_ref(self):
        class StoreAPI:
            def mutate(self, suffix, method, payload):
                self.payload = payload
                return {"content": {"sha": HEAD}}
        api = StoreAPI()
        store = StateStore(api)
        store.version = MAIN
        store.save(state())
        self.assertEqual(api.payload["sha"], MAIN)
        self.assertEqual(api.payload["branch"], "codex-state")
        self.assertNotIn("force", api.payload)

    def test_real_patch_publish_then_independent_ci_completes_code(self):
        with tempfile.TemporaryDirectory() as directory:
            work, base = self.repo(directory)
            data = self.make_patch(work, "frontend/components/sample.tsx", "export const x = 1;\n")
            api, value = FakeAPI(), state()
            api.refs["codex/auto/sample"] = base
            value["tasks"]["sample"] = {**record("developing"), "work_sha": base}
            store = MemoryStore(value)
            payload = json.dumps({"task_id": "sample", "base_sha": base, "status": "ready",
                                  "summary": "actual patch", "patch_b64": base64.b64encode(data).decode()})
            publish(api, store, [TASK], payload, "sample", base, "42", work)
            self.assertEqual(store.value["tasks"]["sample"]["status"], "waiting_ci")
            writes = [call for call in api.calls if call[0] == "PATCH"]
            self.assertEqual(writes[0][2]["force"], False)
            reconcile(api, [TASK], store.value, MAIN)
            self.assertEqual(store.value["tasks"]["sample"]["status"], "done_code")

    def test_disabled_cli_never_needs_tokens_or_creates_state(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            out, report = Path(directory) / "out", Path(directory) / "report"
            env = {key: val for key, val in os.environ.items() if key not in ("GH_TOKEN", "GITHUB_REPOSITORY")}
            env.update(AUTODEV_ENABLED="false", GITHUB_OUTPUT=str(out), GITHUB_STEP_SUMMARY=str(report))
            result = subprocess.run([sys.executable, str(ROOT / "scripts/automation/orchestrator.py")], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("execute=false", out.read_text())


if __name__ == "__main__":
    unittest.main()
