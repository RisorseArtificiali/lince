"""Exercise the shared installer prompt and the resulting launch config in isolation."""
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PresetInstallTests(unittest.TestCase):
    def select(self, answer="", preset=None):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".config/lince-dashboard/config.toml"
            config.parent.mkdir(parents=True)
            env = {**os.environ, "HOME": directory}
            env.pop("LINCE_DASHBOARD_PRESET", None)
            if preset is not None:
                env["LINCE_DASHBOARD_PRESET"] = preset
            result = subprocess.run([
                "bash", "-ec", 'source "$1"; select_dashboard_preset; '
                'write_dashboard_preset_config "$2" "$3"', "bash",
                str(ROOT / "scripts/dashboard-preset.sh"),
                str(ROOT / "lince-dashboard/config.toml"), str(config),
            ], input=answer, env=env, text=True, capture_output=True)
            if result.returncode:
                return result, None, ""
            value = tomllib.loads(config.read_text())["dashboard"]["preset"]
            launched = subprocess.run([str(ROOT / "lince-dashboard/lince-dashboard-launch"),
                                       "--print-layout"], env=env, text=True, capture_output=True, check=True)
            return result, value, launched.stdout

    def test_enter_and_eof_default_to_minimal(self):
        for answer in ("\n", ""):
            result, preset, layout = self.select(answer)
            self.assertEqual(preset, "minimal")
            self.assertIn('sidebar_visible "true"', layout)
            self.assertIn("https://lince.sh/documentation/#/dashboard/views-and-themes", result.stdout)

    def test_choices_are_saved_and_used_by_launcher(self):
        for answer, expected in (("2\n", "statusline"), ("classic\n", "classic")):
            _, preset, layout = self.select(answer)
            self.assertEqual(preset, expected)
            self.assertIn('sidebar_visible "false"' if expected == "statusline"
                          else 'presentation "classic"', layout)

    def test_invalid_answer_reprompts(self):
        result, preset, _ = self.select("wrong\n3\n")
        self.assertEqual(preset, "classic")
        self.assertIn("Choose 1, 2 or 3", result.stdout)

    def test_forwarded_choice_skips_prompt_and_rejects_invalid_value(self):
        for expected in ("minimal", "statusline", "classic"):
            result, preset, _ = self.select(preset=expected)
            self.assertEqual(preset, expected)
            self.assertNotIn("Choose your dashboard preset", result.stdout)
        result, preset, _ = self.select(preset="wrong")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(preset)
