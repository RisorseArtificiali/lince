#!/usr/bin/env python3
"""Tests for `lince-config resolve --json` (#202, design §4.3).

Run with:
    python3 scripts/tests/test_resolve.py
"""

import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_lince_config_module():
    path = REPO_ROOT / "lince-config" / "lince-config"
    spec = importlib.util.spec_from_loader(
        "lince_config_resolve_test",
        importlib.machinery.SourceFileLoader("lince_config_resolve_test", str(path)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ResolveTestCase(unittest.TestCase):
    """Each test runs against the repo registry.d plus a scratch fake $HOME."""

    def setUp(self):
        self.lc = load_lince_config_module()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.sandbox_cfg = root / "agent-sandbox-config.toml"
        self.dashboard_cfg = root / "dashboard-config.toml"
        self.lince_cfg = root / "lince" / "lince.toml"
        self.profiles_dir = root / "profiles"
        self.nono_dir = root / "nono-profiles"
        # Redirect every filesystem touchpoint into the scratch dir.
        self.lc.LINCE_REGISTRY_DIRS = [REPO_ROOT / "registry.d"]
        self.lc.LINCE_CONFIG_PATH = self.lince_cfg
        self.lc.SANDBOX_CONFIG_PATH = self.sandbox_cfg
        self.lc.DASHBOARD_CONFIG_PATH = self.dashboard_cfg
        self.lc.SANDBOX_PROFILES_DIR = self.profiles_dir
        self.lc.NONO_PROFILES_DIR = self.nono_dir

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, **kwargs):
        view, error = self.lc.build_resolved_view(**kwargs)
        self.assertIsNone(error, f"unexpected resolve error: {error}")
        return view

    # ── dual-read: registry only ────────────────────────────────────────

    def test_registry_only_view(self):
        view = self.resolve()
        self.assertEqual(view["guarantee"], "default-deny")
        self.assertIsNone(view["sources"]["user"])
        # all 10 shipped agents present
        self.assertIn("claude", view["agents"])
        self.assertIn("aider", view["agents"])
        claude = view["agents"]["claude"]
        self.assertEqual(claude["binary"], "claude")
        self.assertEqual(claude["level"], "normal")
        self.assertEqual(claude["origin"]["level"], "registry")
        self.assertEqual(claude["event_map"]["Stop"], "input")
        self.assertEqual(claude["dashboard"]["status_pipe_name"], "claude-status")
        # variant derivation incl. the codex exception
        self.assertEqual(view["agents"]["codex"]["variants"]["unsandboxed"]["command"],
                         ["codex", "--full-auto"])
        self.assertFalse(view["agents"]["codex"]["variants"]["unsandboxed"]["bwrap_conflict"])
        self.assertEqual(claude["variants"]["unsandboxed"]["command"], ["claude"])
        self.assertEqual(claude["variants"]["unsandboxed"]["short_label"], "CLU")
        # pi: provider_env = "all" expanded to $NAME self-refs (names only)
        pi_env = view["agents"]["pi"]["env"]
        self.assertEqual(pi_env.get("ANTHROPIC_API_KEY"), "$ANTHROPIC_API_KEY")
        self.assertNotIn("provider_env", pi_env)
        self.assertEqual(view["agents"]["pi"]["variants"]["unsandboxed"]["env"], pi_env)
        # shells pin their level set
        self.assertEqual(view["agents"]["bash"]["levels"], ["normal"])

    # ── dual-read: legacy user configs ──────────────────────────────────

    def test_legacy_sandbox_overrides_and_providers(self):
        self.sandbox_cfg.write_text(
            '[sandbox]\ndefault_provider = "vertex"\n'
            '[security]\nallow_domains = ["pypi.org"]\n'
            '[agents.claude]\ndefault_args = ["--continue"]\n'
            '[providers.vertex]\n'
            'env = { CLOUD_ML_REGION = "us-east5", ANTHROPIC_API_KEY = "sk-ant-LITERALSECRET123456" }\n'
            '[codex.providers.work]\nenv = { OPENAI_API_KEY = "$OPENAI_API_KEY" }\n',
            encoding="utf-8",
        )
        view = self.resolve()
        claude = view["agents"]["claude"]
        # per-field overlay: default_args replaced, everything else intact
        self.assertEqual(claude["default_args"], ["--continue"])
        self.assertEqual(claude["display_name"], "Claude Code")
        # provider attribution: vertex → claude, work → codex
        self.assertEqual(claude["providers_available"], ["vertex"])
        self.assertEqual(view["agents"]["codex"]["providers_available"], ["work"])
        # default provider + allowed hosts
        self.assertEqual(claude["provider"], "vertex")
        self.assertIn("pypi.org", claude["allowed_hosts_effective"])
        # secrets never cross (I4): the literal key is redacted to $NAME
        vertex = view["providers"]["vertex"]
        self.assertEqual(vertex["env"]["ANTHROPIC_API_KEY"], "$ANTHROPIC_API_KEY")
        self.assertEqual(vertex["env"]["CLOUD_ML_REGION"], "us-east5")
        self.assertTrue(vertex["available"])  # literal non-secret value configured

    def test_provider_with_only_a_literal_secret_is_available(self):
        """#222 review: availability is judged on the RAW value (pre-redaction),
        so a provider configured only with a literal API key — and nothing in
        the host env — still resolves as available (was wrongly hidden)."""
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.sandbox_cfg.write_text(
            '[providers.direct]\n'
            'env = { ANTHROPIC_API_KEY = "sk-ant-onlyliteral0000000000" }\n',
            encoding="utf-8",
        )
        view = self.resolve()
        direct = view["providers"]["direct"]
        self.assertTrue(direct["available"], "literal-configured provider hidden")
        # but the value is still redacted out of the JSON (I4)
        self.assertEqual(direct["env"]["ANTHROPIC_API_KEY"], "$ANTHROPIC_API_KEY")

    def test_nonstandard_secret_key_is_redacted(self):
        """#222 review: a secret under a non-standard key name (no API_KEY/
        TOKEN substring) must not leak its literal value into resolve --json."""
        self.sandbox_cfg.write_text(
            '[providers.gw]\n'
            'env = { LLM_GATEWAY_CRED = "k8f3p9q2x7m1w5v0n4", '
            'GATEWAY_REGION = "eu-west" }\n',
            encoding="utf-8",
        )
        view = self.resolve()
        env = view["providers"]["gw"]["env"]
        self.assertEqual(env["LLM_GATEWAY_CRED"], "$LLM_GATEWAY_CRED")  # redacted
        self.assertEqual(env["GATEWAY_REGION"], "eu-west")  # non-secret kept
        self.assertNotIn("k8f3p9q2", json.dumps(view))
        self.assertNotIn("LITERALSECRET", json.dumps(view))

    def test_legacy_dashboard_custom_agent_and_level(self):
        # "acme" must NOT be a shipped agent — the test covers the
        # custom-agent-only-in-user-config path ("bob" pre-#278 shipped set).
        self.dashboard_cfg.write_text(
            '[agents.claude]\nsandbox_level = "paranoid"\n'
            '[agents.acme]\n'
            'command = ["acme", "--go"]\n'
            'display_name = "Acme CLI"\nshort_label = "ACM"\ncolor = "magenta"\n'
            'pane_title_pattern = "acme"\nstatus_pipe_name = "lince-status"\n'
            'sandboxed = true\n'
            '[agents.acme.event_map]\nturn_end = "input"\n',
            encoding="utf-8",
        )
        view = self.resolve()
        self.assertEqual(view["agents"]["claude"]["level"], "paranoid")
        self.assertEqual(view["agents"]["claude"]["origin"]["level"], "user")
        acme = view["agents"]["acme"]
        self.assertEqual(acme["binary"], "acme")
        self.assertEqual(acme["display_name"], "Acme CLI")
        self.assertEqual(acme["event_map"], {"turn_end": "input"})
        # derived variant for free
        self.assertEqual(acme["variants"]["unsandboxed"]["short_label"], "ACU")
        self.assertEqual(acme["variants"]["unsandboxed"]["color"], "red")

    def test_legacy_dashboard_enabled_agents_filters_in_dual_read(self):
        """v2 bridge: [dashboard].enabled_agents in the legacy dashboard config
        restricts the wizard's agent list in dual-read mode (no lince.toml), so
        a legacy user with unmigrated [providers.*] can filter the picker
        without forcing the §5.2 v2 switch (which would drop those providers)."""
        self.dashboard_cfg.write_text(
            '[dashboard]\nenabled_agents = ["claude", "bash"]\n', encoding="utf-8"
        )
        view = self.resolve()
        self.assertEqual(sorted(view["agents"].keys()), ["bash", "claude"])

    def test_legacy_per_level_agent_blocks_are_folded(self):
        """#202 regression: apply-sandbox-levels.py wrote [agents.<base>-<level>]
        blocks into the legacy dashboard config. They must NOT become standalone
        agents (the wizard would show duplicate "<Agent> (<level>)" rows); the
        level stays available on the base via the shipped trio. A genuine custom
        agent that merely contains a dash must still survive."""
        self.dashboard_cfg.write_text(
            '[agents.claude-paranoid]\n'
            'command = ["agent-sandbox", "run"]\n'
            'display_name = "Claude Code (paranoid)"\nshort_label = "CLP"\n'
            'color = "green"\nsandboxed = true\nsandbox_level = "paranoid"\n'
            '[agents.claude-permissive]\n'
            'command = ["agent-sandbox", "run"]\n'
            'display_name = "Claude Code (permissive)"\nshort_label = "CL+"\n'
            'color = "yellow"\nsandboxed = true\nsandbox_level = "permissive"\n'
            '[agents.my-tool]\n'   # genuine custom agent with a dash — must survive
            'command = ["my-tool", "go"]\n'
            'display_name = "My Tool"\nshort_label = "MYT"\ncolor = "cyan"\n'
            'sandboxed = true\n',
            encoding="utf-8",
        )
        view = self.resolve()
        self.assertNotIn("claude-paranoid", view["agents"])
        self.assertNotIn("claude-permissive", view["agents"])
        # the base agent still offers all three shipped levels at step 3
        self.assertEqual(
            view["agents"]["claude"]["levels"], ["paranoid", "normal", "permissive"]
        )
        # a custom agent whose name merely contains a dash is NOT folded
        self.assertIn("my-tool", view["agents"])
        self.assertEqual(view["agents"]["my-tool"]["binary"], "my-tool")

    def test_malformed_custom_agent_fails_that_agent_only(self):
        self.dashboard_cfg.write_text(
            '[agents.broken]\ndisplay_name = "No Command"\n'
            '[agents.claude]\nsandbox_level = "paranoid"\n',
            encoding="utf-8",
        )
        view = self.resolve()
        self.assertNotIn("broken", view["agents"])
        self.assertIn("claude", view["agents"])
        self.assertTrue(any("broken" in w for w in view["warnings"]))

    def test_custom_level_discovery(self):
        self.profiles_dir.mkdir(parents=True)
        (self.profiles_dir / "claude-strict.toml").write_text("[security]\n", encoding="utf-8")
        (self.profiles_dir / "relaxed.toml").write_text("[security]\n", encoding="utf-8")
        (self.profiles_dir / "codex-hard.toml").write_text("[security]\n", encoding="utf-8")
        self.nono_dir.mkdir(parents=True)
        (self.nono_dir / "lince-claude-nstrict.json").write_text("{}", encoding="utf-8")
        view = self.resolve()
        claude = view["agents"]["claude"]
        self.assertEqual(
            claude["levels_by_backend"]["agent-sandbox"],
            ["paranoid", "normal", "permissive", "relaxed", "strict"],
        )
        self.assertIn("nstrict", claude["levels_by_backend"]["nono"])
        # codex-hard is codex's fragment, not an agnostic level for claude
        self.assertNotIn("codex-hard", claude["levels_by_backend"]["agent-sandbox"])
        self.assertIn("hard", view["agents"]["codex"]["levels_by_backend"]["agent-sandbox"])
        # shells keep their pin regardless of discovery
        self.assertEqual(view["agents"]["bash"]["levels"], ["normal"])

    # ── v2 path: lince.toml ─────────────────────────────────────────────

    def write_lince(self, content: str):
        self.lince_cfg.parent.mkdir(parents=True, exist_ok=True)
        self.lince_cfg.write_text(content, encoding="utf-8")

    def test_lince_toml_is_the_only_source(self):
        self.sandbox_cfg.write_text(
            '[agents.claude]\ndefault_args = ["--legacy-should-be-ignored"]\n',
            encoding="utf-8",
        )
        self.write_lince(
            'version = "2.0"\n'
            '[network]\nallowed_hosts = ["pypi.org"]\n'
            '[agents.claude]\nlevel = "paranoid"\nprovider = "anthropic"\n'
            'allowed_hosts = ["github.com"]\n'
        )
        view = self.resolve()
        claude = view["agents"]["claude"]
        # legacy file ignored entirely (§5.2 hard switch) + notice emitted
        self.assertEqual(claude["default_args"], ["--dangerously-skip-permissions"])
        self.assertTrue(any("migrate" in w for w in view["warnings"]))
        self.assertEqual(claude["level"], "paranoid")
        self.assertEqual(claude["origin"]["level"], "user")
        self.assertEqual(claude["provider"], "anthropic")
        hosts = claude["allowed_hosts_effective"]
        self.assertIn("pypi.org", hosts)
        self.assertIn("github.com", hosts)
        # provider hosts auto-added when selected
        self.assertIn("api.anthropic.com", hosts)

    def test_lince_toml_version_contract_fails_closed(self):
        self.write_lince('version = "2.9"\n')
        view, error = self.lc.build_resolved_view()
        self.assertIsNone(view)
        self.assertEqual(error["code"], "version")
        self.assertIn("newer lince", error["message"])

    def test_lince_missing_version_is_hard_error(self):
        self.write_lince('[network]\ndefault = "deny"\n')
        view, error = self.lc.build_resolved_view()
        self.assertIsNone(view)
        self.assertIn('Add: version = "2.0"', error["message"])

    def test_experimental_voids_guarantee(self):
        self.write_lince('version = "2.0"\n[experimental]\npermissive_network = true\n')
        view = self.resolve()
        self.assertEqual(view["guarantee"], "void:permissive_network")

    def test_experimental_reported_per_agent(self):
        """#210: per-agent hatches surface on that agent only; globals on all."""
        self.write_lince(
            'version = "2.0"\n'
            '[experimental]\nseatbelt_extra = "(allow file-write* (subpath \\"/opt\\"))"\n'
            '[experimental.agents.codex]\nraw_bwrap_args = ["--hostname", "x"]\n'
        )
        view = self.resolve()
        self.assertTrue(view["guarantee"].startswith("void:"))
        self.assertIn("seatbelt_extra", view["agents"]["claude"]["experimental"])
        self.assertNotIn("agents.codex.raw_bwrap_args",
                         view["agents"]["claude"]["experimental"])
        self.assertIn("agents.codex.raw_bwrap_args",
                      view["agents"]["codex"]["experimental"])

    def test_experimental_validate_warns_not_blocks(self):
        self.write_lince('version = "2.0"\n[experimental]\nraw_bwrap_args = ["--dev-bind", "/x", "/x"]\n')
        issues = []
        self.lc._validate_lince_file(self.lince_cfg, issues)
        self.assertTrue(any("policy-overridden" in i["message"] for i in issues))
        self.assertFalse(any(i["level"] == "error" for i in issues))

    def test_custom_agent_in_lince_toml(self):
        # "acme" must NOT be a shipped agent (see the legacy-dashboard twin).
        self.write_lince(
            'version = "2.0"\n'
            '[agents.acme]\n'
            'binary = "acme"\ndisplay_name = "Acme CLI"\nshort_label = "ACM"\n'
            'color = "magenta"\nprovider = "openai"\nlevel = "normal"\n'
            '[agents.acme.dashboard]\nhas_native_hooks = false\n'
            '[agents.acme.event_map]\nturn_end = "input"\n'
        )
        view = self.resolve()
        acme = view["agents"]["acme"]
        self.assertEqual(acme["display_name"], "Acme CLI")
        self.assertEqual(acme["event_map"], {"turn_end": "input"})
        self.assertEqual(acme["variants"]["unsandboxed"]["short_label"], "ACU")

    def test_malformed_lince_custom_agent_fails_that_agent_only(self):
        self.write_lince(
            'version = "2.0"\n'
            '[agents.broken]\ncolor = "red"\n'   # missing binary/display/label
            '[agents.claude]\nlevel = "paranoid"\n'
        )
        view = self.resolve()
        self.assertNotIn("broken", view["agents"])
        self.assertEqual(view["agents"]["claude"]["level"], "paranoid")
        self.assertTrue(any("broken" in w for w in view["warnings"]))

    # ── project overlay clamp (§2.4) ────────────────────────────────────

    def test_project_overlay_tighten_applies_loosen_clamped(self):
        self.write_lince('version = "2.0"\n[agents.claude]\nlevel = "normal"\n')
        project = Path(self.tmp.name) / "proj"
        (project / ".lince").mkdir(parents=True)
        (project / ".lince" / "lince.toml").write_text(
            '[agents.claude]\nlevel = "paranoid"\n'
            '[agents.codex]\nlevel = "permissive"\n'
            '[network]\nallowed_hosts = ["sketchy.example"]\n',
            encoding="utf-8",
        )
        view = self.resolve(project_dir=project)
        # tighten (normal → paranoid): applied silently
        self.assertEqual(view["agents"]["claude"]["level"], "paranoid")
        self.assertEqual(view["agents"]["claude"]["origin"]["level"], "project")
        # loosen (normal → permissive): ignored with a notice
        self.assertEqual(view["agents"]["codex"]["level"], "normal")
        self.assertNotIn("sketchy.example",
                         view["agents"]["claude"]["allowed_hosts_effective"])
        self.assertTrue(any("allow_loosening" in w for w in view["warnings"]))

    # ── misc contract ───────────────────────────────────────────────────

    def test_agent_filter(self):
        view = self.resolve(agent_filter="gemini")
        self.assertEqual(list(view["agents"]), ["gemini"])

    def test_cli_flags_override(self):
        view = self.resolve(flag_level="paranoid", flag_allow_hosts=["crates.io"])
        self.assertEqual(view["agents"]["claude"]["level"], "paranoid")
        self.assertEqual(view["agents"]["claude"]["origin"]["level"], "flag")
        self.assertIn("crates.io", view["agents"]["claude"]["allowed_hosts_effective"])

    def test_output_is_json_serializable_and_deterministic(self):
        a = json.dumps(self.resolve(), sort_keys=True)
        b = json.dumps(self.resolve(), sort_keys=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
