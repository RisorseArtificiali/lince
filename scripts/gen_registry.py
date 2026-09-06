#!/usr/bin/env python3
"""gen_registry.py — generate registry.d/ from the legacy agents-defaults files.

Config v2 transition build step (#204, design: docs/design/config-v2-design.md
§3.3): the unified agent registry `registry.d/<agent>.toml` is generated from
the two legacy shipped files

    sandbox/agents-defaults.toml            (bwrap-jail schema)
    lince-dashboard/agents-defaults.toml    (dashboard UI schema)

plus the per-agent level fragments under sandbox/profiles/. After generation
the registry becomes the hand-maintained source of truth; until the legacy
shipped files are deleted from the repo, the diff-guard test
(scripts/tests/test_registry_sync.py) fails on any divergence — no silent
drift in either direction.

Key-by-key mapping: design doc §3.1 (sandbox keys) and §3.2 (dashboard keys).
Variant derivation (`-unsandboxed` entries disappear): §3.5.
Provider table (kills the Pi 31-var × 4 duplication): §3.4.

Intentional, documented deltas vs the legacy files (PR #204):
  1. codex sandbox env gains OPENAI_API_KEY="$OPENAI_API_KEY" — the dashboard
     already exports it for every codex spawn (legacy env_vars); the merged
     [env] table makes standalone `agent-sandbox run --agent codex` match.
     Unset host vars expand to empty strings, so this is inert without a key.
  2. gemini dashboard env_vars gains GEMINI_FORCE_FILE_STORAGE="true" — the
     sandbox already sets it (keytar/D-Bus workaround); for unsandboxed gemini
     it merely forces the file keychain fallback.
  3. The dashboard legacy home_ro_dirs/home_rw_dirs values are DROPPED: they
     are dead fields (declared in the plugin serde struct, never read) and for
     codex they contradict the sandbox copy (ro vs rw .codex). The sandbox
     values are authoritative (§3.2 "single copy").

Usage:
    python3 scripts/gen_registry.py            # (re)write registry.d/
    python3 scripts/gen_registry.py --check    # exit 1 if registry.d/ differs
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DEFAULTS = REPO_ROOT / "sandbox" / "agents-defaults.toml"
DASHBOARD_DEFAULTS = REPO_ROOT / "lince-dashboard" / "agents-defaults.toml"
PROFILES_DIR = REPO_ROOT / "sandbox" / "profiles"
REGISTRY_DIR = REPO_ROOT / "registry.d"

# Shipped agents, in registry emission order (design doc §3).
SHIPPED_AGENTS = (
    "claude", "codex", "bob", "gemini", "aider", "opencode", "amp", "pi", "goose",
    "bash", "zsh", "fish",
)

# Provider table → registry.d/providers.toml (design §3.4). The union of all
# `env` lists MUST equal Pi's legacy 31-variable bundle — asserted at build
# time. `hosts` are proxy-allowlist additions; only providers with a matching
# CREDENTIAL_PROXY_RULES domain in agent-sandbox carry one today.
PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "env": ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"],
        "hosts": ["api.anthropic.com"],
    },
    "openai": {
        "env": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
        "hosts": ["api.openai.com"],
    },
    "azure-openai": {
        "env": ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_BASE_URL"],
    },
    "google": {
        "env": ["GEMINI_API_KEY"],
        "hosts": ["generativelanguage.googleapis.com"],
    },
    "google-vertex": {
        "env": ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"],
    },
    "deepseek": {"env": ["DEEPSEEK_API_KEY"]},
    "mistral": {"env": ["MISTRAL_API_KEY"]},
    "groq": {"env": ["GROQ_API_KEY"]},
    "cerebras": {"env": ["CEREBRAS_API_KEY"]},
    "cloudflare": {"env": ["CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"]},
    "xai": {"env": ["XAI_API_KEY"]},
    "openrouter": {"env": ["OPENROUTER_API_KEY"]},
    "ai-gateway": {"env": ["AI_GATEWAY_API_KEY"]},
    "zai": {"env": ["ZAI_API_KEY"]},
    "opencode": {"env": ["OPENCODE_API_KEY"]},
    "fireworks": {"env": ["FIREWORKS_API_KEY"]},
    "kimi": {"env": ["KIMI_API_KEY"]},
    "minimax": {"env": ["MINIMAX_API_KEY", "MINIMAX_CN_API_KEY"]},
    "aws-bedrock": {
        "env": [
            "AWS_PROFILE", "AWS_REGION", "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
            "AWS_BEARER_TOKEN_BEDROCK", "AWS_ENDPOINT_URL_BEDROCK_RUNTIME",
        ],
    },
}

# Agents whose [env] is the full multi-provider bundle → provider_env = "all"
# (design §3.4: the 31-var block is stored ONCE, in providers.toml).
PROVIDER_ENV_ALL = frozenset({"pi"})

# Display data for sandbox-only agents that have no entry in the legacy
# dashboard file (they become dashboard-visible when the plugin switches to
# `lince config resolve --json`, #202).
DASHBOARD_SUPPLEMENTS: dict[str, dict] = {
    "aider": {"display_name": "Aider", "short_label": "AID", "color": "blue"},
    "amp": {"display_name": "Amp", "short_label": "AMP", "color": "blue"},
}

# $HOME subdir per agent (nono-paranoid scratch rsync source). Mirrors the
# hardcoded match in lince-dashboard/plugin/src/agent.rs (command synthesis);
# aider/amp follow their state-dir convention. Empty = stateless (shells).
HOME_SUBDIRS: dict[str, str] = {
    "claude": ".claude",
    "codex": ".codex",
    "bob": ".bob",
    "gemini": ".gemini",
    "aider": ".aider",
    "opencode": ".config/opencode",
    "amp": ".amplication",
    "pi": ".pi",
    "goose": ".config/goose",
    "bash": "",
    "zsh": "",
    "fish": "",
}

# Per-variant exceptions to the §3.5 derivation rule. The diff-guard verifies
# derived+exceptions == legacy, so a new exception in the legacy file fails
# the test instead of drifting silently.
#   codex: keeps auto-edit semantics outside the sandbox — explicit
#   workspace-write + no approvals (codex CLI >= 0.144 removed --full-auto;
#   claude deliberately drops --dangerously-skip-permissions — see §3.5
#   security note) and flips bwrap_conflict off (no outer bwrap to conflict
#   with).
VARIANT_EXCEPTIONS: dict[str, dict] = {
    "codex": {
        "command": ["codex", "--no-alt-screen", "--sandbox", "workspace-write", "-a", "never"],
        "bwrap_conflict": False,
    },
}

DEFAULT_STATUS_PIPE = "lince-status"


# ── Loading ──────────────────────────────────────────────────────────────

def load_legacy() -> tuple[dict, dict]:
    """Return (sandbox_agents, dashboard_agents) from the legacy files."""
    with open(SANDBOX_DEFAULTS, "rb") as fh:
        sandbox_agents = tomllib.load(fh)["agents"]
    with open(DASHBOARD_DEFAULTS, "rb") as fh:
        dashboard_agents = tomllib.load(fh)["agents"]
    return sandbox_agents, dashboard_agents


def load_levels(name: str) -> dict[str, dict]:
    """Map sandbox/profiles/<name>-<level>.toml fragments to registry
    [sandbox.levels.<level>] tables (lossless; unmapped fragment keys raise)."""
    levels: dict[str, dict] = {}
    for level in ("paranoid", "permissive"):
        path = PROFILES_DIR / f"{name}-{level}.toml"
        if not path.is_file():
            continue
        with open(path, "rb") as fh:
            frag = tomllib.load(fh)
        lv: dict = {}
        consumed: set[tuple] = set()

        agent_tbl = frag.get("agents", {}).get(name, {})
        for key in ("scratch_home_dirs", "scratch_home_files"):
            if key in agent_tbl:
                lv[key] = agent_tbl[key]
                consumed.add(("agents", name, key))
        sec = frag.get("security", {})
        for key in ("unshare_net", "credential_proxy", "block_git_push", "allow_domains"):
            if key in sec:
                lv[key] = sec[key]
                consumed.add(("security", key))
        sbx = frag.get("sandbox", {})
        if "home_ro_dirs" in sbx:
            lv["home_ro_dirs"] = sbx["home_ro_dirs"]
            consumed.add(("sandbox", "home_ro_dirs"))
        if "home_rw_dirs" in sbx:
            lv["home_rw_dirs"] = sbx["home_rw_dirs"]
            consumed.add(("sandbox", "home_rw_dirs"))
        env = frag.get("env", {})
        if "passthrough" in env:
            lv["passthrough"] = env["passthrough"]
            consumed.add(("env", "passthrough"))
        extra = env.get("extra", {})
        if extra:
            lv["env_extra"] = dict(extra)
            consumed.add(("env", "extra"))

        # Guard: every fragment key must have been mapped.
        leftovers = []
        for top, tbl in frag.items():
            if top == "agents":
                for sub_name, sub in tbl.items():
                    for k in sub:
                        if ("agents", sub_name, k) not in consumed:
                            leftovers.append(f"agents.{sub_name}.{k}")
            elif isinstance(tbl, dict):
                for k in tbl:
                    if (top, k) not in consumed and not (top == "env" and k == "extra"):
                        leftovers.append(f"{top}.{k}")
            else:
                leftovers.append(top)
        if leftovers:
            raise SystemExit(
                f"gen_registry: unmapped keys in {path.name}: {', '.join(leftovers)}"
            )
        levels[level] = lv
    return levels


# ── Registry data model ──────────────────────────────────────────────────

def provider_env_union() -> list[str]:
    """All provider env-var names, in providers.toml declaration order."""
    names: list[str] = []
    for prov in PROVIDERS.values():
        for var in prov["env"]:
            if var not in names:
                names.append(var)
    return names


def build_registry() -> dict[str, dict]:
    """Build the registry data model: {agent_name: registry_file_dict}."""
    sandbox_agents, dashboard_agents = load_legacy()

    # Invariant: providers.toml env union == Pi's legacy multi-provider bundle.
    pi_env = sandbox_agents["pi"]["env"]
    union = provider_env_union()
    if set(union) != set(pi_env) or any(pi_env[k] != f"${k}" for k in pi_env):
        raise SystemExit(
            "gen_registry: PROVIDERS env union does not match Pi's legacy env "
            f"bundle (missing: {sorted(set(pi_env) - set(union))}, "
            f"extra: {sorted(set(union) - set(pi_env))})"
        )

    registry: dict[str, dict] = {}
    for name in SHIPPED_AGENTS:
        s = sandbox_agents[name]
        d = dashboard_agents.get(name, {})
        sup = DASHBOARD_SUPPLEMENTS.get(name, {})

        agent = {
            "name": name,
            "display_name": d.get("display_name") or sup["display_name"],
            "short_label": d.get("short_label") or sup["short_label"],
            "color": d.get("color") or sup["color"],
            "binary": s["command"],
            "default_args": list(s.get("default_args", [])),
        }
        sandbox = {
            "backend": "auto",
            "default_level": d.get("sandbox_level", "normal"),
            "allowed_levels": list(d.get("sandbox_levels", [])),
            "home_subdir": HOME_SUBDIRS[name],
            "bwrap_conflict": s.get("bwrap_conflict", False),
            "disable_inner_sandbox_args": list(s.get("disable_inner_sandbox_args", [])),
            "home_ro_dirs": list(s.get("home_ro_dirs", [])),
            "home_rw_dirs": list(s.get("home_rw_dirs", [])),
        }
        dashboard: dict = {}
        pipe = d.get("status_pipe_name", DEFAULT_STATUS_PIPE)
        if pipe != DEFAULT_STATUS_PIPE:
            dashboard["status_pipe_name"] = pipe
        dashboard["has_native_hooks"] = d.get("has_native_hooks", False)
        dashboard["providers"] = list(d.get("providers", ["__discover__"]))

        if name in PROVIDER_ENV_ALL:
            env: dict = {"provider_env": "all"}
        else:
            # Single merged env table (§3.2): sandbox env ∪ dashboard env_vars.
            env = dict(s.get("env", {}))
            env.update(d.get("env_vars", {}))

        entry: dict = {
            "agent": agent,
            "sandbox": sandbox,
            "dashboard": dashboard,
        }
        levels = load_levels(name)
        if levels:
            entry["levels"] = levels
        if name in VARIANT_EXCEPTIONS:
            entry["variants"] = {"unsandboxed": dict(VARIANT_EXCEPTIONS[name])}
        if env:
            entry["env"] = env
        event_map = d.get("event_map", {})
        if event_map:
            entry["event_map"] = dict(event_map)
        registry[name] = entry
    return registry


# ── Projections (legacy views; also exercised by the diff-guard) ─────────

def expand_env(env: dict, providers: dict[str, dict] | None = None) -> dict:
    """Resolve provider_env = "all" into the union of provider env NAMES,
    each mapped to its $VAR host-expansion form (design §3.4)."""
    if providers is None:
        providers = PROVIDERS
    out = {k: v for k, v in env.items() if k != "provider_env"}
    if env.get("provider_env") == "all":
        for prov in providers.values():
            for var in prov.get("env", []):
                out.setdefault(var, f"${var}")
    return out


def sandbox_view(registry: dict[str, dict]) -> dict[str, dict]:
    """Project the registry into the legacy sandbox agents-defaults shape."""
    view: dict[str, dict] = {}
    for name, entry in registry.items():
        agent, sandbox = entry["agent"], entry["sandbox"]
        view[name] = {
            "command": agent["binary"],
            "default_args": list(agent["default_args"]),
            "env": expand_env(entry.get("env", {})),
            "home_ro_dirs": list(sandbox["home_ro_dirs"]),
            "home_rw_dirs": list(sandbox["home_rw_dirs"]),
            "bwrap_conflict": sandbox["bwrap_conflict"],
            "disable_inner_sandbox_args": list(sandbox["disable_inner_sandbox_args"]),
        }
    return view


def derive_unsandboxed(name: str, base: dict) -> dict:
    """§3.5 variant derivation: synthesize the -unsandboxed dashboard entry."""
    exc = base.get("variants", {}).get("unsandboxed", {})
    agent = base["agent"]
    derived = {
        "command": exc.get("command", [agent["binary"]]),
        "pane_title_pattern": agent["binary"],
        "status_pipe_name": base["dashboard"].get("status_pipe_name", DEFAULT_STATUS_PIPE),
        "display_name": agent["display_name"] + " (unsandboxed)",
        "short_label": agent["short_label"][:2].strip() + "U",
        "color": "red",
        "sandboxed": False,
        "has_native_hooks": base["dashboard"]["has_native_hooks"],
        "providers": list(base["dashboard"]["providers"]),
        "env_vars": expand_env(base.get("env", {})),
        "event_map": dict(base.get("event_map", {})),
        "bwrap_conflict": exc.get("bwrap_conflict", base["sandbox"]["bwrap_conflict"]),
        "sandbox_level": None,
        "sandbox_levels": [],
    }
    return derived


def dashboard_view(registry: dict[str, dict]) -> dict[str, dict]:
    """Project the registry into the legacy dashboard agents-defaults shape
    (base + derived -unsandboxed entries). `command` for base entries is the
    synthesized shape — a dead field whenever sandbox_level is set."""
    view: dict[str, dict] = {}
    for name, entry in registry.items():
        agent, sandbox, dashboard = entry["agent"], entry["sandbox"], entry["dashboard"]
        view[name] = {
            "command": [
                "agent-sandbox", "run", "-p", "{project_dir}",
                "--id", "{agent_id}", "--agent", name,
            ],
            "pane_title_pattern": "agent-sandbox",
            "status_pipe_name": dashboard.get("status_pipe_name", DEFAULT_STATUS_PIPE),
            "display_name": agent["display_name"],
            "short_label": agent["short_label"],
            "color": agent["color"],
            "sandboxed": True,
            "has_native_hooks": dashboard["has_native_hooks"],
            "providers": list(dashboard["providers"]),
            "env_vars": expand_env(entry.get("env", {})),
            "event_map": dict(entry.get("event_map", {})),
            "bwrap_conflict": sandbox["bwrap_conflict"],
            "sandbox_level": sandbox["default_level"],
            "sandbox_levels": list(sandbox["allowed_levels"]),
        }
        view[f"{name}-unsandboxed"] = derive_unsandboxed(name, entry)
    return view


# ── Deterministic TOML emission ──────────────────────────────────────────

_BARE_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _toml_key(key: str) -> str:
    if key and set(key) <= _BARE_KEY_CHARS:
        return key
    return json.dumps(key)


def _toml_value(val) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        return json.dumps(val)  # JSON string escaping is valid TOML basic-string
    if isinstance(val, int):
        return str(val)
    if isinstance(val, list):
        return "[" + ", ".join(_toml_value(v) for v in val) + "]"
    raise TypeError(f"unsupported TOML value: {val!r}")


def _emit_table(lines: list[str], header: str, table: dict) -> None:
    lines.append(f"[{header}]")
    sub_tables: list[tuple[str, dict]] = []
    for key, val in table.items():
        if isinstance(val, dict):
            sub_tables.append((key, val))
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(val)}")
    lines.append("")
    for key, val in sub_tables:
        _emit_table(lines, f"{header}.{key}", val)


def emit_agent_toml(name: str, entry: dict) -> str:
    lines = [
        f"# registry.d/{name}.toml — SHIPPED agent definition. Always overwritten",
        "# on update (#199 ownership contract) — user overrides and custom agents",
        "# belong in the user config, never here.",
        "#",
        "# GENERATED by scripts/gen_registry.py from the legacy agents-defaults",
        "# files (design: docs/design/config-v2-design.md §3). Regenerate with:",
        "#     python3 scripts/gen_registry.py",
        "# Guarded against drift by scripts/tests/test_registry_sync.py.",
        "",
    ]
    _emit_table(lines, "agent", entry["agent"])
    _emit_table(lines, "sandbox", entry["sandbox"])
    for level, table in entry.get("levels", {}).items():
        _emit_table(lines, f"sandbox.levels.{level}", table)
    _emit_table(lines, "dashboard", entry["dashboard"])
    for variant, table in entry.get("variants", {}).items():
        lines.append("# Exceptions to the derivation rule (design §3.5); all other")
        lines.append("# variant fields are derived from the base definition.")
        _emit_table(lines, f"variants.{variant}", table)
    if "env" in entry:
        if entry["env"].get("provider_env") == "all":
            lines.append("# provider_env = \"all\" expands to the union of all provider env-var")
            lines.append("# NAMES from registry.d/providers.toml (design §3.4) — the 31-var")
            lines.append("# multi-provider bundle is stored once, not copy-pasted 4x.")
        _emit_table(lines, "env", entry["env"])
    if "event_map" in entry:
        lines.append("# Once per agent; all variants inherit (design §3.5).")
        _emit_table(lines, "event_map", entry["event_map"])
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def emit_providers_toml() -> str:
    lines = [
        "# registry.d/providers.toml — SHIPPED provider table. Always overwritten",
        "# on update (#199). A provider is an env-var bundle (NAMES, never values)",
        "# plus the API hosts auto-added to the credential-proxy allowlist when",
        "# the provider is selected (design: docs/design/config-v2-design.md §3.4).",
        "#",
        "# The union of all env lists is the multi-provider bundle that",
        "# provider_env = \"all\" (registry.d/pi.toml) expands to.",
        "#",
        "# GENERATED by scripts/gen_registry.py — regenerate with:",
        "#     python3 scripts/gen_registry.py",
        "",
    ]
    for name, prov in PROVIDERS.items():
        _emit_table(lines, f"providers.{name}", prov)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def generate_files() -> dict[str, str]:
    """Return {filename: content} for every registry.d/ file."""
    registry = build_registry()
    files = {f"{name}.toml": emit_agent_toml(name, entry) for name, entry in registry.items()}
    files["providers.toml"] = emit_providers_toml()
    return files


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="verify registry.d/ matches generation; exit 1 on divergence",
    )
    args = parser.parse_args()

    files = generate_files()
    if args.check:
        stale = []
        for fname, content in files.items():
            path = REGISTRY_DIR / fname
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                stale.append(fname)
        for existing in sorted(REGISTRY_DIR.glob("*.toml")):
            if existing.name not in files:
                stale.append(f"{existing.name} (unexpected)")
        if stale:
            print(f"registry.d out of sync: {', '.join(stale)}", file=sys.stderr)
            print("Regenerate with: python3 scripts/gen_registry.py", file=sys.stderr)
            return 1
        print("registry.d is in sync.")
        return 0

    REGISTRY_DIR.mkdir(exist_ok=True)
    for fname, content in files.items():
        (REGISTRY_DIR / fname).write_text(content, encoding="utf-8")
        print(f"wrote registry.d/{fname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
