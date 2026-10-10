import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("codex_plus", Path(__file__).resolve().parents[2] / "codex_plus.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class PlusLauncherTests(unittest.TestCase):
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
