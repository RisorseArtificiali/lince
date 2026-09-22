#!/usr/bin/env python3
"""Unit tests for scripts/config_merge.py (stdlib unittest, no pytest).

Run with:
    python3 scripts/tests/test_config_merge.py
"""

import contextlib
import io
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config_merge  # noqa: E402
import tomlkit  # noqa: E402

DEFAULTS = """\
# Shipped defaults
[dashboard]
max_agents = 6
focus_mode = "auto"
new_key = "fresh"

[dashboard.colors]
default = "white"

[providers]
anthropic = "ANTHROPIC_API_KEY"
"""

USER = """\
# My customized config
[dashboard]
max_agents = 12        # I want more agents
focus_mode = "auto"

[dashboard.colors]
default = "white"

[providers]
anthropic = "ANTHROPIC_API_KEY"

# A custom agent of mine
[agents.myagent]
display_name = "Mine"
"""


class ConfigMergeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.user_file = self.tmp / "config.toml"
        self.defaults_file = self.tmp / "defaults.toml"
        self.defaults_file.write_text(DEFAULTS, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def run_merge(self, *extra_args):
        """Run config_merge.main, returning (exit_code, stdout)."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = config_merge.main([str(self.user_file), str(self.defaults_file), *extra_args])
        return code, stdout.getvalue()

    def backups(self):
        return sorted(self.tmp.glob("config.toml.bak.*"))

    # ── Core behaviours ────────────────────────────────────────────────

    def test_missing_user_file_writes_defaults(self):
        code, out = self.run_merge()
        self.assertEqual(code, 0)
        self.assertTrue(self.user_file.exists())
        doc = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(doc["dashboard"]["max_agents"], 6)
        self.assertIn("added: dashboard", out)
        self.assertEqual(self.backups(), [], "no backup expected when user file did not exist")

    def test_empty_user_file_gains_all_defaults(self):
        self.user_file.write_text("", encoding="utf-8")
        code, out = self.run_merge()
        self.assertEqual(code, 0)
        doc = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(doc["dashboard"]["new_key"], "fresh")
        self.assertEqual(len(self.backups()), 1, "backup expected for existing (empty) file")

    def test_identical_files_no_op(self):
        self.user_file.write_text(DEFAULTS, encoding="utf-8")
        code, out = self.run_merge()
        self.assertEqual(code, 0)
        self.assertIn("no changes", out)
        self.assertEqual(self.user_file.read_text(), DEFAULTS, "file must be untouched")
        self.assertEqual(self.backups(), [], "no backup on no-op")

    def test_user_value_preserved_on_conflict(self):
        self.user_file.write_text(USER, encoding="utf-8")
        code, _ = self.run_merge()
        self.assertEqual(code, 0)
        doc = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(doc["dashboard"]["max_agents"], 12, "user value must win")

    def test_explicit_value_migration_updates_retired_dashboard_preset(self):
        self.user_file.write_text('[dashboard]\npreset = "statusline" # old name\n', encoding="utf-8")
        code, out = self.run_merge("--migrate", "dashboard.preset", "statusline", "minimal")
        self.assertEqual(code, 0)
        doc = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(doc["dashboard"]["preset"], "minimal")
        self.assertIn("migrated: dashboard.preset: statusline -> minimal", out)
        self.assertEqual(len(self.backups()), 1)
        self.assertIn("# old name", self.user_file.read_text())

    def test_new_default_key_added(self):
        self.user_file.write_text(USER, encoding="utf-8")
        code, out = self.run_merge()
        self.assertEqual(code, 0)
        doc = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(doc["dashboard"]["new_key"], "fresh")
        self.assertIn("added: dashboard.new_key", out)

    def test_nested_table_merge(self):
        self.user_file.write_text(USER, encoding="utf-8")
        nested_defaults = DEFAULTS + '\n[dashboard.layout]\nmode = "tiled"\n'
        self.defaults_file.write_text(nested_defaults, encoding="utf-8")
        code, out = self.run_merge()
        self.assertEqual(code, 0)
        doc = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(doc["dashboard"]["layout"]["mode"], "tiled")
        self.assertEqual(doc["dashboard"]["colors"]["default"], "white", "existing nested table intact")
        self.assertIn("added: dashboard.layout", out)

    def test_orphan_preserved_and_reported(self):
        self.user_file.write_text(USER, encoding="utf-8")
        code, out = self.run_merge()
        self.assertEqual(code, 0)
        doc = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(doc["agents"]["myagent"]["display_name"], "Mine")
        self.assertIn("orphan (user-only, preserved): agents", out)

    def test_comment_preservation(self):
        self.user_file.write_text(USER, encoding="utf-8")
        code, _ = self.run_merge()
        self.assertEqual(code, 0)
        text = self.user_file.read_text()
        self.assertIn("# My customized config", text)
        self.assertIn("# I want more agents", text)
        self.assertIn("# A custom agent of mine", text)

    def test_backup_created_before_write(self):
        self.user_file.write_text(USER, encoding="utf-8")
        code, out = self.run_merge()
        self.assertEqual(code, 0)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), USER, "backup must hold the pre-merge content")
        self.assertIn("backup:", out)

    def test_backup_collision_same_second_keeps_both(self):
        """Two merges within the same second must NOT clobber the first backup."""
        self.user_file.write_text(USER, encoding="utf-8")
        with unittest.mock.patch("config_merge.datetime") as mock_dt:
            mock_dt.datetime.now.return_value.strftime.return_value = "20260101-120000"
            code1, _ = self.run_merge()
            # Second run with evolved defaults so the user file changes again.
            self.defaults_file.write_text(DEFAULTS + '\n[extra]\nk = 1\n', encoding="utf-8")
            code2, _ = self.run_merge()
        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        backups = self.backups()
        self.assertEqual(len(backups), 2, "collision must produce a suffixed second backup")
        self.assertEqual(backups[0].name, "config.toml.bak.20260101-120000")
        self.assertEqual(backups[1].name, "config.toml.bak.20260101-120000-1")
        self.assertEqual(backups[0].read_text(), USER, "first backup (pre-first-merge) must survive")

    # ── Failure modes ──────────────────────────────────────────────────

    def test_malformed_user_input_no_write_exit_2(self):
        malformed = "[dashboard\nmax_agents = oops"
        self.user_file.write_text(malformed, encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code, _ = self.run_merge()
        self.assertEqual(code, 2)
        self.assertEqual(self.user_file.read_text(), malformed, "malformed file must not be touched")
        self.assertEqual(self.backups(), [])
        self.assertIn("malformed TOML", stderr.getvalue())

    def test_malformed_defaults_no_write_exit_2(self):
        self.user_file.write_text(USER, encoding="utf-8")
        self.defaults_file.write_text("not toml ][", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code, _ = self.run_merge()
        self.assertEqual(code, 2)
        self.assertEqual(self.user_file.read_text(), USER)
        self.assertIn("malformed TOML", stderr.getvalue())

    # ── Dry-run & round-trip ───────────────────────────────────────────

    def test_dry_run_no_mutation(self):
        self.user_file.write_text(USER, encoding="utf-8")
        code, out = self.run_merge("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.user_file.read_text(), USER, "dry-run must not write")
        self.assertEqual(self.backups(), [], "dry-run must not create backups")
        self.assertIn("dry-run: would write", out)
        self.assertIn("added: dashboard.new_key", out)

    def test_output_round_trips(self):
        self.user_file.write_text(USER, encoding="utf-8")
        code, _ = self.run_merge()
        self.assertEqual(code, 0)
        # Must not raise:
        reparsed = tomlkit.parse(self.user_file.read_text())
        self.assertEqual(tomlkit.parse(tomlkit.dumps(reparsed))["dashboard"]["max_agents"], 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
