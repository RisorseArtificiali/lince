# Multi-Agent Support — What Changed

This guide is for existing lince-dashboard + agent-sandbox users. It covers what's new, what changed, and what you need to do (spoiler: almost nothing).

## TL;DR

The dashboard and sandbox now support any CLI coding agent — not just Claude Code. Agents are defined purely in TOML config. Adding a new agent requires zero code changes. Your existing setup continues to work unchanged.

## What's New

### 1. The sandbox runs any agent

The `agent-sandbox` now accepts `--agent` (or `-a`) to specify which agent to run:

```bash
agent-sandbox run -p ~/project/foo --id agent-1                  # Claude Code
agent-sandbox run -a codex -p ~/project/foo --id agent-2         # OpenAI Codex
agent-sandbox run -a gemini -p ~/project/foo --id agent-3        # Google Gemini CLI
agent-sandbox run -a opencode -p ~/project/foo --id agent-4      # OpenCode
agent-sandbox run -a aider -p ~/project/foo --id agent-5         # Aider
agent-sandbox run -a pi -p ~/project/foo --id agent-6            # Pi (https://pi.dev)
```

The `--id` flag sets `LINCE_AGENT_ID` inside the sandbox, allowing the dashboard to track each agent instance.

Each agent gets proper bwrap sandboxing with its own config dirs, env vars, and conflict handling — all from config.

### 2. The dashboard manages mixed agent types

The wizard (`Shift+N`) walks the user through two orthogonal axes — *which* agent to run and *how* to isolate it — across separate steps.

**Step 1 — Agent Type.** Pick the binary. Only base agents are listed (deduplicated via `base_agents()` in `config.rs`); their `<base>-unsandboxed` companions are not shown here and are reached instead from the Sandbox Backend step below.

```
┌─────────── New Agent Wizard ──────────────┐
│                                           │
│  Step 1/N: Agent Type                     │
│                                           │
│  > Claude Code                            │
│    OpenAI Codex                           │
│    Google Gemini CLI                      │
│    OpenCode                               │
│    Pi                                     │
│    Bash Shell                             │
│    Zsh Shell                              │
│    Fish Shell                             │
│                                           │
│  [j/k] Select  [Enter] Next  [Esc] Cancel │
└───────────────────────────────────────────┘
```

**Step 2 — Sandbox Backend.** Pick *how* to isolate the chosen agent. Options reflect what's installed on the host plus the agent's `[agents.<name>-unsandboxed]` companion when present.

```
┌─────────── New Agent Wizard ──────────────┐
│                                           │
│  Step 2/N: Sandbox Backend                │
│                                           │
│  > nono                                   │
│    none  (unsandboxed — red `!` in table) │
│                                           │
└───────────────────────────────────────────┘
```

Selecting `none` rewrites the effective agent type to `<base>-unsandboxed` internally (e.g. `claude` → `claude-unsandboxed`) — the table shows the short label of that companion (e.g. `CLU!`) and skips the subsequent Sandbox Level step. Selecting a sandboxed backend (`nono`, or `agent-sandbox`/bwrap on Linux) keeps the base agent type and continues to Step 3.

**Step 3 — Sandbox Level.** Only shown when a sandboxed backend is selected. Standard options are `paranoid` / `normal` / `permissive`; custom levels are picked up from any `~/.config/nono/profiles/lince-<agent>-<level>.json` or `~/.agent-sandbox/profiles/<agent>-<level>.toml` files present on disk. See `docs/documentation/dashboard/sandbox-levels.md`.

Subsequent steps (Provider, Name, Project dir, Confirm) follow the same skip rules — Provider appears only when the resolved agent type has providers configured, Name and Project dir are always shown, Confirm closes the wizard.

If only one agent type or one sandbox backend is available, the corresponding step is skipped automatically.

The agent table now always shows an **Agent column** with the 3-char type label and a per-agent color. Unsandboxed agents are flagged with a red `!` suffix:

