# Usage Guide

How to launch, navigate, and operate the LINCE Dashboard for multi-agent management inside Zellij.

## Launching

Start the dashboard with the `lince` shell alias (installed by `install.sh`):

```bash
lince
```

Fresh installations use the minimal preset: a compact sidebar, no frames or
standard Zellij bars, and a persistent two-row attention bar. Existing configurations
without a preset retain the classic presentation on upgrade.

```bash
lince-dashboard-launch --preset minimal
lince-dashboard-launch --preset statusline  # controller opened with Alt+d
lince-dashboard-launch --preset classic
lince-floating                            # floating agent window variant
```

The plugin restores saved agents when `.lince-dashboard` exists in the launch
directory. Start in a fresh directory for an empty session. Use the launcher to
apply presets and the LINCE session config; direct `zellij --layout` launches
bypass those settings. See [Views and Themes](dashboard/views-and-themes.md)
for density, sidebar width, frame overrides, palettes and upgrade behavior.

## Keybindings

### Normal Mode

| Key | Action |
|-----|--------|
| `n` | Show inline name prompt, then spawn agent with that name |
| `N` (Shift+N) | Open the agent creation wizard |
| `r` | Rename the selected agent |
| `x` | Kill (stop) the selected agent and close its pane |
| `f` | Focus: show the selected agent's pane |
| `Enter` | Focus the selected agent |
| `h` / `Esc` | Hide: return focus from agent pane to dashboard |
| `Alt+q` / `Q` | Save agent state and quit (`Alt+q` works from any pane) |
| `q` in the `Alt+d` list | Quit without saving |
| `j` / `Down` | Select next agent in list |
| `k` / `Up` | Select previous agent in list |
| `]` | Focus next agent directly (without returning to dashboard) |
| `[` | Focus previous agent directly |
| `i` | Toggle info/detail view (`PageUp` / `PageDown` scroll) |
| `?` | Show help |
| `Alt+d` | Open the expanded list popup from any pane |
| `Alt+i` / `Alt+h` | Open information / help directly |
| `Alt+s` | Toggle the sidebar (minimal/statusline) |
| `Alt+n` | Open the creation wizard from any pane |
| `Alt+1`–`Alt+9` | Focus an agent from any pane |
| `Alt+PageUp` / `Alt+PageDown` | Cycle agents from any pane |

### Inline Name Prompt

Pressing `n` opens a name prompt (a popup in the minimal view):

```
Name: my-agent          (default: myproject-3)  [Enter] OK  [Esc] Cancel
```

- Type a custom name or press `Enter` to accept the default (`project-N`).
- `Esc` cancels without spawning.
- Provider and project directory use config defaults. Use `N` (wizard) for full control.

### Wizard Mode

Pressing `Alt+n` anywhere or `N` (Shift+N) in the list opens a multi-step wizard.
Press `n` immediately on opening or in a selection/review step to use the defaults and enter only a name;
name and path text fields continue accepting `n` as text. Navigation keys:

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

**Step 4: Agent Name** -- Text input for a custom name. Leave empty and press `Enter` to accept the auto-generated default (e.g. `myproject-3`).

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
7. Press `f` to show the agent's pane. Interact with the agent, then press `Alt+d` to return to the controller.
8. Press `i` to view details (full name, project directory, sandbox and provider).
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

Press `i` to open the detail view, shown in a larger popup in the minimal preset. It displays:

- **Agent type** -- display name with color. Red `[UNSANDBOXED]` warning if applicable.
- **Status** -- current status with color coding (`-`, Running, INPUT, PERMISSION, Stopped).
- **Profile** -- the sandbox isolation level in use (paranoid / normal / permissive / custom). `(default)` for unsandboxed agents.
- **Provider** -- the provider env-var bundle in use (e.g. `anthropic`, `vertex`, `zai`). `(default)` if none was selected. **Distinct from Profile (gh#81).**
- **Project directory** -- the working directory path.
- **Started at** -- timestamp when the agent was spawned.

Use `PageUp`/`PageDown` to scroll long details. Press `i` or `Esc` to close them; `Enter` or `f` focuses the agent.

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
- The full table omits headers for a single directory; the compact view retains a project heading.
- Group names appear as dim suffixes when set: `agent-1 [web-stack]`.
- Navigation (`j`/`k`) moves through agents only. Headers are visual-only separators.

## Session Save and Restore

Press `Alt+q` from any pane (or `Q` in the list) to save the current agent configuration and quit after the write succeeds. To quit without saving, press `Alt+d`, then lowercase `q`; previous saved state remains intact. On next launch from the same directory, agents are automatically re-spawned with their saved names, providers, and project directories. (Pre-#81 saved-state files use `profile` as the field name; they continue to load thanks to a serde alias on `provider`. Pre-m-15 state files may also include legacy fields like `tokens_in` / `tokens_out` — they are now ignored.)

- State is saved to `.lince-dashboard` in the directory where `lince` was launched.
- Different directories maintain independent state. Launch from `~/project-a` and `~/project-b` for separate sessions.
- The state file is kept after restore, so an ungraceful quit (`Ctrl-Q`) still preserves the last saved state.
- If no `.lince-dashboard` file exists, the dashboard starts empty.

## Tiled Pane Layout

The launcher defaults to `dashboard-tiled`, with the controller and a shell on
the left and the agent viewport on the right. The selected preset controls the
column width and surrounding bars.

```text
Controller       | Agent viewport
                 | (focused agent)
-----------------|
Shell / VoxCode  |
-----------------+----------------
Attention row (minimal preset)
```

Press `Enter` or `f` in the controller to show the selected agent over the right
viewport. `Alt+d` returns to the controller. Resizing the viewport updates agent
geometry. The VoxCode variant replaces the lower-left shell with the voice pane:

```bash
lince-dashboard-launch --preset minimal --layout dashboard-tiled-vox
```

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
