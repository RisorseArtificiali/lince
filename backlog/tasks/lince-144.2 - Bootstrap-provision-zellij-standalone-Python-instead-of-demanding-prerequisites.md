---
id: LINCE-144.2
title: >-
  Bootstrap: provision zellij + standalone Python instead of demanding
  prerequisites
status: To Do
assignee: []
created_date: '2026-09-19 13:24'
updated_date: '2026-09-19 13:25'
labels:
  - enhancement
  - install-friction
milestone: m-18
dependencies: []
references:
  - docs/install
  - scripts/check-zellij.sh
  - sandbox/install.sh
  - quickstart.sh
parent_task_id: LINCE-144
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context

`docs/install` is the existing curl entrypoint (`curl -sSL https://lince.sh/install | bash`). Today it checks python3.11 / git / jq / node / zellij / bwrap-or-seatbelt / cc / rustup and **exits demanding manual installation** of anything missing. The m-18 goal is zero manual prerequisites: the bootstrap must **provision** what it can instead of refusing.

Locked decision (2026-09-19): Python floor stays 3.11 — we do NOT relax the sandbox to 3.9/3.10. Missing Python gets a standalone interpreter instead.

## Scope

Rework `docs/install` (keep it the single entrypoint; keep the clone → quickstart.sh delegation flow unchanged):

1. **Zellij provisioning**: reuse the >=0.45.1 version gate (already duplicated between `scripts/check-zellij.sh` and `docs/install` — keep them in sync or factor the logic). If missing or too old: download the official static binary (musl builds for Linux x86_64/aarch64, macOS builds — from zellij-org GitHub releases) into `~/.local/bin`, checksum-verify, no root.
2. **Python provisioning**: if system python3 < 3.11, download a **pinned python-build-standalone** CPython (>= 3.11) with checksum into `~/.local/share/lince/python/` and use it for the rest of the install + record it for the `lince` shim. This removes the brew prerequisite on macOS (system python there is 3.9) and covers Ubuntu 22.04 (3.10). No changes to `sandbox/agent-sandbox` itself.
3. **Reclassify the remaining checks**:
   - core, still required: git, bubblewrap (Linux — the one documented system package needing sudo; show the dnf/apt/pacman one-liner, never auto-sudo), Seatbelt (macOS, built-in)
   - agent-specific, soft warning only: node (needed only to spawn npm-installed agents like Claude Code / Codex — not a lince-core blocker)
   - source-build-only: rustup + cc required **only** when the user passes `--build-from-source` (or when artifact download fails and the user opts into fallback)
   - jq: eliminate the dependency from the bootstrap/quickstart code paths if feasible, otherwise downgrade to soft warning
4. **WSL detection** (`grep -qi microsoft /proc/version`): print a clear "WSL not supported yet — tracked separately" message and exit with a pointer to the follow-up task. Do not attempt install.
5. Idempotent re-runs; no root; keep the `--defaults` non-interactive mode working.

## Out of scope

Prebuilt plugin fetch (sibling task), update path (sibling task), WSL support itself.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On a clean Linux machine with only curl+git+bubblewrap, the bootstrap provisions zellij and (if needed) standalone Python and reaches the quickstart handoff without asking the user to install anything
- [ ] #2 On clean macOS without brew, the bootstrap provisions standalone Python >=3.11 and zellij; no brew requirement remains
- [ ] #3 System python >=3.11 and zellij >=0.45.1 already present: no downloads happen (fast path)
- [ ] #4 On WSL the script prints an explicit 'not supported yet' message and exits before installing
- [ ] #5 Missing node/jq never blocks a core install (warning at most); rustup+cc are demanded only with --build-from-source
- [ ] #6 Re-running the bootstrap is safe (idempotent)
<!-- AC:END -->
