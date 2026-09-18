import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import capabilities, invoke, normalize
from hook_config import update
from test_service import MailboxFixture


class ClaudeAdapterTests(MailboxFixture):
    def setUp(self):
        super().setUp()
        self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?",
                              (json.dumps(capabilities("claude", "2.1.272")), self.b["instance"]))
        self.credential = self.path / "token"
        self.credential.write_text(self.b["token"])

    def invoke(self, event, **kwargs):
        return invoke("claude", {"hook_event_name": event, "session_id": "native-claude", **kwargs},
                      self.path / "socket", self.credential)

    def test_original_tui_native_context_and_permission(self):
        start = self.invoke("SessionStart")
        self.assertIn("lince-msg peers", start["hookSpecificOutput"]["additionalContext"])
        self.host("automatic", instance=self.b["instance"], enabled=True)
        request = self.send()["id"]
        self.assertIsNone(self.invoke("PermissionRequest"))
        self.assertIsNone(self.invoke("Notification", notification_type="permission_prompt"))
        self.assertIsNone(self.invoke("PreToolUse", tool_name="AskUserQuestion"))
        stop = self.invoke("Stop", stop_hook_active=False)
        self.assertEqual(stop["decision"], "block")
        self.assertIn(request, stop["reason"])
        self.assertNotIn("permissionDecision", json.dumps(stop))
        self.assertIsNone(self.invoke("Stop", stop_hook_active=True))

    def test_unknown_version_and_subagent(self):
        self.assertEqual(capabilities("claude", "0.0.0")["context_events"], [])
        self.assertIsNone(normalize("claude", {"hook_event_name": "SessionStart", "session_id": "child", "agent_id": "child"}))
        self.assertIsNone(normalize("claude", {"hook_event_name": "Stop"}))

    def test_captured_real_lifecycle(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/claude-2.1.272-lifecycle.json").read_text())
        for payload in fixture["events"]:
            result = invoke("claude", payload, self.path / "socket", self.credential)
            if payload["hook_event_name"] == "SessionStart":
                self.assertIn("additionalContext", result["hookSpecificOutput"])
        self.error("access_denied", self.rpc, self.b, "peers")

    def test_captured_stop_continuation_is_bounded(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/claude-2.1.272-stop-continuation.json").read_text())
        self.host("automatic", instance=self.b["instance"], enabled=True)
        request = self.send()["id"]
        responses = []
        for payload in fixture["events"]:
            result = invoke("claude", payload, self.path / "socket", self.credential)
            if payload["hook_event_name"] == "Stop":
                responses.append(result)
        self.assertEqual(responses[0]["decision"], "block")
        self.assertIn(request, responses[0]["reason"])
        self.assertIsNone(responses[1])
        self.assertEqual(self.host("get", request=request)["work"], "interrupted")

    def test_registration_preserves_user_handlers_and_is_idempotent(self):
        path = self.path / "settings.json"
        original = {"theme": "dark", "hooks": {"Stop": [{"matcher": ".*", "custom": True, "hooks": [
            {"type": "command", "command": "user-hook"},
            {"type": "command", "command": "claude-status-hook.sh"}]}]}}
        path.write_text(json.dumps(original))
        update(path, "claude")
        first = path.read_text()
        update(path, "claude")
        self.assertEqual(path.read_text(), first)
        update(path, "claude", remove=True)
        self.assertEqual(json.loads(path.read_text()), original)

    def test_malformed_settings_unchanged(self):
        path = self.path / "settings.json"
        path.write_text('{"hooks":{"Stop":"broken"}}')
        original = path.read_text()
        with self.assertRaises(ValueError):
            update(path, "claude")
        self.assertEqual(path.read_text(), original)

    def test_hook_failure_never_breaks_agent(self):
        script = Path(__file__).resolve().parents[1] / "lince-msg-hook"
        env = {**os.environ, "LINCE_MSG_ENDPOINT": str(self.path / "missing"),
               "LINCE_MSG_CREDENTIAL": str(self.credential)}
        before = time.monotonic()
        result = subprocess.run([sys.executable, str(script), "claude"], input='{"hook_event_name":"Stop","session_id":"s"}',
                                env=env, capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertLess(time.monotonic() - before, 3)