```
 #  Agent Name             Status
 ┌ ~/project/lince ─────────────────────────
 1  CLA  fullstack        Running
 2  CDX  codex-review     INPUT
 3  CLU! quick-test       Running       ← unsandboxed (red "!")
 ┌ ~/project/other ─────────────────────────
 4  GEM  gemini-docs      Stopped
```

The `!` marker makes it immediately obvious which agents are running without bwrap protection — no need to open the detail panel.

### 3. Unsandboxed mode

You can now run Claude Code (or any agent) without bwrap:

```
 2  CLU! quick-test       Running
```

Unsandboxed agents show a red `!` after their type label in every table row, a `[UNSANDBOXED]` warning in the detail panel, and `[NON-SANDBOXED]` in the Zellij pane title. Use this for trusted projects or systems without bwrap.

**Profiles work for unsandboxed agents too.** When a profile is selected for a non-sandboxed agent, the dashboard:

1. **Unsets** conflicting env vars listed in the profile's `env_unset` (e.g. `ANTHROPIC_API_KEY` when switching to Vertex)
2. **Sets** the profile's env vars (API keys, endpoints, region, etc.)
3. Launches the agent via `env -u VAR1 -u VAR2 VAR3=val ... <command>`

This prevents provider confusion when multiple API keys exist in the host environment. The key difference from sandboxed agents:

- **Sandboxed agents**: `agent-sandbox` does `--clearenv` — starts from a clean environment with no env leakage. Profile env vars are set explicitly into the clean namespace.
- **Non-sandboxed agents**: Inherit the full host environment. Profiles help by setting the right vars AND unsetting conflicting ones via `env_unset`, so the agent sees only the intended provider configuration.

### 4. Status reporting for non-Claude agents

Claude Code has native hooks that report rich status (tool usage, tokens, subagents). Most other agents don't. `lince-agent-wrapper` fills that gap:

- Sends `start` event when the agent launches
- Sends `stopped` event when the agent exits (any reason)
- Transparent to the agent — doesn't touch stdin/stdout

The dashboard injects this wrapper automatically for agents with `has_native_hooks = false`. You don't need to do anything.

Codex can also use its native `notify` command hook to emit `idle` when a turn completes. The dashboard install/update scripts configure that automatically when possible.

Pi (`@mariozechner/pi-coding-agent`) supports lince's full status protocol via a TypeScript extension installed at `~/.pi/agent/extensions/lince-pi-hook.ts`. The extension subscribes to Pi's `session_start`, `turn_start`, `tool_call`, `turn_end`, and `session_shutdown` events and emits the same JSON status schema the dashboard parses for Claude. As a result Pi runs with `has_native_hooks = true` — current tool name and idle/running transitions appear in real time, identical to Claude Code. The dashboard install/update scripts copy the extension automatically.

### 5. Configurable event mapping

Custom agents can define their own event vocabulary via `event_map` in config. The dashboard maps custom event strings to its internal status values:

```toml
[agents.my-agent.event_map]
"agent_ready" = "idle"
"agent_working" = "running"
"agent_done" = "stopped"
"needs_approval" = "permission"
```

## What You Need to Do

### If you just use Claude Code

**Nothing.** Your setup is fully backward compatible. The `[claude]` config section still works. Default behavior is identical.

### If you want to try other agents

1. **Update your installation:**
   ```bash
   cd lince-dashboard && ./update.sh
   ```
   This installs `lince-agent-wrapper` and `agents-defaults.toml`.

2. **Install the agent CLI** you want to use (e.g., `npm install -g @openai/codex`, `pip install aider-chat`).

3. **Set the API key** if needed:
   ```bash
   export OPENAI_API_KEY=sk-...    # for Codex
   export GEMINI_API_KEY=...        # for Gemini
   ```

4. **Spawn from the dashboard** via wizard (`Shift+N`) and select the agent type. Each agent has a direct mode and (where applicable) a sandboxed mode:
   ```bash
   # Direct mode (uses agent's own sandbox if any):
   # Select "OpenAI Codex" in the wizard
   agent-sandbox run -a codex -p ~/project

   # Sandboxed mode (bwrap isolation):
   # Select "OpenAI Codex (sandboxed)" in the wizard
   agent-sandbox run -a codex-bwrap -p ~/project
   ```

