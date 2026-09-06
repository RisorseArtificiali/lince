# Configuration Reference

Complete reference for all LINCE Dashboard configuration files, keys, and merge behavior.

## Overview

The dashboard reads from two configuration files:

| File | Location | Purpose |
|------|----------|---------|
| `config.toml` | `~/.config/lince-dashboard/config.toml` | Dashboard behavior and user overrides |
| `agents-defaults.toml` | `~/.config/lince-dashboard/agents-defaults.toml` | Shipped agent type presets |

Both files are TOML format. User entries in `config.toml` take precedence over defaults in `agents-defaults.toml` for the same agent key. See [Config Merge Order](#config-merge-order) for details.

## config.toml

**File**: `~/.config/lince-dashboard/config.toml`

Created by `install.sh`. Holds dashboard-wide settings and optional agent type overrides.

### [dashboard]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_provider` | string | `""` | Default provider (env-var bundle) for new agents. Empty means no `-P` flag is passed. The legacy spelling `default_profile` is still accepted (gh#81). |
| `sandbox_config_path` | string | `"~/.agent-sandbox/config.toml"` | Path to sandbox config for provider auto-discovery. |
| `default_project_dir` | string | `""` | Default working directory for new agents. Empty means the current directory. |
| `sandbox_command` | string | `"agent-sandbox"` | Path or name of the `agent-sandbox` binary. |
| `agent_layout` | string | `"tiled"` | How agent panes are created. `"tiled"` (default) for the 3-pane layout with agent viewport, `"floating"` for overlay panes. Launch with `lince` (tiled) or `lince-floating`. |
| `focus_mode` | string | `"floating"` | How focusing an agent works. `"floating"` shows an overlay, `"replace"` switches tabs. |
| `status_method` | string | `"pipe"` | Status detection method. `"pipe"` for Zellij pipe (recommended), `"file"` for `/tmp` polling. |
| `status_file_dir` | string | `"/tmp/lince-dashboard"` | Directory for status files when using file mode. |
| `max_agents` | integer | `9` | Maximum number of concurrent agents. |
| `sandbox_backend` | string | `"auto"` | Sandbox backend preference. `"auto"`, `"agent-sandbox"`, or `"nono"`. Auto prefers agent-sandbox on Linux, nono on macOS. |
| `default_agent_type` | string | `"claude"` | Default agent type for new agents. Must match a key in agents-defaults.toml or an `[agents.*]` section. |

### Session defaults (per-project, dynamic)

In addition to the static `default_*` keys above, the `N` wizard's final
**Confirm** step accepts `!` instead of `Enter` to spawn the agent **and**
save all wizard choices (type, sandbox backend, sandbox level, provider,
project dir) as the active `n` quick-spawn defaults for the current
session. Defaults are persisted in `.lince-dashboard` next to the open
agents when the user exits with `Q`, and reapplied on the next launch in
the same directory. Press `!` again from a later wizard to overwrite.

Session defaults take precedence over the static `[dashboard].default_*`
fields — they cover the case where one project wants codex/permissive and
another wants claude/paranoid without editing the global config.

### Hot-Reload

The plugin checks `config.toml` for changes every 5 seconds and applies them without restart. A "Config reloaded" notification appears in the status bar.

**Hot-reloadable** (applied immediately):

- `focus_mode`, `status_method`, `max_agents`, `status_file_dir`
- `agent_layout`, `default_provider`, `default_project_dir`, `default_agent_type`

**Not hot-reloadable** (requires restart, only affects new agents):

- `sandbox_command`

If the config file contains a parse error, the previous working config is preserved and an error message is shown in the status bar.

### [agents.*] Overrides

Add `[agents.<name>]` sections to `config.toml` to override shipped presets or define custom agent types. These sections use the same fields as `agents-defaults.toml`.

Override an existing agent (e.g. change Codex model):

```toml
[agents.codex]
command = ["codex", "--sandbox", "workspace-write", "-a", "never", "--model", "o4-mini"]
pane_title_pattern = "codex"
status_pipe_name = "lince-status"
display_name = "OpenAI Codex (o4-mini)"
short_label = "CDX"
color = "cyan"
sandboxed = false
has_native_hooks = false

[agents.codex.env_vars]
OPENAI_API_KEY = "$OPENAI_API_KEY"
```

When you override an agent key, you must provide **all** required fields. The override replaces the entire agent definition, not individual fields.

Add a new agent type:

```toml
[agents.my-agent]
command = ["my-agent-binary", "--auto", "--project", "{project_dir}"]
pane_title_pattern = "my-agent"
status_pipe_name = "lince-status"
display_name = "My Custom Agent"
short_label = "MCA"
color = "magenta"
sandboxed = true
has_native_hooks = false
home_ro_dirs = ["~/.config/my-agent/"]
```

## agents-defaults.toml

**File**: `~/.config/lince-dashboard/agents-defaults.toml`

Installed and updated by `install.sh` / `update.sh`. Contains preset agent type definitions. This file is overwritten on updates -- put your customizations in `config.toml` instead.

> **Migration note**: older LINCE versions preserved this file across updates, so some users defined custom agents directly in it. Custom `[agents.*]` blocks must now move to `config.toml`. If the old installed file differs from the shipped one in any way (custom agents, edited values, even a malformed file), `update.sh` backs it up as `agents-defaults.toml.bak.<timestamp>` before overwriting, and prints a warning listing any non-shipped agent keys to move. Known side effect: older `quickstart.sh` installs wrote a *filtered* `agents-defaults.toml` containing only the agents selected during setup; after this update the wizard's agent picker again lists **all** shipped agent types. This is an accepted regression of the always-overwrite policy — there is currently no supported way to hide shipped entries.

Each agent type is defined as a `[agents.<name>]` TOML table.

### Agent Type Fields

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `command` | array of strings | Yes | -- | Command template. Supports `{agent_id}`, `{project_dir}`, `{provider}` (and `{profile}` as a legacy alias for `{provider}`) placeholders. |
| `pane_title_pattern` | string | Yes | -- | Pattern to match Zellij pane titles for reconciliation. |
| `status_pipe_name` | string | Yes | -- | Zellij pipe name for receiving status messages from this agent type. |
| `display_name` | string | Yes | -- | Full name shown in the UI and wizard. |
| `short_label` | string | Yes | -- | 3-character label shown in the agent table column (e.g. `CLA`, `CDX`). |
| `color` | string | Yes | -- | ANSI color name for the agent label. Values: `blue`, `red`, `cyan`, `yellow`, `green`, `magenta`, `white`. |
| `sandboxed` | boolean | Yes | -- | Whether the agent runs inside the sandbox. Affects UI warnings and launch behavior. |
| `has_native_hooks` | boolean | No | `false` | If `true`, agent sends its own status events. If `false`, `lince-agent-wrapper` is injected automatically. |
| `bwrap_conflict` | boolean | No | `false` | Set `true` when the agent uses bwrap internally. Triggers injection of `disable_inner_sandbox_args`. |
| `disable_inner_sandbox_args` | array of strings | No | `[]` | Arguments appended to the agent command to disable its internal sandbox when `bwrap_conflict` is `true`. |
| `providers` | array of strings | No | `[]` | Providers (env-var bundles) for this agent type. `["__discover__"]` means auto-discover from the sandbox config. `[]` skips the wizard's Provider step. An explicit list restricts choices to those names. The legacy key name `profiles` is still accepted (gh#81). |
| `home_ro_dirs` | array of strings | No | `[]` | Home subdirectories to bind read-only in the sandbox (e.g. `["~/.claude/"]`). |
| `home_rw_dirs` | array of strings | No | `[]` | Home subdirectories to bind read-write in the sandbox. |
| `env_vars` | table | No | `{}` | Environment variables to set for the agent. Applied for both sandboxed and non-sandboxed agents. See [Environment Variable Resolution](#environment-variable-resolution). |
| `event_map` | table | No | `{}` | Mapping from agent-specific event names to canonical LINCE statuses (`running`, `input`, `permission`, `stopped`). Required when `has_native_hooks = true`. See [Agent Examples](dashboard/agent-examples.md#custom-event-map). |
| `sandbox_backend` | string | No | (global default) | Per-agent sandbox backend override. `"bwrap"` (a.k.a. `"agent-sandbox"`) or `"nono"`. Overrides the global `[dashboard].sandbox_backend`. |
| `sandbox_level` | string | No | `"normal"` | Sandbox isolation level: `"paranoid"`, `"normal"`, `"permissive"`, or any custom name backed by a `<name>.toml` policy fragment. The plugin synthesizes the launch command from `(agent_type, sandbox_backend, sandbox_level)`; when set, the entry's legacy `command` field is ignored. See [Sandbox Levels](dashboard/sandbox-levels.md). |

### Environment Variable Resolution

The `env_vars` table sets environment variables for the agent process. Values starting with `$` are resolved from the host environment at spawn time:

```toml
[agents.codex.env_vars]
OPENAI_API_KEY = "$OPENAI_API_KEY"    # resolved from host env
MY_STATIC_VAR = "literal-value"       # used as-is
```

For **sandboxed** agents, `env_vars` are passed through the sandbox's environment. The sandbox starts with `--clearenv` (blank environment), so only explicitly declared variables are visible to the agent.

For **non-sandboxed** agents, `env_vars` are set via `env VAR=val ...` on the command line. The agent inherits the full host environment plus these overrides.

### Command Template Placeholders

Command arrays support these placeholders, resolved at spawn time:

| Placeholder | Resolved To | Example |
|-------------|-------------|---------|
| `{agent_id}` | Unique agent identifier | `agent-1`, `agent-2` |
| `{project_dir}` | Project directory path | `/home/user/project/backend` |
| `{provider}` | Selected provider name (env-var bundle) | `vertex`, `anthropic`, `zai` |
| `{profile}` | Legacy alias for `{provider}` (gh#81) — same value | `vertex`, `anthropic` |

Example command template:

```toml
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}"]
```

Resolves to:

```bash
agent-sandbox run -p /home/user/project/backend --id agent-1
```

### Provider Discovery

The `providers` field (legacy `profiles`) controls how providers are presented in the wizard's Provider step:

| Value | Behavior |
|-------|----------|
| `["__discover__"]` | Auto-discover providers from `[providers.*]` / `[<agent>.providers.*]` sections in the sandbox config file (`sandbox_config_path`). Legacy `[profiles.*]` is also read. |
| `[]` (empty) | Skip the Provider step in the wizard entirely. |
| `["vertex", "anthropic"]` | Show only the listed providers in the wizard, regardless of what exists in sandbox config. |

Auto-discovered providers are loaded asynchronously at startup via `run_command()` (not direct filesystem access, due to WASI sandbox limitations).

Providers may also declare an `env_unset` list in the sandbox config to remove conflicting environment variables before setting the provider's own vars:

```toml
# In ~/.agent-sandbox/config.toml
[claude.providers.vertex]
description = "Vertex AI"
env_unset = ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]

[claude.providers.vertex.env]
CLAUDE_CODE_USE_VERTEX = "1"
CLOUD_ML_REGION = "us-east5"
```

For sandboxed agents, `env_unset` is a no-op (the sandbox already starts with a blank environment). For non-sandboxed agents, it ensures the host's existing variables do not conflict with the provider's intended configuration.

> **Two orthogonal axes** (gh#81): a *provider* (above) is an env-var bundle.
> A *sandbox profile* (a.k.a. sandbox level — paranoid / normal / permissive)
> is the isolation posture, set via `sandbox_level` and the wizard's separate
> "Sandbox Level" step. They are independent — every combination is valid.

## Config Merge Order

Agent type definitions are loaded from two layers and merged:

```
agents-defaults.toml          <-- shipped presets (overwritten on update)
       |
       v  merged with
config.toml [agents.*]        <-- user overrides + custom agents (never overwritten)
```

Merge rules:

- If `config.toml` defines `[agents.claude]`, it **fully replaces** the `[agents.claude]` entry from `agents-defaults.toml`. There is no per-field merge; the entire agent definition is replaced.
- Because entries fully replace, every `[agents.*]` entry in `config.toml` must be a **complete definition** -- the 7 required fields (`command`, `pane_title_pattern`, `status_pipe_name`, `display_name`, `short_label`, `color`, `sandboxed`) must all be present.
- **Known sharp edge**: if any single `[agents.*]` entry in `config.toml` is malformed or missing a required field, the dashboard silently drops **all** user agent entries and falls back to the shipped defaults only. A more tolerant per-entry loader is deferred to the agent-registry work.
- If `config.toml` defines `[agents.my-custom]` (a key not in defaults), it is added as a new agent type.
- Keys only in `agents-defaults.toml` are preserved as-is.

This means you can safely update `agents-defaults.toml` (via `update.sh`) without losing customizations, as long as your overrides live in `config.toml`.

## See Also

- [Usage Guide](dashboard/usage-guide.md) -- how to operate the dashboard
- [Agent Examples](dashboard/agent-examples.md) -- preset agents and custom configuration examples
- [Sandbox CLI Reference](sandbox/cli-reference.md) -- the `agent-sandbox` command
- [lince-config CLI](https://github.com/RisorseArtificiali/lince/blob/main/lince-config/README.md) -- structured CLI for reading and editing LINCE configuration
- [Multi-Agent Guide](https://github.com/RisorseArtificiali/lince/blob/main/lince-dashboard/MULTI-AGENT-GUIDE.md) -- migration guide for multi-agent support
