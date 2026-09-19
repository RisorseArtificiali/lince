# Configuration Schema Reference

Field reference for the two TOML files this skill writes. Both use the
nested `[agents.<key>]` section form. Field semantics differ between files;
the section header pattern is identical.

---

## 1. Sandbox config — `~/.agent-sandbox/config.toml`

Agent definitions live under `[agents.<key>]`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `command` | string | yes | — | Binary name (must be in `PATH`) |
| `default_args` | list[string] | no | `[]` | Args appended to every invocation |
| `env` | dict | no | `{}` | Env vars. Use `"$VAR"` for host-side expansion |
| `home_ro_dirs` | list[string] | no | `[]` | Home subdirs to bind read-only, **relative to `~`** (`.codex`, NOT `~/.codex/`) |
| `home_rw_dirs` | list[string] | no | `[]` | Home subdirs to bind read-write, relative to `~` |
| `bwrap_conflict` | bool | no | `false` | `true` if the agent uses bwrap internally |
| `disable_inner_sandbox_args` | list[string] | no | `[]` | CLI args to disable the agent's own sandbox when `bwrap_conflict = true` |

### Example

```toml
[agents.codex]
command = "codex"
default_args = ["-a", "never"]
env = { OPENAI_API_KEY = "$OPENAI_API_KEY" }
home_ro_dirs = [".codex"]
home_rw_dirs = []
bwrap_conflict = true
disable_inner_sandbox_args = ["--no-sandbox"]
```

---

## 2. Dashboard config — `~/.config/lince-dashboard/config.toml` `[agents.<key>]`

Custom agents and overrides go into the user's dashboard `config.toml`,
using the same `[agents.<key>]` section form as the shipped defaults. The
dashboard merges these entries over the installed
`~/.config/lince-dashboard/agents-defaults.toml` (shipped data, always
overwritten on update — never edit it); a user entry **fully replaces** the
shipped entry for the same key (no per-field merge), so each entry must be a
COMPLETE definition with all 7 required fields below. Warning: a single
malformed/incomplete `[agents.*]` entry makes the dashboard silently drop
ALL user agent entries.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `command` | list[string] | yes | — | Command template. Supports `{agent_id}`, `{project_dir}`, `{profile}` |
| `display_name` | string | yes | — | Name shown in dashboard UI |
| `short_label` | string | yes | — | 3-character column label (e.g. `"CDX"`) |
| `color` | string | yes | — | ANSI colour name (see below) |
| `sandboxed` | bool | yes | — | Run inside the outer bwrap sandbox |
| `has_native_hooks` | bool | no | `false` | `true` ⇒ Tier A; `false` ⇒ Tier B |
| `pane_title_pattern` | string | yes | — | Substring matched against Zellij pane titles |
| `status_pipe_name` | string | yes | — | Zellij pipe to read events from (use `"lince-status"` unless reserved) |
| `providers` | list[string] | no | `[]` | `["__discover__"]` for auto, or explicit list |
| `sandbox_level` | string | no | `"normal"` | `paranoid` \| `normal` \| `permissive` (or custom) |
| `env_vars` | dict | no | `{}` | Env vars passed to the agent process (note: name is `env_vars`, NOT `env`) |
| `home_ro_dirs` | list[string] | no | `[]` | Bind mounts, **with `~/` prefix** (`~/.codex/`) — opposite of sandbox config |
| `home_rw_dirs` | list[string] | no | `[]` | Same prefix convention |
| `bwrap_conflict` | bool | no | `false` | Agent uses bwrap internally |
| `disable_inner_sandbox_args` | list[string] | no | `[]` | Args to disable the agent's inner sandbox |
| `event_map` | dict | no | `{}` | Native event → canonical event (Tier A only) |

### Example (Tier A)

```toml
[agents.codex]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}", "--agent", "codex"]
pane_title_pattern = "agent-sandbox"
status_pipe_name = "lince-status"
display_name = "OpenAI Codex"
short_label = "CDX"
color = "cyan"
sandboxed = true
has_native_hooks = true
bwrap_conflict = true
disable_inner_sandbox_args = ["--sandbox", "danger-full-access"]
home_ro_dirs = ["~/.codex/"]
providers = ["__discover__"]
sandbox_level = "normal"

[agents.codex.env_vars]
OPENAI_API_KEY = "$OPENAI_API_KEY"

[agents.codex.event_map]
"agent-turn-complete" = "input"
turn_complete = "input"
```

