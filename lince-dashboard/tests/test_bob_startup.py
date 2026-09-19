import runpy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "hooks/lince-bob-startup"))
SCREEN = "Bob Shell\n" + "─" * 80 + "\n❯   Build Anything, @ for context, / for commands, $ for skills\n" + "─" * 80 + "\nAgent Mode (auto-approve)\n"


class BobStartup(unittest.TestCase):
    def test_only_complete_empty_composer_is_ready(self):
        detect = MODULE["prompt_ready"]
        self.assertTrue(detect(SCREEN))
        for screen in ["Loading Bob", "Sign in to continue", "Select a team", "Trust this folder?",
                       SCREEN.replace("❯   Build Anything", "❯ my question"),
                       SCREEN + "Select a team\n", "✖ Authentication failed\n" + SCREEN,
                       "Processing… (Enter to steer, Tab to queue)\n" + SCREEN,
                       SCREEN.replace("Agent Mode (auto-approve)", "Shell Mode"),
                       SCREEN.replace("─" * 80, ""), SCREEN.replace("for commands, $ for skills", "for comm")]:
            self.assertFalse(detect(screen), screen)

    def test_native_hook_wins_race_with_screen_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "bob-1.state"
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
            status = Path(directory) / "bob-1.state"
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
