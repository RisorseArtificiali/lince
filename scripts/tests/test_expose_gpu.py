#!/usr/bin/env python3
"""[sandbox].expose_gpu (#280) — GPU device nodes re-exposed inside bwrap.

`bwrap --dev /dev` mounts a minimal synthetic devtmpfs without the CUDA
device nodes, so GPU runtimes silently fall back to CPU. With
``expose_gpu = true`` the builder appends ``--dev-bind-try`` for every
``/dev/nvidia*`` node plus ``/dev/dri``. These tests pin the helper's
contract host-independently (the /dev listing is mocked).

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

    def test_disabled_by_default(self):
        self.assertEqual(self.sandbox.gpu_dev_bind_args({}), [])
        self.assertEqual(self.sandbox.gpu_dev_bind_args({"expose_gpu": False}), [])

    def test_enabled_binds_nvidia_nodes_and_dri(self):
        fake_dev = ["null", "nvidia0", "nvidia1", "nvidiactl", "nvidia-uvm", "tty"]
        with mock.patch.object(self.sandbox.os, "listdir", return_value=fake_dev), \
             mock.patch.object(self.sandbox.os.path, "exists", return_value=True):
            args = self.sandbox.gpu_dev_bind_args({"expose_gpu": True})
        expected = []
        for p in ("/dev/nvidia-uvm", "/dev/nvidia0", "/dev/nvidia1",
                  "/dev/nvidiactl", "/dev/dri"):
            expected += ["--dev-bind-try", p, p]
        # nvidia* sorted first, /dev/dri appended last; non-nvidia nodes ignored.
        self.assertEqual(args, expected)

    def test_enabled_on_gpuless_host_is_a_noop(self):
        with mock.patch.object(self.sandbox.os, "listdir", return_value=["null", "tty"]), \
             mock.patch.object(self.sandbox.os.path, "exists", return_value=False):
            self.assertEqual(self.sandbox.gpu_dev_bind_args({"expose_gpu": True}), [])


class TestParanoidGpuDenied(unittest.TestCase):
    """Paranoid never inherits the GPU silently — fragment must opt in."""

    @classmethod
    def setUpClass(cls):
        cls.sandbox = load_module("sandbox/agent-sandbox", "agent_sandbox_gpu_test2")

    def test_global_flag_alone_is_denied_at_paranoid(self):
        self.assertTrue(self.sandbox.paranoid_gpu_denied(
            {"expose_gpu": True}, {"security": {"unshare_net": True}}))

    def test_fragment_opt_in_is_honoured(self):
        self.assertFalse(self.sandbox.paranoid_gpu_denied(
            {"expose_gpu": True}, {"sandbox": {"expose_gpu": True}}))

    def test_disabled_globally_nothing_to_deny(self):
        self.assertFalse(self.sandbox.paranoid_gpu_denied({}, {}))
        self.assertFalse(self.sandbox.paranoid_gpu_denied(
            {"expose_gpu": False}, {"sandbox": {}}))


if __name__ == "__main__":
    unittest.main()
