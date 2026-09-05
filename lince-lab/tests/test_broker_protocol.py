#!/usr/bin/env python3
"""Broker protocol + round-trip tests (blueprint §3).

Two layers:

* **pure codec**: envelope encode/decode, request validation, and the unknown-verb
  → exit 64 mapping (no socket);
* **full round-trip over a REAL unix socket**: a :class:`BrokerServer` backed by
  ``FakeBackend`` runs in a background thread on a socket in a ``TemporaryDirectory``;
  a :class:`BrokerClient` drives it. Covered: ping liveness, a vm lifecycle +
  exec round-trip, a nonzero guest exit surfaced verbatim in the response,
  snapshot round-trip, a policy denial mapped to exit 13, and broker-unreachable
  (exit 69) when nothing is listening.

No VM, no KVM — the substrate is entirely the in-memory FakeBackend.

Run with:
    python3 lince-lab/tests/test_broker_protocol.py
"""

import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest

# Put the package dir (lince-lab/) on sys.path so absolute imports resolve.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lince_lab import protocol  # noqa: E402
from lince_lab.broker import BrokerServer  # noqa: E402
from lince_lab.client import BrokerClient  # noqa: E402
from lince_lab.errors import (  # noqa: E402
    BROKER_UNREACHABLE,
    POLICY_DENIED,
    UNKNOWN_VERB,
    BrokerUnreachable,
    DataError,
    LabError,
    UnknownVerb,
)
from lince_lab.backend import ExecResult  # noqa: E402
from lince_lab.fake_backend import FakeBackend  # noqa: E402
from lince_lab.templates import egress_lockdown_argv  # noqa: E402

LAB_VM = "lince-lab-demo"


def _register_lockdown(backend: FakeBackend, vm_name: str, allow_ips=None, allow_ports=None) -> None:
    """Register the runtime egress lock-down exec to succeed on the Fake.

    `_h_start` (a bare vm.start) and recipe.run both apply the lock-down via
    `backend.exec(vm, egress_lockdown_argv(...))`; the Fake returns 127 for an
    unregistered argv (which would fail the start/run), so tests that exercise a
    successful start/run register it to return 0.
    """
    backend.on(vm_name, egress_lockdown_argv(allow_ips or [], allow_ports or []), ExecResult(0, "", ""))


class CodecTests(unittest.TestCase):
    """Pure envelope codec + verb-whitelist behavior (no socket)."""

    def test_encode_decode_round_trip(self):
        req = protocol.make_request("vm.exec", {"name": LAB_VM, "argv": ["true"]})
        line = protocol.encode(req)
        self.assertTrue(line.endswith(b"\n"))
        decoded = protocol.decode(line)
        self.assertEqual(decoded, req)

    def test_encode_is_deterministic(self):
        a = protocol.encode({"v": 1, "id": "x", "verb": "ping", "args": {}})
        b = protocol.encode({"args": {}, "verb": "ping", "id": "x", "v": 1})
        self.assertEqual(a, b)

    def test_make_request_rejects_unknown_verb(self):
        with self.assertRaises(UnknownVerb) as exc:
            protocol.make_request("vm.evil")
        self.assertEqual(exc.exception.exit_code, UNKNOWN_VERB)

    def test_validate_request_unknown_verb_maps_to_64(self):
        envelope = {"v": 1, "id": "abc", "verb": "vm.evil", "args": {}}
        with self.assertRaises(UnknownVerb) as exc:
            protocol.validate_request(envelope)
        self.assertEqual(exc.exception.exit_code, 64)

    def test_validate_request_bad_version(self):
        with self.assertRaises(DataError):
            protocol.validate_request({"v": 99, "id": "x", "verb": "ping", "args": {}})

    def test_decode_malformed_line(self):
        with self.assertRaises(DataError):
            protocol.decode(b"{not json}\n")

    def test_error_envelope_carries_exit(self):
        err = protocol.make_error("id1", "POLICY_DENIED", "nope", 13)
        self.assertFalse(err["ok"])
        self.assertEqual(err["error"]["exit"], 13)


