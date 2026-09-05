---
name: lince-add-supported-agent
description: Add support for a new AI coding agent (or CLI tool) to lince-dashboard and agent-sandbox. The agent provides its own requirements (binary, config dirs, API keys, sandbox behavior) and this skill generates correct TOML configuration. Use when adding a new agent type, setting up multi-agent support, or when asked to add agent, new agent type, support cursor, support bob, support cli, register agent, setup agent, configure agent for dashboard.
license: MIT
compatibility: Requires lince-dashboard and agent-sandbox installed. Works with any agent supporting agentskills.io.
metadata:
  author: lince
  version: "2.0"
---

# lince-add-supported-agent

You are an AI assistant guiding the **user** through registering a new agent
with the LINCE ecosystem (agent-sandbox + lince-dashboard). The output of this
skill is user-side TOML config (plus an optional hook script), written to the
user's `$HOME`. Nothing goes into the repo — shipped agents (claude, codex,
bob, gemini, opencode, pi, bash/zsh/fish) live in
`lince-dashboard/agents-defaults.toml` and are out of scope.

References (consult as needed):

- `references/config-schema.md` — Field reference (sandbox + dashboard)
- `references/examples.md` — Shipped-agent configurations to model from
- `references/hook-templates.md` — Hook script skeletons (bash / TS / JS)
- `scripts/validate-agent.sh` — Post-registration validation, run as last step

---

## 1. Overview & Tier Model

Pick the tier **first**, before writing anything. Ask the user explicitly.

### Tier A — Native hooks (rich status)

