import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import call


class PackagingTests(unittest.TestCase):
    def test_custom_hook_paths_are_explicitly_removed_without_touching_user_handlers(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="lince-custom-hooks-") as directory:
            home = Path(directory)
            env = {k: v for k, v in os.environ.items() if k != "CODEX_HOME" and not k.startswith("LINCE_MSG_")}
            env.update(HOME=directory, LINCE_MESSAGES_INSTALL_DIR=str(home / "module"),
                       LINCE_MESSAGES_BIN_DIR=str(home / "bin"))
            original = {"theme": "user", "hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": "user-owned-handler"}]}]}}
            arguments = []
            paths = []
            for agent in ("claude", "codex", "bob"):
                settings = home / f"custom {agent}.json"
                settings.write_text(json.dumps(original))
                subprocess.run(["bash", str(source / "install.sh"), f"--configure-{agent}", str(settings)],
                               env=env, capture_output=True, check=True, timeout=15)
                self.assertIn("lince-msg-hook", settings.read_text())
                arguments.extend(["--settings", agent, str(settings)])
                paths.append(settings)
            invalid = subprocess.run(["bash", str(source / "uninstall.sh"), "--settings", "unknown", "file"],
                                     env=env, capture_output=True, timeout=15)
            self.assertEqual(invalid.returncode, 2)
            self.assertTrue((home / "bin/lince-msg").exists())
            configured = paths[0].read_text()
            paths[0].write_text("{")
            malformed = subprocess.run(["bash", str(source / "uninstall.sh"), *arguments], env=env,
                                       capture_output=True, timeout=15)
            self.assertNotEqual(malformed.returncode, 0)
            self.assertTrue((home / "bin/lince-msg-hook").exists())
            self.assertEqual(paths[0].read_text(), "{")
            paths[0].write_text(configured)
            for _ in range(2):
                subprocess.run(["bash", str(source / "uninstall.sh"), *arguments], env=env,
                               capture_output=True, check=True, timeout=15)
                for settings in paths:
                    self.assertEqual(json.loads(settings.read_text()), original)

    def test_supervised_identity_upgrade_recovery_and_uninstall(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="lince-package-test-") as directory:
            home = Path(directory)
            env = {k: v for k, v in os.environ.items() if k != "CODEX_HOME" and not k.startswith("LINCE_MSG_")}
            env.update(HOME=directory, LINCE_MESSAGES_INSTALL_DIR=str(home / ".local/lib/lince-messages"),
                       LINCE_MESSAGES_BIN_DIR=str(home / ".local/bin"))
            env["PATH"] = str(home / ".local/bin") + os.pathsep + env["PATH"]
            session = "package-test-" + uuid.uuid4().hex
            key = hashlib.sha256(session.encode()).hexdigest()[:24]
            private = home / ".local/state/lince-messages/sessions" / key
            endpoint = Path(f"/tmp/lince-msg-{os.getuid()}") / key / "mailbox.sock"

            def run(*command):
                result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            def host(op, **args):
                return call(endpoint, (private / "admin.token").read_text(), "host." + op, args)

            try:
                run("bash", str(source / "install.sh"), "--configure-all")
                run("lince-msg-host", "--session", session, "ensure")
                child = run("lince-msg-host", "--session", session, "run", "--alias", "fixture", "--agent", "claude",
                            "--", sys.executable, "-c", "import subprocess; subprocess.run(['lince-msg','peers'],check=True)")
                instance = json.loads(child)["result"]["instance"]
                self.assertEqual(next(i for i in host("snapshot")["instances"] if i["id"] == instance)["live"], 0)
                self.assertEqual(list((home / ".local/state/lince-messages/credentials").glob("*.token")), [])
                a = host("register", alias="sender", agent="claude")
                b = host("register", alias="recipient", agent="codex")
                group = host("group", name="test", members=[a["instance"], b["instance"]])["group"]
                request = call(endpoint, a["token"], "delegate", {"recipient": b["instance"], "group": group,
                    "text": "test work", "key": "work"})["id"]
                call(endpoint, b["token"], "accept", {"request": request})
                run("bash", str(source / "update.sh"))
                self.assertFalse(endpoint.exists())
                run("lince-msg-host", "--session", session, "ensure")
                self.assertEqual(host("get", request=request)["work"], "interrupted")
                run("bash", str(source / "uninstall.sh"))
                self.assertFalse(endpoint.exists())
                self.assertTrue((private / "mailbox.sqlite3").exists())
                self.assertFalse((home / ".local/bin/lince-msg").exists())
                for file in (home / ".claude/settings.json", home / ".codex/hooks.json", home / ".bob/settings/settings.json"):
                    if file.exists():
                        self.assertNotIn("lince-msg-hook", file.read_text())
            finally:
                subprocess.run([sys.executable, str(source / "maintenance.py")], env=env,
                               capture_output=True, timeout=15)
