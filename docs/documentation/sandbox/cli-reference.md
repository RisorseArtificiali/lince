# CLI Reference

## Synopsis

```
agent-sandbox <command> [options] [-- <agent-args>]
```

`agent-sandbox` manages a bubblewrap sandbox for AI coding agents. Commands fall into four groups: setup (`init`), execution (`run`, `learn`), config management (`diff`, `merge`, `status`, `proxy-status`, `nono-sync`, `seatbelt-sync`), and snapshots (`snapshot`, `snapshot-list`, `snapshot-diff`, `snapshot-restore`, `snapshot-prune`).

---

## Commands

### init

```
agent-sandbox init [-f | --force] [--real-config]
```

Set up the sandbox environment. Run once after installation, or again with `--force` to reset.

Creates `~/.agent-sandbox/`, copies `~/.claude/` into an isolated config directory, generates a sanitized `.gitconfig` (credential sections stripped), creates a `git push` blocking wrapper, writes the default `config.toml`, and auto-detects `$PATH` entries under `$HOME`.

| Flag | Default | Description |
|------|---------|-------------|
| `-f`, `--force` | off | Overwrite existing config and all generated files |
| `--real-config` | off | Mount real `~/.claude` directly instead of copying (disables `diff`/`merge`) |

---

### run

```
agent-sandbox run [-p DIR] [-a AGENT] [-P PROFILE] [--sandbox-level NAME]
                  [--log | --no-log] [--safe] [--dry-run]
                  [--rw DIR] [--ro DIR] [--id ID]
                  [-- <agent-args>]
```

Launch an AI coding agent inside the sandbox. Defaults to Claude Code in the current directory.

Options not recognized by `agent-sandbox run` are passed directly to the agent. This means agent flags like `--continue`, `--model`, `--resume`, and `--print` (long form) work without the `--` separator. Use `--` for edge cases where a flag conflicts (e.g., `-p` is used by both agent-sandbox and some agents).

On launch, a banner displays active protections (provider, project path, filesystem mode, network, PID isolation, git push status, env var policy, and credential proxy state).

