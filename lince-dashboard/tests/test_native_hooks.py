"""Exercise hook protocols and install ownership in an isolated home."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"


class NativeHooks(unittest.TestCase):
    def test_observational_hooks_and_unknown_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {k: v for k, v in os.environ.items() if not k.startswith("ZELLIJ")}
            env.update(LINCE_AGENT_ID="peer", LINCE_STATUS_DIR=directory)
            status = Path(directory) / "peer.state"
            for provider, events in {
                "gemini": ["SessionStart", "BeforeAgent", "BeforeTool", "AfterTool", "AfterAgent", "SessionEnd"],
                "goose": ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"],
            }.items():
                field = "hook_event_name" if provider == "gemini" else "event"
                for event in events:
                    result = subprocess.run([sys.executable, str(HOOKS / "native-status-hook.py"), provider],
                                            input=json.dumps({field: event}), env=env, text=True,
                                            capture_output=True, check=True)
                    self.assertEqual(result.stdout, "{}\n" if provider == "gemini" else "")
                    self.assertEqual(status.read_text(), f"{provider}.{event}")
            for notification, expected in [("ToolPermission", "gemini.ToolPermission"), ("unknown", "gemini.ToolPermission")]:
                subprocess.run([sys.executable, str(HOOKS / "native-status-hook.py"), "gemini"],
                               input=json.dumps({"hook_event_name": "Notification", "notification_type": notification}),
                               text=True, capture_output=True, env=env, check=True)
                self.assertEqual(status.read_text(), expected)

    def test_install_update_remove_preserves_other_hooks_and_edited_plugins(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {**os.environ, "HOME": directory, "XDG_CONFIG_HOME": str(home / ".config")}
            settings = home / ".gemini/settings.json"
            settings.parent.mkdir()
            other = {"hooksConfig": {"enabled": False}, "hooks": {"AfterAgent": [{"hooks": [{"command": "mine"}]}]}}
            settings.write_text(json.dumps(other))
            def run(*args, check=True):
                return subprocess.run([sys.executable, str(HOOKS / "native-hooks-config.py"), *args],
                                      env=env, text=True, capture_output=True, check=check)
            run()
            first = settings.read_text()
            run()
            self.assertEqual(settings.read_text(), first)
            plugin = home / ".config/amp/plugins/lince-status.js"
            plugin.write_text("// user edited\n")
            self.assertNotEqual(run(check=False).returncode, 0)
            run("--remove")
            run("--remove")
            self.assertEqual(json.loads(settings.read_text()), other)
            self.assertEqual(plugin.read_text(), "// user edited\n")
            self.assertFalse((home / ".gemini/lince-status.py").exists())
            self.assertFalse((home / ".agents/plugins/lince-status/hooks/hooks.json").exists())
