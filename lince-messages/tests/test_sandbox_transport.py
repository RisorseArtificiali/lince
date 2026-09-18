"""Real bwrap transport and generated Seatbelt rules; no model or Zellij needed."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service import Server
from store import Store


class SandboxTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        loader = importlib.machinery.SourceFileLoader("messaging_sandbox", str(cls.root / "sandbox/agent-sandbox"))
        cls.mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        sys.modules[loader.name] = cls.mod
        loader.exec_module(cls.mod)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.private = self.home / ".local/state/lince-messages"
        (self.private / "credentials").mkdir(parents=True)
        self.credential = self.private / "credentials/instance"
        self.credential.write_text("instance-secret")
        self.credential.chmod(0o600)
        self.public_root = Path(f"/tmp/lince-msg-{os.getuid()}")
        self.public_root.mkdir(mode=0o700, exist_ok=True)
        self.public_tmp = tempfile.TemporaryDirectory(dir=self.public_root)
        self.addCleanup(self.public_tmp.cleanup)
        self.endpoint = Path(self.public_tmp.name) / "mailbox.sock"
        self.store = Store(self.private / "db", "host-secret")
        self.addCleanup(self.store.close)
        self.server = Server(self.endpoint, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.addCleanup(self.stop_server)
        home = mock.patch.object(Path, "home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)
        env = mock.patch.dict(os.environ, {"LINCE_MSG_ENDPOINT": str(self.endpoint),
                                         "LINCE_MSG_CREDENTIAL": str(self.credential)})
        env.start()
        self.addCleanup(env.stop)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_no_project_env_credential_override(self):
        cmd = self.mod.build_env_clear_command({"sandbox": {"auto_expose_path": False},
            "env": {"extra": {"LINCE_MSG_CREDENTIAL": "/evil", "LINCE_MSG_ADMIN": "bad"}}}, "claude")
        self.assertIn(f"LINCE_MSG_CREDENTIAL={self.credential}", cmd)
        self.assertNotIn("LINCE_MSG_CREDENTIAL=/evil", cmd)
        self.assertNotIn("LINCE_MSG_ADMIN=bad", cmd)

    def test_reject_foreign_path_and_open_permissions(self):
        self.credential.chmod(0o644)
        with self.assertRaises(ValueError):
            self.mod.messaging_environment()
        self.credential.chmod(0o600)
        with mock.patch.dict(os.environ, {"LINCE_MSG_CREDENTIAL": "/etc/passwd"}):
            with self.assertRaises(ValueError):
                self.mod.messaging_environment()

    def test_seatbelt_protects_host_state(self):
        profile, _ = self.mod.generate_seatbelt_profile("claude", {}, {})
        self.assertIn(f'(subpath "{self.private}")', profile)
        self.assertIn(f'(require-not (literal "{self.credential}"))', profile)
        self.assertIn(f'(deny file-write* (literal "{self.credential}"))', profile)

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap unavailable: runtime gate unverified")
    def test_real_bwrap_without_zellij(self):
        instance = self.store.handle({"v": 1, "token": "host-secret", "op": "host.register",
                                     "args": {"alias": "sandbox-client", "agent": "test"}})
        self.credential.write_text(instance["token"])
        secret = self.private / "admin.token"
        secret.write_text("host-secret")
        script = """import json,os,pathlib,sys
sys.path.insert(0,sys.argv[1])
from protocol import call,ProtocolError
credential=pathlib.Path(os.environ['LINCE_MSG_CREDENTIAL']).read_text()
assert not pathlib.Path(sys.argv[2]).exists(), 'host credential exposed'
assert not pathlib.Path('/run/user/'+str(os.getuid())+'/zellij').exists(), 'Zellij exposed'
result=call(os.environ['LINCE_MSG_ENDPOINT'],credential,'peers')
try:
    call(os.environ['LINCE_MSG_ENDPOINT'],credential,'host.snapshot')
except ProtocolError as e:
    assert e.code=='access_denied'
else:
    raise AssertionError('agent acquired host privileges')
print(json.dumps(result))
"""
        command = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", "/tmp",
                   "--tmpfs", f"/run/user/{os.getuid()}", "--unshare-pid", "--proc", "/proc",
                   "--ro-bind", str(self.home), str(self.home),
                   *self.mod.messaging_bwrap_args(), "--", sys.executable, "-c", script,
                   str(self.root / "lince-messages"), str(secret)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["instance"], instance["instance"])


if __name__ == "__main__":
    unittest.main()
