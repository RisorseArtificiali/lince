"""Strict mount-mask policy intake, independent of the legacy config merge."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
