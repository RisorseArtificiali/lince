"""Strict mount-mask policy intake, independent of the legacy config merge."""

import io
import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts.tests.test_sandbox_broker_bind import MIN_CONFIG, MIN_AGENT_CONFIG

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sandbox"))

import mount_masking as mask  # noqa: E402


class TestMountMaskIntake(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.invocation = self.root / "invocation"
        self.project = self.root / "project"
        self.invocation.mkdir()
        self.project.mkdir()
        home_patch = patch.object(mask.Path, "home", return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def legacy(self, text='[sandbox]\nmask_mount_points = ["/mount/old"]\n'):
        return self.write(self.home / ".agent-sandbox/config.toml", text)

    def v2(self, text='version = "2.0"\n[filesystem]\nmask_mount_points = ["/mount/new"]\n'):
        return self.write(self.home / ".config/lince/lince.toml", text)

    def test_global_source_switch(self):
        for scenario, v2_text, expected in (
            ("legacy alone", None, (Path("/mount/old"),)),
            ("v2 nonempty", 'version = "2.0"\n[filesystem]\nmask_mount_points = ["/mount/new"]\n',
             (Path("/mount/new"),)),
            ("v2 empty", 'version = "2.0"\n[filesystem]\nmask_mount_points = []\n', ()),
            ("v2 key absent", 'version = "2.0"\n[filesystem]\n', ()),
        ):
            with self.subTest(scenario=scenario):
                self.legacy()
                if v2_text is not None:
                    self.v2(v2_text)
                try:
                    self.assertEqual(mask.load_mount_mask_points(self.invocation, self.project), expected)
                finally:
                    (self.home / ".config/lince/lince.toml").unlink(missing_ok=True)

    def test_no_global_policy(self):
        self.assertEqual(mask.load_mount_mask_points(self.invocation, self.project), ())

    def test_dangling_global_v2_symlink_blocks_legacy_fallback(self):
        self.legacy()
        path = self.home / ".config/lince/lince.toml"
        path.parent.mkdir(parents=True)
        path.symlink_to(self.root / "missing-v2.toml")
        with self.assertRaises(mask.MountMaskError) as raised:
            mask.load_mount_mask_points(self.invocation, self.project)
        self.assertIn(str(path), str(raised.exception))
        self.assertIn("[filesystem].mask_mount_points", str(raised.exception))

    def test_dangling_global_legacy_symlink_is_invalid(self):
        path = self.home / ".agent-sandbox/config.toml"
        path.parent.mkdir(parents=True)
        path.symlink_to(self.root / "missing-legacy.toml")
        with self.assertRaises(mask.MountMaskError) as raised:
            mask.load_mount_mask_points(self.invocation, self.project)
        self.assertIn(str(path), str(raised.exception))
        self.assertIn("[sandbox].mask_mount_points", str(raised.exception))

    def test_dangling_local_symlinks_are_invalid_before_global_selection(self):
        self.legacy()
        for root, label in ((self.invocation, "invocation"), (self.project, "project")):
            for relative, key in ((".lince/lince.toml", "[filesystem].mask_mount_points"),
                                  (".agent-sandbox/config.toml", "[sandbox].mask_mount_points")):
                with self.subTest(root=label, format=relative):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.symlink_to(self.root / "missing-local.toml")
                    try:
                        with self.assertRaises(mask.MountMaskError) as raised:
                            mask.load_mount_mask_points(self.invocation, self.project)
                        self.assertIn(str(path), str(raised.exception))
                        self.assertIn(key, str(raised.exception))
                    finally:
                        path.unlink()

    def test_invalid_selected_v2_never_falls_back(self):
        cases = (
            ("malformed", 'version = "2.0"\n[filesystem]\nmask_mount_points = [', "mask_mount_points"),
            ("missing version", '[filesystem]\nmask_mount_points = []\n', "version"),
            ("newer minor", 'version = "2.1"\n[filesystem]\nmask_mount_points = []\n', "newer lince"),
            ("different major", 'version = "1.0"\n[filesystem]\nmask_mount_points = []\n', "version"),
            ("malformed version", 'version = "2"\n[filesystem]\nmask_mount_points = []\n', "version"),
            ("malformed minor", 'version = "2.-1"\n[filesystem]\nmask_mount_points = []\n', "version"),
            ("bad list type", 'version = "2.0"\n[filesystem]\nmask_mount_points = "bad"\n',
             "mask_mount_points"),
            ("bad list item", 'version = "2.0"\n[filesystem]\nmask_mount_points = [1]\n',
             "mask_mount_points"),
        )
        self.legacy()
        for scenario, text, hint in cases:
            with self.subTest(scenario=scenario):
                path = self.v2(text)
                with self.assertRaises(mask.MountMaskError) as raised:
                    mask.load_mount_mask_points(self.invocation, self.project)
                self.assertIn(str(path), str(raised.exception))
                self.assertIn("[filesystem].mask_mount_points", str(raised.exception))
                self.assertIn(hint, str(raised.exception))
                if scenario == "newer minor":
                    self.assertIn("lince update", str(raised.exception))

    def test_invalid_legacy_value(self):
        for text in ('[sandbox]\nmask_mount_points = "bad"\n',
                     '[sandbox]\nmask_mount_points = [false]\n',
                     '[sandbox]\nmask_mount_points = [\n'):
            with self.subTest(text=text):
                path = self.legacy(text)
                with self.assertRaises(mask.MountMaskError) as raised:
                    mask.load_mount_mask_points(self.invocation, self.project)
                self.assertIn(str(path), str(raised.exception))
                self.assertIn("[sandbox].mask_mount_points", str(raised.exception))

    def test_local_key_rejected_in_each_format_and_each_command_root(self):
        self.legacy()
        self.v2()
        for command, invocation, project, root, label in (
            ("run cwd", self.invocation, self.project, self.invocation, "invocation"),
            ("run -p", self.invocation, self.project, self.project, "project"),
            ("learn cwd", self.invocation, self.invocation, self.invocation, "invocation"),
        ):
            for relative, section in ((".lince/lince.toml", "filesystem"),
                                      (".agent-sandbox/config.toml", "sandbox")):
                for value in ("[]", '["/mount/local"]'):
                    with self.subTest(command=command, format=section, value=value):
                        path = self.write(root / relative, f"[{section}]\nmask_mount_points = {value}\n")
                        try:
                            with self.assertRaises(mask.MountMaskError) as raised:
                                mask.load_mount_mask_points(invocation, project)
                            self.assertIn(label, str(raised.exception))
                            self.assertIn(str(path), str(raised.exception))
                            self.assertIn(f"[{section}].mask_mount_points", str(raised.exception))
                        finally:
                            path.unlink()

    def test_non_selected_local_format_is_still_rejected(self):
        for global_format, local_format, section in (
            ("v2", ".agent-sandbox/config.toml", "sandbox"),
            ("legacy", ".lince/lince.toml", "filesystem"),
        ):
            with self.subTest(global_format=global_format):
                if global_format == "v2":
                    self.v2()
                else:
                    (self.home / ".config/lince/lince.toml").unlink(missing_ok=True)
                    self.legacy()
                path = self.write(self.project / local_format, f"[{section}]\nmask_mount_points = []\n")
                try:
                    with self.assertRaises(mask.MountMaskError):
                        mask.load_mount_mask_points(self.invocation, self.project)
                finally:
                    path.unlink()

    def test_malformed_local_is_fatal_even_when_other_local_has_key(self):
        self.v2()
        self.write(self.project / ".lince/lince.toml", "[")
        path = self.write(self.project / ".agent-sandbox/config.toml", "[sandbox]\nmask_mount_points = []\n")
        with self.assertRaises(mask.MountMaskError) as raised:
            mask.load_mount_mask_points(self.invocation, self.project)
        self.assertIn("mask_mount_points", str(raised.exception))
        self.assertTrue(str(path) in str(raised.exception) or "lince.toml" in str(raised.exception))


class TestMountMaskValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.point = self.root / "mounted"
        self.point.mkdir()

    def mountinfo(self, *points):
        def escape(path):
            return str(path).replace("\\", r"\134").replace(" ", r"\040").replace("\t", r"\011")

        data = "".join(f"36 25 0:31 / {escape(point)} rw - tmpfs tmpfs rw\n" for point in points)
        return patch.object(mask.Path, "read_text", return_value=data)

    def test_empty_list_does_not_inspect_mounts_or_warn(self):
        output = io.StringIO()
        with patch.object(mask.Path, "read_text", side_effect=AssertionError("mountinfo read")):
            with redirect_stderr(output):
                self.assertEqual(mask.validate_mount_mask_points(()), ())
        self.assertEqual(output.getvalue(), "")

    def test_invalid_spellings(self):
        for value in (Path("relative"), Path("~/mounted"), self.root / "../mounted"):
            with self.subTest(value=value):
                with self.assertRaises(mask.MountMaskError):
                    mask.validate_mount_mask_points((value,))

    def test_final_and_intermediate_symlinks_are_rejected(self):
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        (real / "child").mkdir()
        for point in (alias, alias / "child"):
            with self.subTest(point=point):
                with self.assertRaisesRegex(mask.MountMaskError, "symlink"):
                    mask.validate_mount_mask_points((point,))

    def test_file_and_missing_directory_are_rejected(self):
        ordinary_file = self.root / "file"
        ordinary_file.write_text("data", encoding="utf-8")
        with self.assertRaisesRegex(mask.MountMaskError, "not a directory"):
            mask.validate_mount_mask_points((ordinary_file,))
        with self.assertRaisesRegex(mask.MountMaskError, "does not exist"):
            mask.validate_mount_mask_points((self.root / "missing",))

    def test_exact_essential_paths_but_not_run_descendant(self):
        for point in (Path("/"), Path("/proc"), Path("/dev"), Path("/run")):
            with self.subTest(point=point):
                with self.assertRaises(mask.MountMaskError):
                    mask.validate_mount_mask_points((point,))
        run = self.root / "run"
        child = run / "user"
        child.mkdir(parents=True)
        with patch.object(mask, "_ESSENTIAL_MOUNT_POINTS", frozenset({run})):
            with self.mountinfo(child):
                self.assertEqual(mask.validate_mount_mask_points((child,)), (child,))

    def test_exact_mountpoint_warns_for_existing_unmounted_point(self):
        unmounted = self.point / "unmounted"
        unmounted.mkdir()
        output = io.StringIO()
        with self.mountinfo(self.point):
            with redirect_stderr(output):
                self.assertEqual(mask.validate_mount_mask_points((self.point, unmounted)),
                                 (self.point, unmounted))
        warning = output.getvalue()
        self.assertEqual(warning.count("path is not mounted at launch; masking the path anyway"), 1)
        self.assertIn(str(unmounted), warning)
        self.assertNotIn("volume absent", warning)

    def test_decodes_escaped_mountpoint_in_mountinfo(self):
        for name in ("space dir", "tab\tdir", "back\\slash"):
            with self.subTest(name=name):
                point = self.root / name
                point.mkdir()
                output = io.StringIO()
                with self.mountinfo(point):
                    with redirect_stderr(output):
                        self.assertEqual(mask.validate_mount_mask_points((point,)), (point,))
                self.assertEqual(output.getvalue(), "")

    def test_validation_never_resolves_symlinks(self):
        with patch.object(mask.Path, "resolve", side_effect=AssertionError("resolve called")):
            with self.mountinfo(self.point):
                self.assertEqual(mask.validate_mount_mask_points((self.point,)), (self.point,))

    def test_duplicate_paths_rejected_after_lexical_normalization(self):
        with self.assertRaisesRegex(mask.MountMaskError, "duplicate"):
            mask.validate_mount_mask_points((self.point, Path(str(self.point) + "/./")))

    def test_nested_points_are_ancestor_first_in_either_input_order(self):
        child = self.point / "child"
        child.mkdir()
        with self.mountinfo(self.point, child):
            for paths in ((self.point, child), (child, self.point)):
                with self.subTest(paths=paths):
                    self.assertEqual(mask.validate_mount_mask_points(paths), (self.point, child))

    def test_unavailable_mountinfo_is_an_explicit_error(self):
        with patch.object(mask.Path, "read_text", side_effect=OSError("permission denied")):
            with self.assertRaisesRegex(mask.MountMaskError, "mountinfo.*permission denied"):
                mask.validate_mount_mask_points((self.point,))


def load_sandbox():
    path = Path(__file__).resolve().parents[2] / "sandbox/agent-sandbox"
    loader = importlib.machinery.SourceFileLoader("sandbox_mask_test", str(path))
    spec = importlib.util.spec_from_loader("sandbox_mask_test", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class TestMountMaskPlanning(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.point = self.root / "volume"
        self.project = self.point / "parent/deep/project"
        self.project.mkdir(parents=True)
        self.sandbox = load_sandbox()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.sandbox.SANDBOX_DIR = self.runtime

    def build(self, **kwargs):
        return self.sandbox.build_bwrap_cmd(MIN_CONFIG, self.project, [], agent_config=MIN_AGENT_CONFIG, **kwargs)

    def test_ordered_mask_deep_project_and_writable_outside(self):
        argv = self.build(mask_mount_points=(self.point,))
        root = argv.index("--ro-bind")
        mask_at = next(
            i for i in range(root + 1, len(argv) - 1) if argv[i:i + 2] == ["--tmpfs", str(self.point)])
        bind_at = next(i for i in range(mask_at + 1, len(argv) - 2)
                       if argv[i:i + 3] == ["--bind", str(self.project), str(self.project)])
        self.assertEqual(argv[root:root + 3], ["--ro-bind", "/", "/"])
        self.assertLess(root, mask_at)
        self.assertEqual(argv[mask_at:bind_at + 3], [
            "--tmpfs", str(self.point),
            "--dir", str(self.point / "parent"),
            "--dir", str(self.point / "parent/deep"),
            "--dir", str(self.project),
            "--bind", str(self.project), str(self.project),
        ])
        outside = self.point / "other"
        outside.mkdir()
        # Earlier config/CLI writable binds are hidden by the later tmpfs.
        self.build(mask_mount_points=(self.point,), extra_rw_cli=[str(outside)])

    def test_nested_masks_and_project_wide_mask(self):
        nested = self.point / "parent"
        self.assertEqual(mask.mask_mount_args((self.point, nested), self.project), [
            "--tmpfs", str(self.point), "--dir", str(nested), "--tmpfs", str(nested),
            "--dir", str(nested / "deep"), "--dir", str(self.project),
            "--bind", str(self.project), str(self.project),
        ])
        argv = self.build(mask_mount_points=(self.project,))
        at = next(
            i for i in range(len(argv) - 1) if argv[i:i + 2] == ["--tmpfs", str(self.project)])
        self.assertEqual(argv[at:at + 5], ["--tmpfs", str(self.project),
                                               "--bind", str(self.project), str(self.project)])

    def test_project_child_mask_survives_project_bind(self):
        child = self.project / "private"
        child.mkdir()
        argv = self.build(mask_mount_points=(child,))
        project_at = next(i for i in range(len(argv) - 2)
                          if argv[i:i + 3] == ["--bind", str(self.project), str(self.project)])
        self.assertIn(["--tmpfs", str(child)], [argv[i:i + 2] for i in range(project_at + 1, len(argv) - 1)])

    def test_nested_project_children_recreate_directory_after_parent_tmpfs(self):
        child = self.project / "private"
        nested = child / "deeper"
        nested.mkdir(parents=True)
        argv = self.build(mask_mount_points=(child, nested))
        self.assertIn(["--tmpfs", str(child), "--dir", str(nested), "--tmpfs", str(nested)],
                      [argv[i:i + 6] for i in range(len(argv) - 5)])

    def test_experimental_raw_mount_is_an_explicit_override(self):
        sibling = self.point / "hidden"
        sibling.mkdir()
        argv = self.build(mask_mount_points=(self.point,),
                          raw_bwrap_args=["--bind", str(sibling), str(sibling)])
        self.assertIn(["--bind", str(sibling), str(sibling)],
                      [argv[i:i + 3] for i in range(len(argv) - 2)])

    def test_later_sibling_or_ancestor_bind_rejected_even_after_messaging(self):
        sibling = self.point / "hidden"
        sibling.mkdir()
        with patch.object(self.sandbox, "messaging_bwrap_args",
                          return_value=["--bind", str(sibling), str(sibling)]):
            with self.assertRaisesRegex(mask.MountMaskError, "hidden"):
                self.build(mask_mount_points=(self.point,))
        with patch.object(self.sandbox, "messaging_bwrap_args",
                          return_value=["--ro-bind", str(self.point), str(self.point)]):
            with self.assertRaisesRegex(mask.MountMaskError, "volume"):
                self.build(mask_mount_points=(self.point,))

    def test_later_bind_through_symlinked_source_is_rejected(self):
        sibling = self.point / "hidden"
        sibling.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(self.point, target_is_directory=True)
        with patch.object(self.sandbox, "messaging_bwrap_args",
                          return_value=["--bind", str(alias / "hidden"), str(self.root / "exposed")]):
            with self.assertRaisesRegex(mask.MountMaskError, "hidden"):
                self.build(mask_mount_points=(self.point,))

    def test_generated_claude_bind_of_masked_ancestor_exposes_child_alias(self):
        config_dir = self.runtime / "claude-config"
        hidden = config_dir / "private"
        hidden.mkdir(parents=True)
        config = {**MIN_CONFIG, "claude": {"config_dir": str(config_dir)}}
        with self.assertRaisesRegex(mask.MountMaskError, r"private.*\.claude/private"):
            self.sandbox.build_bwrap_cmd(config, self.project, [], agent_config=MIN_AGENT_CONFIG,
                                         mask_mount_points=(hidden,))

    def test_late_ancestor_alias_requires_final_overlay_of_mapped_child(self):
        alias = self.root / "alternate"
        hidden_alias = alias / self.point.relative_to(self.root)
        bind = ["--bind", str(self.root), str(alias)]
        with patch.object(self.sandbox, "messaging_bwrap_args", return_value=bind):
            with self.assertRaisesRegex(mask.MountMaskError, "alternate"):
                self.build(mask_mount_points=(self.point,))
        with patch.object(self.sandbox, "messaging_bwrap_args",
                          return_value=bind + ["--tmpfs", str(hidden_alias)]):
            self.build(mask_mount_points=(self.point,))
        safe = self.root / "safe"
        safe.mkdir()
        with patch.object(self.sandbox, "messaging_bwrap_args",
                          return_value=bind + ["--ro-bind", str(safe), str(hidden_alias)]):
            self.build(mask_mount_points=(self.point,))
        with patch.object(self.sandbox, "messaging_bwrap_args",
                          return_value=bind + ["--tmpfs", str(hidden_alias)] + bind):
            with self.assertRaisesRegex(mask.MountMaskError, "alternate"):
                self.build(mask_mount_points=(self.point,))

    def test_mask_cannot_hide_required_status_runtime_bind(self):
        with self.assertRaisesRegex(mask.MountMaskError, "lince-dashboard"):
            self.build(mask_mount_points=(Path("/tmp"),))

    def test_no_list_unchanged_argv_with_late_options(self):
        old = self.build(landlock={"connect_ports": [], "bind_ports": []})
        self.assertEqual(old, self.build(mask_mount_points=(), landlock={"connect_ports": [], "bind_ports": []}))

    def test_run_empty_list_keeps_backend_selection_and_checks_local_policy(self):
        args = type("Args", (), {"project": str(self.project), "agent": "claude", "backend": None,
                                 "sandbox_level": None})()
        with patch.object(self.sandbox, "load_config", return_value=(MIN_CONFIG, self.root)), \
             patch.object(self.sandbox, "load_mount_mask_points", return_value=()) as load, \
             patch.object(self.sandbox, "validate_mount_mask_points", return_value=()) as validate, \
             patch.object(self.sandbox, "resolve_backend", side_effect=RuntimeError("backend selected")) as choose:
            with self.assertRaisesRegex(RuntimeError, "backend selected"):
                self.sandbox.cmd_run(args, [])
        load.assert_called_once_with(Path.cwd(), self.project)
        validate.assert_called_once_with(())
        choose.assert_called_once()

    def test_run_bad_local_policy_fails_before_backend_selection(self):
        args = type("Args", (), {"project": str(self.project), "agent": "claude", "backend": None,
                                 "sandbox_level": None})()
        with patch.object(self.sandbox, "load_config", return_value=(MIN_CONFIG, self.root)), \
             patch.object(self.sandbox, "load_mount_mask_points",
                          side_effect=mask.MountMaskError("local global-only")), \
             patch.object(self.sandbox, "resolve_backend", side_effect=AssertionError("backend selected")):
            with redirect_stderr(io.StringIO()) as output, self.assertRaises(SystemExit):
                self.sandbox.cmd_run(args, [])
        self.assertIn("local global-only", output.getvalue())

    def test_run_preflight_rejects_nono_and_seatbelt_before_helpers(self):
        args = type("Args", (), {"project": str(self.project), "agent": "claude", "backend": None,
                                 "sandbox_level": None})()
        for backend in ("nono", "seatbelt"):
            with self.subTest(backend=backend):
                with patch.object(self.sandbox, "load_config", return_value=(MIN_CONFIG, self.root)), \
                     patch.object(self.sandbox, "resolve_backend", return_value=backend), \
                     patch.object(self.sandbox, "load_mount_mask_points", return_value=(self.point,)), \
                     patch.object(self.sandbox, "validate_mount_mask_points",
                                  return_value=(self.point,)) as validate, \
                     patch.object(self.sandbox, "ensure_git_wrapper", side_effect=AssertionError("helper started")), \
                     patch.object(self.sandbox.subprocess, "Popen", side_effect=AssertionError("agent started")):
                    with self.assertRaisesRegex(SystemExit, "1"):
                        with redirect_stderr(io.StringIO()) as output:
                            self.sandbox.cmd_run(args, [])
                    self.assertIn("mask_mount_points", output.getvalue())
                    validate.assert_called_once_with((self.point,))


if __name__ == "__main__":
    unittest.main()