# A realistic-enough broker config: an image allowlist + default image (so a bare
# vm.create can build a Fake-ignored template) + VM sizing defaults.
_FAKE_CONFIG = {
    "default_image": "fedora",
    "images": {"fedora": {"location": "https://example/Fedora.qcow2", "arch": "x86_64", "digest": ""}},
    "vm": {"cpus": 2, "memory": "2GiB", "disk": "20GiB"},
}


class _ServerFixture(unittest.TestCase):
    """Starts a FakeBackend-backed BrokerServer on a real unix socket in a thread."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sock_path = str(pathlib.Path(self.tmp.name) / "lince-lab.sock")
        self.backend = FakeBackend()
        # A bare vm.start applies the DENY egress lock-down server-side; register
        # it to succeed so the lifecycle round-trips proceed past `vm.start`.
        _register_lockdown(self.backend, LAB_VM)
        self.server = BrokerServer(self.sock_path, self.backend, config=_FAKE_CONFIG)
        self.server.bind()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._await_socket()

    def tearDown(self):
        self.server.stop()
        self.thread.join(timeout=2.0)
        self.tmp.cleanup()

    def _await_socket(self) -> None:
        """Block until the listening socket accepts a connection."""
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                with BrokerClient(self.sock_path, timeout=1.0) as client:
                    client.call("ping")
                return
            except BrokerUnreachable:
                time.sleep(0.01)
        self.fail("broker socket never came up")

    def client(self) -> BrokerClient:
        return BrokerClient(self.sock_path, timeout=2.0)


class RoundTripTests(_ServerFixture):
    """End-to-end CLI-side client → real socket → broker → FakeBackend."""

    def test_ping(self):
        with self.client() as c:
            result = c.call("ping")
        self.assertTrue(result["pong"])

    def test_vm_lifecycle_and_exec(self):
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM, "template_yaml": "ignored-by-policy"})
            c.call("vm.start", {"name": LAB_VM})
            # Register a passing command on the backend, then exec it.
            self.backend.on(LAB_VM, ["sh", "-c", "make test"], ExecResult(0, "ok", ""))
            result = c.call("vm.exec", {"name": LAB_VM, "argv": ["sh", "-c", "make test"]})
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "ok")

    def test_nonzero_exec_exit_surfaced(self):
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM})
            c.call("vm.start", {"name": LAB_VM})
            self.backend.on(LAB_VM, ["false"], ExecResult(1, "", "boom"))
            result = c.call("vm.exec", {"name": LAB_VM, "argv": ["false"]})
        # A failing guest command is data, not an error: the exit code rides the
        # successful response and is the oracle/bisect signal.
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["stderr"], "boom")

    def test_bare_start_applies_deny_lockdown(self):
        # A bare vm.start (the `vm up` verb) must apply the DENY egress lock-down
        # server-side: the Fake records the `sudo sh -c <nft script>` exec, the
        # script is the deny (drop-only) posture, and it keeps Lima SSH alive via
        # established/related. The lock-down is server-applied, never client-chosen.
        seen: list[list[str]] = []
        orig_exec = self.backend.exec

        def rec_exec(name, argv, **kw):
            seen.append(list(argv))
            return orig_exec(name, argv, **kw)

        self.backend.exec = rec_exec  # type: ignore[method-assign]
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM})
            c.call("vm.start", {"name": LAB_VM})
        deny_argv = egress_lockdown_argv([], [])
        self.assertIn(deny_argv, seen)
        script = deny_argv[3]
        self.assertIn("policy drop", script)
        self.assertIn("ct state established,related accept", script)
        # The only daddr rule is the default-gateway control-plane exception (keeps
        # Lima SSH alive); deny has NO port-scoped / external-host egress allow.
        self.assertIn('ip daddr "$LL_GW" accept', script)
        self.assertNotIn("tcp dport", script)

    def test_status_and_list(self):
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM})
            c.call("vm.start", {"name": LAB_VM})
            status = c.call("vm.status", {"name": LAB_VM})
            listing = c.call("vm.list", {})
        self.assertEqual(status["status"], "running")
        self.assertIn(LAB_VM, [s["name"] for s in listing])

    def test_snapshot_round_trip(self):
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM})
            c.call("vm.start", {"name": LAB_VM})
            c.call("snap.create", {"name": LAB_VM, "tag": "base-clean"})
            tags = c.call("snap.list", {"name": LAB_VM})
            c.call("snap.apply", {"name": LAB_VM, "tag": "base-clean"})
        self.assertIn("base-clean", tags["snapshots"])

    def test_unknown_verb_round_trip_is_64(self):
        # Bypass the client's local whitelist by putting a raw envelope on the wire.
        with self.client() as c:
            c.connect()
            raw = {"v": 1, "id": "x1", "verb": "vm.evil", "args": {}}
            c.send(raw)
            response = c.recv()
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["exit"], UNKNOWN_VERB)

    def test_policy_denial_is_13(self):
        with self.client() as c:
            with self.assertRaises(LabError) as exc:
                # Unprefixed VM name trips the §3.5 name-prefix guard.
                c.call("vm.start", {"name": "not-a-lab-vm"})
        self.assertEqual(exc.exception.exit_code, POLICY_DENIED)

    def test_template_forcing_drops_client_template(self):
        # The client template is ignored entirely; the broker builds its own
        # policy-forced template server-side.
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM, "template_yaml": "mounts: [/home]"})
        stored = self.backend.fs_of(LAB_VM)["/.lince-lab/template.yaml"].decode()
        # The client's attempted host mount is dropped, and the non-overridable
        # isolation invariants are present: no host mounts, plain mode, no host
        # ssh keys.
        self.assertNotIn("/home", stored)
        self.assertIn('"mounts": []', stored)
        self.assertIn('"plain": true', stored)
        self.assertIn('"loadDotSSHPubKeys": false', stored)

    def test_bare_copy_in_with_forged_workspace_is_denied(self):
        # The broker never trusts a client workspace_dir: a bare vm.copy_in (no
        # server-side recipe context) is fail-closed denied, so workspace_dir='/'
        # cannot turn copy_in into /etc/shadow exfiltration (exit 13).
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM})
            c.call("vm.start", {"name": LAB_VM})
            with self.assertRaises(LabError) as exc:
                c.call(
                    "vm.copy_in",
                    {
                        "name": LAB_VM,
                        "host_path": "/etc/shadow",
                        "guest_path": "/work",
                        "workspace_dir": "/",
                    },
                )
        self.assertEqual(exc.exception.exit_code, POLICY_DENIED)

    def test_copy_out_destination_is_policy_bounded(self):
        # A vm.copy_out to an out-of-bounds host destination is denied (exit 13),
        # so the guest cannot be used to clobber arbitrary host files.
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM})
            c.call("vm.start", {"name": LAB_VM})
            with self.assertRaises(LabError) as exc:
                c.call(
                    "vm.copy_out",
                    {"name": LAB_VM, "guest_path": "/etc/passwd", "host_path": "/etc/cron.d/evil"},
                )
        self.assertEqual(exc.exception.exit_code, POLICY_DENIED)

    def test_capture_stream_verb_is_policy_gated(self):
        # After capture.open the connection upgrades to a line stream; smuggling a
        # non-capture verb (here vm.exec) onto that stream is policy-denied (13),
        # proving the capture stream is NOT a policy bypass.
        with self.client() as c:
            c.call("vm.create", {"name": LAB_VM})
            c.call("vm.start", {"name": LAB_VM})
            c.connect()
            # Open a capture stream (FakeBackend returns a default silent channel).
            c.send(protocol.make_request("capture.open", {"name": LAB_VM, "program": ["sh"]}))
            opened = c.recv()
            self.assertTrue(opened["ok"])
            # Smuggle a non-capture verb onto the upgraded stream.
            c.send(protocol.make_request("vm.exec", {"name": LAB_VM, "argv": ["true"]}))
            denied = c.recv()
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["error"]["exit"], POLICY_DENIED)


class EgressLogTests(unittest.TestCase):
    """#253: recipe.run writes the effective egress decision to egress.log.

    Substrate-free: a FakeBackend-backed broker with an isolated HOME runs a deny
    recipe and an allow recipe; we assert egress.log lands under the server-derived
    artifacts root and records the decision the run enforces (host-side resolved,
    never a client value).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.recipe_dir = self.root / "recipes"
        (self.recipe_dir / "fixtures").mkdir(parents=True)
        self.config = {
            "vm": {"cpus": 2, "memory": "2GiB", "disk": "20GiB"},
            "images": {"fedora": {"location": "https://example/Fedora.qcow2", "arch": "x86_64", "digest": ""}},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _write_recipe(self, name, network_toml):
        path = self.recipe_dir / f"{name}.toml"
        path.write_text(
            f"[recipe]\nname='{name}'\ndescription='d'\nversion='1'\n"
            "[vm]\nimage='fedora'\ncpus=2\n"
            f"{network_toml}"
            "[workspace]\nhost_dir='./fixtures'\nguest_dir='/work'\n"
            "[[step]]\nname='s1'\nrun=['true']\n"
            "[assert]\nexit_code=0\n",
            encoding="utf-8",
        )
        return path

    def _egress_log(self):
        return self.home / ".local/share/lince/lince-lab/artifacts/egress.log"

    def test_deny_recipe_writes_deny_decision(self):
        backend = FakeBackend()
        server = BrokerServer("unused.sock", backend, self.config, home=self.home)
        recipe_path = self._write_recipe("deny-demo", "[network]\nmode='deny'\n")
        # Register the step command so the run succeeds end-to-end on the Fake.
        backend.on("lince-lab-deny-demo", ["true"], ExecResult(0, "", ""))
        # The deny recipe applies the deny (drop-only) lock-down before its steps.
        _register_lockdown(backend, "lince-lab-deny-demo")
        from lince_lab.recipe import load_recipe

        result = server._h_recipe_run(load_recipe(str(recipe_path)), {})
        log = self._egress_log()
        self.assertTrue(log.exists(), "egress.log must be written under the artifacts root")
        doc = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(doc["recipe"], "deny-demo")
        self.assertEqual(doc["egress"]["decision"], "deny")
        self.assertEqual(doc["egress"]["rules"], [])
        # Compare canonical paths: the broker resolves the artifacts root, and on
        # macOS the tmpdir lives under /var → /private/var (a symlink), so an
        # unresolved expectation would spuriously mismatch. Identical on Linux.
        self.assertEqual(result["egress_log"], str(log.resolve()))

    def test_allow_recipe_writes_resolved_rules(self):
        backend = FakeBackend()
        server = BrokerServer("unused.sock", backend, self.config, home=self.home)
        recipe_path = self._write_recipe(
            "allow-demo",
            "[network]\nmode='allow'\nallow_hosts=['registry.npmjs.org']\nallow_ports=[443]\n",
        )
        # Resolve the allow host deterministically (no real DNS).
        from lince_lab import recipe as recipe_mod

        backend.on("lince-lab-allow-demo", ["true"], ExecResult(0, "", ""))
        # The allow recipe resolves its host to 104.16.11.34 and applies the
        # host-scoped lock-down for that ip:443 before its steps.
        _register_lockdown(backend, "lince-lab-allow-demo", allow_ips=["104.16.11.34"], allow_ports=[443])
        # The egress LOG uses resolve_allow_ips; the lock-down + /etc/hosts pin use
        # resolve_allow_map. Patch both so neither hits real DNS.
        orig_ips = recipe_mod.resolve_allow_ips
        orig_map = recipe_mod.resolve_allow_map
        recipe_mod.resolve_allow_ips = lambda hosts: ["104.16.11.34"] if hosts else []
        recipe_mod.resolve_allow_map = lambda hosts: {"registry.npmjs.org": ["104.16.11.34"]} if hosts else {}
        try:
            server._h_recipe_run(recipe_mod.load_recipe(str(recipe_path)), {})
        finally:
            recipe_mod.resolve_allow_ips = orig_ips
            recipe_mod.resolve_allow_map = orig_map
        doc = json.loads(self._egress_log().read_text(encoding="utf-8"))
        self.assertEqual(doc["egress"]["decision"], "allow")
        self.assertEqual(doc["egress"]["resolved_ips"], ["104.16.11.34"])
        self.assertIn("ip daddr 104.16.11.34 tcp dport 443 accept", doc["egress"]["rules"])


class PresetWiringTests(unittest.TestCase):
    """#stage4: a --preset on recipe.run overlays the effective config (no socket).

    Drives the broker handler directly with a loaded recipe and a preset arg,
    asserting the preset's knobs change effective behavior — here the ``bisect``
    preset's ``retain_base_snapshot`` keeps the base-clean snapshot that the
    default run drops.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.recipe_dir = self.root / "recipes"
        (self.recipe_dir / "fixtures").mkdir(parents=True)
        self.config = {
            "vm": {"cpus": 2, "memory": "2GiB", "disk": "20GiB"},
            "images": {"fedora": {"location": "https://example/Fedora.qcow2", "arch": "x86_64", "digest": ""}},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _recipe_path(self):
        path = self.recipe_dir / "demo.toml"
        path.write_text(
            "[recipe]\nname='demo'\ndescription='d'\nversion='1'\n"
            "[vm]\nimage='fedora'\ncpus=2\n"
            "[network]\nmode='deny'\n"
            "[workspace]\nhost_dir='./fixtures'\nguest_dir='/work'\n"
            "[[step]]\nname='s1'\nrun=['true']\n"
            "[assert]\nexit_code=0\n",
            encoding="utf-8",
        )
        return path

    def test_unknown_preset_is_data_error(self):
        backend = FakeBackend()
        server = BrokerServer("unused.sock", backend, self.config, home=self.home)
        with self.assertRaises(DataError):
            server._effective_config({"preset": "definitely-missing"})  # noqa: SLF001
        # A no-preset request returns the base config unchanged.
        self.assertIs(server._effective_config({}), server.config)  # noqa: SLF001
        # A known preset overlays its vm knob onto the effective config.
        quick_cfg = server._effective_config({"preset": "quick"})  # noqa: SLF001
        self.assertEqual(quick_cfg["vm"]["cpus"], 1)

    def test_bisect_preset_retains_base_snapshot(self):
        from lince_lab.recipe import BASE_SNAPSHOT_TAG, load_recipe

        backend = FakeBackend()
        backend.on("lince-lab-demo", ["true"], ExecResult(0, "", ""))
        _register_lockdown(backend, "lince-lab-demo")
        server = BrokerServer("unused.sock", backend, self.config, home=self.home)
        recipe = load_recipe(str(self._recipe_path()))
        # keep=True via explicit arg so the VM (and its snapshots) survive for the
        # assertion; preset 'bisect' sets retain_base_snapshot=True.
        server._h_recipe_run(recipe, {"preset": "bisect", "keep": True})  # noqa: SLF001
        self.assertIn(BASE_SNAPSHOT_TAG, backend.snapshot_list("lince-lab-demo"))

    def test_no_preset_drops_base_snapshot(self):
        from lince_lab.recipe import BASE_SNAPSHOT_TAG, load_recipe

        backend = FakeBackend()
        backend.on("lince-lab-demo", ["true"], ExecResult(0, "", ""))
        _register_lockdown(backend, "lince-lab-demo")
        server = BrokerServer("unused.sock", backend, self.config, home=self.home)
        recipe = load_recipe(str(self._recipe_path()))
        server._h_recipe_run(recipe, {"keep": True})  # noqa: SLF001
        self.assertNotIn(BASE_SNAPSHOT_TAG, backend.snapshot_list("lince-lab-demo"))


class LockTableBoundTests(unittest.TestCase):
    """#stage4: the per-VM lock table is capped so it cannot grow without bound."""

    def test_lock_table_is_capped_and_reuses(self):
        backend = FakeBackend()
        server = BrokerServer("unused.sock", backend, config={})
        # Re-requesting the same name returns the same lock (no churn).
        first = server._lock_for("lince-lab-a")  # noqa: SLF001
        self.assertIs(first, server._lock_for("lince-lab-a"))  # noqa: SLF001
        # Churn far more distinct names than the cap; the table never exceeds it.
        for i in range(server._MAX_LOCKS * 3):  # noqa: SLF001
            server._lock_for(f"lince-lab-{i}")  # noqa: SLF001
            self.assertLessEqual(len(server._locks), server._MAX_LOCKS)  # noqa: SLF001


class UnreachableTests(unittest.TestCase):
    """A missing socket maps to BROKER_UNREACHABLE (exit 69)."""

    def test_missing_socket_is_69(self):
        with tempfile.TemporaryDirectory() as d:
            missing = str(pathlib.Path(d) / "nope.sock")
            with self.assertRaises(BrokerUnreachable) as exc:
                BrokerClient(missing, timeout=0.5).call("ping")
        self.assertEqual(exc.exception.exit_code, BROKER_UNREACHABLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
