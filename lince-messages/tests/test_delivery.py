import json
import uuid

from test_service import MailboxFixture
from store import digest


class DeliveryTests(MailboxFixture):
    def setUp(self):
        super().setUp()
        caps = {"session_identity": True, "human_attribution": True, "context_events": ["Stop"]}
        self.store.db.execute("UPDATE instances SET capabilities=? WHERE id=?", (json.dumps(caps), self.b["instance"]))
        self.host("automatic", instance=self.b["instance"], enabled=True)
        self.hook("SessionStart")

    def hook(self, event, key=None, **kwargs):
        return self.rpc(self.b, "hook", event=event, session="native-b", key=key or str(uuid.uuid4()), **kwargs)

    def snapshot_instance(self, actor):
        return next(i for i in self.host("snapshot")["instances"] if i["id"] == actor["instance"])

    def test_native_boundary_delivery_without_acceptance(self):
        request = self.send()["id"]
        for event in ("PreToolUse", "PermissionRequest", "Question", "unknown"):
            self.assertIsNone(self.hook(event)["context"])
            self.assertEqual(self.rpc(self.b, "get", request=request)["delivery"], "queued")
        delivery = self.hook("Stop")
        self.assertEqual(delivery["request"], request)
        self.assertIn("untrusted peer", delivery["context"])
        self.assertEqual(self.rpc(self.b, "get", request=request)["delivery"], "delivered")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "pending")
        self.assertEqual(self.snapshot_instance(self.b)["provenance"], "unknown")
        self.rpc(self.b, "accept", request=request)
        self.assertEqual(self.snapshot_instance(self.b)["provenance"], "peer-question")

    def test_human_input_pauses_and_duplicate_does_not_pause_resume(self):
        request = self.send()["id"]
        self.rpc(self.b, "accept", request=request)
        self.hook("UserPromptSubmit", key="human-turn")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "paused")
        self.assertEqual(self.snapshot_instance(self.b)["provenance"], "human")
        self.rpc(self.b, "resume", request=request)
        self.hook("UserPromptSubmit", key="human-turn")
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "active")
        self.assertEqual(self.snapshot_instance(self.b)["provenance"], "peer-question")

    def test_nested_question_keeps_original_provenance(self):
        request = self.send()["id"]
        self.rpc(self.b, "accept", request=request)
        nested = self.rpc(self.b, "ask", recipient=self.a["instance"], group=self.group,
                          text="check", key="nested", parent=request)
        self.assertEqual(nested["parent"], request)
        self.assertEqual(self.snapshot_instance(self.b)["provenance"], "peer-question")
        self.assertIsNone(self.hook("Stop")["context"])

    def test_replaced_session_and_exit_fail_closed(self):
        request = self.send()["id"]
        self.error("session_mismatch", self.rpc, self.b, "hook", event="Stop", session="other", key="k")
        self.hook("SessionEnd")
        self.error("access_denied", self.hook, "Stop")
        self.assertEqual(self.rpc(self.a, "get", request=request)["work"], "interrupted")

    def test_cancellation_and_loop_bounds(self):
        request = self.send()["id"]
        self.rpc(self.a, "cancel", request=request)
        self.assertIsNone(self.hook("Stop")["context"])
        next_request = self.send("next")["id"]
        self.assertIsNone(self.hook("Stop", continuation=True)["context"])
        self.assertEqual(self.hook("Stop", key="stop1")["request"], next_request)
        self.assertIsNone(self.hook("Stop", key="stop1")["context"])
        self.send("another")
        self.assertIsNone(self.hook("Stop")["context"])

    def test_unsupported_adapter_stays_explicit(self):
        self.error("unsupported", self.host, "automatic", instance=self.c["instance"], enabled=True)
        result = self.rpc(self.c, "hook", session="bob", event="Stop", key="b")
        self.assertIsNone(result["context"])
        self.assertIn("not been verified", result["reason"])

    def test_native_continuation_is_not_a_human_prompt(self):
        request = self.send()["id"]
        delivery = self.hook("Stop")
        self.rpc(self.b, "accept", request=request)
        self.hook("UserPromptSubmit", prompt_hash=digest(delivery["context"]))
        self.assertEqual(self.rpc(self.b, "get", request=request)["work"], "active")
        self.assertEqual(self.snapshot_instance(self.b)["provenance"], "peer-question")

    def test_orphan_lease_revokes_credentials(self):
        request = self.send()["id"]
        self.store.db.execute("UPDATE instances SET lease_expires=1 WHERE id=?", (self.b["instance"],))
        self.error("access_denied", self.rpc, self.b, "peers")
        self.assertEqual(self.rpc(self.a, "get", request=request)["work"], "interrupted")
