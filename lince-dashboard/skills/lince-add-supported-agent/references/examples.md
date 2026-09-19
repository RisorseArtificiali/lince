# Agent Configuration Examples

Real-world configurations from the lince ecosystem, organised by tier.

All examples use the `[agents.<key>]` nested form — that's how the sandbox
config, the shipped dashboard defaults (`agents-defaults.toml`) and the user
dashboard config (`config.toml` `[agents.*]`) all lay out agent entries.
Verify against `lince-dashboard/agents-defaults.toml` in the repo before
copying. User-side entries always go into
`~/.config/lince-dashboard/config.toml` — never into the installed
`agents-defaults.toml`, which is overwritten on update.

---

## Tier A (rich) — Claude Code

Native hooks emit lifecycle events (`PreToolUse`, `Stop`, `idle_prompt`,
`permission_prompt`, …). The dashboard maps every native name into the
canonical set via `event_map`.

### Sandbox config

```toml
[agents.claude]
command = "claude"
default_args = ["--dangerously-skip-permissions"]
env = {}
home_ro_dirs = []
home_rw_dirs = []
bwrap_conflict = false
disable_inner_sandbox_args = []
```

### Dashboard config (shipped: `lince-dashboard/agents-defaults.toml`)

```toml
[agents.claude]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}"]
pane_title_pattern = "agent-sandbox"
status_pipe_name = "claude-status"     # reserved name for Claude
display_name = "Claude Code"
short_label = "CLA"
color = "blue"
sandboxed = true
has_native_hooks = true
home_ro_dirs = ["~/.claude/"]
providers = ["__discover__"]
sandbox_level = "normal"

[agents.claude.event_map]
PreToolUse = "running"
PostToolUse = "running"
SessionStart = "running"
UserPromptSubmit = "running"
Stop = "stopped"
idle_prompt = "input"
permission_prompt = "permission"
```

### Hook script

`lince-dashboard/hooks/claude-status-hook.sh` — installed by
`install-claude-hooks.sh`. The hook emits the **native** event name; the
`event_map` above performs translation.

---

## Tier A (lean) — OpenAI Codex

Codex only fires one notify event (`agent-turn-complete`) on turn completion,
which maps to `input` (waiting for the user's next prompt). All other states
remain unknown because Codex doesn't surface them.

### Sandbox config

```toml
[agents.codex]
command = "codex"
default_args = ["-a", "never"]
env = {}
home_ro_dirs = [".codex"]
home_rw_dirs = []
bwrap_conflict = true
disable_inner_sandbox_args = ["--no-sandbox"]
```

### Dashboard config (shipped)

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

### Hook script

`lince-dashboard/hooks/codex-status-hook.sh` — installed by
`install-codex-hooks.sh`.

---

## Tier B — Google Gemini CLI (no native hooks)

The dashboard shows `-` (Unknown) for Gemini's entire lifetime. No
`event_map`, no hook script.

### Sandbox config

```toml
[agents.gemini]
command = "gemini"
default_args = []
env = {}
home_ro_dirs = [".gemini"]
home_rw_dirs = []
bwrap_conflict = false
disable_inner_sandbox_args = []
```

### Dashboard config (shipped)

```toml
[agents.gemini]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}", "--agent", "gemini"]
pane_title_pattern = "agent-sandbox"
status_pipe_name = "lince-status"
display_name = "Google Gemini CLI"
short_label = "GEM"
color = "blue"
sandboxed = true
has_native_hooks = false             # <-- the Tier B marker
home_ro_dirs = ["~/.gemini/"]
providers = ["__discover__"]
sandbox_level = "normal"

[agents.gemini.env_vars]
GEMINI_API_KEY = "$GEMINI_API_KEY"
```

---

## Tier B — bash / zsh / fish (no native hooks, no providers)

Shells are the simplest case: just a wrapper with `has_native_hooks = false`
and no provider env vars.

```toml
[agents.bash]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}", "--agent", "bash"]
pane_title_pattern = "agent-sandbox"
status_pipe_name = "lince-status"
display_name = "Bash"
short_label = "BSH"
color = "white"
sandboxed = true
has_native_hooks = false
```

---

## Tier C — User-side custom agent

Hypothetical "kiro" agent registered entirely in `$HOME`. Identical schema
to the shipped agents, only the file location differs.

### `~/.agent-sandbox/config.toml`

```toml
[agents.kiro]
command = "kiro"
default_args = ["--headless"]
env = { AWS_ACCESS_KEY_ID = "$AWS_ACCESS_KEY_ID", AWS_SECRET_ACCESS_KEY = "$AWS_SECRET_ACCESS_KEY" }
home_ro_dirs = [".kiro"]
home_rw_dirs = []
bwrap_conflict = false
disable_inner_sandbox_args = []
```

### `~/.config/lince-dashboard/config.toml`

```toml
[agents.kiro]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}", "--agent", "kiro"]
pane_title_pattern = "agent-sandbox"
status_pipe_name = "lince-status"
display_name = "Kiro"
short_label = "KIR"
color = "magenta"
sandboxed = true
has_native_hooks = false    # Tier B: leave it here, promote later if needed
home_ro_dirs = ["~/.kiro/"]
providers = ["__discover__"]
sandbox_level = "normal"

[agents.kiro.env_vars]
AWS_ACCESS_KEY_ID = "$AWS_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY = "$AWS_SECRET_ACCESS_KEY"
```

Promote to Tier A later by writing
`~/.local/share/lince/hooks/kiro-status-hook.sh`, flipping
`has_native_hooks = true`, and adding `[agents.kiro.event_map]`.

---

## Sandbox vs Dashboard config — quick contrast

| Aspect | Sandbox (`~/.agent-sandbox/config.toml`) | Dashboard (`~/.config/lince-dashboard/config.toml` `[agents.*]`) |
|--------|------------------------------------------|--------------------------------------------------------------|
| Section header | `[agents.<key>]` | `[agents.<key>]` (same form) |
| `command` type | string (binary name) | list[string] (full launch template) |
| Env-vars table name | `env` | `env_vars` |
| `home_ro_dirs` format | relative to `~` (`.codex`) | with `~/` prefix (`~/.codex/`) |
| UI fields | none | `display_name`, `short_label`, `color`, `pane_title_pattern`, `status_pipe_name` |
| `has_native_hooks` | N/A | required |
| `event_map` | N/A | Tier A only |
