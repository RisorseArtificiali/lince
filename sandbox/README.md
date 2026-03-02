# claude-sandbox

A lightweight Linux sandbox for running [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with `--dangerously-skip-permissions` safely. It uses [bubblewrap](https://github.com/containers/bubblewrap) (the same technology behind Flatpak) to restrict what Claude can see and touch on your machine, with near-zero overhead.

## Why

Claude Code's `--dangerously-skip-permissions` flag removes all confirmation prompts, letting Claude execute any bash command, edit any file, and install anything without asking. This is great for productivity but terrifying for your system: a bad prompt, a hallucination, or a prompt injection from malicious code in a repo could wipe your home directory, exfiltrate your SSH keys, push to production, or install a backdoor.

**claude-sandbox** creates a restricted environment where Claude has full autonomy *within* the project you're working on, but physically cannot damage anything else.

## What it blocks

| Attack vector | Protection | How |
|---|---|---|
| **File deletion/modification** | Entire filesystem is read-only except the project dir | `--ro-bind / /` + `--tmpfs $HOME` |
| **SSH key theft** | `~/.ssh` does not exist inside the sandbox | Hidden by tmpfs overlay on `$HOME` |
| **Cloud credential theft** | `~/.aws`, `~/.config/gcloud`, etc. invisible | Hidden by tmpfs overlay on `$HOME` |
| **Git push** | Blocked at three layers | Wrapper script + sanitized `.gitconfig` + no credential helpers |
| **Environment variable leaks** | Only whitelisted vars pass through | `--clearenv` + explicit `--setenv` |
| **Process killing/inspection** | Host processes invisible | `--unshare-pid` (PID namespace) |
| **System modification** | Cannot write to `/usr`, `/etc`, `/var` | Read-only root filesystem |
| **DBus/desktop access** | Session bus socket hidden | `--tmpfs /run` |
| **X11/Wayland keylogging** | Display sockets hidden | `--tmpfs /tmp` |
| **Cron/systemd persistence** | Cannot create services or cron jobs | Read-only `/etc`, tmpfs `/run` |

### What it allows

| Capability | Why | How |
|---|---|---|
| **Read/write project directory** | Claude needs to edit your code | `--bind $PWD $PWD` (writable) |
| **Read other projects** | Claude may need to reference sibling repos | `--ro-bind ~/project ~/project` (read-only, configurable) |
| **Network access** | Needed for Anthropic API, pip, npm, git clone | No `--unshare-net` |
| **Build tools** | python, node, cargo, make, gcc, etc. | System dirs read-only + `$HOME` PATH dirs auto-detected |
| **Claude config** | Settings, MCP servers, skills | Isolated copy in `~/.claude-sandbox/claude-config` |
| **Package caches** | `cargo build` can download crates, npm can cache | Persistent writable dirs for registry/cache subdirectories |

### Security model

The sandbox protects your **host machine from Claude**, not secrets from Claude. Claude still has its own API key (it needs it to function) and can see whatever MCP server credentials are in its config. The threat model is:

1. **Primary**: prompt injection from malicious code in a repository causes Claude to run destructive commands
2. **Secondary**: Claude hallucinating dangerous commands (rm -rf, git push --force, etc.)
3. **Tertiary**: accidental damage from overly broad file operations

The sandbox is **not** a defense against a compromised Claude binary or a kernel-level exploit. For that level of isolation, use a VM.

## How it works

claude-sandbox builds a [bubblewrap](https://github.com/containers/bubblewrap) command that sets up a Linux mount namespace. In plain terms, it creates a "view" of the filesystem where:

```
/                           read-only   (entire OS visible but unmodifiable)
├── /tmp                    fresh tmpfs (empty, writable, isolated)
├── /run                    fresh tmpfs (hides DBus, Wayland sockets)
├── /dev                    minimal     (null, zero, random only)
├── /proc                   namespaced  (only sandbox processes visible)
└── /home/you               tmpfs       (entire home hidden)
    ├── .ssh                GONE        (does not exist)
    ├── .aws                GONE
    ├── .gnupg              GONE
    ├── .gitconfig          sanitized   (read-only, no credential helpers)
    ├── .claude/            SANDBOX     (writable isolated copy)
    ├── .local/             read-only   (auto-detected from PATH)
    ├── .cargo/             read-only   (binaries), writable (registry cache)
    ├── project/            read-only   (sibling repos visible)
    │   └── myrepo/         WRITABLE    (your current project)
    └── ...other PATH dirs  read-only   (auto-detected)
```

Environment variables are cleared (`--clearenv`) and only an explicit whitelist is passed through. This prevents leaking `AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN`, or any other secret that might be in your shell.

Git push is blocked via a wrapper script placed first in `$PATH` that intercepts `git push` and returns an error. Additionally, the `.gitconfig` is sanitized to remove `[credential]` sections, and `push.default` is forced to `nothing`.

## Requirements

- **Linux** (any distribution with kernel 3.8+ for user namespaces)
- **Python 3.11+** (for `tomllib` in the standard library)
- **bubblewrap** (`bwrap`)
- **Claude Code** (the `claude` CLI)

### Installing bubblewrap

**Fedora / RHEL / CentOS Stream:**
```bash
sudo dnf install bubblewrap
```

**Ubuntu / Debian:**
```bash
sudo apt install bubblewrap
```

**Arch Linux:**
```bash
sudo pacman -S bubblewrap
```

**openSUSE:**
```bash
sudo zypper install bubblewrap
```

Verify it's installed:
```bash
bwrap --version
```

### Installing Claude Code

Follow the [official instructions](https://docs.anthropic.com/en/docs/claude-code/getting-started). Typically:

```bash
npm install -g @anthropic-ai/claude-code
```

Verify:
```bash
claude --version
```

### Installing claude-sandbox

```bash
# Option 1: copy to a directory in your PATH
cp claude-sandbox ~/.local/bin/
chmod +x ~/.local/bin/claude-sandbox

# Option 2: symlink (so updates to the repo are picked up automatically)
ln -s "$(pwd)/claude-sandbox" ~/.local/bin/claude-sandbox
```

Make sure `~/.local/bin` is in your `$PATH`. If it isn't, add this to your `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Quick start

```bash
# 1. Initialize the sandbox (copies Claude config, sanitizes gitconfig)
claude-sandbox init

# 2. Go to your project
cd ~/project/my-repo

# 3. Run Claude inside the sandbox
claude-sandbox run
```

That's it. Claude starts with `--dangerously-skip-permissions` by default (configurable) and has full autonomy within your project directory, but cannot escape.

## Usage

### Commands

#### `claude-sandbox init`

Sets up the sandbox environment. Run this once, or again with `--force` to reset.

What it does:
- Creates `~/.claude-sandbox/` directory structure
- Copies `~/.claude/` to `~/.claude-sandbox/claude-config/` (isolated copy)
- Generates a sanitized `~/.claude-sandbox/gitconfig` (credential sections stripped)
- Creates a `git` wrapper script that blocks `git push`
- Writes default `~/.claude-sandbox/config.toml`
- Auto-detects `$PATH` entries under `$HOME` and reports them

```bash
claude-sandbox init                # first-time setup
claude-sandbox init --force        # reset everything
claude-sandbox init --real-config  # use real ~/.claude directly (no copy)
```

#### `claude-sandbox run`

Launches Claude Code inside the bubblewrap sandbox.

```bash
claude-sandbox run                        # run in current directory
claude-sandbox run -p ~/project/foo       # run in a specific project
claude-sandbox run -P zai                 # run with "zai" provider profile
claude-sandbox run --profile mm           # run with "mm" provider profile
claude-sandbox run --safe                 # disable --dangerously-skip-permissions
claude-sandbox run --log                  # enable session transcript logging
claude-sandbox run --dry-run              # print the bwrap command without executing
claude-sandbox run --continue             # --continue passed to Claude automatically
claude-sandbox run --model opus --resume ID  # --model and --resume passed to Claude
claude-sandbox run -- -p                  # -p passed to Claude (--print) via separator
claude-sandbox run -p /tmp --continue     # -p /tmp to sandbox, --continue to Claude
```

**CLI pass-through**: Options not recognized by `claude-sandbox run` are passed directly to Claude. This means you can use Claude CLI flags like `--continue`, `--model`, `--resume`, `--print` (long form) without the `--` separator. The `--` separator is still supported for edge cases, e.g. when you need to pass `-p` to Claude (since `-p` is used by claude-sandbox for `--project`).

On launch, it prints a banner showing active protections:
```
claude-sandbox
  profile     zai (Vertex AI via zai project)
  project     /home/you/project/my-repo
  filesystem  read-only root, writable project dir
  network     enabled
  pid isolat. on
  git push    blocked
  env vars    clearenv + whitelist
```

#### `claude-sandbox diff`

Shows a unified diff between your real `~/.claude/` config and the sandbox's isolated copy. Useful to see what Claude changed inside the sandbox (installed MCP servers, modified settings, etc.).

```bash
claude-sandbox diff
```

#### `claude-sandbox merge`

Interactive file-by-file merge of sandbox config changes back to your real `~/.claude/`. For each changed file, you can (a)pply, (s)kip, view (d)iff, or (q)uit.

```bash
claude-sandbox merge
```

This is the safe way to adopt changes Claude made in the sandbox (like installing a new MCP server or skill) into your real environment.

#### `claude-sandbox status`

Shows the current state of the sandbox: config location, file counts, toolchain cache sizes, log count, bwrap version, and pending config changes.

```bash
claude-sandbox status
```

## Configuration

The config file is searched in order:

1. **`./.claude-sandbox/config.toml`** — project-local (takes priority)
2. **`~/.claude-sandbox/config.toml`** — global fallback

This lets you have project-specific sandbox settings (different profiles, extra writable dirs, etc.) while keeping a global default. If no config is found in either location, the sandbox refuses to start with a clear error.

There is no inline default config — you must always have a real `config.toml` file. Create one with `claude-sandbox init`, or copy an existing one into `.claude-sandbox/` in your project directory.

Here's a reference of every option:

### `[sandbox]`

```toml
[sandbox]
# Extra directories Claude can write to (besides the current project)
extra_rw = []

# Directories Claude can read (but not write)
ro_dirs = ["~/project"]

# Persist build tool caches (cargo registry, npm cache, go modules)
persist_toolchains = true

# Auto-detect PATH entries under $HOME and expose them read-only.
# This makes tools installed in ~/.local/bin, ~/.cargo/bin, ~/.nvm, etc.
# available inside the sandbox without manual configuration.
auto_expose_path = true

# Additional home subdirectories to expose read-only (relative to $HOME).
# .config/gcloud is needed for Vertex AI / Google Cloud authentication.
home_ro_dirs = [".config/gcloud"]
# Other examples: ".rustup", ".nvm", ".pyenv"

# Default provider profile (used when -P is not specified).
# Set to a profile name defined in [profiles.*].
# Leave empty to run without a profile.
default_profile = "zai"
```

### `[claude]`

```toml
[claude]
# Arguments always passed to Claude.
# --dangerously-skip-permissions is the default (the whole point of the sandbox).
# To disable it for a single run, use: claude-sandbox run --safe
default_args = ["--dangerously-skip-permissions"]

# Where the sandbox keeps its isolated copy of Claude's config
config_dir = "~/.claude-sandbox/claude-config"

# Use the real ~/.claude and ~/.claude.json directly (no isolated copy).
# Skips the copy during init and mounts the real dirs in the sandbox.
# Disables diff/merge commands (no separate copy to compare against).
use_real_config = false
```

### `[git]`

```toml
[git]
# Regex patterns for .gitconfig section headers to strip.
# "credential" removes all credential helpers.
# 'url ".*"' removes URL rewrite rules (often used for auth).
strip_sections = ['credential', 'url ".*"']

# Git config values forced in the sanitized gitconfig.
# push.default = nothing means bare `git push` does nothing.
[git.overrides]
"push.default" = "nothing"
```

### `[env]`

```toml
[env]
# Explicit whitelist of host environment variables passed into the sandbox.
# EVERYTHING ELSE IS STRIPPED. This is the main defense against
# leaking AWS_SECRET_ACCESS_KEY, GITHUB_TOKEN, etc.
#
# API keys and provider settings should go in [profiles.*] sections,
# not here. Only terminal/locale vars need passthrough from the host.
passthrough = [
    "TERM",
    "COLORTERM",
    "TERM_PROGRAM",
    "LANG",
    "LC_ALL",
    "EDITOR",
    "VISUAL",
]

# Extra env vars to set inside the sandbox (always applied, regardless of profile)
[env.extra]
# MY_CUSTOM_VAR = "value"
```

### `[logging]`

```toml
[logging]
# Enable transcript logging by default (overridable with --log / --no-log)
enabled = false

# Where log files are stored
dir = "~/.claude-sandbox/logs"
```

When enabled, the session is recorded using the `script` command. Logs are saved as `YYYY-MM-DD_HHMMSS_projectname.log` and contain the full terminal output (including ANSI colors). View them with `cat` (colors preserved) or pipe through `col -b` for plain text.

### `[security]`

```toml
[security]
# PID namespace: Claude can only see its own processes
unshare_pid = true

# New terminal session: prevents escape-sequence attacks on the parent terminal.
# May interfere with Ctrl+C in some terminal emulators. Disabled by default.
new_session = false

# Block git push via a wrapper script
block_git_push = true
```

### `[profiles.<name>]`

Provider profiles let you put **all credentials in the TOML file** instead of depending on your shell environment. Each profile defines the environment variables needed for a specific Claude provider.

If you have wrapper commands like `zai-claude` and `mm-claude` that set env vars before launching Claude, you can replace them entirely with profiles:

```toml
[sandbox]
# Use "zai" by default when no -P flag is given
default_profile = "zai"

[profiles.zai]
description = "Vertex AI via zai project"
# Optional: override default_args for this profile
# default_args = ["--dangerously-skip-permissions", "--model", "opus"]
[profiles.zai.env]
CLAUDE_CODE_USE_VERTEX = "1"
ANTHROPIC_VERTEX_PROJECT_ID = "my-zai-project"
ANTHROPIC_VERTEX_REGION = "us-east5"

[profiles.mm]
description = "Direct Anthropic API"
[profiles.mm.env]
ANTHROPIC_API_KEY = "sk-ant-api01-..."
```

Usage:
```bash
claude-sandbox run              # uses default_profile ("zai" in example above)
claude-sandbox run -P mm        # override: uses "mm" profile instead
claude-sandbox run -P zai       # explicit: same as default in this case
```

**How it works:**
- `default_profile` in `[sandbox]` sets which profile is used when you just run `claude-sandbox run` without `-P`. All credentials come from the TOML.
- `-P <name>` overrides the default for that invocation.
- Profile env vars are set via bwrap `--setenv` and **do not need to exist in your host shell**. Your shell stays clean.
- The `[env].passthrough` list only needs terminal/locale vars (TERM, LANG, etc.) — no API keys.
- If a profile defines `default_args`, those replace the base `[claude].default_args` for that profile.

**Security note:** Since API keys live in the TOML file, make sure it has appropriate permissions:
```bash
chmod 600 ~/.claude-sandbox/config.toml
```

## Directory layout

After initialization, `~/.claude-sandbox/` contains:

```
~/.claude-sandbox/
├── config.toml             # Sandbox configuration
├── claude-config/          # Isolated copy of ~/.claude (writable by Claude)
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
└── logs/                   # Session transcripts (if logging enabled)
    └── 2025-01-15_143022_myrepo.log
```

## How build tools work inside the sandbox

**pip**: Use a virtual environment in your project directory. The venv lives inside the project (writable), so `pip install` works normally:
```bash
python -m venv .venv
source .venv/bin/activate
pip install requests  # works: writes to ./venv/
```

**npm**: `node_modules/` is created in the project directory by default, so `npm install` works out of the box. The npm download cache is redirected to a persistent sandbox directory (`~/.claude-sandbox/toolchains/npm-cache/`).

**cargo**: If you have Rust installed on your system (`~/.cargo/bin/`), the binaries are available read-only. Cargo's registry and git caches are mounted writable from `~/.claude-sandbox/toolchains/cargo/`, so `cargo build` can download dependencies.

**go**: `GOPATH` and `GOMODCACHE` are redirected to `~/.claude-sandbox/toolchains/go/`, so `go build` and `go mod download` work.

**System-installed tools**: Everything in `/usr/bin`, `/usr/local/bin`, etc. is available read-only. If you have tools installed under `$HOME` (via nvm, pyenv, sdkman, etc.), they are auto-detected from your `$PATH` and exposed read-only inside the sandbox.

## Typical workflows

### Daily development

```bash
cd ~/project/my-app
claude-sandbox run
# Claude works freely inside my-app/ but can't touch anything else
```

### Reviewing what Claude changed in config

```bash
# After a sandbox session where Claude installed an MCP server:
claude-sandbox diff
# Shows: +++ sandbox/settings.json has new mcpServers entry

claude-sandbox merge
# [MOD] settings.json
#   apply? (y)es / (n)o / (d)iff / (q)uit: d
#   <shows diff>
#   apply? (y)es / (n)o / (d)iff / (q)uit: y
#   applied.
```

### Switching between providers

```bash
# Define profiles in config.toml (see Configuration section),
# then use -P to select:
claude-sandbox run -P zai           # Vertex AI
claude-sandbox run -P mm            # Direct Anthropic API
claude-sandbox run -P zai --dry-run # inspect the bwrap command for a profile
```

### Using real Claude config (no isolated copy)

By default, `claude-sandbox init` copies `~/.claude/` into the sandbox. This lets you review changes Claude made (via `diff`/`merge`) before applying them to your real config. If you prefer to skip this isolation and let Claude work directly with your real config:

```bash
# Option 1: set during init
claude-sandbox init --real-config

# Option 2: edit config.toml
[claude]
use_real_config = true
```

With `use_real_config = true`:
- `init` skips copying `~/.claude` and `~/.claude.json`
- `run` mounts the real `~/.claude` and `~/.claude.json` writable
- `diff` and `merge` are disabled (no separate copy to compare against)

### Debugging the sandbox

```bash
# See exactly what bwrap command would be executed
claude-sandbox run --dry-run

# Check sandbox state
claude-sandbox status
```

### Logging a session for audit

```bash
claude-sandbox run --log
# After the session:
ls ~/.claude-sandbox/logs/
cat ~/.claude-sandbox/logs/2025-01-15_143022_myrepo.log
```

## Known limitations

1. **Network is open**: Claude can make outbound HTTP requests. This is necessary for the Anthropic API, package managers, and git clone. A determined prompt injection could exfiltrate project source code via the network. Restricting to specific domains is possible with iptables but fragile and not implemented.

2. **Git push bypass**: The `git` wrapper blocks `git push`, but Claude could call `/usr/bin/git push` directly. However, without SSH keys or credential helpers, the push would fail anyway (no authentication available). The wrapper is defense-in-depth.

3. **Not a VM**: bubblewrap uses Linux namespaces, which are a kernel feature. A kernel vulnerability in namespace handling could theoretically allow escape. For higher assurance, run the sandbox inside a VM.

4. **Read-only build tools**: Tools installed under `$HOME` (like `~/.cargo/bin/cargo`) are available read-only. `cargo install new-tool` inside the sandbox will fail. Use system package managers to install new tools, or add specific writable directories via `extra_rw` in config.

5. **MCP server secrets**: If your `~/.claude/settings.json` contains API keys in MCP server environment variables, those are copied to the sandbox. Review `~/.claude-sandbox/claude-config/settings.json` after init and remove any credentials you don't want exposed.

6. **Tmpfs home is writable**: The `$HOME` tmpfs overlay is writable (that's how tmpfs works). Claude can create files like `~/temp.txt`, but they are ephemeral and vanish when the sandbox exits. They never touch your real home directory.

## Troubleshooting

### "bwrap: No permissions to creating new namespace"

Your kernel may have user namespaces disabled. Check:
```bash
sysctl kernel.unprivileged_userns_clone
```
If it returns `0`, enable it:
```bash
sudo sysctl -w kernel.unprivileged_userns_clone=1
# To make permanent:
echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/99-userns.conf
```

### Claude can't find a tool (node, python, etc.)

If the tool is installed under `$HOME` but not in your `$PATH`, add its directory to `home_ro_dirs` in the config:
```toml
[sandbox]
home_ro_dirs = [".nvm", ".pyenv"]
```

### Ctrl+C doesn't work

If you have `new_session = true` in the config, try setting it to `false`. The new-session security feature can interfere with signal propagation in some terminals.

### "API Error: Unable to connect" or DNS failures

On systemd-based distros, `/etc/resolv.conf` is a symlink to `/run/systemd/resolve/stub-resolv.conf`. If the sandbox hides `/run`, DNS breaks. claude-sandbox handles this by only hiding `/run/user/$UID` (DBus/Wayland sockets) instead of all of `/run`. If you still see DNS issues, check:
```bash
# Inside the sandbox:
cat /etc/resolv.conf
# Should show your DNS config, not "No such file"
```

### Using Claude with Vertex AI (Google Cloud)

If you use Claude via Vertex AI, create a profile with the Vertex env vars:
```toml
[sandbox]
home_ro_dirs = [".config/gcloud"]  # Google Cloud ADC credentials
default_profile = "vertex"

[profiles.vertex]
description = "Vertex AI"
[profiles.vertex.env]
CLAUDE_CODE_USE_VERTEX = "1"
ANTHROPIC_VERTEX_PROJECT_ID = "my-gcp-project"
ANTHROPIC_VERTEX_REGION = "us-east5"
```
The `home_ro_dirs` entry for `.config/gcloud` is included in the default config and gives Claude read-only access to your Google Cloud ADC credentials.

Do NOT add `CLAUDECODE` or `CLAUDE_CODE_ENTRYPOINT` to env passthrough or profiles: these are session markers that would trigger "nested session" detection and prevent Claude from starting.

### Claude says "permission denied" writing to a file

The file is outside the writable project directory. Either:
- Move the file into the project, or
- Add the target directory to `extra_rw` in the config:
```toml
[sandbox]
extra_rw = ["/path/to/other/dir"]
```

## License

MIT
