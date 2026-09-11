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

    def test_minimal_replaces_both_standard_bars(self):
        for name in ("dashboard", "dashboard-vox", "dashboard-tiled", "dashboard-tiled-vox", "dashboard-statusline"):
            text = (ROOT / "layouts" / f"{name}.kdl").read_text()
            result = launcher["presentation_layout"](text, "minimal", True, True)
            self.assertNotIn('location="zellij:tab-bar"', result)
            self.assertNotIn('location="zellij:status-bar"', result)
            self.assertEqual(result.count('role "statusline"'), 1)
            self.assertEqual(result.count('config_path "'), 1)

    def test_classic_retains_standard_bars(self):
        text = (ROOT / "layouts/dashboard-tiled.kdl").read_text()
        result = launcher["presentation_layout"](text, "classic", False, True)
        self.assertIn('location="zellij:tab-bar"', result)
        self.assertIn('location="zellij:status-bar"', result)
        self.assertIn('compact "false"', result)

    def test_install_update_preserve_user_session_config(self):
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            global_config = home / ".config/zellij/config.kdl"
            global_config.parent.mkdir(parents=True)
            global_config.write_text('// personal global config\n')
            env = {**os.environ, "HOME": directory}
            subprocess.run(["bash", str(ROOT / "install-ui.sh")], env=env, check=True)
            active = home / ".config/lince-dashboard/zellij.kdl"
            active.write_text('// personal LINCE config\n')
            subprocess.run(["bash", str(ROOT / "install-ui.sh")], env=env, check=True)
            self.assertEqual(active.read_text(), '// personal LINCE config\n')
            self.assertEqual(global_config.read_text(), '// personal global config\n')
            self.assertTrue(active.with_suffix('.kdl.dist').exists())
            self.assertTrue((home / ".local/bin/lince-dashboard-launch").stat().st_mode & 0o111)
            self.assertEqual({p.name for p in (home / ".config/zellij/layouts").glob('*.kdl')},
                             {p.name for p in (ROOT / 'layouts').glob('*.kdl')})
