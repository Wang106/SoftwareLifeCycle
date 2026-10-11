import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import subprocess
import io
from contextlib import redirect_stdout, redirect_stderr

spec = importlib.util.spec_from_file_location("codex_plus", Path(__file__).resolve().parents[2] / "codex_plus.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class PlusLauncherTests(unittest.TestCase):
    def probe(self, remote="https://github.com/Wang106/SoftwareLifeCycle.git", dirty="", permission="WRITE", pulls="[]", node="v22.20.0"):
        def run(command, env):
            if "--version" in command:
                return node
            if "get-url" in command:
                return remote
            if "--porcelain" in command:
                return dirty
            if "view" in command:
                return '{"nameWithOwner":"Wang106/SoftwareLifeCycle","viewerPermission":"' + permission + '"}'
            return pulls
        return patch.object(launcher, "read_command", side_effect=run)

    def test_preflight_preserves_dirty_work_and_reports_open_pr(self):
        with patch.object(launcher.shutil, "which", side_effect=lambda name: "/bin/" + name), self.probe(dirty=" M file", pulls='[{"number":52}]'):
            errors, notices = launcher.check_environment({"PATH": "/bin"})
        self.assertEqual(errors, [])
        self.assertTrue(any("本地改动" in n for n in notices))
        self.assertTrue(any("#52" in n for n in notices))

    def test_wrong_remote_or_read_only_account_blocks_start(self):
        with patch.object(launcher.shutil, "which", return_value="/bin/tool"), self.probe(remote="https://github.com/other/repo.git", permission="READ", node="v20.0.0"):
            errors, _ = launcher.check_environment({})
        self.assertEqual(len(errors), 3)
        self.assertTrue(any("origin" in e for e in errors))
        self.assertTrue(any("写入权限" in e for e in errors))
        self.assertTrue(any("Node.js 22" in e for e in errors))

    def test_missing_tools_block_without_probes(self):
        with patch.object(launcher.shutil, "which", return_value=None), patch.object(launcher, "read_command") as read:
            errors, _ = launcher.check_environment({})
        self.assertEqual(len(errors), 4)
        read.assert_not_called()

    def test_malformed_github_response_blocks_start(self):
        with patch.object(launcher.shutil, "which", return_value="/bin/tool"), self.probe(pulls='[{"number":"52"}]'):
            errors, _ = launcher.check_environment({})
        self.assertTrue(any("响应无法验证" in e for e in errors))

    def test_check_mode_never_starts_a_model(self):
        with patch.object(launcher.sys, "argv", ["launcher", "--check"]), patch.object(launcher, "check_environment", return_value=([], [])), patch.object(launcher.subprocess, "call") as call, redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(), 0)
        call.assert_not_called()

    def test_failed_preflight_never_starts_a_model(self):
        with patch.object(launcher.sys, "argv", ["launcher"]), patch.object(launcher, "check_environment", return_value=(["missing gh"], [])), patch.object(launcher.subprocess, "call") as call, redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(), 2)
        call.assert_not_called()

    def test_probe_failure_does_not_expose_subprocess_output(self):
        failed = subprocess.CompletedProcess(["gh"], 1, "secret-stdout", "secret-stderr")
        with patch.object(launcher.subprocess, "run", return_value=failed) as run:
            with self.assertRaises(launcher.CheckFailed) as caught:
                launcher.read_command(["gh", "repo", "view"], {"PATH": "/bin"})
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(run.call_args.kwargs["timeout"], 15)
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_probe_timeout_is_bounded_and_redacted(self):
        with patch.object(launcher.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 15, output="secret")):
            with self.assertRaises(launcher.CheckFailed) as caught:
                launcher.read_command(["gh"], {})
        self.assertNotIn("secret", str(caught.exception))

    def test_start_and_resume_force_chatgpt_and_preserve_sandbox(self):
        for resume in (False, True):
            command = launcher.build_command("/example/codex", resume)
            self.assertIn('forced_login_method="chatgpt"', command)
            self.assertIn('model_provider="openai"', command)
            self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
            self.assertEqual(command[command.index("--ask-for-approval") + 1], "on-request")
            self.assertNotIn("--last", command)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
            self.assertEqual(command[1] == "resume", resume)
            self.assertEqual(launcher.PROMPT in command, not resume)

    def test_api_environment_is_removed_without_mutating_parent(self):
        source = {"OPENAI_API_KEY": "test-only", "CODEX_API_KEY": "test-only", "AZURE_OPENAI_API_KEY": "test-only", "OPENAI_BASE_URL": "https://example.invalid", "PATH": "/bin", "GH_TOKEN": "test-only"}
        result = launcher.session_env(source)
        self.assertEqual(result, {"PATH": "/bin", "GH_TOKEN": "test-only"})
        self.assertIn("OPENAI_API_KEY", source)
