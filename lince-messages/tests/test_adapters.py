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


class CodexAdapterTests(MailboxFixture):
    def test_native_turn_duplicates_do_not_interrupt_resumed_work_or_deliver_next_item(self):
        self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?",
                             (json.dumps(capabilities("codex", "0.154.0")), self.b["instance"]))
        credential = self.path / "token"
        credential.write_text(self.b["token"])

        def event(name, turn="turn-1"):
            return invoke("codex", {"hook_event_name": name, "session_id": "session", "turn_id": turn},
                          self.path / "socket", credential)

        event("SessionStart")
        request = self.send()["id"]
        self.rpc(self.b, "accept", request=request)
        event("UserPromptSubmit")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "paused")
        self.rpc(self.b, "resume", request=request)
        event("UserPromptSubmit")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "active")
        event("UserPromptSubmit", "turn-2")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "paused")
        self.rpc(self.b, "resume", request=request)
        self.rpc(self.b, "reply", request=request, text="done", key="result")
        self.host("automatic", instance=self.b["instance"], enabled=True)
        first, second = self.send("first")["id"], self.send("second")["id"]
        self.assertIn(first, event("Stop", "turn-3")["reason"])
        self.store.db.execute("UPDATE instances SET last_delivery=0 WHERE id=?", (self.b["instance"],))
        self.assertIsNone(event("Stop", "turn-3"))
        self.assertEqual(self.rpc(self.b, "get", request=second)["delivery"], "queued")

    def test_payload_equality_without_native_turn_identity_is_not_deduplication(self):
        for agent in ("claude", "codex", "bob"):
            payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": "Again"}
            self.assertNotEqual(normalize(agent, payload)["key"], normalize(agent, payload)["key"])

    def test_captured_stop_continuation_is_bounded(self):
        self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?",
                             (json.dumps(capabilities("codex", "0.154.0")), self.b["instance"]))
        credential = self.path / "token"
        credential.write_text(self.b["token"])
        fixture = json.loads((Path(__file__).parent / "fixtures/codex-0.154.0-stop-continuation.json").read_text())
        self.host("automatic", instance=self.b["instance"], enabled=True)
        request = self.send()["id"]
        responses = []
        for payload in fixture["events"]:
            result = invoke("codex", payload, self.path / "socket", credential)
            if payload["hook_event_name"] == "Stop":
                responses.append(result)
        self.assertEqual(responses[0]["decision"], "block")
        self.assertIn(request, responses[0]["reason"])
        self.assertIsNone(responses[1])
        self.assertEqual(self.host("get", request=request)["work"], "interrupted")

    def test_captured_real_lifecycle(self):
        self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?",
                             (json.dumps(capabilities("codex", "0.154.0")), self.b["instance"]))
        credential = self.path / "token"
        credential.write_text(self.b["token"])
        fixture = json.loads((Path(__file__).parent / "fixtures/codex-0.154.0-lifecycle.json").read_text())
        for payload in fixture["events"]:
            result = invoke("codex", payload, self.path / "socket", credential)
            if payload["hook_event_name"] == "SessionStart":
                self.assertIn("additionalContext", result["hookSpecificOutput"])
        self.error("access_denied", self.rpc, self.b, "peers")

    def test_native_context_and_exact_continuation_origin(self):
        self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?",
                             (json.dumps(capabilities("codex", "0.154.0")), self.b["instance"]))
        credential = self.path / "codex-token"
        credential.write_text(self.b["token"])
        def event(name, **kwargs):
            return invoke("codex", {"hook_event_name": name, "session_id": "codex-root", **kwargs},
                          self.path / "socket", credential)
        event("SessionStart")
        self.host("automatic", instance=self.b["instance"], enabled=True)
        request = self.send()["id"]
        self.assertIsNone(event("PermissionRequest"))
        output = event("Stop", stop_hook_active=False, turn_id="turn-1")
        self.assertEqual(output["decision"], "block")
        self.rpc(self.b, "accept", request=request)
        event("UserPromptSubmit", prompt=output["reason"], turn_id="turn-2")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "active")
        event("Interrupt", turn_id="turn-2")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "paused")
        self.assertIsNone(event("Stop", stop_hook_active=True))

    def test_registration_and_unknown_version(self):
        path = self.path / "hooks.json"
        original = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "codex-status-hook.sh"}]}]}}
        path.write_text(json.dumps(original))
        update(path, "codex")
        first = path.read_text()
        update(path, "codex")
        self.assertEqual(first, path.read_text())
        update(path, "codex", remove=True)
        self.assertEqual(json.loads(path.read_text()), original)
        self.assertFalse(capabilities("codex", "0.1.0")["session_identity"])


class BobAdapterTests(MailboxFixture):
    def test_context_explicit_inbox_and_human_precedence(self):
        self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?",
                             (json.dumps(capabilities("bob", "2.0.4")), self.b["instance"]))
        credential = self.path / "bob-token"
        credential.write_text(self.b["token"])
        def event(name, field="event"):
            return invoke("bob", {field: name, "session_id": "bob-session"}, self.path / "socket", credential)
        self.assertIn("lince-msg peers", event("SessionStart"))
        request = self.send()["id"]
        self.assertIsNone(event("Stop", field="hook_event_name"))
        self.assertEqual(self.rpc(self.b, "get", request=request)["delivery"], "queued")
        self.error("unsupported", self.host, "automatic", instance=self.b["instance"], enabled=True)
        self.rpc(self.b, "accept", request=request)
        event("UserPromptSubmit")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "paused")
        self.rpc(self.b, "resume", request=request)
        self.assertEqual(self.rpc(self.b, "reply", request=request, key="reply", text="checked")["work"], "completed")

    def test_registration_does_not_invent_permission_hooks(self):
        path = self.path / "bob-settings.json"
        original = {"hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "bob-status-hook.sh"}]}]}}
        path.write_text(json.dumps(original))
        update(path, "bob")
        installed = path.read_text()
        self.assertNotIn("PermissionRequest", installed)
        self.assertNotIn("Notification", installed)
        update(path, "bob")
        self.assertEqual(path.read_text(), installed)
        update(path, "bob", remove=True)
        self.assertEqual(json.loads(path.read_text()), original)
