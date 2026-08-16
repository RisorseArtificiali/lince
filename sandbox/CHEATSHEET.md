# agent-sandbox Cheat Sheet

Quick reference for what the sandbox blocks and what it lets through.

## Filesystem

| Resource | Access | Notes |
|----------|--------|-------|
| Project directory (`$PWD`) | **Read-Write** | Primary workspace |
| `/` (system root) | Read-only | OS files immutable |
| `/usr`, `/bin`, `/lib` | Read-only | System binaries and libraries |
| `~/.ssh/` | **Blocked** | SSH keys hidden |
| `~/.aws/` | **Blocked** | AWS credentials hidden |
| `~/.gnupg/` | **Blocked** | GPG keyring hidden |
| `~/.kube/` | **Blocked** | Kubernetes config hidden |
| `~/.docker/` | **Blocked** | Docker credentials hidden |
| `~/.netrc` | **Blocked** | Network auth hidden |
| `~/.bash_history`, `~/.zsh_history` | **Blocked** | Shell history hidden |
| `~/.npmrc` | **Blocked** | npm tokens hidden |
| `~/.claude/` | Read-Write | Isolated copy (or real, if configured) |
| `~/.pi/` | Read-Write | Pi agent state (when `--agent pi`) |
| `~/.config/gcloud/` | Read-only | Vertex AI credentials |
| Version managers (`.nvm`, `.rustup`, `.pyenv`, `.sdkman`) | Read-only | Auto-detected from PATH |
| Toolchain caches (`.cargo/registry`, `.npm/`, `.uv-cache/`, `.go/`, `.m2/repository`) | Read-Write | Persistent across sessions, isolated from the host caches. At permissive, the real `~/.m2` is mounted instead (#286) |
| `~/.agent-sandbox/bin/` | Read-only | Sandbox helpers, first in PATH: git-push blocker + `xdg-open` host-open bridge (#284) — inside Zellij, URL opens are forwarded to the host browser via `zellij run` |
| `/tmp` | Read-Write | Fresh tmpfs, isolated from host |
| Home directory (`~/`) | Tmpfs | Ephemeral overlay, hides everything not explicitly mounted |

## Network

| Resource | Access | Notes |
|----------|--------|-------|
| Outbound HTTP/HTTPS | **Allowed** | Needed for APIs, package managers |
| DNS | **Allowed** | resolv.conf mounted |
| All outbound traffic | **Allowed** | No IP-level filtering |

## Git

| Operation | Access | Notes |
|-----------|--------|-------|
| `git status`, `log`, `diff` | **Allowed** | Local reads work |
| `git add`, `commit` | **Allowed** | Local writes work |
| `git clone`, `pull` | **Allowed** | If auth available |
| `git push` | **Blocked** | Wrapper intercepts + no credentials + `push.default=nothing` |

## Processes & Isolation

| Resource | Access | Notes |
|----------|--------|-------|
| Host processes | **Hidden** | PID namespace: agent sees only its own process tree |
| System calls | **Allowed** | No seccomp filtering |
| Linux capabilities | **Allowed** | Restricted by namespace, not by dropped caps |
| DBus / PipeWire sockets | **Hidden** | `/run/user/` is fresh tmpfs |

## Devices

| Device | Access | Notes |
|--------|--------|-------|
| `/dev/null`, `/dev/zero` | **Allowed** | Standard devices |
| `/dev/random`, `/dev/urandom` | **Allowed** | RNG |
| Block devices (`/dev/sda`, etc.) | **Blocked** | No direct disk access |
| Audio, video, input devices | **Blocked** | Not mounted |

## Environment Variables

| Variable | Access | Notes |
|----------|--------|-------|
| `TERM`, `LANG`, `EDITOR` | **Passed through** | Basic shell env |
| `PATH` | **Set by sandbox** | Includes sandbox bin, system, detected home tools, and deep subdirectories explicitly in host PATH |
| `ANTHROPIC_API_KEY` | **From provider only** | Not inherited from shell — set in `[<agent>.providers.<name>.env]` |
| `AWS_SECRET_ACCESS_KEY` | **Blocked** | Never passed |
| `GITHUB_TOKEN`, `GH_TOKEN` | **Blocked** | Never passed |
| Other secrets | **Blocked** | `--clearenv` strips everything not whitelisted |

## What This Protects Against

- Accidental or malicious writes to your host filesystem
- Credential theft (SSH, AWS, GPG, Docker, Kubernetes)
- Pushing code to remote repositories
- Inspecting host processes
- Persisting malware via cron/systemd (read-only `/etc`, `/var`)

## What This Does NOT Protect Against

- Network exfiltration (outbound traffic is open)
- Kernel exploits (namespaces are not a full VM)
- Compromised agent binary itself
