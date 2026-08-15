#!/usr/bin/env python3
"""[sandbox].expose_gpu (#280) — GPU device nodes re-exposed inside bwrap.

`bwrap --dev /dev` mounts a minimal synthetic devtmpfs without the CUDA
device nodes, so GPU runtimes silently fall back to CPU. `expose_gpu`
defaults to TRUE: normal/permissive/custom levels re-expose every
``/dev/nvidia*`` node plus ``/dev/dri`` via ``--dev-bind-try`` unless the
user sets it to false. The paranoid level ignores the global flag and only
exposes the GPU when its own fragment opts in (`paranoid_gpu_denied`).
These tests pin both contracts host-independently (the /dev listing is
mocked).

Run with:
    python3 -m pytest scripts/tests/test_expose_gpu.py
"""

import importlib.machinery
import importlib.util
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_module(rel_path: str, name: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, str(path))
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestGpuDevBindArgs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = load_module("sandbox/agent-sandbox", "agent_sandbox_gpu_test")

    def test_explicit_false_disables(self):
        self.assertEqual(self.sandbox.gpu_dev_bind_args({"expose_gpu": False}), [])

    def test_enabled_by_default_binds_nvidia_nodes_and_dri(self):
        fake_dev = ["null", "nvidia0", "nvidia1", "nvidiactl", "nvidia-uvm", "tty"]
        expected = []
        for p in ("/dev/nvidia-uvm", "/dev/nvidia0", "/dev/nvidia1",
                  "/dev/nvidiactl", "/dev/dri"):
            expected += ["--dev-bind-try", p, p]
        with mock.patch.object(self.sandbox.os, "listdir", return_value=fake_dev), \
             mock.patch.object(self.sandbox.os.path, "exists", return_value=True):
            # key absent -> default true; explicit true identical
            self.assertEqual(self.sandbox.gpu_dev_bind_args({}), expected)
            self.assertEqual(
                self.sandbox.gpu_dev_bind_args({"expose_gpu": True}), expected)

    def test_default_on_gpuless_host_is_a_noop(self):
        with mock.patch.object(self.sandbox.os, "listdir", return_value=["null", "tty"]), \
             mock.patch.object(self.sandbox.os.path, "exists", return_value=False):
            self.assertEqual(self.sandbox.gpu_dev_bind_args({}), [])


class TestParanoidGpuDenied(unittest.TestCase):
    """Paranoid never inherits the GPU — not even from the true default."""

    @classmethod
    def setUpClass(cls):
        cls.sandbox = load_module("sandbox/agent-sandbox", "agent_sandbox_gpu_test2")

    def test_default_true_is_denied_at_paranoid(self):
        # Key absent everywhere -> the global default (true) must NOT leak
        # into paranoid: denied unless the fragment opts in.
        self.assertTrue(self.sandbox.paranoid_gpu_denied({}, {}))
        self.assertTrue(self.sandbox.paranoid_gpu_denied(
            {"expose_gpu": True}, {"security": {"unshare_net": True}}))

    def test_fragment_opt_in_is_honoured(self):
        self.assertFalse(self.sandbox.paranoid_gpu_denied(
            {"expose_gpu": True}, {"sandbox": {"expose_gpu": True}}))

    def test_disabled_globally_nothing_to_deny(self):
        self.assertFalse(self.sandbox.paranoid_gpu_denied(
            {"expose_gpu": False}, {"sandbox": {}}))


if __name__ == "__main__":
    unittest.main()
