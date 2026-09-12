"""X11 clipboard access survives bwrap's tmpfs overlays and clearenv."""

import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


class X11ClipboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / "sandbox/agent-sandbox"
        loader = importlib.machinery.SourceFileLoader("sandbox_x11_test", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.mod = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.mod)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.auth = self.root / "Xauthority"
        self.auth.write_text("test-cookie")
        env = mock.patch.dict(self.mod.os.environ, {
            "DISPLAY": ":7.0", "XAUTHORITY": str(self.auth),
        }, clear=True)
        env.start()
        self.addCleanup(env.stop)
        sockets = mock.patch.object(Path, "is_socket", autospec=True,
                                    side_effect=lambda p: str(p) == "/tmp/.X11-unix/X7")
        sockets.start()
        self.addCleanup(sockets.stop)

    def test_local_display_and_authentication(self):
        args = self.mod.x11_bwrap_args({})
        self.assertEqual(args, [
            "--ro-bind", "/tmp/.X11-unix/X7", "/tmp/.X11-unix/X7",
            "--setenv", "DISPLAY", ":7.0",
            "--ro-bind", str(self.auth), "/tmp/.lince-xauthority",
            "--setenv", "XAUTHORITY", "/tmp/.lince-xauthority",
        ])

    def test_home_authentication_fallback(self):
        del self.mod.os.environ["XAUTHORITY"]
        auth = self.root / ".Xauthority"
        auth.write_text("test-cookie")
        with mock.patch.object(Path, "home", return_value=self.root):
            self.assertIn(str(auth), self.mod.x11_bwrap_args({}))

    def test_runtime_authentication_symlink(self):
        link = self.root / "auth-link"
        link.symlink_to(self.auth)
        self.mod.os.environ["XAUTHORITY"] = str(link)
        self.assertIn(str(self.auth), self.mod.x11_bwrap_args({}))
        self.assertNotIn(str(link), self.mod.x11_bwrap_args({}))

    def test_missing_authentication_keeps_socket_access(self):
        self.auth.unlink()
        args = self.mod.x11_bwrap_args({})
        self.assertIn("DISPLAY", args)
        self.assertNotIn("XAUTHORITY", args)

    def test_disabled_or_network_isolated(self):
        for config in ({"sandbox": {"expose_x11": False}},
                       {"security": {"unshare_net": True}}):
            with self.subTest(config=config):
                self.assertEqual(self.mod.x11_bwrap_args(config), [])

    def test_absent_remote_or_invalid_display(self):
        for display in ("", ":9", "localhost:7", "host:7", ":../7", ":7/bad"):
            with self.subTest(display=display):
                self.mod.os.environ["DISPLAY"] = display
                self.assertEqual(self.mod.x11_bwrap_args({}), [])

    def test_unix_display_formats(self):
        for display in (":7", "unix:7", "unix/:7.0"):
            with self.subTest(display=display):
                self.mod.os.environ["DISPLAY"] = display
                self.assertIn("/tmp/.X11-unix/X7", self.mod.x11_bwrap_args({}))

    def test_builders_expose_x11_after_overlays_and_clearenv(self):
        config = {
            "sandbox": {"auto_expose_path": False, "persist_toolchains": False,
                        "expose_gpu": False},
            "security": {"block_git_push": False},
        }
        agent = {"command": "true", "home_ro_dirs": [], "home_rw_dirs": []}
        with mock.patch.object(self.mod, "SANDBOX_DIR", self.root):
            commands = [
                self.mod.build_bwrap_cmd(config, self.root, [], agent_config=agent),
                self.mod.build_learn_bwrap_cmd(config, self.root, agent),
            ]
        expected = self.mod.x11_bwrap_args(config)
        for cmd in commands:
            with self.subTest(builder=cmd):
                start = cmd.index("/tmp/.X11-unix/X7") - 1
                self.assertEqual(cmd[start:start + len(expected)], expected)
                self.assertGreater(start, cmd.index("--clearenv"))
                self.assertGreater(start, max(i for i, arg in enumerate(cmd)
                                              if arg == "--tmpfs"))


if __name__ == "__main__":
    unittest.main()
