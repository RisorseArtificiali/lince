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
        self.assertIn('pane size="30%" name="lince-sidebar-aux" {', result)

    def test_invalid_width_rejected(self):
        for width in (0, 9, 61, 100, 30.5, True):
            with self.assertRaises(ValueError):
                launcher["sidebar_layout"]("layout {}", width)

    def test_minimal_replaces_both_standard_bars(self):
        for name in ("dashboard", "dashboard-vox", "dashboard-tiled", "dashboard-tiled-vox", "dashboard-statusline"):
            text = (ROOT / "layouts" / f"{name}.kdl").read_text()
            result = launcher["presentation_layout"](text, "minimal", True, True)
            self.assertNotIn('location="zellij:tab-bar"', result)
            self.assertNotIn('location="zellij:status-bar"', result)
            # The swap inherits the one status row through default_tab_template.
            self.assertEqual(result.count('role "statusline"'), 1)
            self.assertEqual(result.count('config_path "'), 2)

    def test_classic_retains_standard_bars(self):
        text = (ROOT / "layouts/dashboard-tiled.kdl").read_text()
        result = launcher["presentation_layout"](text, "classic", False, True)
        self.assertIn('location="zellij:tab-bar"', result)
        self.assertIn('location="zellij:status-bar"', result)
        self.assertIn('compact "false"', result)

    def test_launch_defaults_overrides_and_validation(self):
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".config/lince-dashboard/config.toml"
            env = {**os.environ, "HOME": directory}

            def launch(*args):
                return subprocess.run([str(ROOT / "lince-dashboard-launch"), "--print-layout", *args],
                                      env=env, text=True, capture_output=True)

            fresh = launch()
            self.assertEqual(fresh.returncode, 0, fresh.stderr)
            self.assertIn("pane_frames false", fresh.stdout)
            self.assertIn('pane size="15%" split_direction="horizontal"', fresh.stdout)
            self.assertIn('pane size="85%" name="lince-viewport"', fresh.stdout)
            self.assertIn('role "dialog"', fresh.stdout)
            config.parent.mkdir(parents=True)
            config.write_text('[dashboard]\n')
            legacy = launch()
            self.assertIn('location="zellij:tab-bar"', legacy.stdout)
            self.assertIn("pane_frames true", legacy.stdout)
            config.write_text('[dashboard]\npreset="statusline"\ncompact=false\n')
            explicit = launch("--frames")
            self.assertIn('presentation "managed"', explicit.stdout)
            self.assertIn('sidebar_visible "false"', explicit.stdout)
            self.assertIn('compact "false"', explicit.stdout)
            self.assertIn('pane_frames true', explicit.stdout)
            self.assertIn('role "dialog"', explicit.stdout)
            for value in ('preset="typo"', 'pane_frames="false"', 'sidebar_width=9'):
                config.write_text('[dashboard]\n' + value + '\n')
                invalid = launch()
                self.assertNotEqual(invalid.returncode, 0)
                self.assertIn('lince:', invalid.stderr)

    def test_shortcut_migration_preserves_custom_bindings(self):
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory) / ".config/lince-dashboard/zellij.kdl"
            active.parent.mkdir(parents=True)
            old = ('keybinds {\n    locked {\n        bind "Ctrl l" { SwitchToMode "normal"; }\n    }\n'
                   '    shared_except "locked" {\n'
                   '        bind "Alt n" { NewPane; }\n'
                   '        bind "Alt l" { MessagePlugin { name "lince-sidebar-toggle"; }; }\n'
                   '        bind "Alt i" { Write 42; }\n    }\n}\n')
            active.write_text(old)
            env = {**os.environ, "HOME": directory}
            subprocess.run(["bash", str(ROOT / "install-ui.sh")], env=env, check=True)
            migrated = active.read_text()
            self.assertIn('payload "wizard"', migrated)
            self.assertIn('bind "Alt s" { MessagePlugin { name "lince-sidebar-toggle"; }; }', migrated)
            self.assertNotIn('bind "Alt l"', migrated)
            self.assertEqual(migrated.count('bind "Alt b" { MessagePlugin { name "lince-statusbar-toggle"; }; }'), 2)
            self.assertIn('bind "Alt q" { MessagePlugin { name "lince-save-quit"; }; }', migrated)
            self.assertIn('bind "Alt i" { Write 42; }', migrated)
            self.assertNotIn('bind "Alt n" { NewPane; }', migrated)
            self.assertEqual(active.with_suffix('.kdl.bak-shortcuts').read_text(), old)
            subprocess.run(["bash", str(ROOT / "install-ui.sh")], env=env, check=True)
            self.assertEqual(active.read_text(), migrated)
            self.assertEqual(active.with_suffix('.kdl.bak-shortcuts').read_text(), old)

    def test_install_update_preserve_user_session_config(self):
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            global_config = home / ".config/zellij/config.kdl"
            global_config.parent.mkdir(parents=True)
            global_config.write_text('// personal global config\n')
            rc = home / ".bashrc"
            rc.write_text('# LINCE aliases\nalias lince="zellij --layout dashboard-tiled"\nalias custom="echo mine"\n')
            env = {**os.environ, "HOME": directory}
            subprocess.run(["bash", str(ROOT / "install-ui.sh")], env=env, check=True)
            active = home / ".config/lince-dashboard/zellij.kdl"
            active.write_text('// personal LINCE config\n')
            subprocess.run(["bash", str(ROOT / "install-ui.sh")], env=env, check=True)
            self.assertIn('alias lince="lince-dashboard-launch"', rc.read_text())
            self.assertIn('alias custom="echo mine"', rc.read_text())
            self.assertEqual(active.read_text(), '// personal LINCE config\n')
            self.assertEqual(global_config.read_text(), '// personal global config\n')
            self.assertTrue(active.with_suffix('.kdl.dist').exists())
            self.assertTrue((home / ".local/bin/lince-dashboard-launch").stat().st_mode & 0o111)
            self.assertEqual({p.name for p in (home / ".config/zellij/layouts").glob('*.kdl')},
                             {p.name for p in (ROOT / 'layouts').glob('*.kdl')})
