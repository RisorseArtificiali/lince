import json
import os
from pathlib import Path
import subprocess
import sys

from test_service import MailboxFixture


class CliTests(MailboxFixture):
    def cli(self, actor, *args, stdin=None):
        credential = self.path / (actor["instance"] + ".token")
        credential.write_text(actor["token"])
        env = {**os.environ, "LINCE_MSG_ENDPOINT": str(self.path / "socket"),
               "LINCE_MSG_CREDENTIAL": str(credential)}
        process = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "lince-msg"), *args],
                                 env=env, input=stdin, text=True, capture_output=True, timeout=10)
        return process.returncode, json.loads(process.stdout)

    def test_cli_question_result_and_timeout(self):
        text = "two lines\n$(touch /tmp/lince-must-not-execute) `id` 'quoted'"
        status, result = self.cli(self.a, "ask", self.b["instance"], "--group", self.group,
                                  "--stdin", "--key", "cli-q", stdin=text)
        self.assertEqual(status, 0)
        request = result["result"]["id"]
        self.assertEqual(result["result"]["text"], text)
        status, timeout = self.cli(self.a, "wait", request, "--timeout", "0.02")
        self.assertEqual(status, 4)
        self.assertEqual(timeout["result"]["work"], "pending")
        self.assertEqual(self.cli(self.b, "accept", request)[0], 0)
        self.assertEqual(self.cli(self.b, "reply", request, "--text", "answer")[0], 0)
        self.assertEqual(self.cli(self.a, "wait", request, "--timeout", "1")[0], 0)

    def test_cli_file_delegate_duplicate_and_denied(self):
        source = self.path / "message.txt"
        source.write_text("Delegate from local file")
        args = ("delegate", self.b["instance"], "--group", self.group, "--file", str(source), "--key", "d")
        one = self.cli(self.a, *args)[1]["result"]["id"]
        self.assertEqual(self.cli(self.a, *args)[1]["result"]["id"], one)
        self.assertEqual(self.cli(self.c, "get", one)[0], 3)
        self.cli(self.b, "accept", one)
        self.assertEqual(self.cli(self.b, "complete", one, "--text", "completed")[0], 0)
        self.assertEqual(self.cli(self.a, "get", one)[1]["result"]["work"], "completed")

    def test_cli_malformed_body(self):
        status, error = self.cli(self.a, "ask", self.b["instance"], "--group", self.group,
                                 "--stdin", stdin="bad\x1b[2J")
        self.assertEqual(status, 2)
        self.assertEqual(error["error"]["code"], "invalid_request")

    def test_install_update_uninstall_preserve_user_files(self):
        root = Path(__file__).resolve().parents[1]
        dest, bin_dir = self.path / "install", self.path / "bin"
        dest.mkdir()
        (dest / "user-settings.toml").write_text("preserve")
        env = {**os.environ, "HOME": str(self.path), "LINCE_MESSAGES_INSTALL_DIR": str(dest),
               "LINCE_MESSAGES_BIN_DIR": str(bin_dir)}
        for script in ("install.sh", "update.sh", "uninstall.sh", "uninstall.sh"):
            result = subprocess.run(["bash", str(root / script)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((dest / "user-settings.toml").read_text(), "preserve")
        self.assertFalse((bin_dir / "lince-msg").exists())
