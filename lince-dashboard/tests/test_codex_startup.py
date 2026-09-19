import runpy
from pathlib import Path
import subprocess
import tempfile
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
        for screen in ["Loading Codex", "Sign in to continue", "Trust this folder?",
                       SCREEN.replace("› Ask Codex to do anything", "› my question"),
                       SCREEN + "Select a model\n",
                       SCREEN.replace("model:     gpt-6-astra medium", "model:     loading"),
                       "• Starting MCP servers (1/2)\n" + SCREEN,
                       "• Working (esc to interrupt)\n" + SCREEN,
                       SCREEN.replace("Ask Codex to do anything", "Ask Codex to do")]:
            self.assertFalse(detect(screen), screen)


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
