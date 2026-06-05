# Configuration Reference

## Overview

The sandbox is configured through TOML files loaded in a cascade:

1. `~/.agent-sandbox/config.toml` — **global config** (base layer)
2. `./.agent-sandbox/config.toml` — **project-local config** (deep-merged on top, optional)

When both files exist, agent-sandbox deep-merges the project-local file on top of the global one:

- **Scalars** from the local file replace the global value.
- **Lists** are appended and deduplicated (global entries first, local entries added at the end).
- **Tables** (TOML sections) are merged recursively.

A startup line is printed to stderr when the merge is active:
```
config: merged ~/.agent-sandbox/config.toml + .agent-sandbox/config.toml
```

When only one file exists, it is loaded as-is (no merge). `agent-sandbox init` creates the global config. No inline defaults exist; the sandbox refuses to start without at least one config file.

**Project-local config example** — only the fields that differ from the global need to be specified:

```toml
# .agent-sandbox/config.toml
[security]
block_git_push = false   # allow git push in this project only

[sandbox]
extra_rw = ["/tmp/my-project-cache"]  # appended to global extra_rw
```

---

## [sandbox]

General sandbox behavior and filesystem exposure.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `extra_rw` | list of strings | `[]` | Extra directories the agent can write to (besides the current project) |
| `ro_dirs` | list of strings | `["~/project"]` | Directories the agent can read but not write |
| `persist_toolchains` | bool | `true` | Persist build-tool caches (cargo registry, npm cache, go modules) between sessions |
| `auto_expose_path` | bool | `true` | Auto-detect `$PATH` entries under `$HOME` and expose them read-only. Top-level dirs are mounted, and deeper subdirectories explicitly in the host PATH are also added to the sandbox PATH (e.g. `~/Applications/apache-maven-3.9.14/bin`) |
| `home_ro_dirs` | list of strings | `[".config/gcloud"]` | Additional home subdirectories to expose read-only (relative to `$HOME`). Note: this only mounts the filesystem — it does not add entries to PATH. Add the tool's `bin` directory to your host shell PATH for automatic sandbox PATH inclusion |
| `default_provider` | string | `""` | Default provider (env-var bundle) when `-P` / `--provider` is not specified. Set to a provider name defined in `[providers.*]` / `[<agent>.providers.*]`. Leave empty to run without a provider. The legacy spelling `default_profile` is still accepted (gh#81). |
| `backend` | string | `"auto"` | Sandbox backend: `"agent-sandbox"` (bubblewrap, Linux), `"seatbelt"` (macOS sandbox-exec, recommended on macOS), `"nono"` (Landlock/Seatbelt, **deprecated**), or `"auto"` (prefers agent-sandbox on Linux, seatbelt on macOS) |

```toml
[sandbox]
extra_rw = []
ro_dirs = ["~/project"]
persist_toolchains = true
auto_expose_path = true
home_ro_dirs = [".config/gcloud"]
default_provider = "zai"
backend = "auto"   # auto: Linux → agent-sandbox; macOS → seatbelt → nono (fallback)
```

---

## [claude]

Legacy section for Claude Code configuration. Still works for backward compatibility. Prefer `[agents.claude]` for new setups.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `config_dir` | string | `"~/.agent-sandbox/claude-config"` | Sandbox's isolated copy of Claude's config directory |
| `use_real_config` | bool | `false` | Use real `~/.claude` and `~/.claude.json` directly instead of an isolated copy. Disables `diff`/`merge` |

```toml
[claude]
config_dir = "~/.agent-sandbox/claude-config"
use_real_config = false
```

---

## [agents.\<name\>]

Per-agent configuration. Defines how to run a specific AI coding agent inside the sandbox. Overrides defaults from `agents-defaults.toml`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `command` | string | (required) | Binary name to execute |
| `default_args` | list of strings | `[]` | Default CLI arguments passed to the agent |
| `env` | table | `{}` | Extra environment variables to set inside the sandbox |
| `home_ro_dirs` | list of strings | `[]` | Home subdirectories to bind read-only |
| `home_rw_dirs` | list of strings | `[]` | Home subdirectories to bind read-write |
| `bwrap_conflict` | bool | `false` | Agent uses bwrap internally (triggers inner-sandbox disabling) |
| `disable_inner_sandbox_args` | list of strings | `[]` | Arguments injected to disable the agent's own sandbox when `bwrap_conflict` is true |

```toml
[agents.codex]
command = "codex"
default_args = ["--full-auto"]
env = {}
home_ro_dirs = []
home_rw_dirs = [".codex"]
bwrap_conflict = true
disable_inner_sandbox_args = ["--sandbox", "danger-full-access"]
```

Shipped defaults (in `agents-defaults.toml`): `claude`, `codex`, `gemini`, `aider`, `opencode`, `amp`, `bash`.

---

## [git]

Git configuration sanitization for the sandbox.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `strip_sections` | list of strings | `['credential', 'url ".*"']` | Regex patterns matched against `.gitconfig` section headers to strip. Removes credential helpers and URL rewrite rules |

### [git.overrides]

Git config values forced in the sanitized gitconfig.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `"push.default"` | string | `"nothing"` | Forces bare `git push` to do nothing |

```toml
[git]
strip_sections = ['credential', 'url ".*"']

[git.overrides]
"push.default" = "nothing"
```

---

## [env]

Environment variable isolation. All host env vars are cleared; only those listed here pass through.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `passthrough` | list of strings | `["TERM", "COLORTERM", "TERM_PROGRAM", "LANG", "LC_ALL", "EDITOR", "VISUAL", "ZELLIJ", "ZELLIJ_SESSION_NAME", "LINCE_AGENT_ID"]` | Host environment variables passed into the sandbox. API keys should go in providers (`[<agent>.providers.<name>.env]`), not here |

### [env.extra]

Static environment variables set inside every sandbox run, regardless of provider.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| *(any key)* | string | -- | `KEY = "value"` pairs injected via `--setenv` |

```toml
[env]
passthrough = ["TERM", "COLORTERM", "TERM_PROGRAM", "LANG", "LC_ALL", "EDITOR", "VISUAL"]

[env.extra]
# MY_CUSTOM_VAR = "value"
```

---

## [logging]

Session transcript logging via the `script` command.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Enable transcript logging by default (overridable with `--log` / `--no-log`) |
| `dir` | string | `"~/.agent-sandbox/logs"` | Directory for log files |

Logs are saved as `YYYY-MM-DD_HHMMSS_projectname.log` with full ANSI colors. View with `cat` (colors preserved) or pipe through `col -b` for plain text.

```toml
[logging]
enabled = false
dir = "~/.agent-sandbox/logs"
```

---

## [snapshot]

Filesystem snapshot configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `auto_project` | bool | `false` | Auto-snapshot the project directory before each sandbox run. Off by default (can be slow for large repos) |
| `auto_config` | bool | `true` | Auto-snapshot the agent config directory before each run. Config dirs are small, so this is essentially free |
| `max_project_snapshots` | int | `3` | Maximum project snapshots to keep (oldest pruned first) |
| `max_config_snapshots` | int | `5` | Maximum agent config snapshots to keep |
| `project_exclude` | list of strings | `[".git", "node_modules", "target", "__pycache__", ".venv", "build", "dist"]` | Directories excluded from project snapshots |

Snapshots are stored in `~/.agent-sandbox/snapshots/` using rsync `--link-dest` for hardlink-based deduplication. Unchanged files share disk blocks with the previous snapshot.

```toml
[snapshot]
auto_project = false
auto_config = true
max_project_snapshots = 3
max_config_snapshots = 5
project_exclude = [".git", "node_modules", "target", "__pycache__", ".venv", "build", "dist"]
```

---

## [security]

Security features and hardening options.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `unshare_pid` | bool | `true` | PID namespace: hide host processes from the sandbox |
| `new_session` | bool | `false` | New terminal session: prevents terminal escape-sequence attacks. May interfere with Ctrl+C propagation |
| `block_git_push` | bool | `true` | Block `git push` via a wrapper script placed first in `$PATH` |
| `credential_proxy` | bool | `false` | Credential proxy: intercept API calls and inject credentials on the host side so API keys never enter the sandbox |
| `unshare_net` | bool | `false` | Network namespace: run the agent inside a fresh network namespace (`bwrap --unshare-net`). Combined with `credential_proxy`, the proxy is reached via a unix socket bind-mounted into the sandbox. Set automatically by the `paranoid` sandbox level |
| `allow_domains` | list of strings | `[]` | Extra hosts the credential proxy is allowed to forward to, on top of those covered by credential rules. Anything off-list returns `403`. Append-merged with sandbox level fragments |

```toml
[security]
unshare_pid = true
new_session = false
block_git_push = true
credential_proxy = false
unshare_net = false
allow_domains = []
```

---

## [credential_proxy]

Optional configuration for the credential proxy (only relevant when `[security].credential_proxy = true`).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `blocked_hosts` | list of strings | `["169.254.169.254", "metadata.google.internal", "metadata.azure.internal"]` | Extra hosts to block. Cloud metadata endpoints are always blocked |

```toml
[credential_proxy]
blocked_hosts = ["169.254.169.254", "metadata.google.internal", "metadata.azure.internal"]
```

---

## Sandbox Levels

Three named levels package the security keys above into ready-made policies, selected per run with `agent-sandbox run --sandbox-level <name>`:

- `paranoid` — kernel-level network isolation (`unshare_net = true`) plus auto-enabled credential proxy. The agent's only path to the network is the bind-mounted proxy socket.
- `normal` — the default. Network is open, credential proxy is opt-in.
- `permissive` — adds extra read-only host paths on top of `normal`.

Levels are loaded from policy fragments in `sandbox/profiles/<level>.toml` (built-in) or `~/.agent-sandbox/profiles/<level>.toml` (user-supplied) and deep-merged on top of the resolved config. List keys (`home_ro_dirs`, `allow_domains`) are append-merged, so extending a level doesn't require forking the file.

**Option A — one-off override in `~/.agent-sandbox/config.toml`:**

```toml
[security]
allow_domains = ["pypi.org", "files.pythonhosted.org"]
```

**Option B — named reusable level with `extends` (create `~/.agent-sandbox/profiles/paranoid-with-ssh.toml`):**

```toml
extends = "paranoid"

[sandbox]
home_ro_dirs = [".ssh"]   # read-only access to SSH keys, appended to parent's list
```

The optional top-level `extends = "<name>"` field causes the named parent fragment to be resolved and loaded first (same 3-dir, agent-prefix search), then the child is merged on top. Chains of any depth are supported; cycles and missing parents are hard errors. The `extends` key does not appear in the final merged config.

For the full level matrix, per-backend behavior, and custom-level recipes, see [Sandbox Levels](dashboard/sandbox-levels.md).

---

## Providers

A *provider* is a named env-var bundle that switches the model
provider/account (Anthropic vs Vertex vs Z.ai vs Minimax …). API keys live
in the TOML file instead of your shell environment.

> **Naming note (gh#81):** what was called "profile" pre-#81 is now
> "provider". The legacy `[profiles.*]` / `[<agent>.profiles.*]` spelling is
> still accepted (with a one-shot deprecation note on stderr); run
> `agent-sandbox migrate-providers` to rewrite the file in place. The word
> "profile" now refers exclusively to the **sandbox isolation level**
> (paranoid / normal / permissive — see [Sandbox Levels](#sandbox-levels)
> above), which is a separate axis you can combine freely with any provider.

Two naming formats are accepted (both for canonical and legacy):

**Namespaced (recommended)**:
```toml
[claude.providers.vertex]
description = "Vertex AI"
[claude.providers.vertex.env]
CLAUDE_CODE_USE_VERTEX = "1"
ANTHROPIC_VERTEX_PROJECT_ID = "my-gcp-project"
ANTHROPIC_VERTEX_REGION = "us-east5"

[codex.providers.default]
description = "Default OpenAI key"
[codex.providers.default.env]
OPENAI_API_KEY = "sk-..."
```

**Top-level (mapped to `claude`)**:
```toml
[providers.vertex]
description = "Vertex AI"
[providers.vertex.env]
CLAUDE_CODE_USE_VERTEX = "1"
```

**Legacy (still works)**: replace `providers` with `profiles` in any of the
above. `agent-sandbox migrate-providers` rewrites it for you.

### Provider keys

| Key | Type | Description |
|-----|------|-------------|
| `description` | string | Human-readable label (shown in the run banner) |
| `env` | table | Environment variables injected via `--setenv` |
| `env_unset` | list of strings | Environment variables to explicitly unset inside the sandbox |
| `default_args` | list of strings | Override the agent's `default_args` when this provider is active |

### Interaction with the -P / --provider flag

- `default_provider` in `[sandbox]` sets the provider used when `-P` /
  `--provider` is omitted (legacy `default_profile` still accepted).
- `-P <name>` (= `--provider <name>` = `--profile <name>`) overrides for
  that invocation.
- Provider env vars are injected via bwrap `--setenv` and do not need to
  exist in the host shell.
- If a provider defines `default_args`, those replace the base agent
  `default_args`.

### Security note

API keys live in the TOML file. Set restrictive permissions:

```bash
chmod 600 ~/.agent-sandbox/config.toml
```

---

## Directory Layout

After initialization, `~/.agent-sandbox/` contains:

```
~/.agent-sandbox/
├── config.toml             # Sandbox configuration
├── claude-config/          # Isolated copy of ~/.claude (writable by agent)
│   ├── settings.json
│   ├── CLAUDE.md
│   ├── projects/
│   └── ...
├── gitconfig               # Sanitized .gitconfig (read-only in sandbox)
├── bin/
│   └── git                 # Wrapper that blocks git push
├── toolchains/             # Persistent build caches
│   ├── cargo/
│   │   ├── registry/       # Cargo crate downloads (writable)
│   │   └── git/            # Cargo git checkouts (writable)
│   ├── npm-cache/          # npm download cache (writable)
│   └── go/                 # Go module cache (writable)
├── snapshots/              # Filesystem snapshots
│   ├── projects/           # Project dir snapshots (by project hash)
│   │   └── a1b2c3d4e5f6/
│   │       └── 20260326T120000/
│   └── configs/            # Agent config snapshots (by agent name)
│       └── claude/
│           └── 20260326T120000/
├── proxy.pid               # Credential proxy PID file (when running)
└── logs/                   # Session transcripts (if logging enabled)
    └── 2025-01-15_143022_myrepo.log
```

---

## See Also

- [CLI Reference](sandbox/cli-reference.md) -- command synopsis, flags, and usage examples
- [Security Model](sandbox/security-model.md) -- threat model, defense layers, credential proxy details
- [Cheatsheet](https://github.com/RisorseArtificiali/lince/blob/main/sandbox/CHEATSHEET.md) -- quick-reference card
- [lince-config CLI](https://github.com/RisorseArtificiali/lince/blob/main/lince-config/README.md) -- structured CLI for reading and editing LINCE configuration
