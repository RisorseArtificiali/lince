# Agent Examples

Preset agent types, configuration patterns, and examples for adding custom agents to the LINCE Dashboard.

## Default Agent Types

The following agent types ship in `agents-defaults.toml` and are available in the wizard out of the box.

| Key | Display Name | Short | Sandboxed | Native Hooks | Notes |
|-----|-------------|-------|-----------|--------------|-------|
| `claude` | Claude Code | CLA | Yes | Yes | Default. Rich status via `claude-status` pipe. |
| `claude-unsandboxed` | Claude Code (unsandboxed) | CLU | No | Yes | Red `CLU!` label. |
| `codex` | OpenAI Codex | CDX | Yes | Yes | `bwrap_conflict` handled automatically. Maps `agent-turn-complete` → `INPUT`. |
| `bob` | Bob | BOB | Yes | Yes | IBM's CLI. Claude-style hooks (`hook_event_name` contract) but no `Notification` event, so PERMISSION is never shown. Levels: normal + permissive only. |
| `bob-unsandboxed` | Bob (unsandboxed) | BOU | No | Yes | Bare `bob` chat TUI — keeps bob's own approval prompts. |
| `gemini` | Google Gemini CLI | GEM | Yes | No | Wrapper-only (Tier B). |
| `opencode` | OpenCode | OPC | Yes | Yes | Maps OpenCode `session.*` events to canonical statuses. |
| `pi` | Pi (multi-provider) | PI  | Yes | Yes | Provider env vars passed through (`OPENAI_API_KEY`, etc.). Native hook via `lince-pi-hook.ts`. |
| `bash` | Bash Shell | BSH | Yes | No | Raw shell session in the project dir (gh#91). Pinned to `sandbox_level = "normal"`. |
| `bash-unsandboxed` | Bash Shell (unsandboxed) | BSU | No | No | Raw bash on the host, no isolation. |
| `zsh` | Zsh Shell | ZSH | Yes | No | Zsh equivalent of `bash` — typical default on macOS. |
| `zsh-unsandboxed` | Zsh Shell (unsandboxed) | ZSU | No | No | Raw zsh on the host, no isolation. |
| `fish` | Fish Shell | FSH | Yes | No | Fish equivalent of `bash`. |
| `fish-unsandboxed` | Fish Shell (unsandboxed) | FSU | No | No | Raw fish on the host, no isolation. |

Each sandboxed agent ships at `sandbox_level = "normal"` by default. `paranoid` and `permissive` variants are available as commented blocks in the shipped `agents-defaults.toml` — copy a block into `~/.config/lince-dashboard/config.toml` as a complete `[agents.<key>]` entry to add it to the N-picker (do not edit the installed `agents-defaults.toml`; it is overwritten on update). See [Sandbox Levels](dashboard/sandbox-levels.md) for what each level enforces.

### Shell Agents (bash / zsh / fish)

The shell agents (`bash`, `zsh`, `fish`) open a raw shell pane in the project directory (gh#91). They behave like the AI coding agents in every other respect — backend selection (bwrap / nono / unsandboxed), pane lifecycle, focus/hide, dashboard color cues — except for two intentional restrictions:

- **Sandbox level: only `normal`.** Shell agents declare `sandbox_levels = ["normal"]`, so the wizard's *Sandbox Level* step is auto-skipped (a one-row picker would be useless). `paranoid` and `permissive` aren't offered: a paranoid shell with no agent state dir is pointless, and a permissive one is no different from `normal` for an interactive shell.
- **No providers.** Shells don't talk to AI APIs, so the wizard's *Provider* step is also skipped.

What you *do* still pick: backend (any installed: `bwrap`, `nono`, or unsandboxed), name, and project directory.

The `quickstart.sh` installer asks which shells to configure (multi-select, host `$SHELL` pre-checked) and which one to use as the **default shell** for the tiled layout's right-hand placeholder pane. Only the chosen shells are written to `agents-defaults.toml` and `~/.agent-sandbox/agents-defaults.toml`; the default shell is hardcoded into `~/.local/bin/lince-viewport-placeholder`.

## Backend and Level Selection

Each agent is configured with two attributes that select its sandbox behavior at runtime:

- `sandbox_backend` — `"bwrap"` (Linux) or `"nono"` (macOS, also available on Linux). Defaults to bwrap on Linux and nono on macOS; can be overridden per agent.
- `sandbox_level` — `"paranoid"` | `"normal"` | `"permissive"` (or any custom name backed by a `<name>.toml` profile fragment). Defaults to `"normal"`.

```toml
[agents.claude]
sandbox_level = "normal"
# sandbox_backend = "nono"   # uncomment to force nono on Linux
```

The dashboard plugin synthesizes the launch command from `(agent_type, sandbox_backend, sandbox_level)` — the legacy `command` field is kept as a fallback for entries without `sandbox_level`.

The `-unsandboxed` variants (e.g. `claude-unsandboxed`) bypass agent-sandbox entirely. Use them only in trusted environments.

## Unsandboxed Mode

Agents with `sandboxed = false` run without any LINCE-managed isolation. The dashboard makes this visually obvious:

- A red `!` suffix on the type label in every table row (e.g. `CLU!`).
- A red `[NON-SANDBOXED]` tag in the Zellij pane title.
- A red `[NON-SANDBOXED]` warning in the detail panel.

Use unsandboxed mode only in trusted environments where sandbox restrictions are impractical. Unsandboxed agents still support providers (env-var bundles) -- the dashboard uses `env -u VAR1 VAR2=val ...` to set and unset environment variables cleanly.

## Adding a Custom Agent

### Automatic: /lince-add-supported-agent Skill

The easiest way to add a new agent is the `/lince-add-supported-agent` skill. Run the target agent outside the dashboard, invoke `/lince-add-supported-agent`, and the agent describes its own requirements. The skill generates correct TOML for both sandbox and dashboard configs.

The skill organises agents into a three-tier model — pick the tier **first**:

- **Tier A — Native hooks**: agent emits lifecycle events through a hook script and shows `Running / INPUT / PERMISSION / Stopped`.
- **Tier B — Wrapper-only**: no native events, dashboard shows `-` (Unknown) for the agent's lifetime. Honest, not broken.
- **Tier C — User contribution**: everything the skill produces, written to the user's `$HOME` (never the repo).

See the skill's `SKILL.md` and [CONTRIBUTING.md](https://github.com/RisorseArtificiali/lince/blob/main/CONTRIBUTING.md) for the full tier table.

For ongoing configuration changes (providers, sandbox levels, API keys, diagnostics), use the **`/lince-configure` skill** — a natural-language interface backed by the `lince-config` CLI that supports both conversational and guided-menu interaction.

See the [Multi-Agent Guide](https://github.com/RisorseArtificiali/lince/blob/main/lince-dashboard/MULTI-AGENT-GUIDE.md) for the full flow and examples.

### Manual Configuration

To add a custom agent manually:

1. Choose a unique key (lowercase, hyphens allowed).
2. Add an `[agents.<key>]` section to `~/.config/lince-dashboard/config.toml`.
3. Set the required fields: `command`, `pane_title_pattern`, `status_pipe_name`, `display_name`, `short_label`, `color`, `sandboxed`, `has_native_hooks`.
4. If `has_native_hooks = true`, add an `[agents.<key>.event_map]` section translating the agent's native event names to canonical LINCE statuses (`running`, `input`, `permission`, `stopped`).
5. Optionally set `env_vars`, `home_ro_dirs`, `providers` (legacy `profiles`), etc.
6. Restart the dashboard. The new type appears in the wizard.

No code changes or recompilation required.

#### Example: Tier A entry modelled on `claude` from `agents-defaults.toml`

```toml
[agents.claude]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}"]
pane_title_pattern = "agent-sandbox"
status_pipe_name = "claude-status"
display_name = "Claude Code"
short_label = "CLA"
color = "blue"
sandboxed = true
has_native_hooks = true
home_ro_dirs = ["~/.claude/"]
providers = ["__discover__"]
sandbox_level = "normal"

# Translate Claude's native hook events to canonical LINCE statuses.
# Canonical values: running | input | permission | stopped.
[agents.claude.event_map]
PreToolUse = "running"
PostToolUse = "running"
SessionStart = "running"
UserPromptSubmit = "running"
Stop = "stopped"
idle_prompt = "input"
permission_prompt = "permission"
```

For a wrapper-only (Tier B) agent, set `has_native_hooks = false` and omit the `event_map` block — the dashboard injects `lince-agent-wrapper` automatically and shows `-` until the process exits (`Stopped`).

## Example: Simple Bash Agent

A minimal custom agent that runs a bash automation script inside the sandbox.

**Dashboard config** (`~/.config/lince-dashboard/config.toml`):

```toml
[agents.bash-helper]
command = ["agent-sandbox", "run", "-a", "bash", "-p", "{project_dir}", "--id", "{agent_id}"]
pane_title_pattern = "bash"
status_pipe_name = "lince-status"
display_name = "Bash Helper"
short_label = "BSH"
color = "white"
sandboxed = true
has_native_hooks = false
```

Since `has_native_hooks = false`, the dashboard automatically wraps the command with `lince-agent-wrapper` to emit the `stopped` event on exit. The agent shows `-` (Unknown) while running — that is the expected Tier B state.

In the wizard, this agent appears as:

```
  > Bash Helper (bash-helper)
```

After spawning, the table shows:

```
 1  BSH  bash-agent-1      -
```

## Example: Agent with Multiple Providers

Claude Code can connect to different providers (Anthropic direct, Vertex AI, etc.) using **provider** entries (env-var bundles — gh#81 renamed these from "profiles" to disambiguate from sandbox isolation profiles). This example shows how to configure provider switching for both sandboxed and unsandboxed modes.

**Provider entries** in `~/.agent-sandbox/config.toml`:

```toml
[claude.providers.anthropic]
description = "Anthropic Direct API"
env_unset = ["CLAUDE_CODE_USE_VERTEX", "CLOUD_ML_REGION"]

[claude.providers.anthropic.env]
ANTHROPIC_API_KEY = "sk-ant-..."

[claude.providers.vertex]
description = "Vertex AI"
env_unset = ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]

[claude.providers.vertex.env]
CLAUDE_CODE_USE_VERTEX = "1"
CLOUD_ML_REGION = "us-east5"
```

**Dashboard config** for the unsandboxed variant (`~/.config/lince-dashboard/config.toml`):

```toml
[agents.claude-unsandboxed]
command = ["claude"]
pane_title_pattern = "claude"
status_pipe_name = "claude-status"
display_name = "Claude Code (unsandboxed)"
short_label = "CLU"
color = "red"
sandboxed = false
has_native_hooks = true
providers = ["__discover__"]   # legacy name `profiles` is also accepted
```

The `env_unset` field is critical for unsandboxed agents. Because they inherit the full host environment, switching from Anthropic to Vertex requires **unsetting** `ANTHROPIC_API_KEY` before **setting** `CLAUDE_CODE_USE_VERTEX`. Without `env_unset`, both keys would be present and the agent could pick the wrong provider.

For sandboxed agents, `env_unset` is a no-op because `agent-sandbox` uses `--clearenv` to start from a blank environment.

> Pre-#81 configs spelled these `[profiles.*]` / `[<agent>.profiles.*]`. The
> legacy form still works (with a one-shot deprecation note); run
> `agent-sandbox migrate-providers` to rewrite the file in place.

## Handling bwrap Conflicts

Some agents (like Codex) use bubblewrap internally. Nesting bwrap fails, so the agent's inner sandbox must be disabled before wrapping it in the LINCE bwrap jail. The default `[agents.codex]` entry handles this automatically:

1. Set `bwrap_conflict = true` on the agent type.
2. Set `disable_inner_sandbox_args` to the arguments that disable the agent's internal sandbox.

```toml
[agents.codex]
sandboxed = true
bwrap_conflict = true
disable_inner_sandbox_args = ["--sandbox", "danger-full-access"]
sandbox_level = "normal"
```

The sandbox injects `--sandbox danger-full-access` into the Codex command, disabling its internal bwrap before wrapping it in the LINCE bwrap jail.

**Dry-run verification**: Always verify the final command with `--dry-run` before first use:

```bash
agent-sandbox run -a codex -p ~/project --dry-run
# Output shows: ... codex --full-auto --sandbox danger-full-access
```

## Status Reporting

### Agent States

The dashboard models every agent with one of five canonical states:

| State | Color | Meaning |
|-------|-------|---------|
| `-` (Unknown) | Dim gray | Agent has no native hooks, or hasn't reported yet |
| `Running` | Green | Agent is actively working |
| `INPUT` | Bold yellow | Agent is waiting for user input |
| `PERMISSION` | Bold red | Agent is asking for approval |
| `Stopped` | Dim | Agent process has exited (optional exit code shown) |

Tier B (wrapper-only) agents stay at `-` for their entire run, switching to `Stopped` when the process exits. Tier A agents transition through `Running`, `INPUT`, and `PERMISSION` driven by their hook script.

### Hook Contract

The dashboard accepts a single minimal JSON message per write to the agent's Zellij pipe:

```json
{"agent_id": "<id>", "event": "<native_event_name>"}
```

- `agent_id` — value of `$LINCE_AGENT_ID`, set by the dashboard when spawning the agent.
- `event` — the **native** event name (e.g. `PreToolUse`, `idle_prompt`, `agent-turn-complete`). The hook MUST NOT translate the event itself — translation happens dashboard-side via `[agents.<key>.event_map]`.

No other fields are accepted: token counts, tool names, subagent counters and similar rich payload fields were removed in the m-15 simplification. See the skill's `SKILL.md` for the full contract.

### Native Hooks

Per-agent hook scripts live under `lince-dashboard/hooks/` and are installed via the matching `install-<agent>-hooks.sh` script (`install-claude-hooks.sh`, `install-codex-hooks.sh`, `install-bob-hooks.sh`, `install-opencode-hooks.sh`, `install-pi-hooks.sh`). Each script:

1. Writes the hook binary/script.
2. Wires it into the target agent's native event system (Claude's `~/.claude/settings.json`, Codex's `notify`, Bob's `~/.bob/settings/settings.json`, OpenCode events, Pi extension).
3. The hook emits the minimal JSON above to the appropriate Zellij pipe (`claude-status` or `lince-status`).

### lince-agent-wrapper

For agents with `has_native_hooks = false`, the dashboard automatically injects `lince-agent-wrapper` around the agent command. The wrapper sends a `stopped` event when the agent process exits (any reason) and is transparent to the agent — it does not touch stdin or stdout. The dashboard keeps these agents at `-` until that signal arrives.

### Custom event_map

Agents with native hooks declare a mapping from their native event names to canonical LINCE statuses:

```toml
[agents.my-agent.event_map]
"agent_working" = "running"
"agent_done" = "stopped"
"needs_input" = "input"
"needs_approval" = "permission"
```

The left side is the native event string the hook forwards. The right side is one of the four canonical values: `running`, `input`, `permission`, `stopped`. Events without a mapping leave the previous status unchanged.

## See Also

- [Usage Guide](dashboard/usage-guide.md) -- how to operate the dashboard
- [Configuration Reference](dashboard/config-reference.md) -- all config keys and their defaults
- [Sandbox CLI Reference](sandbox/cli-reference.md) -- the `agent-sandbox` command
- [lince-config CLI](https://github.com/RisorseArtificiali/lince/blob/main/lince-config/README.md) -- structured CLI for reading and editing LINCE configuration
- [Multi-Agent Guide](https://github.com/RisorseArtificiali/lince/blob/main/lince-dashboard/MULTI-AGENT-GUIDE.md) -- migration guide for multi-agent support
