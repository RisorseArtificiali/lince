# registry.d/ — Unified agent registry

One TOML file per shipped agent, plus `providers.toml` — the single source of
truth for agent definitions consumed by **both** the sandbox (`agent-sandbox`)
and the dashboard (`lince-dashboard`). Replaces the two divergent
`agents-defaults.toml` files (Config v2, issue #204; design:
`docs/design/config-v2-design.md` §3).

## Ownership contract (#199)

- **Shipped data, always overwritten** by `install.sh` / `update.sh`
  (installed to `~/.local/share/lince/registry.d/`). Never hand-edit the
  installed copies.
- **User overrides and custom agents never live here** — they belong in the
  user config (today: `[agents.<name>]` in `~/.agent-sandbox/config.toml` /
  `~/.config/lince-dashboard/config.toml`; with Config v2:
  `~/.config/lince/lince.toml`).

## File schema (per agent)

| Table | Keys | Notes |
|---|---|---|
| `[agent]` | `name`, `display_name`, `short_label`, `color`, `binary`, `default_args` | identity + launch facts. `default_args` are sandbox-coupled flags — never applied to unsandboxed variants (§3.5) |
| `[sandbox]` | `backend`, `default_level`, `allowed_levels`, `home_subdir`, `bwrap_conflict`, `disable_inner_sandbox_args`, `home_ro_dirs`, `home_rw_dirs` | jail facts; home dirs in relative form (`.codex`, not `~/.codex/`) |
| `[sandbox.levels.<level>]` | `scratch_home_dirs`, `scratch_home_files`, `unshare_net`, `credential_proxy`, `block_git_push`, `allow_domains`, `home_ro_dirs`, `home_rw_dirs`, `passthrough`, `[…env_extra]` | per-level policy, absorbed from `sandbox/profiles/<agent>-<level>.toml` |
| `[dashboard]` | `status_pipe_name` (default `lince-status`), `has_native_hooks`, `providers` | `pane_title_pattern` is derived: `agent-sandbox` when sandboxed, `binary` when not |
| `[variants.unsandboxed]` | any | exceptions to the §3.5 derivation rule only |
| `[env]` | agent env vars, or `provider_env = "all"` | single merged table (kills the sandbox/dashboard env duplication); `provider_env = "all"` expands to the union of all provider env-var NAMES from `providers.toml` |
| `[event_map]` | agent event → canonical status | once per agent; all variants inherit |

`-unsandboxed` entries do not exist here — they are **derived** (design §3.5):
`command = [binary]`, `color = "red"`, `short_label = <first 2 chars>U`,
display name suffixed, sandbox levels dropped, everything else inherited.

## Adding a new agent

Drop one `<name>.toml` file here following the schema above (see
`claude.toml` for a template) — both modules pick it up on the next
install/update. For agents with status hooks, also ship the hook (see
`lince-dashboard/hooks/`).

## Transition state (#204)

These files were generated from the legacy `sandbox/agents-defaults.toml` +
`lince-dashboard/agents-defaults.toml` by `scripts/gen_registry.py`. Until the
legacy shipped files are deleted from the repo, the diff-guard test keeps the
three in sync — edit the **legacy files** and regenerate:

```bash
python3 scripts/gen_registry.py            # regenerate registry.d/
python3 scripts/tests/test_registry_sync.py # verify no drift
```
