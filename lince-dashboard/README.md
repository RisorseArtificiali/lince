# LINCE Dashboard

Multi-agent TUI dashboard for managing AI coding agents in [Zellij](https://zellij.dev). A WASM plugin that lets you spawn, monitor, and switch between multiple agents — Claude Code, Codex, Gemini, OpenCode, Aider, and more — all from one terminal pane.

## Overview

New installs use a compact sidebar and a two-row attention bar, with pane frames
and standard Zellij bars hidden. Choose the presentation independently of colors:

```bash
lince-dashboard-launch --preset minimal     # compact sidebar
lince-dashboard-launch --preset statusline  # two rows; Alt+d opens the controller
lince-dashboard-launch --preset classic     # full table and standard bars
```

Existing configurations without a preset retain `classic` on update. `Alt+d` opens
the expanded list, `Alt+i` opens details, and `Alt+h` opens help in bordered popups.
`Alt+s` toggles the 15% sidebar; `Alt+b` cycles the status bar: hidden → left summary → full; `Alt+n` opens the wizard (then `n` for defaults/name only). The bottom
bar identifies waiting agents and sandbox levels by color even without frames.
`Alt+q` saves agents, sidebar visibility and status bar mode for the next launch
in the same project; `Alt+d`, then `q`, leaves the previous saved state unchanged.
See [Views and Themes](https://lince.sh/documentation/#/dashboard/views-and-themes)
for palettes, width, frame overrides and session configuration.

Sandboxed agents run inside [agent-sandbox](../sandbox/) (bubblewrap, Linux) or [nono](https://github.com/always-further/nono) (Landlock/Seatbelt, Linux + macOS) — the dashboard manages pane lifecycle and status, not isolation. The sandbox backend is auto-detected or configurable per-agent.

**Message relay**: Send conversation messages between agents (`s` to relay last message, `S` for N messages).

## Prerequisites

- **Zellij** >= 0.45.1
- **Rust** with `wasm32-wasip1` target (`rustup target add wasm32-wasip1`)
- **At least one supported AI coding agent** (Claude Code, Codex, Gemini, OpenCode, Aider, Amp)
- **A sandbox backend** (at least one):
  - **Linux**: [agent-sandbox](../sandbox/) (recommended) or [nono](https://github.com/always-further/nono)
  - **macOS**: [nono](https://github.com/always-further/nono) (required — agent-sandbox is Linux-only)
- **[VoxCode](https://github.com/RisorseArtificiali/voxcode)** (optional, for voice relay)

## Installation

```bash
cd lince-dashboard
chmod +x install.sh
./install.sh
```

The installer:
1. Checks prerequisites (Zellij, Rust, WASM target)
2. Builds the plugin (Rust → WASM, ~900 KB)
3. Copies plugin to `~/.config/zellij/plugins/`
4. Installs layouts to `~/.config/zellij/layouts/`
5. Creates config at `~/.config/lince-dashboard/config.toml`
6. Installs Claude Code status hooks
7. Adds `lince` shell alias
8. Optionally adds `lince-tiled` / `lince-tiled-vox` aliases

After installation:

```bash
source ~/.bashrc
lince              # launch the dashboard (tiled layout)
lince-floating     # launch the floating overlay layout
zd                 # legacy alias for lince
```

## Quick Start

Press `n` to spawn an agent (quick name prompt), or `N` for the full wizard (type, name, profile, directory).

| Key | Action |
|-----|--------|
| `n` | Spawn agent with name prompt |
| `N` | Open creation wizard |
| `f` / `Enter` | Focus agent pane |
| `h` / `Esc` | Hide agent pane |
| `j` / `k` | Navigate agent list |
| `i` | Toggle details; PageUp/PageDown scroll |
| `Alt+d` | Expanded list popup from any pane |
| `Alt+i` / `Alt+h` | Information / help popup |
| `Alt+s` | Toggle sidebar (minimal/statusline) |
| `Alt+b` | Cycle status bar: hidden → left summary → full (minimal/statusline) |
| `Alt+n` | Creation wizard |
| `Alt+1`–`Alt+9` | Focus agent from any pane |
| `s` | Relay last message to another agent |
| `S` | Relay N messages (prompt for count) |
| `x` | Kill agent |
| `Alt+q` / `Q` | Save state & quit (`Alt+q` from any pane) |
| `Alt+d`, then `q` | Quit without saving |
| `?` | Help overlay |

## Documentation

| Document | Description |
|----------|-------------|
| **[Usage Guide](https://lince.sh/documentation/#/dashboard/usage-guide)** | Keybindings, wizard, features, voice relay |
| **[Configuration Reference](https://lince.sh/documentation/#/dashboard/config-reference)** | Dashboard config.toml and agents-defaults.toml |
| **[Agent Examples](https://lince.sh/documentation/#/dashboard/agent-examples)** | Default agents, custom agents, multi-provider setups |
| **[Sandbox Levels](https://lince.sh/documentation/#/dashboard/sandbox-levels)** | Three shipped levels (paranoid/normal/permissive), how to choose, and how to ship a custom level |
| **[Multi-Agent Guide](MULTI-AGENT-GUIDE.md)** | What changed for multi-agent support |

Each agent can run at one of three sandbox levels — `paranoid`, `normal`, `permissive` — selected via `sandbox_level` in `agents-defaults.toml` or per-agent in `config.toml`. The level controls network reach (Anthropic-only vs. + GitHub) and filesystem exposure (scratch config vs. real `~/.claude` vs. `~/.config/gh` for `gh` CLI). The same knob accepts custom values pointing at your own profile files. See the [Sandbox Levels doc](https://lince.sh/documentation/#/dashboard/sandbox-levels) for the full reference.

## Architecture

```
lince-dashboard/
├── plugin/
│   ├── Cargo.toml              # Rust WASM crate
│   ├── build.sh                # Build → .wasm
│   └── src/
│       ├── main.rs             # Plugin entry, key handling, pipe dispatch
│       ├── config.rs           # TOML config parsing, agent type loading
│       ├── types.rs            # AgentInfo, AgentStatus, StatusMessage, WizardState
│       ├── dashboard.rs        # TUI rendering (ANSI), overlays (wizard, help)
│       ├── agent.rs            # Agent spawn/stop/tracking (multi-type)
│       ├── theme.rs            # Independent UI palettes
│       ├── attention.rs        # Passive attention/navigation snapshots
│       ├── render_output.rs    # Shared rendering for dialog popups
│       ├── pane_manager.rs     # Pane focus/hide/show
│       └── state_file.rs       # Save/restore agent state (.lince-dashboard)
├── hooks/
│   ├── claude-status-hook.sh   # Claude Code hook → pipe + file
│   ├── codex-status-hook.sh    # Codex lifecycle/notify hooks → pipe + file
│   ├── bob-status-hook.sh      # Bob (IBM) hook → pipe + file
│   ├── lince-agent-wrapper     # Generic wrapper for agents without native hooks
│   └── install-hooks.sh        # Hook installer
├── layouts/
│   ├── dashboard.kdl           # Main layout (plugin + voxcode + shell)
│   ├── dashboard-tiled.kdl     # Controller left, agent viewport right
│   └── dashboard-statusline.kdl # Attention row and on-demand controller
├── lince-dashboard-launch      # Presets and session-scoped Zellij config
├── agents-defaults.toml        # Default agent type definitions
├── config.toml                 # Default dashboard configuration
├── install.sh                  # Interactive installer
└── README.md
```

### Plugin API usage

| Zellij API | Purpose |
|------------|---------|
| `open_command_pane_floating()` / `open_command_pane()` | Spawn agent panes (floating or tiled) |
| `hide_pane_with_id()` / `show_pane_with_id()` | Toggle pane visibility |
| `focus_terminal_pane()` | Focus a specific pane |
| `close_terminal_pane()` | Kill agent panes |
| `write_chars_to_pane_id()` | Forward voice text to agent |
| `pipe()` method | Receive status + voice messages |
| `run_command()` | Detect launch directory, load config |
| `quit_zellij()` | Save state and exit session |

## Troubleshooting

### Plugin won't load
- Check the WASM file exists: `ls ~/.config/zellij/plugins/lince-dashboard.wasm`
- Verify Zellij version: `zellij --version` (need >= 0.45.1)
- Check layout generation: `lince-dashboard-launch --preset minimal --print-layout`
- Grant permissions when Zellij prompts

### Status not updating
- Verify hooks are installed: check `~/.claude/settings.json` for `hooks` section
- Test hook manually: `echo '{"hook_event_name":"Stop"}' | LINCE_AGENT_ID=test-1 bash ~/.local/bin/claude-status-hook.sh`
- Check file fallback: `cat /tmp/lince-dashboard/claude-test-1.state`
- For Codex, run `bash hooks/install-codex-hooks.sh`, then open `/hooks` in Codex and review/trust the `codex-status-hook.sh` handlers. Restart the Codex session. The installer merges lifecycle events into `$CODEX_HOME/hooks.json` (default `~/.codex/hooks.json`) and preserves other hooks. Legacy `notify` alone can only report turn completion, so it cannot switch the dashboard to `RUNNING`.
- Verify Bob hooks are installed: check `~/.bob/settings/settings.json` for `bob-status-hook.sh` entries under `hooks`
- Ensure sandbox passes env vars (see [Sandbox Integration](https://lince.sh/documentation/#/dashboard/usage-guide?id=sandbox-integration))

### Codex scrolling and multiline input

Lince starts Codex with `--no-alt-screen` to retain Zellij's pane scrollback.
After updating Lince, start a new Codex pane. Use the mouse wheel, or `Ctrl+s`
then `PageUp`/`PageDown` (`Esc` returns to normal mode).

The shipped Zellij config maps `Shift+Enter` to LF, Codex's `Ctrl+j` newline.
Existing Zellij configs are preserved by updates: add this inside `keybinds`
in your active config and restart Zellij:

```kdl
shared_among "normal" "locked" {
    bind "Shift Enter" { Write 10; }
}
```

The host terminal must send a distinct key sequence for `Shift+Enter`.
If it sends ordinary Enter, use `Ctrl+j`, or `Ctrl+g` to compose in your editor.
A trailing backslash is not a portable multiline shortcut for Codex.

### Agent panes not hiding
- This is a known Zellij behavior — `hide_pane_with_id` requires `ChangeApplicationState` permission
- The plugin requests this permission on load; accept the permission prompt

### Voice relay not working
- VoxCode must send via pipe: `zellij pipe --name "voxcode-text" --payload "text"`
- Check an agent is selected/focused in the dashboard
- Ensure VoxCode has `use_pipe = true` in its `[zellij]` config section
