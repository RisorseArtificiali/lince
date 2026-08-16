# Usage Guide

How to launch, navigate, and operate the LINCE Dashboard for multi-agent management inside Zellij.

## Launching

Start the dashboard with the `lince` shell alias (installed by `install.sh`):

```bash
lince
```

For the tiled (3-pane) layout:

```bash
lince            # tiled is the default
lince-floating   # floating overlay layout
```

This opens Zellij with the dashboard layout. The plugin loads in a dedicated pane, ready to spawn and manage agents. If a `.lince-dashboard` state file exists in the current directory, saved agents are automatically restored.

For the tiled layout variant:

```bash
zellij --layout ~/.config/zellij/layouts/dashboard-tiled.kdl
```

## Keybindings

### Normal Mode

| Key | Action |
|-----|--------|
| `n` | Show inline name prompt, then spawn agent with that name |
| `N` (Shift+N) | Open the agent creation wizard |
| `r` | Rename the selected agent |
| `x` | Kill (stop) the selected agent and close its pane |
| `f` | Focus: show the selected agent's pane |
| `Enter` | Toggle detail panel for the selected agent |
| `h` / `Esc` | Hide: return focus from agent pane to dashboard |
| `Q` | Save agent state to `.lince-dashboard` and quit Zellij |
| `j` / `Down` | Select next agent in list |
| `Up` | Select previous agent in list |
| `]` | Focus next agent directly (without returning to dashboard) |
| `[` | Focus previous agent directly |
| `i` | Toggle info/detail panel |

### Inline Name Prompt

Pressing `n` shows a blue prompt bar at the bottom of the dashboard:

```
Name: my-agent          (default: agent-3)  [Enter] OK  [Esc] Cancel
```

- Type a custom name or press `Enter` to accept the default (`agent-N`).
- `Esc` cancels without spawning.
- Provider and project directory use config defaults. Use `N` (wizard) for full control.

### Wizard Mode

Pressing `N` (Shift+N) opens a multi-step wizard. Navigation keys:

| Key | Action |
|-----|--------|
| `Enter` | Advance to the next step |
| `Backspace` | Go back to the previous step |
| `Esc` | Cancel the wizard |
| `j` / `k` | Move selection in list steps |

### Quick Select

Keys `1` through `9` focus the corresponding agent by its row number in the table. This is the fastest way to jump to a specific agent.

## Agent Creation Wizard

The wizard (`N`) walks through up to seven steps to create a new agent
(steps that are not applicable are auto-skipped — e.g. `Sandbox Backend`
when only one is installed, `Sandbox Level` for unsandboxed agents,
`Provider` for agent types with no providers configured).

**Step 1: Agent Type** -- Select from available agent types using `j`/`k`. Sandboxed agents are shown in green; unsandboxed agents are shown in red. Skipped when only one agent type is configured.

**Step 2: Sandbox Backend** -- Pick `bwrap` (agent-sandbox) or `nono`. Skipped when only one backend is detected on this host. Selecting "no sandbox" routes to the agent type's `<base>-unsandboxed` entry.

