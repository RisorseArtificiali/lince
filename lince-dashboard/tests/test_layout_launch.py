"""Layout generation must agree with the actual viewport on nondefault widths."""
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
launcher = runpy.run_path(str(ROOT / "lince-dashboard-launch"))


class LayoutTests(unittest.TestCase):
    def test_width_changes_only_root_columns(self):
        text = (ROOT / "layouts/dashboard-tiled.kdl").read_text()
        result = launcher["sidebar_layout"](text, 22)
        self.assertIn('pane size="22%" split_direction="horizontal"', result)
        self.assertIn('pane size="78%" name="lince-viewport"', result)
        self.assertIn('pane size="70%" focus=true', result)
        self.assertIn('pane size="30%" {', result)

    def test_invalid_width_rejected(self):
        for width in (0, 17, 61, 100):
            with self.assertRaises(ValueError):
                launcher["sidebar_layout"]("layout {}", width)
