#!/usr/bin/env python3
"""Host-open bridge (#284) — xdg-open shim + sandbox bin dir mount.

Inside bwrap the home is hidden and /tmp is private: the stock xdg-open
can't see ~/.config/mimeapps.list and X11 browsers can't start. The shim
forwards URL opens to the host through `zellij run` (the Zellij socket is
already mounted for the status pipes) and falls back to the stock
xdg-open outside Zellij. `ensure_xdg_open_shim()` writes it into
SANDBOX_DIR/bin — which the bwrap builder now actually mounts.

Run with:
    python3 -m pytest scripts/tests/test_xdg_open_shim.py
"""

import importlib.machinery
import importlib.util
import subprocess
import tempfile
import unittest
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


class TestXdgOpenShim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = load_module("sandbox/agent-sandbox", "agent_sandbox_shim_test")

    def test_shim_is_valid_bash_with_zellij_bridge_and_fallback(self):
        shim = self.sandbox.XDG_OPEN_SHIM
        # Host bridge goes through zellij run; fallback execs the real binary
        # (absolute path — the shim itself shadows `xdg-open` on PATH).
        self.assertIn('zellij run', shim)
        self.assertIn('--close-on-exit', shim)
        self.assertIn('exec /usr/bin/xdg-open "$@"', shim)
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as fh:
            fh.write(shim)
            fh.flush()
            proc = subprocess.run(["bash", "-n", fh.name], capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())

    def test_ensure_writes_executable_shim_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig = self.sandbox.SANDBOX_DIR
            self.sandbox.SANDBOX_DIR = Path(tmp)
            try:
                bin_dir = self.sandbox.ensure_xdg_open_shim()
                shim = bin_dir / "xdg-open"
                self.assertTrue(shim.exists())
                self.assertTrue(shim.stat().st_mode & 0o111, "shim not executable")
                self.assertEqual(shim.read_text(), self.sandbox.XDG_OPEN_SHIM)
                mtime = shim.stat().st_mtime_ns
                # Second call must not rewrite an up-to-date shim.
                self.sandbox.ensure_xdg_open_shim()
                self.assertEqual(shim.stat().st_mtime_ns, mtime)
                # A stale/modified shim gets refreshed to the shipped content.
                shim.write_text("#!/bin/bash\necho stale\n")
                self.sandbox.ensure_xdg_open_shim()
                self.assertEqual(shim.read_text(), self.sandbox.XDG_OPEN_SHIM)
            finally:
                self.sandbox.SANDBOX_DIR = orig


if __name__ == "__main__":
    unittest.main()