### Example (Tier B)

```toml
[agents.gemini]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}", "--agent", "gemini"]
pane_title_pattern = "agent-sandbox"
status_pipe_name = "lince-status"
display_name = "Google Gemini CLI"
short_label = "GEM"
color = "blue"
sandboxed = true
has_native_hooks = false
home_ro_dirs = ["~/.gemini/"]
providers = ["__discover__"]
sandbox_level = "normal"

[agents.gemini.env_vars]
GEMINI_API_KEY = "$GEMINI_API_KEY"
```

Tier B: no `event_map`, no hook script.

---

## 3. Canonical events (m-15 contract)

The closed set used by `event_map` values:

| Canonical    | Meaning                                            |
|--------------|----------------------------------------------------|
| `running`    | Agent is actively working                          |
| `input`      | Agent is waiting on the user (user's turn)         |
| `permission` | Agent is asking approval for a tool / action       |
| `stopped`    | Agent process ended (voluntary or error)           |
| `unknown`    | Internal fallback only — do NOT emit from hooks    |

Any `event_map` value outside `{running, input, permission, stopped}` is a
configuration bug. The dashboard logs a warning to stderr and resolves to
`Unknown`.

---

## 4. Valid colours

| Colour | Typical use |
|--------|-------------|
| `red` | Unsandboxed variants, danger |
| `green` | Available, paranoid sandbox |
| `yellow` | Caution, permissive sandbox |
| `blue` | Default / normal sandbox |
| `magenta` | Alternative agents |
| `cyan` | Secondary agents (Codex) |
| `white` | Neutral |

---

## 5. Pipe-name conventions

| Pipe name | Usage |
|-----------|-------|
| `claude-status` | Reserved for Claude Code (rich native hook payloads) |
| `lince-status` | Default for every other agent. Receives the minimal `{agent_id, event}` JSON contract |

---

## 6. bwrap conflict patterns

Some agents use bwrap (or Docker) internally. When `agent-sandbox` also uses
bwrap to sandbox the agent, nesting conflicts occur. Solution:

1. Set `bwrap_conflict = true`
2. Provide `disable_inner_sandbox_args` to disable the agent's own sandbox
3. The outer agent-sandbox bwrap provides the actual isolation

| Agent | Internal sandbox | `disable_inner_sandbox_args` |
|-------|------------------|------------------------------|
| Codex | bwrap | `["--no-sandbox"]` (sandbox config) / `["--sandbox", "danger-full-access"]` (dashboard config) |
| Gemini | Docker | `["--sandbox", "none"]` (when applicable) |
| Claude Code | none | N/A |
| Aider | none | N/A |
| OpenCode | none | N/A |

---

## 7. Command-template placeholders

The dashboard `command` field supports these placeholders (resolved at
launch time):

| Placeholder | Meaning | Example |
|-------------|---------|---------|
| `{agent_id}` | Unique id assigned by the dashboard | `agent-1` |
| `{project_dir}` | Absolute path to the project | `/home/user/project/foo` |
| `{profile}` | Sandbox profile name | `anthropic` |

Typical templates:

```toml
# Sandboxed via agent-sandbox (most agents)
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}", "--agent", "<key>"]

# Unsandboxed (direct execution, env propagates LINCE_AGENT_ID)
command = ["env", "LINCE_AGENT_ID={agent_id}", "<binary>"]
```

---

## 8. File locations

| File | Purpose | Section form |
|------|---------|--------------|
| `~/.agent-sandbox/config.toml` | Sandbox config + per-user agent overrides | `[agents.<key>]` |
| `~/.config/lince-dashboard/agents-defaults.toml` | Installed shipped defaults — always overwritten on update, **do not edit** | `[agents.<key>]` |
| `~/.config/lince-dashboard/config.toml` | Dashboard UI settings + custom agent definitions | `[dashboard]`, `[agents.<key>]` |
| `lince-dashboard/agents-defaults.toml` (repo) | Shipped defaults — **do not edit from this skill** | `[agents.<key>]` |
