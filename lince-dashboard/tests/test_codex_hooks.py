"""Exercise installation, preservation, and dashboard lifecycle transitions."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


DASHBOARD = Path(__file__).resolve().parents[1]
HOOKS = DASHBOARD / "hooks"
EXPECTED = {
    "SessionStart": "input", "UserPromptSubmit": "running",
    "PreToolUse": "running", "PermissionRequest": "permission",
    "PostToolUse": "running", "PreCompact": "running", "PostCompact": "running",
    "Stop": "input", "Interrupt": "input", "SessionEnd": "stopped",
}


class CodexHooksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.codex = self.home / "custom-codex-home"
        self.codex.mkdir()
        self.config = self.codex / "config.toml"
        self.hooks = self.codex / "hooks.json"
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.codex)}

    def install(self):
        return subprocess.run(
            ["bash", str(HOOKS / "install-codex-hooks.sh")], env=self.env,
            capture_output=True, text=True,
        )

    def test_install_and_update_are_idempotent(self):
        self.config.write_text('model = "test-model"\n[projects."/tmp/example"]\ntrust_level = "trusted"\n')
        self.assertEqual(self.install().returncode, 0)
        first = (self.config.read_bytes(), self.hooks.read_bytes())
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(first, (self.config.read_bytes(), self.hooks.read_bytes()))
        self.assertFalse(list(self.codex.glob("hooks.json.lince.bak*")))
        cfg = tomllib.loads(self.config.read_text())
        self.assertEqual(cfg["notify"], ["codex-status-hook.sh"])
        self.assertEqual(cfg["model"], "test-model")
        self.assertTrue((self.home / ".local/bin/codex-status-hook.sh").is_file())
        self.assertFalse((self.home / ".codex").exists())

    def test_existing_unmanaged_lince_notify_is_not_duplicated(self):
        original = 'notify = ["codex-status-hook.sh"]\n[features]\nhooks = true\n'
        self.config.write_text(original)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.config.read_text(), original)

    def test_preserves_user_notify_and_hooks_and_uninstalls_only_ours(self):
        config = 'notify = ["my-notifier", "--flag"]\n'
        original = {"description": "User hooks", "hooks": {
            "Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "my-stop"}]}],
            "SubagentStop": [{"hooks": [{"type": "command", "command": "my-subagent"}]}],
        }}
        self.config.write_text(config)
        self.hooks.write_text(json.dumps(original))
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.config.read_text(), config)
        self.assertEqual(json.loads(self.hooks.with_name("hooks.json.lince.bak").read_text()), original)
        installed = json.loads(self.hooks.read_text())
        self.assertEqual(installed["hooks"]["Stop"][0], original["hooks"]["Stop"][0])
        subprocess.run(["python3", str(HOOKS / "codex-hooks-config.py"), str(self.hooks), "--remove"], check=True)
        self.assertEqual(json.loads(self.hooks.read_text()), original)

    def test_malformed_hooks_are_preserved(self):
        for raw in ('{invalid json', '{"hooks": []}', '{"hooks": {"Stop": [{}]}}'):
            with self.subTest(raw=raw):
                self.hooks.write_text(raw)
                result = self.install()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.hooks.read_text(), raw)

    def test_installed_lifecycle_reaches_dashboard_status_for_both_variants(self):
        self.assertEqual(self.install().returncode, 0)
        installed = json.loads(self.hooks.read_text())["hooks"]
        agents = tomllib.loads((DASHBOARD / "agents-defaults.toml").read_text())["agents"]
        registry = tomllib.loads((DASHBOARD.parent / "registry.d/codex.toml").read_text())
        for event, expected_status in EXPECTED.items():
            with self.subTest(event=event):
                self.assertEqual(installed[event][0]["hooks"][0]["command"], "codex-status-hook.sh")
                result = subprocess.run(
                    ["bash", str(self.home / ".local/bin/codex-status-hook.sh")],
                    input=json.dumps({"hook_event_name": event}), text=True, capture_output=True,
                    env={**self.env, "ZELLIJ": "", "LINCE_AGENT_ID": "test-lifecycle",
                         "LINCE_STATUS_DIR": str(self.home / "state")},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")  # no accidental model context
                native_event = (self.home / "state/test-lifecycle.state").read_text().strip()
                for variant in ("codex", "codex-unsandboxed"):
                    self.assertEqual(agents[variant]["event_map"][native_event], expected_status)
                self.assertEqual(registry["event_map"][native_event], expected_status)


if __name__ == "__main__":
    unittest.main()
