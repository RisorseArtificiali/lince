#!/usr/bin/env python3
"""Sandbox ↔ lince-lab broker socket bind (#255).

Verifies that ``build_bwrap_cmd`` in ``sandbox/agent-sandbox`` exposes the
host-side lince-lab broker socket into the sandbox **iff** the socket exists —
the strictly-additive, existence-guarded behaviour that keeps every existing
user unaffected (the socket only exists once lince-lab is installed and its
broker is running).

Run with:
    python3 scripts/tests/test_sandbox_broker_bind.py
"""

import importlib.machinery
import importlib.util
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "sandbox"))


def load_agent_sandbox():
    """Import the no-extension ``sandbox/agent-sandbox`` script as a module."""
    path = REPO_ROOT / "sandbox" / "agent-sandbox"
    loader = importlib.machinery.SourceFileLoader("agent_sandbox_under_test", str(path))
    spec = importlib.util.spec_from_loader("agent_sandbox_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _has_bind(cmd: list[str], src: str, dst: str) -> bool:
    """True iff ``cmd`` contains the contiguous ``--bind src dst`` triple."""
    for i in range(len(cmd) - 2):
        if cmd[i] == "--bind" and cmd[i + 1] == src and cmd[i + 2] == dst:
            return True
    return False


# A minimal config that avoids host-dependent branches (PATH auto-expose,
# toolchain caches) so the builder runs deterministically in a test.
MIN_CONFIG = {
    "sandbox": {"auto_expose_path": False, "persist_toolchains": False},
    "claude": {},
    "security": {},
    "env": {},
}
MIN_AGENT_CONFIG = {"command": "claude", "home_ro_dirs": [], "home_rw_dirs": []}


class BrokerSocketBindTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_agent_sandbox()
        self._tmp = tempfile.TemporaryDirectory()
        self.sandbox_dir = pathlib.Path(self._tmp.name)
        # Redirect the sandbox runtime dir (where the broker socket lives).
        self._orig_sandbox_dir = self.mod.SANDBOX_DIR
        self.mod.SANDBOX_DIR = self.sandbox_dir
        self._proj = tempfile.TemporaryDirectory()
        self.project_dir = pathlib.Path(self._proj.name)

    def tearDown(self) -> None:
        self.mod.SANDBOX_DIR = self._orig_sandbox_dir
        self._tmp.cleanup()
        self._proj.cleanup()

    def _build(self) -> list[str]:
        return self.mod.build_bwrap_cmd(
            MIN_CONFIG,
            self.project_dir,
            agent_extra_args=[],
            agent_config=dict(MIN_AGENT_CONFIG),
        )

    def test_socket_absent_no_bind(self) -> None:
        # No broker socket present → the command is unchanged (no broker bind).
        sock = str(self.sandbox_dir / "lince-lab.sock")
        cmd = self._build()
        self.assertFalse(_has_bind(cmd, sock, sock))

    def test_socket_present_is_bound_rw(self) -> None:
        # Broker socket present → it is bind-mounted (read-write) at the same path.
        sock_path = self.sandbox_dir / "lince-lab.sock"
        sock_path.write_text("")  # a plain file is enough for the .exists() guard
        sock = str(sock_path)
        cmd = self._build()
        self.assertTrue(_has_bind(cmd, sock, sock), "expected a --bind of the broker socket")

    def test_bind_comes_after_home_tmpfs(self) -> None:
        # The bind must come *after* the `--tmpfs <home>` that wipes $HOME, or it
        # would be hidden. Assert ordering so the exposure actually survives.
        sock_path = self.sandbox_dir / "lince-lab.sock"
        sock_path.write_text("")
        sock = str(sock_path)
        cmd = self._build()
        home = str(pathlib.Path.home())
        tmpfs_home_idx = max(
            (i for i in range(len(cmd) - 1) if cmd[i] == "--tmpfs" and cmd[i + 1] == home),
            default=-1,
        )
        bind_idx = next(
            i for i in range(len(cmd) - 2) if cmd[i] == "--bind" and cmd[i + 1] == sock and cmd[i + 2] == sock
        )
        self.assertGreater(tmpfs_home_idx, -1, "expected a --tmpfs of $HOME")
        self.assertGreater(bind_idx, tmpfs_home_idx, "broker bind must come after the $HOME tmpfs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
