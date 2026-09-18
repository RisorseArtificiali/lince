"""Deterministic native-adapter/CLI/service scenarios, explicitly without models."""
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import capabilities, invoke
from test_service import MailboxFixture
import test_cli


class OrderedPairTests(MailboxFixture):
    cli = test_cli.CliTests.cli

    def test_all_ordered_pairs_questions_tasks_and_human_takeover(self):
        actors = [(self.a, "claude", "2.1.272"), (self.b, "codex", "0.154.0"), (self.c, "bob", "2.0.4")]
        self.host("group", group=self.group, name="all v1", members=[a["instance"] for a, _, _ in actors])
        for actor, agent, version in actors:
            self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?",
                                  (json.dumps(capabilities(agent, version)), actor["instance"]))
            credential = self.path / (actor["instance"] + ".token")
            credential.write_text(actor["token"])
            invoke(agent, {"hook_event_name": "SessionStart", "session_id": actor["instance"]},
                   self.path / "socket", credential)
        for sender, sender_type, _ in actors:
            for recipient, recipient_type, _ in actors:
                if sender == recipient:
                    continue
                for kind, result_op in (("ask", "reply"), ("delegate", "complete")):
                    with self.subTest(sender=sender_type, recipient=recipient_type, kind=kind):
                        code, sent = self.cli(sender, kind, recipient["instance"], "--group", self.group,
                                              "--text", "Check the contract", "--key", str(uuid.uuid4()))
                        self.assertEqual(code, 0)
                        request = sent["result"]["id"]
                        self.assertEqual(self.cli(recipient, "accept", request)[0], 0)
                        outgoing = self.rpc(recipient, "ask", recipient=sender["instance"], group=self.group,
                                            text="Clarify scope", key=str(uuid.uuid4()), parent=request)
                        current = next(i for i in self.host("snapshot")["instances"] if i["id"] == recipient["instance"])
                        self.assertEqual(current["current"]["id"], request)
                        self.assertEqual(outgoing["parent"], request)
                        self.rpc(recipient, "cancel", request=outgoing["id"])
                        credential = self.path / (recipient["instance"] + ".token")
                        invoke(recipient_type, {"hook_event_name": "UserPromptSubmit", "session_id": recipient["instance"],
                               "prompt": "Please pause and explain"}, self.path / "socket", credential)
                        self.assertEqual(self.rpc(recipient, "get", request=request)["work"], "paused")
                        self.host("resume", request=request)
                        self.assertEqual(self.cli(recipient, result_op, request, "--text", "Verified contract")[0], 0)
                        code, waited = self.cli(sender, "wait", request, "--timeout", "0")
                        self.assertEqual(code, 0)
                        self.assertEqual(waited["result"]["work"], "completed")
