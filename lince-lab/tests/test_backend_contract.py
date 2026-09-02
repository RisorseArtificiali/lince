#!/usr/bin/env python3
"""Backend contract suite (blueprint §2, §9).

A single set of assertions that every :class:`~lince_lab.backend.Backend` must
satisfy, written against a *factory* so it can run against more than one
implementation. It runs against ``FakeBackend`` here; a ``LimaBackend`` factory
plugs in only when ``LINCE_LAB_KVM=1`` (skipped otherwise — no VM in unit tests).

Run with:
    python3 lince-lab/tests/test_backend_contract.py
"""

import os
import pathlib
import sys
import unittest
from collections.abc import Callable

# Put the package dir (lince-lab/) on sys.path so absolute imports resolve.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lince_lab.backend import Backend, ExecResult, VmStatus  # noqa: E402
from lince_lab.fake_backend import FakeBackend  # noqa: E402


class BackendContractMixin:
    """The backend-independent contract. Subclasses set :attr:`make_backend`."""

    make_backend: Callable[[], Backend]

    def setUp(self) -> None:
        self.backend = self.make_backend()
        self.name = "lince-lab-contract-test"

    def _create_and_start(self) -> None:
        self.backend.create(self.name, "images: []\n")
        self.backend.start(self.name)

    # ── lifecycle transitions ───────────────────────────────────────────────
    def test_lifecycle_transitions(self) -> None:
        self.assertEqual(self.backend.status(self.name).status, VmStatus.ABSENT)
        self.backend.create(self.name, "images: []\n")
        self.assertEqual(self.backend.status(self.name).status, VmStatus.STOPPED)
        self.backend.start(self.name)
        self.assertEqual(self.backend.status(self.name).status, VmStatus.RUNNING)
        self.backend.stop(self.name)
        self.assertEqual(self.backend.status(self.name).status, VmStatus.STOPPED)
        self.backend.delete(self.name)
        self.assertEqual(self.backend.status(self.name).status, VmStatus.ABSENT)

    def test_list_reflects_created_vms(self) -> None:
        self.backend.create(self.name, "images: []\n")
        names = [s.name for s in self.backend.list()]
        self.assertIn(self.name, names)

    # ── snapshots round-trip ────────────────────────────────────────────────
    def test_snapshot_round_trip(self) -> None:
        self._create_and_start()
        self.backend.snapshot_create(self.name, "base")
        self.assertIn("base", self.backend.snapshot_list(self.name))
        self.backend.snapshot_apply(self.name, "base")
        self.backend.snapshot_delete(self.name, "base")
        self.assertNotIn("base", self.backend.snapshot_list(self.name))

    def test_snapshot_apply_resets_filesystem(self) -> None:
        # Backend-independent in spirit; Fake models fs precisely. We register a
        # command that writes a marker, snapshot before, mutate, then reset.
        self._create_and_start()

        def write_marker(fs: dict, argv: list) -> ExecResult:
            fs["/marker"] = b"x"
            return ExecResult(0, "", "")

        # Only the Fake exposes on(); the Lima path skips this finer assertion.
        if not isinstance(self.backend, FakeBackend):
            self.skipTest("fs-reset assertion is Fake-specific")
        self.backend.on(self.name, ["touch", "/marker"], write_marker)
        self.backend.snapshot_create(self.name, "clean")
        self.backend.exec(self.name, ["touch", "/marker"])
        self.assertIn("/marker", self.backend.fs_of(self.name))
        self.backend.snapshot_apply(self.name, "clean")
        self.assertNotIn("/marker", self.backend.fs_of(self.name))

    # ── exec exit-code passthrough ──────────────────────────────────────────
    def test_exec_exit_code_passthrough(self) -> None:
        self._create_and_start()
        if isinstance(self.backend, FakeBackend):
            self.backend.on(self.name, ["true"], ExecResult(0, "ok", ""))
            self.backend.on(self.name, ["false"], ExecResult(1, "", "boom"))
            self.backend.on(self.name, ["exit", "42"], ExecResult(42, "", ""))
            self.assertEqual(self.backend.exec(self.name, ["true"]).exit_code, 0)
            self.assertEqual(self.backend.exec(self.name, ["false"]).exit_code, 1)
            self.assertEqual(self.backend.exec(self.name, ["exit", "42"]).exit_code, 42)
        else:  # pragma: no cover - KVM path
            self.assertEqual(self.backend.exec(self.name, ["true"]).exit_code, 0)
            self.assertEqual(self.backend.exec(self.name, ["sh", "-c", "exit 42"]).exit_code, 42)

    def test_exec_unregistered_is_command_not_found(self) -> None:
        if not isinstance(self.backend, FakeBackend):
            self.skipTest("unregistered-default is Fake-specific")
        self._create_and_start()
        result = self.backend.exec(self.name, ["definitely-not-a-real-command"])
        self.assertEqual(result.exit_code, 127)
        self.assertIn("not found", result.stderr)

    # ── copy round-trip ─────────────────────────────────────────────────────
    def test_copy_in_then_test_f(self) -> None:
        self._create_and_start()
        self.backend.copy_in(self.name, "/host/data.txt", "/work/data.txt")
        # test -f succeeds on a copied-in path (Fake builtin / real guest).
        self.assertEqual(self.backend.exec(self.name, ["test", "-f", "/work/data.txt"]).exit_code, 0)
        self.assertEqual(self.backend.exec(self.name, ["test", "-f", "/work/missing"]).exit_code, 1)

    def test_copy_out_round_trip(self) -> None:
        self._create_and_start()
        self.backend.copy_in(self.name, "/host/a", "/work/a")
        # copy_out of an existing guest path must not error.
        self.backend.copy_out(self.name, "/work/a", "/host/out/a")


class FakeBackendContractTest(BackendContractMixin, unittest.TestCase):
    make_backend = staticmethod(FakeBackend)


@unittest.skipUnless(os.environ.get("LINCE_LAB_KVM") == "1", "LINCE_LAB_KVM!=1: real-VM backend skipped")
class LimaBackendContractTest(BackendContractMixin, unittest.TestCase):  # pragma: no cover - KVM only
    @staticmethod
    def make_backend() -> Backend:
        from lince_lab.lima_backend import LimaBackend  # imported lazily; KVM-only glue

        return LimaBackend()


@unittest.skipUnless(os.environ.get("LINCE_LAB_TART") == "1", "LINCE_LAB_TART!=1: macOS backend skipped")
class MacosBackendContractTest(BackendContractMixin, unittest.TestCase):  # pragma: no cover - Tart only
    @staticmethod
    def make_backend() -> Backend:
        from lince_lab.macos_backend import MacosBackend  # imported lazily; macOS/Tart-only glue

        return MacosBackend()


if __name__ == "__main__":
    unittest.main(verbosity=2)
