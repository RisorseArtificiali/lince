import fcntl
import os
import runpy
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "hooks/lince-codex-startup"))
SCREEN = """╭──────────────────────────────────────────────────╮
│ >_ OpenAI Codex (v0.155.1)                         │
│ model:     gpt-6-astra medium   /model to change   │
│ directory: ~/project/lince                        │
╰──────────────────────────────────────────────────╯

› Ask Codex to do anything

  gpt-6-astra medium · ~/project/lince
"""


class CodexStartup(unittest.TestCase):
    def test_only_complete_empty_composer_is_ready(self):
        detect = MODULE["prompt_ready"]
        self.assertTrue(detect(SCREEN))
        self.assertTrue(detect(SCREEN.replace("gpt-6-astra medium · ~/project/lince", "? for shortcuts")))
        self.assertTrue(detect(SCREEN.replace("gpt-6-astra medium · ~/project/lince", "gpt-6-astra medium")))
        self.assertTrue(detect(SCREEN.replace(
            "gpt-6-astra medium · ~/project/lince",
            "main · 100% context left",
        )))
        self.assertTrue(detect(SCREEN.replace(
            "gpt-6-astra medium · ~/project/lince",
            "gpt-6-astra medium ·\n  ~/project/lince",
        )))
        self.assertTrue(detect(SCREEN.replace("  gpt-6-astra medium · ~/project/lince\n", "")))
        for screen in ["Loading Codex", "Sign in to continue", "Trust this folder?",
                       SCREEN.replace("› Ask Codex to do anything", "› my question"),
                       SCREEN + "Select a model\n",
                       SCREEN.replace("model:     gpt-6-astra medium", "model:     loading"),
                       "• Starting MCP servers (1/2)\n" + SCREEN,
                       "• Booting MCP server: serena\n" + SCREEN,
                       "• Working (esc to interrupt)\n" + SCREEN,
                       SCREEN.replace("Ask Codex to do anything", "Ask Codex to do")]:
            self.assertFalse(detect(screen), screen)

    def test_native_hook_waits_for_startup_lock_before_writing(self):
        hook = Path(__file__).resolve().parents[1] / "hooks/codex-status-hook.sh"
        with tempfile.TemporaryDirectory() as directory:
            status_dir = Path(directory)
            status = status_dir / "codex-1.state"
            lock = status_dir / "codex-1.startup-flock"
            status.write_text(MODULE["STARTING"])
            lock_handle = lock.open("a")
            fcntl.flock(lock_handle, fcntl.LOCK_EX)
            env = os.environ | {
                "LINCE_AGENT_ID": "codex-1",
                "LINCE_STATUS_DIR": directory,
                "ZELLIJ": "",
            }
            process = subprocess.Popen(
                ["bash", str(hook)],
                env=env,
                stdin=subprocess.PIPE,
                text=True,
            )
            process.stdin.write('{"hook_event_name":"UserPromptSubmit"}')
            process.stdin.close()
            time.sleep(0.8)
            self.assertIsNone(process.poll())
            self.assertEqual(status.read_text(), MODULE["STARTING"])
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
            lock_handle.close()
            self.assertEqual(process.wait(timeout=2), 0)
            self.assertEqual(status.read_text().strip(), "UserPromptSubmit")


    def test_native_hook_wins_race_with_screen_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "codex-1.state"
            child = Mock()
            child.poll.return_value = None
            stop = Mock()
            stop.wait.side_effect = [False, True]
            status.write_text(MODULE["STARTING"])

            def dump(*args, **kwargs):
                status.write_text("UserPromptSubmit")
                return subprocess.CompletedProcess(args, 0, SCREEN)

            with patch("subprocess.run", side_effect=dump):
                MODULE["observe"](child, status, "session", "1", stop)
            self.assertEqual(status.read_text(), "UserPromptSubmit")

    def test_startup_publishes_ready_once_and_leaves_native_hooks_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "codex-1.state"
            child = Mock()
            child.poll.return_value = None
            stop = Mock()
            stop.wait.return_value = False
            status.write_text(MODULE["STARTING"])
            with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, SCREEN)) as dump:
                MODULE["observe"](child, status, "session", "1", stop)
                self.assertEqual(status.read_text().strip(), MODULE["READY"])
                dump.assert_called_once()
                status.write_text("PreToolUse")
                MODULE["observe"](child, status, "session", "1", stop)
                dump.assert_called_once()
                self.assertEqual(status.read_text(), "PreToolUse")

    def test_startup_observer_uses_namespace_independent_file_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "codex-1.state"
            lock = status.with_suffix(".startup-flock")
            status.write_text(MODULE["STARTING"])
            lock_handle = lock.open("a")
            fcntl.flock(lock_handle, fcntl.LOCK_EX)
            child = Mock()
            child.poll.return_value = None
            stop = Mock()
            stop.wait.return_value = False

            with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, SCREEN)):
                observer = subprocess.Popen([
                    "python3", str(Path(__file__).resolve().parents[1] / "hooks/lince-codex-startup"),
                    "--write-state", str(status), MODULE["READY"],
                ])
                time.sleep(0.2)
                self.assertIsNone(observer.poll())
                self.assertEqual(status.read_text().strip(), MODULE["STARTING"])
                fcntl.flock(lock_handle, fcntl.LOCK_UN)
                lock_handle.close()
                self.assertEqual(observer.wait(timeout=2), 0)

            self.assertEqual(status.read_text().strip(), MODULE["READY"])

    def test_native_hook_does_not_mutate_legacy_lock_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            status_dir = Path(directory)
            status = status_dir / "codex-1.state"
            lock = status_dir / "codex-1.startup-lock"
            status.write_text(MODULE["STARTING"])
            lock.mkdir()
            hook = Path(__file__).resolve().parents[1] / "hooks/codex-status-hook.sh"
            result = subprocess.run(
                ["bash", str(hook), '{"hook_event_name":"UserPromptSubmit"}'],
                env=os.environ | {
                    "LINCE_AGENT_ID": "codex-1",
                    "LINCE_STATUS_DIR": directory,
                    "ZELLIJ": "",
                },
                timeout=2,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(status.read_text().strip(), "UserPromptSubmit")
            self.assertEqual(list(lock.iterdir()), [])

    def test_native_hook_rejects_agent_id_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status_dir = root / "status"
            status_dir.mkdir()
            outside = root / "victim.state"
            outside.write_text("unchanged\n")
            hook = Path(__file__).resolve().parents[1] / "hooks/codex-status-hook.sh"
            result = subprocess.run(
                ["bash", str(hook), '{"hook_event_name":"Stop"}'],
                env=os.environ | {
                    "LINCE_AGENT_ID": "../victim",
                    "LINCE_STATUS_DIR": str(status_dir),
                    "ZELLIJ": "",
                },
                timeout=2,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(outside.read_text(), "unchanged\n")