**Step 3: Sandbox Level (Profile)** -- Pick the isolation posture: `paranoid`, `normal`, `permissive`, or any custom level discovered on disk. This is the **sandbox profile** axis (gh#81) — the wizard label is "Sandbox Level" but the value also appears as `Profile:` in the detail pane. Skipped for unsandboxed runs.

**Step 4: Agent Name** -- Text input for a custom name. Leave empty and press `Enter` to accept the auto-generated default (e.g. `agent-3`).

**Step 5: Provider** -- Conditional step, shown only when the selected agent type has providers configured (`providers = ["__discover__"]` or an explicit list in `agents-defaults.toml`). Pick a provider name (env-var bundle: `vertex`, `anthropic`, `zai`, …) discovered from `~/.agent-sandbox/config.toml`. The Provider axis is **independent** of Sandbox Level — combine freely. Was named "Profile" pre-#81.

**Step 6: Project Directory** -- Text input for the working directory path. Tab-completion is available. Defaults to the directory where `lince` was launched.

**Step 7: Confirm** -- Review all settings (Type / Backend / Profile / Name / Provider / Dir). Press `Enter` to create the agent, or `Backspace` to go back and change a setting.

## Agent Lifecycle

1. Press `n` (name prompt) or `N` (wizard) to spawn an agent.
2. The dashboard creates panes using the configured command for the selected agent type. Panes are hidden by default.
3. The agent appears in the table as `-` (Unknown, dim gray) until a hook reports otherwise.
4. Status hooks report via Zellij pipe. The status updates to **Running** (green) when the agent starts working.
5. When the agent needs user input, the status shows **INPUT** (bold yellow).
6. When the agent asks for permission/approval, the status shows **PERMISSION** (bold red).
7. Press `f` to show the agent's pane. Interact with the agent, then press `h` to hide it.
8. Press `Enter` to view the detail panel (project dir, profile, provider, elapsed time).
9. Press `x` to kill the agent and close its pane. Status becomes **Stopped** (dim).

### Agent Statuses

| Status | Color | Meaning |
|--------|-------|---------|
| `-` (Unknown) | Dim gray | Agent has no native hooks, or hasn't reported yet |
| Running | Green | Agent is actively working |
| INPUT | Bold yellow | Agent is waiting for user input |
| PERMISSION | Bold red | Agent is asking for approval |
| Stopped | Dim | Agent process has exited (optional exit code shown) |

These are the only five canonical states. Tier B (wrapper-only) agents stay at `-` until they exit; Tier A agents (Claude, Codex, OpenCode, Pi) transition through the rich states via their hook scripts.

## Agent Detail Panel

Press `i` to toggle a detail panel below the table. It displays:

- **Agent type** -- display name with color. Red `[UNSANDBOXED]` warning if applicable.
- **Status** -- current status with color coding (`-`, Running, INPUT, PERMISSION, Stopped).
- **Profile** -- the sandbox isolation level in use (paranoid / normal / permissive / custom). `(default)` for unsandboxed agents.
- **Provider** -- the provider env-var bundle in use (e.g. `anthropic`, `vertex`, `zai`). `(default)` if none was selected. **Distinct from Profile (gh#81).**
- **Project directory** -- the working directory path.
- **Started at** -- timestamp when the agent was spawned.

Press `Enter` again to close the panel. `f` still focuses the agent pane.

## Swimlane Grouping

When agents span multiple project directories, the dashboard automatically groups them into swimlanes with colored headers:

```
 #  Agent Name             Status
 +-- ~/project/lince -----------------------------------
 1  CLA  agent-1 [fullstack]  Running
 2  CDX  agent-2              INPUT
 3  CLU! quick-test           Running        <-- unsandboxed
 +-- ~/project/other-app --------------------------------
 4  GEM  agent-3              Stopped
```

- Every row shows a 3-char type label (e.g. `CLA`, `CDX`, `GEM`) in the agent's configured color.
- Unsandboxed agents show a red `!` suffix (e.g. `CLU!`).
- Agents are grouped by `project_dir` and sorted by name within each group.
- Swimlane headers show shortened paths (`~` replaces `$HOME`).
- When all agents share the same directory, no headers are shown (flat list).
- Group names appear as dim suffixes when set: `agent-1 [web-stack]`.
- Navigation (`j`/`k`) moves through agents only. Headers are visual-only separators.

## Session Save and Restore

Press `Q` to save the current agent configuration and quit Zellij. On next launch from the same directory, agents are automatically re-spawned with their saved names, providers, and project directories. (Pre-#81 saved-state files use `profile` as the field name; they continue to load thanks to a serde alias on `provider`. Pre-m-15 state files may also include legacy fields like `tokens_in` / `tokens_out` — they are now ignored.)

- State is saved to `.lince-dashboard` in the directory where `lince` was launched.
- Different directories maintain independent state. Launch from `~/project-a` and `~/project-b` for separate sessions.
- The state file is kept after restore, so an ungraceful quit (`Ctrl-Q`) still preserves the last saved state.
- If no `.lince-dashboard` file exists, the dashboard starts empty.

## Tiled Pane Layout

Set `agent_layout = "tiled"` in `config.toml` and launch with `lince` for a fixed three-pane layout:

```
┌──────────────┬─────────────────────┐
│              │                     │
│  Dashboard   │  Shell / VoxCode    │
│  plugin      │                     │
├──────────────┤                     │
│  Agent       │                     │
│  viewport    │                     │
└──────────────┴─────────────────────┘
```

- The dashboard plugin occupies the top-left pane (A).
- The bottom-left pane (C) is the **agent viewport** — an ASCII art placeholder that is covered by the focused agent's floating pane.
- The right column (B) is the agent viewport — covered by the focused agent's floating pane.
- Press `f` to focus an agent — its pane overlays the viewport. Press `h` to unfocus and return to the placeholder.

## Voice Relay

[VoxCode](https://github.com/RisorseArtificiali/voxcode) runs in the fixed bottom-left pane and provides voice-to-text input for agents. When configured with pipe mode, transcribed text flows through the dashboard to the active agent:

```
VoxCode --> zellij pipe --name "voxcode-text" --> Dashboard Plugin --> agent pane
```

To enable pipe mode, set in your VoxCode config:

```toml
[zellij]
use_pipe = true
```

When `use_pipe = false` (default), VoxCode uses the legacy focus-switch method, which works without the dashboard.

**Target priority** for voice relay:

1. Focused agent (if one is currently shown).
2. Selected agent (highlighted in the table).
3. No agent available -- error message in the command bar.

## Status Detection

### Pipe Mode (default)

Agents report status via `zellij pipe` using their configured `status_pipe_name`. This is the recommended method. Every payload is the minimal contract:

```json
{"agent_id": "<id>", "event": "<native_event_name>"}
```

The dashboard maps the native event name to a canonical status (`running` / `input` / `permission` / `stopped`) via the agent's `[agents.<key>.event_map]` block in `agents-defaults.toml` (or the user's override in `config.toml`).

- **Claude Code** (`claude-status` pipe): Hook script forwards Claude's native events (`PreToolUse`, `Stop`, `idle_prompt`, `permission_prompt`, …) without translating them.
- **Codex** (`lince-status` pipe): The Codex `notify` hook forwards `agent-turn-complete` (mapped to `input`).
- **OpenCode / Pi** (`lince-status` pipe): Per-agent hook scripts forward each agent's native events.
- **Tier B agents** (`lince-status` pipe): `lince-agent-wrapper` only emits a `stopped` event on process exit.

```bash
# Claude Code native hook example (the dashboard does the translation):
zellij pipe --name "claude-status" --payload '{"agent_id":"agent-1","event":"PreToolUse"}'

# lince-agent-wrapper example (stop only):
zellij pipe --name "lince-status" --payload '{"agent_id":"agent-5","event":"stopped"}'
```

Hook scripts and their installers live in `lince-dashboard/hooks/`: `install-claude-hooks.sh`, `install-codex-hooks.sh`, `install-bob-hooks.sh`, `install-opencode-hooks.sh`, `install-pi-hooks.sh`.

### File Mode (fallback)

Status files are written to `/tmp/lince-dashboard/{agent_id}.state`. The plugin polls every 2 seconds.

Set `status_method = "file"` in `config.toml` to use this mode. Use it only when pipe mode is unavailable.

## Sandbox Integration

For status reporting to work inside `agent-sandbox`, the sandbox must pass through Zellij environment variables. Add to your sandbox config (`~/.agent-sandbox/config.toml`):

```toml
[env]
passthrough = ["ZELLIJ", "ZELLIJ_SESSION_NAME", "LINCE_AGENT_ID"]
```

Agent-specific environment variables (e.g. `OPENAI_API_KEY` for Codex) are set via the `env_vars` field in the agent type configuration and passed through automatically.

## Troubleshooting

### Ctrl+Shift+C kills agent (Terminator + Zellij)

When running agents inside the dashboard on **Terminator**, pressing **Ctrl+Shift+C** to copy also delivers a SIGINT to the agent in the focused pane, interrupting it. The same key combo behaves correctly in Terminator without Zellij — the conflict only appears in the Terminator + Zellij combination.

**Fix**: remap Terminator's copy shortcut to a key that doesn't include Ctrl+C.

Option 1 — Edit `~/.config/terminator/config`:
```ini
[keybindings]
copy = <Primary>Insert
```
Restart Terminator. `Ctrl+Insert` will copy without sending SIGINT.

Option 2 — Via GUI: **Terminator → Preferences → Keybindings → copy_clipboard**, bind it to `Ctrl+Insert` or another shortcut that doesn't include Ctrl+C.

## See Also

- [Configuration Reference](dashboard/config-reference.md) -- all config keys and their defaults
- [Agent Examples](dashboard/agent-examples.md) -- preset agents and custom configuration examples
- [Sandbox CLI Reference](sandbox/cli-reference.md) -- the `agent-sandbox` command
- [lince-config CLI](https://github.com/RisorseArtificiali/lince/blob/main/lince-config/README.md) -- structured CLI for reading and editing LINCE configuration
- [Multi-Agent Guide](https://github.com/RisorseArtificiali/lince/blob/main/lince-dashboard/MULTI-AGENT-GUIDE.md) -- migration guide for multi-agent support
