#!/usr/bin/env python3
"""Diff-guard for the unified agent registry (Config v2, #204).

Design contract (docs/design/config-v2-design.md §3.3): registry.d/ was
generated once from the two legacy agents-defaults files; until those legacy
shipped files are deleted from the repo, this test fails on any divergence
between them and registry.d/ — no silent drift in either direction.

Run with:
    python3 scripts/tests/test_registry_sync.py
"""

import importlib.util
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import gen_registry  # noqa: E402

# Intentional, documented deltas vs the legacy files (see gen_registry.py
# module docstring and PR #204). Anything beyond these fails the guard.
SANDBOX_ENV_DELTAS = {
    # dashboard parity: env_vars already exported OPENAI_API_KEY on every spawn
    "codex": {"OPENAI_API_KEY": "$OPENAI_API_KEY"},
}
DASHBOARD_ENV_DELTAS = {
    # sandbox parity: keytar/D-Bus workaround; inert for sandboxed spawns,
    # forces the file-keychain fallback for unsandboxed gemini
    "gemini": {"GEMINI_FORCE_FILE_STORAGE": "true"},
    "gemini-unsandboxed": {"GEMINI_FORCE_FILE_STORAGE": "true"},
}

# Dashboard fields compared field-by-field. Excluded, with reasons:
#   command (base entries)  — dead whenever sandbox_level is set (all shipped
#                             base entries set it); compared for -unsandboxed
#                             entries where it is live.
#   home_ro_dirs/home_rw_dirs/disable_inner_sandbox_args — dead fields in the
#                             plugin (declared in serde, never read); the
#                             sandbox copies are authoritative (§3.2).
#   sandbox_home_subdir     — absent from the legacy file (hardcoded in
#                             agent.rs); the registry now carries it.
DASHBOARD_COMPARED_FIELDS = (
    "pane_title_pattern", "status_pipe_name", "display_name", "short_label",
    "color", "sandboxed", "has_native_hooks", "providers", "event_map",
    "env_vars", "sandbox_level", "sandbox_levels", "bwrap_conflict",
)

DASHBOARD_FIELD_DEFAULTS = {
    "has_native_hooks": False,
    "providers": [],
    "event_map": {},
    "env_vars": {},
    "sandbox_level": None,
    "sandbox_levels": [],
    "bwrap_conflict": False,
}


def load_legacy_sandbox() -> dict:
    with open(REPO_ROOT / "sandbox" / "agents-defaults.toml", "rb") as fh:
        return tomllib.load(fh)["agents"]


def load_legacy_dashboard() -> dict:
    with open(REPO_ROOT / "lince-dashboard" / "agents-defaults.toml", "rb") as fh:
        return tomllib.load(fh)["agents"]


