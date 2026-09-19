import concurrent.futures
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import ProtocolError, call
from service import Server
from store import Store


class MailboxFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path / "db", "administrator")
        self.server = Server(self.path / "socket", self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.a = self.host("register", alias="a", agent="claude")
        self.b = self.host("register", alias="b", agent="codex")
        self.c = self.host("register", alias="c", agent="bob")
        self.group = self.host("group", name="review", members=[self.a["instance"], self.b["instance"]])["group"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.temp.cleanup()

    def rpc(self, who, op, **args):
        return call(self.path / "socket", who["token"], op, args)

    def host(self, op, **args):
        return call(self.path / "socket", "administrator", "host." + op, args)

    def send(self, key="one", **overrides):
        args = dict(recipient=self.b["instance"], group=self.group, text="Review $(touch /tmp/no) `echo x`", key=key)
        args.update(overrides)
        return self.rpc(self.a, "ask", **args)

    def error(self, code, fn, *args, **kwargs):
        with self.assertRaises(ProtocolError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)


class MailboxTests(MailboxFixture):
    def test_maximum_escaped_request_and_result_remain_readable(self):
        body = '\n' * 16384
        request = self.send(text=body)['id']
        self.rpc(self.b, 'accept', request=request)
        self.rpc(self.b, 'reply', request=request, text=body, key='large-result')
        cursor = 0
        events = []
        while True:
            page = self.rpc(self.a, 'get', request=request, after=cursor)
            self.assertEqual(page['text'], body)
            events.extend(page['events'])
            cursor = page['cursor']
            if not page['more']:
                break
        self.assertTrue(any(event['text'] == body for event in events))

    def test_full_registry_snapshot_fits_bounded_response(self):
        from protocol import MAX_RESPONSE_FRAME, encode
        # Populate the exact host limits without turning this sizing test into
        # a rate-limit test. Values remain within the public field constraints.
        import uuid
        caps = json.dumps({'reason': '\\' * 1000})
        with self.store.lock:
            self.store.db.execute('UPDATE instances SET alias=?,capabilities=?', ('\n' * 128, caps))
            for _ in range(125):
                self.store.db.execute('INSERT INTO instances(id,alias,agent,credential,capabilities,created) '
                                      'VALUES(?,?,?,?,?,?)',
                                      (str(uuid.uuid4()), '\n' * 128, '\n' * 64, str(uuid.uuid4()), caps, time.time()))
            members = [row[0] for row in self.store.db.execute('SELECT id FROM instances')]
            self.store.db.execute('DELETE FROM members')
            self.store.db.execute('DELETE FROM groups')
            for _ in range(64):
                group = str(uuid.uuid4())
                self.store.db.execute('INSERT INTO groups(id,name) VALUES(?,?)', (group, '\n' * 128))
                self.store.db.executemany('INSERT INTO members(group_id,instance) VALUES(?,?)',
                                         [(group, instance) for instance in members])
        snapshot = self.host('snapshot')
        self.assertEqual(len(snapshot['members']), 8192)
        self.assertEqual(len(snapshot['instances']), 128)
        self.assertLess(len(encode(snapshot)), MAX_RESPONSE_FRAME)

    def test_auth_groups_and_spoofing(self):
        self.assertEqual(self.rpc(self.c, "peers")["peers"], [])
        self.error("access_denied", self.rpc, self.c, "host.snapshot")
        self.error("access_denied", self.send, recipient=self.c["instance"])
        self.error("invalid_request", self.send, sender=self.c["instance"])
        request = self.send()["id"]
        self.error("access_denied", self.rpc, self.c, "get", request=request)
        self.error("unknown_operation", self.rpc, self.a, "exec", command="id")
        self.error("invalid_request", self.rpc, self.a, "inbox", path="/etc/passwd")
        self.host("revoke", instance=self.b["instance"])
        self.error("access_denied", self.rpc, self.b, "peers")
        self.assertEqual(self.rpc(self.a, "get", request=request)["work"], "interrupted")

    def test_read_accept_and_explicit_result(self):
        request = self.send()["id"]
        self.assertEqual(self.rpc(self.b, "read", request=request)["work"], "pending")
        self.error("conflict", self.rpc, self.b, "reply", request=request, text="ok", key="reply")
        self.rpc(self.b, "accept", request=request)
        result = self.rpc(self.b, "reply", request=request, text="Safe", key="reply")
        self.assertEqual(result["work"], "completed")
        self.assertEqual(self.rpc(self.a, "get", request=request)["work"], "completed")

    def test_one_owned_item_and_pause(self):
        one, two = self.send()["id"], self.send("two")["id"]
        self.rpc(self.b, "accept", request=one)
        self.host("pause", request=one)
        self.error("busy", self.rpc, self.b, "accept", request=two)
        self.error("conflict", self.rpc, self.b, "reply", request=one, text="result", key="r")
        self.host("resume", request=one)
        self.rpc(self.a, "cancel", request=one)
        self.assertEqual(self.rpc(self.b, "reply", request=one, text="late", key="r")["work"], "cancelled")
        self.assertEqual(self.rpc(self.b, "cancel-ack", request=one)["cancel_ack"], 1)
        self.rpc(self.b, "accept", request=two)

    def test_dedup_and_concurrent_clients(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.send(), range(8)))
        self.assertEqual(len({r["id"] for r in results}), 1)
        self.error("conflict", self.send, text="different")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM requests").fetchone()[0], 1)

    def test_control_and_payload_limits(self):
        for value in ["evil\x1b[2J", "a\x00b", "a\u202eb", "\ud800", "a" * 16385]:
            self.error("invalid_request", self.store.handle,
                       {"v": 1, "token": self.a["token"], "op": "ask", "args": dict(
                           recipient=self.b["instance"], group=self.group, text=value, key="invalid")})
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(self.path / "socket"))
            client.sendall(b"x" * 65537 + b"\n")
            result = json.loads(client.recv(4096))
            self.assertEqual(result["error"]["code"], "invalid_request")

    def test_group_revocation_and_new_instance(self):
        request = self.send()["id"]
        self.host("rename", instance=self.b["instance"], alias="renamed")
        self.assertEqual(self.rpc(self.a, "get", request=request)["recipient"], self.b["instance"])
        self.host("group", group=self.group, name="review", members=[self.a["instance"]])
        self.error("access_denied", self.rpc, self.b, "get", request=request)
        new = self.host("register", alias="renamed", agent="codex")
        self.assertNotEqual(new["instance"], self.b["instance"])
        self.assertEqual(self.rpc(self.a, "get", request=request)["work"], "interrupted")

    def test_wait_cycle_and_independent_reply(self):
        ab = self.send()["id"]
        ba = self.rpc(self.b, "ask", recipient=self.a["instance"], group=self.group, text="nested", key="ba", parent=ab)["id"]
        self.rpc(self.a, "wait", request=ab, timeout=10)
        self.error("wait_cycle", self.rpc, self.b, "wait", request=ba, timeout=10)
        self.rpc(self.b, "accept", request=ab)
        self.rpc(self.b, "reply", request=ab, text="done", key="r")
        self.rpc(self.b, "wait", request=ba, timeout=10)

    def test_restart_no_replay(self):
        request = self.send()["id"]
        self.rpc(self.b, "accept", request=request)
        queued = self.send("queued")["id"]
        with self.store.lock:
            self.store.db.execute("UPDATE requests SET delivery='delivered' WHERE id=?", (queued,))
            self.store.close()
            self.store = Store(self.path / "db", "administrator")
            self.server.store = self.store
        self.assertEqual(self.rpc(self.a, "get", request=request)["work"], "interrupted")
        self.assertEqual(self.rpc(self.b, "get", request=queued)["delivery"], "uncertain")
        transitions = self.store.db.execute(
            "SELECT actor,type,text FROM events WHERE request=? AND type='delivery'", (queued,)).fetchall()
        self.assertEqual([tuple(event) for event in transitions], [("host", "delivery", "uncertain")])
        with self.store.lock:
            self.store.close()
            self.store = Store(self.path / "db", "administrator")
            self.server.store = self.store
        transitions = self.store.db.execute(
            "SELECT actor,type,text FROM events WHERE request=? AND type='delivery'", (queued,)).fetchall()
        self.assertEqual([tuple(event) for event in transitions], [("host", "delivery", "uncertain")])
        self.assertEqual(self.host("reconcile", request=queued, retry=True)["delivery"], "queued")
        self.assertEqual(self.send("queued")["id"], queued)

    def test_event_pagination(self):
        request = self.send()["id"]
        self.rpc(self.b, "accept", request=request)
        self.rpc(self.b, "reply", request=request, text="ü" * 8000, key="result")
        events, cursor = [], 0
        while True:
            page = self.rpc(self.a, "get", request=request, after=cursor)
            events += page["events"]
            cursor = page["cursor"]
            if not page["more"]:
                break
        self.assertEqual(sum(event["type"] == "reply" for event in events), 1)
        self.assertEqual(events[-1]["text"], "completed")

    def test_rate_limit(self):
        self.store.rates[self.a["instance"]].extend([time.monotonic()] * 60)
        self.error("rate_limited", self.rpc, self.a, "peers")
        self.assertEqual(self.rpc(self.b, "peers")["instance"], self.b["instance"])

    def test_group_removal_clears_recipient_provenance(self):
        request = self.send()["id"]
        self.rpc(self.b, "accept", request=request)
        self.host("group", group=self.group, name="review", members=[self.b["instance"]])
        snapshot = self.host("snapshot")
        recipient = next(i for i in snapshot["instances"] if i["id"] == self.b["instance"])
        self.assertEqual(recipient["provenance"], "unknown")

    def test_queue_bound_and_prune_keeps_live_work(self):
        # Clear the independently tested per-second limiter to exercise queue capacity.
        for i in range(128):
            self.store.rates.clear()
            self.send(str(i))
        self.store.rates.clear()
        self.error("queue_full", self.send, "full")
        self.store.db.execute("UPDATE requests SET updated=?", (time.time() - 40 * 86400,))
        self.assertEqual(self.host("prune")["deleted"], 0)


if __name__ == "__main__":
    unittest.main()