The agent runs an external program on lifecycle events (e.g. Claude Code's
`PreToolUse` / `Stop`, Codex's `notify`, OpenCode events). Output:

- `[agents.<key>]` in `~/.agent-sandbox/config.toml`
- `[agents.<key>]` in `~/.config/lince-dashboard/config.toml` with
  `has_native_hooks = true` and a populated `[agents.<key>.event_map]`
- Hook script in `~/.local/share/lince/hooks/<key>-status-hook.<ext>`

Dashboard shows **Running / INPUT / PERMISSION / Stopped** for the agent's
whole lifetime.

### Tier B — Wrapper-only (Unknown)

The agent has no native hook system (raw shells, simple CLIs, or any binary
you don't yet know how to instrument). Output: only the two TOML sections,
`has_native_hooks = false`, **no** hook script, **no** event_map. The
dashboard displays `-` (Unknown) for the agent's lifetime. This is honest,
not broken.

### Tier C — User contribution

Everything this skill produces is Tier C: it lives in the user's `$HOME`,
never in the repo. Repo defaults are managed by `update.sh`.

**State explicitly to the user**: *"If you are uncertain whether the agent
has native hooks, pick Tier B. You can promote to Tier A later by writing a
hook script and adding an event_map."*

---

## 2. Hook Contract (Tier A only)

The dashboard accepts a single minimal JSON message per Zellij pipe write:

```json
{"agent_id": "<id>", "event": "<native_event_name>"}
```

- `agent_id` — value of `$LINCE_AGENT_ID`, set by the dashboard when spawning
  the agent. The hook MUST exit 0 silently if this is empty.
- `event` — the **native** event name from the agent (e.g. `PreToolUse`,
  `idle_prompt`, `agent-turn-complete`). Do NOT translate inside the hook.

The dashboard resolves it in this order:

1. Look up `event` in `[agents.<key>.event_map]` → map to canonical
2. If unmapped, check whether `event` is itself a canonical name
3. Otherwise → `Unknown` + warning log line (no silent fallback)

### Canonical events (the 5 m-15 states)

| Canonical    | Meaning                                            |
|--------------|----------------------------------------------------|
| `running`    | Agent is actively working                          |
| `input`      | Agent is waiting on the user (user's turn)         |
| `permission` | Agent is asking approval for a tool / action       |
| `stopped`    | Agent process ended (voluntary or error)           |
| `unknown`    | Internal fallback only — do NOT emit from hooks    |

Pipe name defaults to `lince-status`; override per-agent with
`status_pipe_name = "..."` (e.g. Claude uses `"claude-status"`).

After generation, verify wiring with:

```bash
echo '{"agent_id":"test","event":"running"}' | zellij pipe --name lince-status
```

---

## 3. Decision Tree (walk the user through in order)

1. **Binary** — Command name and install path (e.g. `cursor-agent` at
   `~/.local/bin/cursor-agent`). Verify with `command -v <binary>`.
2. **Config directory** — Does the agent persist config / credentials on
   disk? (e.g. `~/.cursor/`). This becomes `home_ro_dirs`. Empty list if none.
3. **API key environment variables** — Which env vars must reach the agent?
   (e.g. `CURSOR_API_KEY`). These populate `[agents.<key>.env_vars]`.
4. **Internal sandbox conflict** — Does the agent itself use bwrap, Docker,
   or seccomp internally? If yes, find the CLI flag that disables it and set
   `bwrap_conflict = true` plus `disable_inner_sandbox_args`.
5. **Has native lifecycle hooks?** This is the **Tier A vs B** decision.
   - "Does the agent run an external program on tool use, idle, permission
     prompts, or exit?" → Tier A.
   - "No, it just runs and prints to stdout / takes stdin." → Tier B.
6. **Hook language** (Tier A only) — bash / TypeScript / JavaScript. Default
   to bash unless the agent's docs explicitly require a different runtime.

Confirm all answers back to the user before writing anything.

### Derive the config key

Lowercase the binary name; replace spaces / underscores with hyphens; strip
special characters (`cursor-agent` → `cursor-agent`, `Bob_CLI` → `bob-cli`).
Show the derived key and ask for confirmation; allow override.

---

## 4. Generation Steps

Pre-flight: check the target files for an existing `[agents.<key>]` section
and ask **replace / keep / abort** before overwriting. The skill is
idempotent — re-running must update in place, never duplicate.

### 4.1 Sandbox TOML (always, both tiers)

Target file: `~/.agent-sandbox/config.toml`.

```toml
[agents.<key>]
command = "<binary>"
default_args = [<headless args>]
env = { <API_KEY> = "$<API_KEY>" }
home_ro_dirs = ["<dir relative to ~>"]  # e.g. ".cursor" — no leading ~ or /
home_rw_dirs = []
bwrap_conflict = <true|false>
disable_inner_sandbox_args = [<args>]   # only when bwrap_conflict = true
```

### 4.2 Dashboard TOML (always, both tiers)

Target file: `~/.config/lince-dashboard/config.toml` — append the
`[agents.<key>]` block at the end of the file. Custom agents and overrides
live here; `~/.config/lince-dashboard/agents-defaults.toml` is shipped data
and is always overwritten by `update.sh`. Entries are merged over the shipped
defaults at load time as **full replacements** (no per-field merge), so every
entry must be a COMPLETE definition: `command`, `pane_title_pattern`,
`status_pipe_name`, `display_name`, `short_label`, `color`, `sandboxed` are
all required. Warning: one malformed/incomplete `[agents.*]` entry makes the
dashboard silently drop ALL user agent entries.

```toml
[agents.<key>]
command = ["agent-sandbox", "run", "-p", "{project_dir}", "--id", "{agent_id}", "--agent", "<key>"]
display_name = "<Human Name>"
short_label = "<3 chars uppercase>"
color = "<color>"
sandboxed = true
has_native_hooks = <true|false>
pane_title_pattern = "agent-sandbox"
status_pipe_name = "lince-status"
providers = ["__discover__"]
sandbox_level = "normal"
home_ro_dirs = ["~/<dir>/"]   # with ~/ prefix here, unlike sandbox config

[agents.<key>.env_vars]
<API_KEY> = "$<API_KEY>"
```

LINCE defaults to apply without asking the user:

| Field | Default | Notes |
|-------|---------|-------|
| `has_native_hooks` | from Tier A/B | `true` only for Tier A |
| `status_pipe_name` | `"lince-status"` | Reserved: `"claude-status"` for Claude |
| `sandboxed` | `true` | Add `<key>-unsandboxed` variant only if asked |
| `pane_title_pattern` | `"agent-sandbox"` (sandboxed) or `<binary>` (unsandboxed) | |
| `color` | propose by name | red, green, yellow, blue, magenta, cyan, white |
| `short_label` | first 3 chars uppercase | Pad with space if needed |
| `sandbox_level` | `"normal"` | Omit for shells / no-provider agents |

### 4.3 Tier A only: event_map + hook script

Append an `event_map` sub-table mapping the agent's **native** event names to
canonical events. Propose entries from the agent's docs; prompt the user if
unknown. Example:

```toml
[agents.<key>.event_map]
"PreToolUse"     = "running"
"idle_prompt"    = "input"
"permission_prompt" = "permission"
"Stop"           = "stopped"
```

For Tier B: **omit** `event_map` entirely.

Write the hook script to `~/.local/share/lince/hooks/<key>-status-hook.<ext>`
using a template from `references/hook-templates.md`. The bash skeleton:

```bash
#!/usr/bin/env bash
set -uo pipefail
AGENT_ID="${1:-unknown}"
PIPE_NAME="${LINCE_PIPE:-lince-status}"

send() {
    local event="$1"
    local payload
    payload=$(printf '{"agent_id":"%s","event":"%s"}' "$AGENT_ID" "$event")
    if command -v zellij >/dev/null 2>&1 && [[ -n "${ZELLIJ:-}" ]]; then
        echo "$payload" | zellij pipe --name "$PIPE_NAME" 2>/dev/null || true
    fi
    mkdir -p /tmp/lince-dashboard
    echo "$payload" > "/tmp/lince-dashboard/${AGENT_ID}.state"
}

# TODO: customise the trigger logic for your agent.
# Example: parse stdin JSON, watch a file, etc., then call:
#   send "running"   |   send "input"   |   send "permission"   |   send "stopped"
```

Then `chmod +x` the file. Show the user the pipe test command from §2 and
tell them what they still need to fill in (the event-detection logic).

### 4.4 Tier B only

Skip hooks. State explicitly to the user: *"The dashboard will show `-` for
this agent. That is expected — there is no signal to read."*

---

## 5. Examples (reference implementations)

Point the user at these in-repo examples (read-only, ship with LINCE):

| Tier | Agent | Reference files |
|------|-------|-----------------|
| A (rich) | Claude Code | `lince-dashboard/hooks/claude-status-hook.sh`, `[agents.claude]` + `[agents.claude.event_map]` in `lince-dashboard/agents-defaults.toml` |
| A (lean) | Codex | `lince-dashboard/hooks/codex-status-hook.sh`, `[agents.codex]` + `[agents.codex.event_map]` in `lince-dashboard/agents-defaults.toml` |
| A (claude-style) | Bob | `lince-dashboard/hooks/bob-status-hook.sh`, `[agents.bob]` + `[agents.bob.event_map]` in `lince-dashboard/agents-defaults.toml` — Claude's hook contract, no Notification event |
| B | Gemini | `[agents.gemini]` with `has_native_hooks = false` (no event_map, no hook script) in `lince-dashboard/agents-defaults.toml` |
| B | Bash / Zsh / Fish | `[agents.bash]` etc. — `has_native_hooks = false`, no providers, no event_map |
| C | User-side | Anything generated by this skill, in `~/.config/lince-dashboard/config.toml` `[agents.*]` (same schema, $HOME instead of repo) |

See `references/examples.md` for full TOML snippets.

---

## 6. Validate

After writing, run:

```bash
bash <skill_dir>/scripts/validate-agent.sh <key>
```

The script:

- Parses both TOML files with `python3 -c "import tomllib; ..."` (FAIL on
  syntax error)
- Confirms `[agents.<key>]` exists in both files
- Verifies the binary is in `PATH`
- Tier A: syntax-checks the hook script (`bash -n`) and verifies every
  `event_map` value is a canonical event (`running|input|permission|stopped`)
- Tier B: confirms `has_native_hooks = false` and that no hook script and no
  `event_map` were written
- Prints **PASS / FAIL** summary

Report the output verbatim to the user. On failure, surface the message and
offer to re-edit.

---

## Important Notes

- The skill is **idempotent** — re-running for the same key updates in place.
- Never write into the repo's `lince-dashboard/agents-defaults.toml`. That
  file ships with LINCE and is managed by `update.sh`.
- Never write into `~/.config/lince-dashboard/agents-defaults.toml` either —
  it is the installed copy of the shipped file and is **always overwritten**
  by `update.sh` (#199). Custom agents go in
  `~/.config/lince-dashboard/config.toml` `[agents.<key>]`.
- All file writes go through this skill — never by hand instructions
  (project CLAUDE.md, no-manual-edits rule).
- The dashboard config file uses the same `[agents.<key>]` nested table form
  as the sandbox config. Field semantics differ (see `references/config-schema.md`)
  but the section header pattern is identical.
- `event_map` values are validated against the closed set
  `{running, input, permission, stopped}`. Typos cause silent dev-only warnings
  to stderr — the validate script catches them.
- Unknown / unmapped events resolve to `Unknown` with a warning, not a fallback.
