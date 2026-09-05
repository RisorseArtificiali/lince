# LINCE

**Linux Intelligent Native Coding Environment** — [lince.sh](https://lince.sh)

A toolkit that turns your terminal into a multi-agent engineering workstation — spawn parallel AI coding agents, track their status in real time, relay voice commands, all from a single TUI dashboard running in Zellij.

## Demo

![LINCE demo](demo.gif)

> The full workflow: voice command → Whisper transcription → Claude Code executes in sandbox → backlog updates — all from one terminal.

## The Dashboard

The primary way to use LINCE is the **TUI Dashboard** — a Zellij WASM plugin that acts as a command center for multiple Claude Code agents.

```
┌─────────────────────────────────────────────────────────┐
│  LINCE Dashboard                                        │
│ ┌───┬────────────┬──────────┬────────┬───────┐          │
│ │ # │ Name       │ Status   │Profile │Project│          │
│ ├───┼────────────┼──────────┼────────┼───────┤          │
│ │ 1 │ backend    │ Running  │ vertex │ api/  │          │
│ │>2 │ frontend   │ INPUT    │        │ web/  │          │
│ │ 3 │ tester     │   -      │ zai    │ tests/│          │
│ └───┴────────────┴──────────┴────────┴───────┘          │
├───────────────────────┬─────────────────────────────────┤
│                       │                                 │
│   VoxCode             │   Shell                         │
│   Voice input →       │                                 │
│   relayed to agents   │                                 │
│                       │                                 │
└───────────────────────┴─────────────────────────────────┘
```

What the dashboard gives you:

- **Multi-agent**: Spawn up to 8 AI coding agents in parallel (Claude Code, Codex, Bob, Gemini, OpenCode, Aider, and any custom agent), each in its own sandboxed pane
- **Real-time status**: See at a glance which agents are running, waiting for input, asking for permission, or stopped — five canonical states, color-coded
- **Pane control**: Show/hide agent panes with a keystroke (`f` to focus, `h` to hide)
- **Voice relay**: VoxCode transcriptions are piped directly to the focused agent
- **Session persistence**: Save/restore your agent constellation across sessions (`Q` to save & quit)
- **Swimlane grouping**: Agents auto-grouped by project directory when working across repos
- **Sandbox isolation**: Every agent runs inside [agent-sandbox](sandbox/) — full autonomy, zero host risk

## Quick Start

For a detailed step-by-step guide with scenarios (Mini/Full/Custom), troubleshooting, and quick reference, see [QUICKSTART.md](QUICKSTART.md).

### Prerequisites

- **Linux** (tested on Fedora 43, works on Ubuntu/Debian/Arch)
- **Zellij** >= 0.40
- **Claude Code** (`npm install -g @anthropic-ai/claude-code`)
- **bubblewrap** (`sudo dnf install bubblewrap` / `sudo apt install bubblewrap`)
- **Rust** with `wasm32-wasip1` target (for building the dashboard plugin)
- **macOS** (experimental): native **Seatbelt** sandbox backend (`sandbox-exec`, built into macOS — no extra install), Python 3.11+, Zellij. The legacy `nono` backend is deprecated — see the [migration guide](docs/documentation/sandbox/migration-nono-to-seatbelt.md)

### Step 1: Install the sandbox

```bash
cd sandbox
./install.sh
```

This creates an isolated environment where Claude has full write access to your project but physically cannot reach your SSH keys, cloud credentials, or anything outside the project directory. See [sandbox/README.md](sandbox/README.md) for the full configuration reference.

### Step 2: Install the dashboard

```bash
cd lince-dashboard
./install.sh
```

The installer builds the WASM plugin, copies it to `~/.config/zellij/plugins/`, installs Zellij layouts, sets up Claude Code status hooks, and creates the `lince` shell alias. After sourcing your shell config:

```bash
source ~/.bashrc
lince    # launch the dashboard
```

### Step 3: Launch

```bash
lince
```

Press `n` to spawn an agent (quick), or `N` for the full wizard (name, sandbox profile, project directory). Press `?` for the full keybindings overlay.

### Alternative: Use the Quickstart Installer

For an interactive installer that handles all modules with dependency resolution:
```bash
./quickstart.sh
```

See [QUICKSTART.md](QUICKSTART.md) for more options (--mini, --full, --yes flags).

### The Workflow in Practice

```
You (speaking):  "Pick up the next task from the backlog and start working on it"
                        │
                        ▼
VoxCode:         Whisper transcribes locally → pipes text to dashboard
                        │
                        ▼
Dashboard:       Routes text to focused/selected agent
                        │
                        ▼
Claude Code:     Reads the backlog via MCP → picks a task →
                 marks it in-progress → writes code → runs tests
                        │
                        ▼
Dashboard:       Status updates in real-time (Running → INPUT → Stopped)
                 Five canonical states: - / Running / INPUT / PERMISSION / Stopped
```

## Modules

### [lince-dashboard/](lince-dashboard/)

The multi-agent TUI dashboard — a Zellij WASM plugin (Rust, ~900 KB) that manages multiple AI coding agents (Claude Code, Codex, Bob, Gemini, OpenCode, and any custom agent). Spawn agents, monitor status, show/hide panes, relay voice input, persist sessions. Agent types are fully config-driven — add new agents via TOML or use the `/lince-add-supported-agent` skill. See [lince-dashboard/README.md](lince-dashboard/README.md).

Documentation: [Usage Guide](https://lince.sh/documentation/#/dashboard/usage-guide) | [Configuration](https://lince.sh/documentation/#/dashboard/config-reference) | [Agent Examples](https://lince.sh/documentation/#/dashboard/agent-examples)

### [lince-config/](lince-config/)

Structured CLI for reading and editing LINCE configuration files (`~/.agent-sandbox/config.toml` and `~/.config/lince-dashboard/config.toml`). Preserves comments and formatting via `tomlkit`. Installed to `~/.local/bin/lince-config`.

Also powers the **`/lince-configure` skill** — a natural-language interface that lets any AI coding agent read and modify its own configuration interactively (conversational or guided-menu mode). Installed automatically by `quickstart.sh` or `lince-dashboard/install.sh`.

**Config v2**: configuration is converging on a single versioned policy file (`~/.config/lince/lince.toml`) + a shipped agent registry. Get started with `lince-config discover` / `lince-config apply <agent>+<level>+<provider>`; existing installs keep working unchanged — see the [user migration guide](docs/migration-v2-users.md) and the [developer migration guide](docs/migration-v2-developers.md).

### [sandbox/](sandbox/)

Bubblewrap-based sandbox for running AI coding agents safely. Restricts filesystem access, blocks git push, isolates environment variables, and hides host processes — with near-zero overhead. Supports any agent via `--agent` flag (`agent-sandbox run -a codex`, `-a gemini`, etc.). Used by the dashboard to spawn every agent.

Documentation: [CLI Reference](https://lince.sh/documentation/#/sandbox/cli-reference) | [Configuration](https://lince.sh/documentation/#/sandbox/config-reference) | [Security Model](https://lince.sh/documentation/#/sandbox/security-model)

### `/lince-add-supported-agent` skill (bundled with lince-dashboard)

An [agentskills.io](https://agentskills.io)-compliant skill that lets any AI coding agent register itself with the lince ecosystem. Generates correct TOML configuration for both agent-sandbox and lince-dashboard. Installed automatically by `lince-dashboard/install.sh`.

### `/lince-configure` skill (bundled with lince-dashboard)

An [agentskills.io](https://agentskills.io)-compliant skill for natural-language configuration of LINCE. Ask any AI agent to configure providers, change sandbox levels, set API keys, adjust dashboard settings, or diagnose issues — it drives `lince-config` under the hood. Supports conversational and guided-menu interaction. Installed automatically by `lince-dashboard/install.sh` (requires the `lince-config` CLI).

## Related Projects

| Project | Description |
|---------|-------------|
| [VoxCode](https://github.com/RisorseArtificiali/voxcode) | Voice input for AI agents — local Whisper transcription, integrates with the dashboard via Zellij pipes |
| [VoxTTS](https://github.com/RisorseArtificiali/voxtts) | Text-to-Speech with local GPU/CPU engines (Kokoro, Piper) |
| [Agent Ready Skill](https://github.com/RisorseArtificiali/agent-ready-skill) | Assess any project's readiness for agentic coding (agentskills.io) |

## License

MIT
