from test_service import MailboxFixture


class BrowserApiTests(MailboxFixture):
    def test_filtered_history_paginates_without_skipping_equal_timestamps(self):
        ids = [self.send(str(i))["id"] for i in range(5)]
        self.store.db.execute("UPDATE requests SET created=1")
        page = self.host("list", filter="unread", limit=2)
        self.assertEqual([r["id"] for r in page["requests"]], list(reversed(ids[-2:])))
        self.assertTrue(page["more"])
        older = self.host("list", filter="unread", limit=2, before=page["cursor"])
        self.assertEqual([r["id"] for r in older["requests"]], [ids[2], ids[1]])
        self.rpc(self.b, "accept", request=ids[0])
        self.host("pause", request=ids[0])
        active = self.host("list", filter="active")
        self.assertEqual([r["id"] for r in active["requests"]], [ids[0]])
        self.host("cancel", request=ids[0])
        self.assertEqual(self.host("list", filter="completed")["requests"][0]["cancel_ack"], 0)
        self.rpc(self.b, "cancel-ack", request=ids[0])
        self.assertEqual(self.host("list", filter="completed")["requests"][0]["cancel_ack"], 1)

    def test_history_filters_are_host_only_and_not_sql(self):
        self.error("access_denied", self.rpc, self.a, "host.list")
        self.error("invalid_request", self.host, "list", filter="1); DROP TABLE requests")
        self.error("invalid_request", self.host, "list", before=1.5)
        self.error("invalid_request", self.host, "list", limit=1000)

    def test_uncertain_error_view_and_deliberate_reconciliation(self):
        request = self.send()["id"]
        self.store.db.execute("UPDATE requests SET delivery='uncertain' WHERE id=?", (request,))
        self.assertEqual(self.host("list", filter="errors")["requests"][0]["id"], request)
        self.host("reconcile", request=request, retry=False)
        self.assertEqual(self.host("list", filter="errors")["requests"], [])
        self.assertEqual(self.host("get", request=request)["work"], "pending")