def load_agent_sandbox_module():
    """Import the single-file sandbox/agent-sandbox script as a module."""
    path = REPO_ROOT / "sandbox" / "agent-sandbox"
    spec = importlib.util.spec_from_loader(
        "agent_sandbox_under_test",
        importlib.machinery.SourceFileLoader("agent_sandbox_under_test", str(path)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRegistryFilesInSync(unittest.TestCase):
    """Checked-in registry.d/ must byte-match regeneration from legacy files."""

    def test_registry_matches_generation(self):
        files = gen_registry.generate_files()
        registry_dir = REPO_ROOT / "registry.d"
        for fname, content in files.items():
            path = registry_dir / fname
            self.assertTrue(path.is_file(), f"missing registry.d/{fname}")
            self.assertEqual(
                path.read_text(encoding="utf-8"), content,
                f"registry.d/{fname} is stale — regenerate with: python3 scripts/gen_registry.py",
            )
        on_disk = {p.name for p in registry_dir.glob("*.toml")}
        self.assertEqual(
            on_disk, set(files),
            "unexpected files in registry.d/ — shipped set drifted",
        )


class TestSandboxViewParity(unittest.TestCase):
    """Registry → legacy sandbox projection must equal the legacy file."""

    def assert_sandbox_parity(self, view: dict):
        legacy = load_legacy_sandbox()
        self.assertEqual(set(view), set(legacy), "agent name sets differ")
        for name, legacy_entry in legacy.items():
            expected = {
                "command": legacy_entry["command"],
                "default_args": list(legacy_entry.get("default_args", [])),
                "env": {**legacy_entry.get("env", {}), **SANDBOX_ENV_DELTAS.get(name, {})},
                "home_ro_dirs": list(legacy_entry.get("home_ro_dirs", [])),
                "home_rw_dirs": list(legacy_entry.get("home_rw_dirs", [])),
                "bwrap_conflict": legacy_entry.get("bwrap_conflict", False),
                "disable_inner_sandbox_args": list(legacy_entry.get("disable_inner_sandbox_args", [])),
            }
            self.assertEqual(view[name], expected, f"sandbox view differs for {name}")

    def test_gen_script_projection(self):
        registry = gen_registry.build_registry()
        self.assert_sandbox_parity(gen_registry.sandbox_view(registry))

    def test_agent_sandbox_runtime_loader(self):
        """The real consumer code path: agent-sandbox's registry loader,
        reading the actual checked-in registry.d/ files."""
        mod = load_agent_sandbox_module()
        view = mod.load_registry_defaults(REPO_ROOT / "registry.d")
        self.assert_sandbox_parity(view)

    def test_codex_user_skills_are_visible_in_the_sandbox(self):
        """Codex discovers user-installed skills under ~/.agents/skills."""
        mod = load_agent_sandbox_module()
        view = mod.load_registry_defaults(REPO_ROOT / "registry.d")
        self.assertIn(".agents", view["codex"]["home_ro_dirs"])


class TestDashboardViewParity(unittest.TestCase):
    """Registry → legacy dashboard projection (incl. §3.5 variant derivation)
    must equal the legacy dashboard file on every live field."""

    def test_dashboard_view(self):
        registry = gen_registry.build_registry()
        view = gen_registry.dashboard_view(registry)
        legacy = load_legacy_dashboard()

        # Every legacy dashboard entry must exist in the projected view.
        # (The reverse is not required: aider/amp are sandbox-only today and
        # become dashboard-visible only with resolve --json, #202.)
        missing = set(legacy) - set(view)
        self.assertFalse(missing, f"legacy dashboard agents missing from registry view: {missing}")

        for name, legacy_entry in legacy.items():
            gen_entry = view[name]
            for field in DASHBOARD_COMPARED_FIELDS:
                legacy_val = legacy_entry.get(field, DASHBOARD_FIELD_DEFAULTS.get(field))
                gen_val = gen_entry.get(field, DASHBOARD_FIELD_DEFAULTS.get(field))
                if field == "env_vars":
                    legacy_val = {**legacy_val, **DASHBOARD_ENV_DELTAS.get(name, {})}
                self.assertEqual(
                    gen_val, legacy_val,
                    f"dashboard view differs for {name}.{field}",
                )
            # command is live only for unsandboxed variants (no sandbox_level).
            if name.endswith("-unsandboxed"):
                self.assertEqual(
                    gen_entry["command"], legacy_entry["command"],
                    f"derived unsandboxed command differs for {name} — "
                    "add a [variants.unsandboxed] exception (design §3.5)",
                )


class TestLevelFragmentParity(unittest.TestCase):
    """Registry [sandbox.levels.*] must stay lossless vs the shipped
    sandbox/profiles fragments (covered transitively by regeneration, but
    asserted directly so a fragment edit fails with a named level)."""

    def test_levels_match_fragments(self):
        registry = gen_registry.build_registry()
        for name, entry in registry.items():
            self.assertEqual(
                entry.get("levels", {}), gen_registry.load_levels(name),
                f"levels differ for {name}",
            )


class TestProviderBundle(unittest.TestCase):
    def test_provider_union_is_pi_bundle(self):
        legacy = load_legacy_sandbox()
        union = gen_registry.provider_env_union()
        self.assertEqual(set(union), set(legacy["pi"]["env"]))

    def test_provider_env_all_expansion(self):
        legacy = load_legacy_sandbox()
        expanded = gen_registry.expand_env({"provider_env": "all"})
        self.assertEqual(expanded, legacy["pi"]["env"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