| Flag | Default | Description |
|------|---------|-------------|
| `-p`, `--project` | `.` (cwd) | Project directory to mount writable |
| `-a`, `--agent` | `claude` | Agent to run (looks up `[agents.<name>]` in config) |
| `-P`, `--provider`, `--profile` | config default | Provider name — env-var bundle defined under `[providers.*]` / `[<agent>.providers.*]` in `config.toml` (e.g. `anthropic`, `vertex`, `zai`). `--profile` is the legacy spelling and still works (gh#81). |
| `--sandbox-level NAME` | per-agent default | Sandbox isolation level: `paranoid`, `normal`, `permissive`, or any custom name. Loads `sandbox/profiles/<NAME>.toml` (built-in) or `~/.agent-sandbox/profiles/<NAME>.toml` (user-supplied) and deep-merges it into the config. See [Configuration Reference](sandbox/config-reference.md#sandbox-levels) |
| `--log` | config value | Enable session transcript logging |
| `--no-log` | config value | Disable session transcript logging |
| `--safe` | off | Disable `--dangerously-skip-permissions` for this run |
| `--dry-run` | off | Print the bwrap command without executing |
| `--rw DIR` | none | Extra read-write directory (repeatable) |
| `--ro DIR` | none | Extra read-only directory (repeatable) |
| `--id ID` | none | Agent ID (sets `LINCE_AGENT_ID` env var inside sandbox) |

---

### diff

```
agent-sandbox diff
```

Show a unified diff between the real `~/.claude/` config and the sandbox's isolated copy. Useful for reviewing what the agent changed during a session (installed MCP servers, modified settings, etc.).

Disabled when `use_real_config = true`.

---

### merge

```
agent-sandbox merge
```

Interactive file-by-file merge of sandbox config changes back to the real `~/.claude/`. For each changed file you can **(a)pply**, **(s)kip**, view **(d)iff**, or **(q)uit**.

This is the safe way to adopt agent changes (new MCP servers, skills, settings) into your real environment.

Disabled when `use_real_config = true`.

---

### status

```
agent-sandbox status
```

Display sandbox state: config location, file counts, toolchain cache sizes, log count, bwrap version, pending config changes, detected backends (bubblewrap, nono, seatbelt), active profiles, and credential proxy status.

---

### proxy-status

```
agent-sandbox proxy-status
```

Show credential proxy state: whether it is running, listening port, uptime, PID, and configured API domains. API keys are never displayed.

---

### snapshot

```
agent-sandbox snapshot [-a AGENT] [-p DIR] [--config-only] [--project-only]
```

Create a filesystem snapshot of the project directory and/or the agent config directory. Uses rsync with `--link-dest` for hardlink-based deduplication (near-zero cost for unchanged files).

| Flag | Default | Description |
|------|---------|-------------|
| `-a`, `--agent` | `claude` | Agent name (selects config directory) |
| `-p`, `--project` | `.` (cwd) | Project directory |
| `--config-only` | off | Snapshot only the agent config directory |
| `--project-only` | off | Snapshot only the project directory |

---

### snapshot-list

```
agent-sandbox snapshot-list [-a AGENT] [-p DIR] [--config-only | --project-only]
```

List available snapshots grouped by type (project/config) with timestamps and disk usage.

| Flag | Default | Description |
|------|---------|-------------|
| `-a`, `--agent` | `claude` | Agent name |
| `-p`, `--project` | `.` (cwd) | Project directory |
| `--config-only` | off | Show only config snapshots |
| `--project-only` | off | Show only project snapshots |

---

### snapshot-diff

```
agent-sandbox snapshot-diff [TIMESTAMPS...] [-a AGENT] [-p DIR]
                            [--config-only | --project-only]
```

Compare a snapshot against the current state, or two snapshots against each other. Supports prefix matching on timestamps.

| Flag | Default | Description |
|------|---------|-------------|
| `TIMESTAMPS` | latest | 0 args = latest vs current; 1 = that snapshot vs current; 2 = compare two snapshots |
| `-a`, `--agent` | `claude` | Agent name |
| `-p`, `--project` | `.` (cwd) | Project directory |
| `--config-only` | off | Diff only config snapshots |
| `--project-only` | off | Diff only project snapshots |

---

### snapshot-restore

```
agent-sandbox snapshot-restore [TIMESTAMP] [-a AGENT] [-p DIR]
                               [--config-only | --project-only]
```

Interactive restore from a snapshot. Presents each changed file for per-file accept/reject using the same UX as `merge`. Warns if there are unmerged config changes.

| Flag | Default | Description |
|------|---------|-------------|
| `TIMESTAMP` | latest | Snapshot timestamp to restore from |
| `-a`, `--agent` | `claude` | Agent name |
| `-p`, `--project` | `.` (cwd) | Project directory |
| `--config-only` | off | Restore only config |
| `--project-only` | off | Restore only project |

---

### snapshot-prune

```
agent-sandbox snapshot-prune [-a AGENT] [-p DIR]
                             [--config-only] [--project-only] [--all]
```

Remove old snapshots beyond the configured maximum count (`max_project_snapshots`, `max_config_snapshots`).

| Flag | Default | Description |
|------|---------|-------------|
| `-a`, `--agent` | `claude` | Agent name |
| `-p`, `--project` | `.` (cwd) | Project directory |
| `--config-only` | off | Prune only config snapshots |
| `--project-only` | off | Prune only project snapshots |
| `--all` | off | Prune both project and config snapshots |

---

### learn

```
agent-sandbox learn [-a AGENT] [-P PROVIDER] [--duration SECONDS]
                    [--compare] [--apply] [--output FILE]
```

Run the agent inside a permissive sandbox with `strace` attached to discover actual filesystem paths, network connections, and executables it uses. Produces a suggested `config.toml` fragment to tighten or loosen your sandbox.

Requires `strace` (standard on all Linux distributions).

| Flag | Default | Description |
|------|---------|-------------|
| `-a`, `--agent` | `claude` | Agent to learn |
| `-P`, `--provider`, `--profile` | none | Provider name (env-var bundle) |
| `--duration` | unlimited | Kill the agent after N seconds |
| `--compare` | off | Compare observed needs vs current config |
| `--apply` | off | Auto-merge suggestions into `config.toml` |
| `--output FILE` | temp file | Save TOML suggestions to FILE |

---

### migrate-providers

```
agent-sandbox migrate-providers [--dry-run]
```

Rewrite the resolved `config.toml` in place, translating the legacy
`[profiles.*]` / `[<agent>.profiles.*]` keys (and `default_profile`) to
the canonical `[providers.*]` / `[<agent>.providers.*]` / `default_provider`
spelling introduced in gh#81. A `.bak` backup is written next to the
original. Use `--dry-run` to preview a unified diff. Idempotent — re-running
on an already-migrated file is a no-op.

---

### nono-sync

```
agent-sandbox nono-sync [--dry-run] [--agent NAME] [-P PROVIDER]
```

Generate nono JSON profiles from lince agent configuration. Used when the `nono` backend is selected or on macOS.

**DEPRECATED**: The nono backend is deprecated in favor of `seatbelt`. Use `agent-sandbox seatbelt-sync` instead. See [Migration Guide](sandbox/migration-nono-to-seatbelt.md).

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | off | Print generated JSON without writing files |
| `--agent` | all agents | Sync a specific agent only |
| `-P`, `--provider`, `--profile` | none | Provider name (env-var bundle) for env var mapping |

---

### seatbelt-sync

```
agent-sandbox seatbelt-sync [--dry-run] [--agent NAME] [-P PROVIDER]
```

Generate macOS Seatbelt (`.sb`) profiles from lince agent configuration. Used with the `seatbelt` backend (native `sandbox-exec`). Preferred backend for macOS.

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | off | Print generated profiles without writing files |
| `--agent` | all agents | Sync a specific agent only |
| `-P`, `--provider`, `--profile` | none | Provider name (env-var bundle) for env var mapping |

---

## Global Behavior

**Config search order** -- the config file is loaded from the first location found:

1. `./.agent-sandbox/config.toml` -- project-local (takes priority)
2. `~/.agent-sandbox/config.toml` -- global fallback

If neither exists, the sandbox refuses to start with a clear error. There is no inline default; run `agent-sandbox init` to create the file.

**Agent defaults** are loaded from three layers (later overrides earlier):

1. `agents-defaults.toml` (shipped with the script; searched in `./.agent-sandbox/`, `~/.agent-sandbox/`, and the script directory)
2. `[agents.<name>]` in user `config.toml`
3. Hardcoded fallback for `claude`

**Environment handling** -- all host environment variables are cleared via `--clearenv`. Only variables listed in `[env].passthrough` and those defined in the active provider are injected. API keys belong in `[*.providers.*.env]` sections (legacy `[*.profiles.*.env]` still works), not in your shell.

---

## Examples

Daily development:
```bash
cd ~/project/my-app && agent-sandbox run
```

Run a different agent:
```bash
agent-sandbox run -a codex
agent-sandbox run -a gemini
```

Switch providers (env-var bundles):
```bash
agent-sandbox run --provider zai          # Z.AI / GLM
agent-sandbox run -P vertex               # Vertex AI (-P is a shorter form)
agent-sandbox run -P anthropic            # Direct Anthropic API
```

Review and merge config changes after a session:
```bash
agent-sandbox diff
agent-sandbox merge
```

Inspect the generated bwrap command without executing:
```bash
agent-sandbox run --dry-run
```

Enable credential proxy and verify:
```bash
agent-sandbox run -P anthropic    # proxy starts automatically if configured
agent-sandbox proxy-status
```

Run at a tighter sandbox level (kernel-enforced network isolation + credential proxy):
```bash
agent-sandbox run --sandbox-level paranoid
agent-sandbox run --sandbox-level paranoid -a codex
```

Snapshot workflow (before and after a risky session):
```bash
agent-sandbox snapshot
agent-sandbox run
agent-sandbox snapshot-diff
agent-sandbox snapshot-restore 20260326
```

Discover and tighten sandbox permissions:
```bash
agent-sandbox learn --duration 120
agent-sandbox learn --compare
agent-sandbox learn --apply
```

Log a session for audit:
```bash
agent-sandbox run --log
ls ~/.agent-sandbox/logs/
```

---

## See Also

- [Configuration Reference](sandbox/config-reference.md) -- every TOML key documented
- [Security Model](sandbox/security-model.md) -- threat model, defense layers, credential proxy details
- [Cheatsheet](https://github.com/RisorseArtificiali/lince/blob/main/sandbox/CHEATSHEET.md) -- quick-reference card
- [lince-config CLI](https://github.com/RisorseArtificiali/lince/blob/main/lince-config/README.md) -- structured CLI for reading and editing LINCE configuration
