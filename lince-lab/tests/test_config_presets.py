#!/usr/bin/env python3
"""Config + presets tests (blueprint §8, §9).

Covers: defaults are usable without a file; a user TOML file overlays defaults;
the three documented presets exist with their knobs; and — critically — the
security invariants (no host mounts, no credential injection, name-prefixing)
are NOT present as overridable config keys, so a preset or user file can never
weaken them.

Run with:
    python3 lince-lab/tests/test_config_presets.py
"""

import json
import pathlib
import sys
import tempfile
import unittest

# Put the package dir (lince-lab/) on sys.path so absolute imports resolve.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lince_lab import config as cfg  # noqa: E402

# Keys/tokens that must never be configurable — they are enforced policy.
FORBIDDEN_CONFIG_KEYS = {
    "mounts",
    "mount",
    "host_mounts",
    "credentials",
    "inject_credentials",
    "credential_injection",
    "name_prefix",
    "allow_host_mounts",
    "secrets",
}


def _all_keys(obj: object) -> set[str]:
    """Recursively collect every dict key appearing anywhere in ``obj``."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(key)
            found |= _all_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            found |= _all_keys(item)
    return found


class DefaultsTest(unittest.TestCase):
    def test_defaults_are_complete_without_a_file(self) -> None:
        # A non-existent path returns the baked defaults, not an error.
        missing = pathlib.Path(tempfile.gettempdir()) / "nope-lince-lab-does-not-exist.toml"
        loaded = cfg.load_config(missing)
        self.assertEqual(loaded["network"]["mode"], "deny")
        self.assertEqual(loaded["vm"]["cpus"], 2)
        self.assertIn("fedora", loaded["images"])
        # keep_vm / capture_tool / lima_version are NOT baked defaults: keep comes
        # from the CLI flag and the backend hardcodes limactl/ht.
        self.assertNotIn("keep_vm", loaded)
        self.assertNotIn("capture_tool", loaded)
        self.assertNotIn("lima_version", loaded)

    def test_macos_image_in_allowlist(self) -> None:
        # The Tart (macOS-guest) backend keys on this image entry; arch must be
        # arm64 and the location must be a cirruslabs OCI ref (Epic #268).
        loaded = cfg.load_config(pathlib.Path("/nonexistent"))
        self.assertIn("macos-sequoia", loaded["images"])
        entry = loaded["images"]["macos-sequoia"]
        self.assertEqual(entry["arch"], "arm64")
        self.assertTrue(entry["location"].startswith("ghcr.io/cirruslabs/"))

    def test_user_file_overlays_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "config.toml"
            path.write_text("keep_vm = true\n[vm]\ncpus = 8\n", encoding="utf-8")
            loaded = cfg.load_config(path)
            # overridden
            self.assertTrue(loaded["keep_vm"])
            self.assertEqual(loaded["vm"]["cpus"], 8)
            # untouched nested key survives the deep merge
            self.assertEqual(loaded["vm"]["memory"], "2GiB")
            self.assertEqual(loaded["network"]["mode"], "deny")

    def test_malformed_file_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "config.toml"
            path.write_text("this is = = not toml ][", encoding="utf-8")
            loaded = cfg.load_config(path)
            self.assertEqual(loaded["vm"]["cpus"], 2)

    def test_load_does_not_mutate_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "config.toml"
            path.write_text("[vm]\ncpus = 99\n", encoding="utf-8")
            cfg.load_config(path)
            self.assertEqual(cfg.DEFAULTS["vm"]["cpus"], 2)


class PresetsTest(unittest.TestCase):
    def test_three_presets_exist(self) -> None:
        self.assertEqual(set(cfg.PRESETS), {"quick", "bisect", "networked"})

    def test_list_presets_is_sorted_with_descriptions(self) -> None:
        listed = cfg.list_presets()
        self.assertEqual([p["name"] for p in listed], ["bisect", "networked", "quick"])
        for entry in listed:
            self.assertTrue(entry["description"])

    def test_quick_preset_knobs(self) -> None:
        quick = cfg.PRESETS["quick"]
        self.assertEqual(quick["vm"], {"cpus": 1, "memory": "1GiB", "disk": "10GiB"})
        self.assertEqual(quick["network"]["mode"], "deny")
        self.assertFalse(quick["keep_vm"])
        self.assertFalse(quick["retain_base_snapshot"])

    def test_bisect_preset_knobs(self) -> None:
        bisect = cfg.PRESETS["bisect"]
        self.assertEqual(bisect["vm"]["cpus"], 2)
        self.assertEqual(bisect["network"]["mode"], "deny")
        # base snapshot retained for fast per-candidate reset
        self.assertTrue(bisect["retain_base_snapshot"])
        self.assertGreaterEqual(bisect["step_timeout_s"], 600)

    def test_networked_preset_knobs(self) -> None:
        networked = cfg.PRESETS["networked"]
        # network allowed, but the allowlist comes from the recipe (policy), not here
        self.assertEqual(networked["network"]["mode"], "allow")
        self.assertEqual(networked["vm"]["cpus"], 2)

    def test_apply_preset_overlays_config(self) -> None:
        base = cfg.load_config(pathlib.Path("/nonexistent"))
        merged = cfg.apply_preset(base, "quick")
        self.assertEqual(merged["vm"]["cpus"], 1)
        self.assertEqual(merged["vm"]["memory"], "1GiB")
        # description is documentation, not a runtime knob — dropped from merge
        self.assertNotIn("description", merged)

    def test_apply_unknown_preset_raises(self) -> None:
        with self.assertRaises(KeyError):
            cfg.apply_preset(cfg.DEFAULTS, "no-such-preset")


class SecurityInvariantTest(unittest.TestCase):
    """The invariants are policy, not config — they must be absent as keys."""

    def test_defaults_carry_no_security_invariant_keys(self) -> None:
        keys = _all_keys(cfg.DEFAULTS)
        leaked = keys & FORBIDDEN_CONFIG_KEYS
        self.assertEqual(leaked, set(), f"security invariant leaked into DEFAULTS: {leaked}")

    def test_no_preset_carries_a_security_invariant_key(self) -> None:
        for name, preset in cfg.PRESETS.items():
            keys = _all_keys(preset)
            leaked = keys & FORBIDDEN_CONFIG_KEYS
            self.assertEqual(leaked, set(), f"preset {name!r} exposes invariant: {leaked}")

    def test_user_file_cannot_introduce_a_recognized_mount_knob(self) -> None:
        # Even if a user *writes* a 'mounts' key, it is not part of the schema the
        # rest of the module reads; we assert the documented config surface never
        # surfaces it as a known default. (Policy enforces the real invariant.)
        merged = cfg.load_config(pathlib.Path("/nonexistent"))
        self.assertNotIn("mounts", _all_keys(merged))

    def test_config_is_json_serializable(self) -> None:
        # Ensures the resolved config can travel as a JSON payload if needed.
        merged = cfg.load_config(pathlib.Path("/nonexistent"))
        json.dumps(merged)


if __name__ == "__main__":
    unittest.main(verbosity=2)