That's it. The defaults file already has presets for all supported agents.

### If you want to add a custom agent

#### Option A: Let the agent register itself (recommended)

The `/lince-add-supported-agent` skill lets any AI agent self-configure its own integration. The agent knows what it needs (binary, config dirs, API keys, sandbox behavior); the skill knows the lince config format. Together they generate correct TOML for both sandbox and dashboard.

**How it works**: run the target agent outside the dashboard, invoke the skill, and the agent introspects itself to provide the answers:

```bash
# Example: you're running Kiro and want to add it to the dashboard
# Inside Kiro's CLI, invoke the skill:
/lince-add-supported-agent

# The skill asks Kiro about itself:
#   - Binary name? → "kiro"
#   - Config dir? → "~/.kiro/"
#   - API keys? → "KIRO_API_KEY"
#   - Default args? → ["--auto"]
#   - Uses bwrap internally? → No
#
# Kiro answers these about ITSELF, then the skill generates
# both sandbox and dashboard TOML and writes them to config.
```

The skill is installed automatically by `install.sh` to `~/.claude/skills/lince-add-supported-agent/`. It follows the [agentskills.io](https://agentskills.io) specification, so any agent supporting that standard can use it. For agents without skill support, you can paste the content of `SKILL.md` as a prompt.

The skill is **idempotent** — running it again for the same agent detects the existing config and offers to update rather than duplicate.

#### Option B: Manual configuration

Add a section to your `~/.agent-sandbox/config.toml`:

```toml
[agents.my-agent]
command = "my-agent-cli"
default_args = ["--auto"]
env = { MY_API_KEY = "sk-..." }
home_ro_dirs = [".config/my-agent"]
home_rw_dirs = []
bwrap_conflict = false
disable_inner_sandbox_args = []
```

Then run it: `agent-sandbox run -a my-agent -p ~/project`

For the dashboard to display it properly, also add to your dashboard config:

```toml
[agents.my-agent]
command = ["agent-sandbox", "run", "-a", "my-agent", "-p", "{project_dir}"]
display_name = "My Agent"
short_label = "MYA"
color = "magenta"
sandboxed = true
has_native_hooks = false
pane_title_pattern = "my-agent"
status_pipe_name = "lince-status"
```

## Config Architecture

```
agents-defaults.toml          ← shipped presets (overwritten on update)
  ↓ merged with
config.toml [agents.*]        ← your overrides + custom agents (never overwritten)
```

User config always wins. The defaults file is safe to overwrite on updates because your customizations live in `config.toml`.

### env_vars on agent type vs env on profile

Two layers of env-var configuration interact at agent launch:

1. **`[agents.<name>.env_vars]`** in `agents-defaults.toml` — the *passthrough universe* for that agent type. Every var listed gets forwarded from the host shell into the agent process. Listing a var here whose host value is unset is harmless (it expands to an empty string and is dropped). Use this to declare *which host env vars are eligible* for the agent. For multi-provider agents like Pi, this list is large by design (one entry per supported provider key + base URL + cloud project).
2. **`[<agent>.profiles.<name>]`** in user config — *narrows* the universe per launch. `env` adds or overrides values for this specific run; `env_unset` strips host vars that would otherwise propagate. Use profiles when you want, e.g., "only ZAI active right now, no other provider keys leaking in."

This separation is why `env_unset` is profile-only: the agent type defines what *can* be present; the profile defines what *should* be present for this particular launch. Sandboxed agents (`--clearenv` baseline) only see what `env_vars` + profile `env` explicitly allow; non-sandboxed agents inherit the full host env, and `env_unset` is the tool for trimming it.

### Profile `env_unset` field

Profiles can declare an `env_unset` list to remove conflicting environment variables before the profile's own vars are applied. This is essential for non-sandboxed agents that inherit the full host environment:

```toml
[profiles.vertex]
description = "Vertex AI"
env_unset = ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]  # clean conflicting vars

[profiles.vertex.env]
CLAUDE_CODE_USE_VERTEX = "1"
CLOUD_ML_REGION = "us-east5"
```

For sandboxed agents, `env_unset` is a no-op because `--clearenv` already starts from a blank environment. For non-sandboxed agents, it ensures the host's existing variables don't conflict with the profile's intended provider.

### Agent config fields (sandbox)

| Field | Purpose | Example |
|-------|---------|---------|
| `command` | Binary to execute | `"codex"` |
| `default_args` | Default CLI args | `["--full-auto"]` |
| `env` | Env vars to set | `{ OPENAI_API_KEY = "$OPENAI_API_KEY" }` |
| `home_ro_dirs` | Home dirs to mount read-only | `[".codex", ".config/codex"]` |
| `home_rw_dirs` | Home dirs to mount read-write | `[]` |
| `bwrap_conflict` | Agent uses bwrap internally | `true` for Codex |
| `disable_inner_sandbox_args` | Args to disable inner sandbox | `["--sandbox", "danger-full-access"]` |
| `profiles` | Sandbox profiles for this agent | `["__discover__"]` = auto-discover; `[]` = skip profile step; explicit list restricts choices |

### Agent config fields (dashboard)

All of the above, plus:

| Field | Purpose | Example |
|-------|---------|---------|
| `display_name` | Full name in UI | `"OpenAI Codex"` |
| `short_label` | 3-char table column | `"CDX"` |
| `color` | ANSI color name | `"cyan"` |
| `sandboxed` | Whether bwrap is used | `true` |
| `has_native_hooks` | Agent sends own status | `false` (use wrapper) |
| `pane_title_pattern` | Pane title match string | `"codex"` |
| `status_pipe_name` | Zellij pipe name | `"lince-status"` |
| `event_map` | Custom event → status mapping | `{ "ready" = "idle" }` |

## bwrap Conflict Handling

Some agents (Codex, Claude Code itself) use bwrap internally. Nesting bwrap fails. The sandbox handles this automatically for `-bwrap` variants:

- When `bwrap_conflict = true`, the sandbox appends `disable_inner_sandbox_args` to the agent command
- Example: Codex inside our bwrap (`codex-bwrap`) gets `--sandbox danger-full-access` injected automatically
- Direct variants (codex, gemini, opencode) don't use bwrap at all, so there's no conflict — they run the agent as-is, relying on whatever sandbox the agent provides natively
- You don't need to think about this — it's preconfigured in the defaults

Use `--dry-run` to verify what gets injected:

```bash
agent-sandbox run -a codex-bwrap -p ~/project --dry-run
# Shows: ... codex --full-auto --sandbox danger-full-access
```

## Status Pipes

The dashboard now listens on two pipe names:

| Pipe | Used by | Events |
|------|---------|--------|
| `claude-status` | Claude Code (native hooks) | Rich: idle, running, permission, PreToolUse, tokens, subagents |
| `lince-status` | All other agents (via wrapper) | Lifecycle: start, stopped |

Both pipes are active simultaneously. No configuration needed.

## File Changes Summary

| File | Change |
|------|--------|
| `sandbox/agent-sandbox` | `--agent` flag, `resolve_agent_config()`, `[agents.*]` config |
| `sandbox/agents-defaults.toml` | **New** — presets for claude, codex, gemini, aider, amp |
| `lince-dashboard/plugin/src/config.rs` | `AgentTypeConfig` struct, async loading from TOML |
| `lince-dashboard/plugin/src/types.rs` | `agent_type: String` in AgentInfo, event_map support |
| `lince-dashboard/plugin/src/agent.rs` | Generic spawn with command templates, per-type pane matching |
| `lince-dashboard/plugin/src/main.rs` | Dual pipe listener, wizard agent type step |
| `lince-dashboard/plugin/src/dashboard.rs` | Type column, unsandboxed warning, wizard rendering |
| `lince-dashboard/hooks/lince-agent-wrapper` | **New** — lifecycle wrapper for non-Claude agents |
| `lince-dashboard/install.sh` | Installs wrapper + defaults file |
| `lince-dashboard/update.sh` | Updates wrapper + defaults file |
| `lince-dashboard/uninstall.sh` | Removes wrapper + defaults file |
