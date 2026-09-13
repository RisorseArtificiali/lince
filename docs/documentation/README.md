# LINCE Documentation

LINCE (Linux Intelligent Native Coding Environment) turns your terminal into a multi-agent engineering workstation. Run Claude Code, Codex, Gemini, or any AI coding agent in parallel -- each one sandboxed, monitored, and controllable by voice.

## Sandbox (agent-sandbox)

Bubblewrap-based sandbox for running AI coding agents safely. Restricts filesystem access, blocks git push, isolates environment variables, and hides host processes -- with near-zero overhead.

- [CLI Reference](sandbox/cli-reference.md) -- all commands and flags
- [Configuration Reference](sandbox/config-reference.md) -- every TOML config option
- [Security Model](sandbox/security-model.md) -- threat model, defense layers, what's blocked

## Dashboard (lince-dashboard)

Multi-agent TUI dashboard for Zellij. Spawn, monitor, and switch between multiple agents from one terminal pane.

- [Views and Themes](dashboard/views-and-themes.md) -- minimal, statusline and classic presets, palettes, attention and upgrades
- [Usage Guide](dashboard/usage-guide.md) -- keybindings, wizard, features
- [Configuration Reference](dashboard/config-reference.md) -- dashboard and agent type config
- [Agent Examples](dashboard/agent-examples.md) -- defaults, custom agents, advanced setups
- [Sandbox Levels](dashboard/sandbox-levels.md) -- paranoid / normal / permissive: what each level does and how to ship a custom one

## Configuration CLI (lince-config)

Structured CLI for reading and editing LINCE TOML configuration files. Also powers the `/lince-configure` skill for natural-language configuration.

- [README & Commands](https://github.com/RisorseArtificiali/lince/blob/main/lince-config/README.md) -- install, commands, and examples

## Quick Links

- [Getting Started](https://github.com/RisorseArtificiali/lince/blob/main/QUICKSTART.md)
- [GitHub Repository](https://github.com/RisorseArtificiali/lince)
- [Cheat Sheet](https://github.com/RisorseArtificiali/lince/blob/main/sandbox/CHEATSHEET.md)
- [Multi-Agent Guide](https://github.com/RisorseArtificiali/lince/blob/main/lince-dashboard/MULTI-AGENT-GUIDE.md)
- [lince-config README](https://github.com/RisorseArtificiali/lince/blob/main/lince-config/README.md)
- [Migrating from nono to Seatbelt](sandbox/migration-nono-to-seatbelt.md)
