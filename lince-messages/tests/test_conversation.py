import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import ProtocolError, call
from service import Server
from store import Store
from transport import TerminalTransport


class Conversations(unittest.TestCase):
    def setUp(self):
        self.delivery = Mock(return_value=("submitted", "sent"))
        self.store = Store(None, "admin", self.delivery)
        self.a = self.host("register", alias="A", agent="claude", pane_ref="1")
        self.b = self.host("register", alias="B", agent="codex", pane_ref="2")

    def rpc(self, actor, op, **args):
        return self.store.handle({"v": 1, "token": actor, "op": op, "args": args})

    def host(self, op, **args):
        return self.rpc("admin", "host." + op, **args)

    def send(self, **args):
        return self.rpc(self.a["token"], "send", recipient="B", text="Question?", **args)

    def test_rename_updates_resolution_history_and_preserves_identity(self):
        message = self.send()
        aliases = [{"pane_ref": "2", "status_id": "wrong-pane", "alias": "Wrong"}]
        self.host("snapshot", aliases=aliases)
        self.assertEqual(self.store.instances[self.b["instance"]]["alias"], "B")
        aliases[0].update(status_id="", alias="Reviewer")
        snapshot = self.host("snapshot", aliases=aliases)
        self.assertEqual(snapshot["messages"][0]["recipient_name"], "Reviewer")
        self.assertEqual(snapshot["messages"][0]["conversation"], message["conversation"])
        self.assertEqual(self.rpc(self.a["token"], "peers")["peers"][0]["alias"], "Reviewer")
        with self.assertRaises(ProtocolError):
            self.send()
        self.rpc(self.a["token"], "send", recipient="Reviewer", text="Follow-up", conversation=message["conversation"])
        with self.assertRaises(ProtocolError):
            self.rpc(self.a["token"], "host.snapshot", aliases=aliases)
        self.store.flush()
        self.assertEqual(self.delivery.call_args.args[0]["id"], self.b["instance"])

    def test_async_round_trip_correlation_and_no_task_protocol(self):
        result = self.send()
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.delivery.call_count, 0)
        self.store.flush()
        prompt = self.delivery.call_args.args[1]
        self.assertIn(self.a["instance"], prompt)
        self.assertIn(result["conversation"], prompt)
        self.assertIn("Question?", prompt)
        self.rpc(self.b["token"], "send", recipient="A", text="Regarding your question: yes",
                 conversation=result["conversation"])
        self.store.flush()
        self.assertEqual(self.delivery.call_count, 2)
        self.assertEqual([m["status"] for m in self.host("snapshot")["messages"]], ["submitted"] * 2)
        for op in ("accept", "inbox", "delegate", "wait", "group", "complete"):
            with self.assertRaises(ProtocolError): self.rpc(self.a["token"], op)

    def test_busy_recipient_keeps_fifo_without_blocking_sender(self):
        self.delivery.return_value = ("pending", "busy")
        self.send(); self.send()
        self.store.flush()
        self.assertEqual(self.delivery.call_count, 1)
        self.delivery.return_value = ("submitted", "sent")
        self.store.flush()
        self.assertEqual([m["status"] for m in self.store.messages], ["submitted", "pending"])
        self.store.flush()
        self.assertEqual([m["status"] for m in self.store.messages], ["submitted", "submitted"])

    def test_closed_recipient_cannot_be_retargeted_to_reused_pane(self):
        self.send()
        self.host("register", alias="B", agent="codex", pane_ref="2")
        self.store.flush()
        self.delivery.assert_not_called()
        self.assertEqual(self.store.messages[0]["status"], "failed")
        with self.assertRaises(ProtocolError): self.rpc(self.b["token"], "peers")

    def test_host_auth_controls_and_conversation_participants(self):
        with self.assertRaises(ProtocolError): self.rpc(self.a["token"], "host.snapshot")
        for body in ("bad\x1b[201~", "bad\r", "x" * 16385):
            with self.assertRaises(ProtocolError): self.rpc(self.a["token"], "send", recipient="B", text=body)
        convo = self.send()["conversation"]
        third = self.host("register", alias="C", agent="bob")
        with self.assertRaises(ProtocolError):
            self.rpc(third["token"], "send", recipient="B", text="spoof", conversation=convo)
        snapshot = json.dumps(self.host("snapshot"))
        self.assertNotIn(self.a["token"], snapshot)
        self.assertNotIn("credential", snapshot)

    def test_uncertain_send_is_never_replayed(self):
        self.delivery.return_value = ("uncertain", "write timeout")
        self.send(); self.store.flush(); self.store.flush()
        self.assertEqual(self.delivery.call_count, 1)

    def test_expired_leases_and_timeout(self):
        self.send()
        self.store.messages[0]["created"] -= 301
        self.store.flush()
        self.assertEqual(self.store.messages[0]["status"], "failed")
        self.store.instances[self.a["instance"]]["lease_expires"] = 1
        with self.assertRaises(ProtocolError): self.rpc(self.a["token"], "peers")

    def test_real_socket_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            endpoint = Path(directory) / "mailbox.sock"
            token = Path(directory) / "token"
            token.write_text(self.a["token"])
            server = Server(endpoint, self.store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            try:
                env = {**os.environ, "LINCE_MSG_ENDPOINT": str(endpoint), "LINCE_MSG_CREDENTIAL": str(token)}
                result = subprocess.run([sys.executable, str(Path(__file__).parents[1] / "lince-msg"),
                                         "send", "B", "--stdin"], input="hello\nworld", text=True,
                                        capture_output=True, env=env, check=True)
                self.assertEqual(json.loads(result.stdout)["result"]["status"], "pending")
                self.assertEqual(self.store.messages[0]["text"], "hello\nworld")
            finally:
                server.shutdown(); server.server_close(); thread.join()


class Transport(unittest.TestCase):
    def test_bob_real_hook_and_distinct_pending_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = {"status_dir": directory, "status_id": "bob-42", "created": time.time(),
                        "last_submit": 0, "pid": os.getpid(), "pane_ref": "2"}
            transport = TerminalTransport("session")
            self.assertIn("first lifecycle hook", transport(instance, "question")[1])
            status = Path(directory) / "bob-42.state"
            status.write_text("Stop")
            os.utime(status, (1, 1))
            self.assertIn("predates this pane", transport(instance, "question")[1])
            env = {k: v for k, v in os.environ.items() if not k.startswith("ZELLIJ")}
            env.update(LINCE_AGENT_ID="bob-42", LINCE_STATUS_DIR=directory)
            hook = Path(__file__).resolve().parents[2] / "lince-dashboard/hooks/bob-status-hook.sh"
            for event in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
                subprocess.run(["bash", str(hook)], input=json.dumps({"hook_event_name": event}),
                               env=env, text=True, capture_output=True, check=True, timeout=5)
                self.assertEqual(transport.ready(instance), event in {"SessionStart", "Stop"})
                if not transport.ready(instance):
                    self.assertIn(event, transport(instance, "question")[1])
            transport.action = Mock(return_value=json.dumps([{"id": 2, "is_plugin": False}]))
            with patch("transport.time.sleep"):
                self.assertEqual(transport(instance, "question")[0], "submitted")
            instance["last_submit"] = time.time() + 2
            self.assertIn("previous delivery", transport(instance, "question")[1])

    def test_real_claude_hook_status_path_and_permission_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            agent_id = "claude-1234"
            instance = {"status_dir": directory, "status_id": agent_id, "created": 0,
                        "last_submit": 0, "pid": os.getpid(), "pane_ref": "2"}
            env = {k: v for k, v in os.environ.items() if not k.startswith("ZELLIJ")}
            env.update(LINCE_AGENT_ID=agent_id, LINCE_STATUS_DIR=directory)
            hook = Path(__file__).resolve().parents[2] / "lince-dashboard/hooks/claude-status-hook.sh"
            transport = TerminalTransport("session")
            transport.action = Mock(return_value=json.dumps([{"id": 2, "is_plugin": False}]))
            for event, notification, idle in [("SessionStart", None, True),
                                               ("Notification", "permission_prompt", False),
                                               ("Notification", "idle_prompt", True),
                                               ("PreToolUse", None, False), ("Stop", None, True)]:
                payload = {"hook_event_name": event, "notification_type": notification}
                subprocess.run(["bash", str(hook)], input=json.dumps(payload), env=env,
                               text=True, capture_output=True, check=True, timeout=5)
                # A generic idle file must not override a newer Claude permission/tool state.
                (Path(directory) / f"{agent_id}.state").write_text("input")
                self.assertEqual(transport.ready(instance), idle, event)
            with patch("transport.time.sleep"):
                self.assertEqual(transport(instance, "question")[0], "submitted")
            instance["last_submit"] = time.time() + 2
            self.assertFalse(transport.ready(instance))

    def test_idle_signal_must_be_fresh_and_advanced_after_each_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "agent.state"
            instance = {"status_dir": directory, "status_id": "agent", "created": time.time(),
                        "last_submit": 0, "pid": os.getpid(), "pane_ref": "2"}
            transport = TerminalTransport("session")
            transport.action = Mock(return_value=json.dumps([{"id": 2, "is_plugin": False}]))
            self.assertEqual(transport(instance, "hello")[0], "pending")
            for event in ("PreToolUse", "PermissionRequest", "permission_prompt", "unknown", "SessionEnd"):
                status.write_text(event)
                self.assertEqual(transport(instance, "hello")[0], "pending")
            status.write_text("Stop")
            os.utime(status, (time.time()+1, time.time()+1))
            with patch("transport.time.sleep"):
                self.assertEqual(transport(instance, "hello\nworld")[0], "submitted")
            self.assertEqual(transport.action.call_args_list[-2].args,
                             ("write-chars", "--pane-id", "2", "--", "\x1b[200~hello\nworld\x1b[201~"))
            self.assertEqual(transport.action.call_args_list[-1].args, ("write", "--pane-id", "2", "13"))
            instance["last_submit"] = time.time()+2
            self.assertEqual(transport(instance, "again")[0], "pending")

    def test_pi_and_opencode_idle_events_exclude_tool_turns_busy_and_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / 'peer.state'
            instance = {'status_dir': directory, 'status_id': 'peer', 'created': 0, 'last_submit': 0}
            transport = TerminalTransport('session')
            for event in ('session_start', 'agent_end', 'agent_settled', 'session.created', 'session.status.idle', 'session.idle',
                          'bob.PromptReady', 'gemini.SessionStart', 'gemini.AfterAgent', 'goose.SessionStart', 'goose.Stop', 'amp.idle'):
                status.write_text(event)
                self.assertTrue(transport.ready(instance), event)
            for event in ('turn_end', 'turn_start', 'tool_call', 'session_shutdown',
                          'session.status.busy', 'session.status.unknown', 'session.deleted',
                          'gemini.BeforeAgent', 'gemini.BeforeTool', 'gemini.ToolPermission', 'gemini.SessionEnd',
                          'goose.UserPromptSubmit', 'goose.PreToolUse', 'goose.SessionEnd',
                          'amp.running', 'amp.awaiting-approval', 'amp.error', 'amp.unknown', 'amp.stopped'):
                status.write_text(event)
                self.assertFalse(transport.ready(instance), event)

    def test_partial_write_is_uncertain(self):
        transport = TerminalTransport("session")
        transport.ready = Mock(return_value=True)
        transport.action = Mock(side_effect=[json.dumps([{"id": 2, "is_plugin": False}]), "", OSError()])
        with patch("transport.time.sleep"):
            status, _ = transport({"pane_ref": "2", "pid": os.getpid()}, "hello")
        self.assertEqual(status, "uncertain")


if __name__ == "__main__": unittest.main()
