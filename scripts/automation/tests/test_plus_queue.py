import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("codex_plus_queue", Path(__file__).resolve().parents[2] / "codex_plus.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class PlusQueueTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs/automation").mkdir(parents=True)
            (root / "docs/automation/plus-tasks.json").write_text(json.dumps(data))
            with patch.object(launcher, "ROOT", root):
                return launcher.load_plus_tasks()

    def queue(self):
        return json.loads((launcher.ROOT / "docs/automation/plus-tasks.json").read_text())

    def test_current_queue_has_evidence_and_one_scoped_review(self):
        tasks = launcher.load_plus_tasks()
        self.assertEqual([t["evidence"]["pr"] for t in tasks if t["status"] == "completed"], [47, 48])
        pending = [t for t in tasks if t["status"] == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], "impact-withdrawal-design-review")
        self.assertIn("impact-withdrawal-design-review", launcher.task_summary(tasks)[-2])

    def test_invalid_completion_or_dependency_cannot_start(self):
        for mutation in ("evidence", "dependency", "duplicate", "mode"):
            data = self.queue()
            if mutation == "evidence":
                data["tasks"][0]["evidence"]["merge_sha"] = "pending"
            elif mutation == "dependency":
                data["tasks"][0]["depends_on"] = [data["tasks"][-1]["id"]]
            elif mutation == "duplicate":
                data["tasks"].append(data["tasks"][-1])
            else:
                data["mode"] = "api"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.load(data)

    def test_review_cannot_expand_to_migration_or_unsafe_paths(self):
        for path in ("backend/alembic/versions/0023_impact.py", "docs/../secrets.md", "docs/*.md", "/docs/review.md", ".github/workflows/ci.yml"):
            data = self.queue()
            data["tasks"][-1]["allowed_paths"] = [path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.load(data)

    def test_completed_dependencies_do_not_release_blocked_tasks(self):
        tasks = launcher.load_plus_tasks()
        tasks[-1]["status"] = "blocked"
        self.assertIn("无；停止", launcher.task_summary(tasks)[-2])

    def test_show_tasks_has_no_tool_or_model_calls(self):
        with patch.object(launcher.sys, "argv", ["launcher", "--show-tasks"]), patch.object(launcher, "check_environment") as check, patch.object(launcher.subprocess, "call") as call, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(), 0)
        check.assert_not_called()
        call.assert_not_called()
        self.assertIn("impact-withdrawal-design-review", output.getvalue())

    def test_unreadable_queue_blocks_show_tasks(self):
        with patch.object(launcher.sys, "argv", ["launcher", "--show-tasks"]), patch.object(launcher, "load_plus_tasks", side_effect=ValueError("secret text")), redirect_stderr(io.StringIO()) as output:
            self.assertEqual(launcher.main(), 2)
        self.assertNotIn("secret text", output.getvalue())


if __name__ == "__main__":
    unittest.main()
