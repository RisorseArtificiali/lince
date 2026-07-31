# agent-sandbox

A lightweight Linux sandbox for running [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with `--dangerously-skip-permissions` safely. It uses [bubblewrap](https://github.com/containers/bubblewrap) (the same technology behind Flatpak) to restrict what Claude can see and touch on your machine, with near-zero overhead.

## Why

Claude Code's `--dangerously-skip-permissions` flag removes all confirmation prompts, letting Claude execute any bash command, edit any file, and install anything without asking. This is great for productivity but terrifying for your system: a bad prompt, a hallucination, or a prompt injection from malicious code in a repo could wipe your home directory, exfiltrate your SSH keys, push to production, or install a backdoor.

**agent-sandbox** creates a restricted environment where Claude has full autonomy *within* the project you're working on, but physically cannot damage anything else.

## What it blocks

| Attack vector | Protection | How |
|---|---|---|
| **File deletion/modification** | Entire filesystem is read-only except the project dir | `--ro-bind / /` + `--tmpfs $HOME` |
| **SSH key theft** | `~/.ssh` does not exist inside the sandbox | Hidden by tmpfs overlay on `$HOME` |
| **Cloud credential theft** | `~/.aws`, `~/.config/gcloud`, etc. invisible | Hidden by tmpfs overlay on `$HOME` |
| **Git push** | Blocked at three layers | Wrapper script + sanitized `.gitconfig` + no credential helpers |
| **API key exfiltration** | Credential proxy keeps keys outside sandbox | Reverse proxy injects headers; keys never enter sandbox env |
| **Cloud SSRF** | Metadata endpoints blocked | Proxy blocks `169.254.169.254`, `metadata.google.internal`, etc. |
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
| **Build tools** | python, node, cargo, make, gcc, etc. | System dirs read-only + `$HOME` PATH dirs auto-detected (including deep subdirectories) |
| **Claude config** | Settings, MCP servers, skills | Isolated copy in `~/.agent-sandbox/claude-config` |
| **Package caches** | `cargo build` can download crates, npm can cache | Persistent writable dirs for registry/cache subdirectories |
| **Filesystem snapshots** | Undo agent damage to project or config dirs | rsync hardlink-based snapshots with interactive restore |

## How it works

agent-sandbox builds a [bubblewrap](https://github.com/containers/bubblewrap) command that sets up a Linux mount namespace. In plain terms, it creates a "view" of the filesystem where:

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
    └── ...other PATH dirs  read-only   (auto-detected, deep subdirs included)
```

## Sandbox Backends

| Backend | Isolation | Platform | Kernel | Dependencies | Default |
|---------|-----------|----------|--------|-------------|---------|
| **agent-sandbox** (bubblewrap) | Linux namespaces | Linux only | 3.8+ | Zero (Python stdlib + bwrap) | Default on Linux |
| **seatbelt** (`sandbox-exec`) | macOS Seatbelt | macOS only | — | Zero (built into macOS) | Default on macOS |
| **[nono](https://github.com/always-further/nono)** (deprecated) | Landlock LSM / Seatbelt | Linux + macOS | 5.13+ | Rust binary | Deprecated |

**macOS users** (experimental): use the native Seatbelt backend — run `agent-sandbox seatbelt-sync` and set `backend = "seatbelt"` (or leave `backend = "auto"`, which prefers Seatbelt on macOS) in config.toml. The legacy nono backend is deprecated; see [Migrating from nono to Seatbelt](../docs/documentation/sandbox/migration-nono-to-seatbelt.md).

## Requirements

- **Linux** (kernel 3.8+ for user namespaces) or **macOS** (via the built-in Seatbelt backend)
- **Python 3.11+** (for `tomllib`)
- **bubblewrap** (Linux) or **sandbox-exec** (macOS, ships with the OS)
- **An AI coding agent** (Claude Code, Codex, Gemini, OpenCode, Aider, [Pi](https://pi.dev), etc.)

**Install bubblewrap:** `sudo dnf install bubblewrap` (Fedora) | `sudo apt install bubblewrap` (Ubuntu/Debian) | `sudo pacman -S bubblewrap` (Arch)

> **Ubuntu 24.04+ note**: unprivileged user namespaces are AppArmor-restricted
> by default, so bwrap-based sandboxing can fail with
> `write failed /proc/self/uid_map: Operation not permitted`. Installing
> bubblewrap **from apt** ships the AppArmor profile that allows it; if you
> installed bwrap another way, either add a profile or set
> `sudo sysctl kernel.apparmor_restrict_unprivileged_userns=0`.

## Quick start

```bash
# 1. Initialize the sandbox (copies Claude config, sanitizes gitconfig)
agent-sandbox init

# 2. Go to your project
cd ~/project/my-repo

# 3. Run Claude inside the sandbox
agent-sandbox run
```

That's it. Claude starts with `--dangerously-skip-permissions` by default (configurable) and has full autonomy within your project directory, but cannot escape.

## Using providers

A **provider** is a named env-var bundle that lets you switch between API
providers (Anthropic direct, Vertex AI, Z.AI, custom endpoints …) without
editing the rest of your config. Define one or more in
`~/.agent-sandbox/config.toml`:

```toml
[claude.providers.vertex]
description = "Vertex AI"
[claude.providers.vertex.env]
CLAUDE_CODE_USE_VERTEX = "1"
ANTHROPIC_VERTEX_PROJECT_ID = "my-gcp-project"
ANTHROPIC_VERTEX_REGION = "us-east5"

[claude.providers.anthropic]
description = "Direct Anthropic API"
[claude.providers.anthropic.env]
ANTHROPIC_API_KEY = "sk-ant-..."
```

Then use `-P` / `--provider` (legacy spelling `--profile` still works) to
pick one at runtime:

```bash
# Use the default provider (or none, if not configured)
agent-sandbox run

# Use a specific provider
agent-sandbox run --provider vertex
agent-sandbox run -P anthropic

# Set a default in [sandbox] to avoid specifying it each time
[sandbox]
default_provider = "vertex"
```

> **Naming note (gh#81):** what used to be called `[profiles.*]` /
> `default_profile` is now `[providers.*]` / `default_provider`. The legacy
> spelling is still accepted (the sandbox prints a one-shot stderr
> deprecation note when only the legacy form is present); run
> `agent-sandbox migrate-providers` to rewrite your config in place. See
> `config.toml.example` for the full syntax.

## Two orthogonal axes: sandbox profile vs provider

agent-sandbox has two configuration knobs that historically shared the word
"profile" (gh#81). They are independent and can be combined freely:

| Axis | What it controls | Where it lives | How to select |
|------|------------------|----------------|---------------|
| **Sandbox profile** (a.k.a. sandbox level) | Isolation posture: file/network policy, credential proxy, namespace flags | TOML fragments under `sandbox/profiles/<agent>-<level>.toml` (`paranoid` / `normal` / `permissive` ship by default) | `--sandbox-level <name>` |
| **Provider** | Env-var bundle that switches the model provider/account (Anthropic vs Vertex vs Z.ai vs Minimax …) | `[providers.<name>]` / `[<agent>.providers.<name>]` in `~/.agent-sandbox/config.toml` | `-P <name>` / `--provider <name>`, or `[sandbox].default_provider` |

So `agent-sandbox run --sandbox-level paranoid -P zai` picks the paranoid
isolation level *and* the Z.AI env-var bundle — the two don't interact.

## Project-local config overrides

Place a `.agent-sandbox/config.toml` file in any project directory to override specific settings without duplicating the entire global config. agent-sandbox deep-merges the project-local file on top of `~/.agent-sandbox/config.toml` at startup.

```toml
# .agent-sandbox/config.toml — minimal project-local override
[security]
block_git_push = false   # allow git push in this project only
```

Lists (e.g. `extra_rw`, `allow_domains`) are **appended**, not replaced, so project-specific paths or domains accumulate on top of the global ones. See [Project-local config overrides](https://lince.sh/documentation/#/sandbox/sandbox-levels#project-local-config-overrides) in the sandbox-levels docs for more examples.

## Documentation

| Document | Description |
|----------|-------------|
| **[CLI Reference](https://lince.sh/documentation/#/sandbox/cli-reference)** | All commands and flags (man-page style) |
| **[Configuration Reference](https://lince.sh/documentation/#/sandbox/config-reference)** | Every TOML config option with types and defaults |
| **[Security Model](https://lince.sh/documentation/#/sandbox/security-model)** | Threat model, defense layers, credential proxy |
| **[Cheat Sheet](CHEATSHEET.md)** | Quick-reference table of what's allowed/blocked |
| **[nono Integration](docs/nono-integration.md)** | Alternative backend setup (macOS + Linux Landlock) |
| **[agent-sandbox vs nono](docs/comparison-agent-sandbox-vs-nono.md)** | Side-by-side feature comparison |

## Known limitations

1. **Network is open** (without credential proxy): Claude can make outbound HTTP requests. This is necessary for the Anthropic API, package managers, and git clone. A determined prompt injection could exfiltrate project source code via the network. Enable `credential_proxy = true` to at least prevent API key exfiltration and block cloud SSRF endpoints.

2. **Git push bypass**: The `git` wrapper blocks `git push`, but Claude could call `/usr/bin/git push` directly. However, without SSH keys or credential helpers, the push would fail anyway (no authentication available). The wrapper is defense-in-depth.

3. **Not a VM**: bubblewrap uses Linux namespaces, which are a kernel feature. A kernel vulnerability in namespace handling could theoretically allow escape. For higher assurance, run the sandbox inside a VM.

4. **Linux only (bwrap backend)**: the bubblewrap backend depends on Linux kernel namespaces and does not work on macOS or Windows. macOS users should use the native Seatbelt backend (`sandbox-exec`, built into macOS) — `agent-sandbox seatbelt-sync` generates the profiles. The legacy [nono](https://github.com/always-further/nono) backend is deprecated; see the [migration guide](../docs/documentation/sandbox/migration-nono-to-seatbelt.md).

5. **Read-only build tools**: Tools installed under `$HOME` (like `~/.cargo/bin/cargo`) are available read-only. `cargo install new-tool` inside the sandbox will fail. Use system package managers to install new tools, or add specific writable directories via `extra_rw` in config.

6. **MCP server secrets**: If your `~/.claude/settings.json` contains API keys in MCP server environment variables, those are copied to the sandbox. Review `~/.agent-sandbox/claude-config/settings.json` after init and remove any credentials you don't want exposed. With `credential_proxy = true`, API keys configured in providers (`[<agent>.providers.<name>.env]`) are kept outside the sandbox.

7. **Tmpfs home is writable**: The `$HOME` tmpfs overlay is writable (that's how tmpfs works). Claude can create files like `~/temp.txt`, but they are ephemeral and vanish when the sandbox exits. They never touch your real home directory.

8. **Credential proxy and HTTPS**: The credential proxy works by rewriting the agent's `*_BASE_URL` to point to the local proxy, which then forwards with credentials over HTTPS. This means the agent sees `http://localhost:PORT` instead of the real API URL. All major AI SDKs support base URL overrides, so this works transparently. Custom HTTP clients that ignore `*_BASE_URL` env vars will not benefit from the proxy.

9. **Learn mode accuracy**: The `learn` command uses `strace` to trace syscalls, which captures actual I/O but may miss paths that are checked with `access()` or `stat()` without opening. It also runs in a permissive sandbox, so the agent may access paths that would be blocked in the real sandbox. Use the report as guidance, not as an exhaustive specification.

10. **Snapshot disk usage**: While snapshots use hardlinks for deduplication, they still consume disk space for changed files. Monitor usage with `agent-sandbox snapshot-list --all` (every project, not just the current directory) and configure `max_project_snapshots` / `max_config_snapshots` to limit growth. Because the per-project maximum is only applied to the project you run from, use `agent-sandbox snapshot-prune --all-projects` to reclaim space across the whole store, including projects you have moved or deleted.

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

The sandbox auto-detects `$HOME` directories from your host `$PATH` and exposes them read-only. It also includes any deeper subdirectories that are explicitly in your host PATH — for example, if your shell has `~/Applications/apache-maven-3.9.14/bin` in `$PATH`, the sandbox will mount `~/Applications` read-only and add the deep `bin` path to the sandbox PATH automatically.

If the tool is installed under `$HOME` but not in your `$PATH`, add its directory to `home_ro_dirs` in the config:
```toml
[sandbox]
home_ro_dirs = [".nvm", ".pyenv"]
```

Note: `home_ro_dirs` only mounts the filesystem — it does not add entries to PATH. For the tool to be found, either add its `bin` directory to your host shell PATH (preferred — the sandbox will pick it up automatically) or use the full path inside the sandbox.

### Ctrl+C doesn't work

If you have `new_session = true` in the config, try setting it to `false`. The new-session security feature can interfere with signal propagation in some terminals.

### "API Error: Unable to connect" or DNS failures

On systemd-based distros, `/etc/resolv.conf` is a symlink to `/run/systemd/resolve/stub-resolv.conf`. If the sandbox hides `/run`, DNS breaks. agent-sandbox handles this by only hiding `/run/user/$UID` (DBus/Wayland sockets) instead of all of `/run`. If you still see DNS issues, check:
```bash
# Inside the sandbox:
cat /etc/resolv.conf
# Should show your DNS config, not "No such file"
```

### Using Claude with Vertex AI (Google Cloud)

If you use Claude via Vertex AI, define a `vertex` provider with the Vertex
env vars (see [Using providers](#using-providers) above for the full
example). Also expose the Google Cloud ADC credentials directory:

```toml
[sandbox]
home_ro_dirs = [".config/gcloud"]  # Google Cloud ADC credentials
```

Do NOT add `CLAUDECODE` or `CLAUDE_CODE_ENTRYPOINT` to env passthrough or
provider env tables: these are session markers that would trigger "nested
session" detection and prevent Claude from starting.

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
