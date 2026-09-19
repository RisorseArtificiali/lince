---
id: LINCE-144
title: 'Epic: Zero-friction install — curl bootstrap + prebuilt artifacts'
status: To Do
assignee: []
created_date: '2026-09-19 13:23'
labels:
  - enhancement
  - epic
  - install-friction
milestone: m-18
dependencies: []
references:
  - docs/install
  - quickstart.sh
  - scripts/check-zellij.sh
  - 'https://github.com/RisorseArtificiali/lince/issues/97'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

Installing lince today requires: Zellij >= 0.45.1, Python 3.11+, bubblewrap, git, jq, node, a C linker, rustup with the wasm32-wasip1 target, and a from-source WASM plugin build (~15-20 min, ~1GB toolchain). The existing curl entrypoint `docs/install` (served at https://lince.sh/install) checks all of these and **exits demanding manual installation**. This is the main adoption bottleneck identified in the 2026-09 herdr comparison.

## Locked decisions (2026-09-19, chat with Stefano)

1. **Channel**: curl one-liner + GitHub Releases artifacts. NOT npm (revises epic #97 / milestone m-14). npm/brew can be added later as extra channels on top of the same artifacts.
2. **Python**: floor stays **3.11** (tomllib in sandbox/agent-sandbox is the gate; 3.9 is EOL and ML deps already abandoned it). When system Python < 3.11 the installer **provisions a standalone CPython** (python-build-standalone style) — this removes the brew prerequisite on macOS and covers Ubuntu 22.04 (3.10). No changes to sandbox code.
3. **WSL**: deferred to its own follow-up subtask, not in first round.
4. **Scope**: friction-killing core ONLY. The epic #97 CLI unification (lince-cli module, moving binaries off PATH, alias removal, `lince config` surface) is **out of scope**.

## Architecture target

```
curl -sSL https://lince.sh/install | bash
  → detect OS/arch (linux x86_64/aarch64, darwin x86_64/arm64; WSL → warning)
  → provision zellij (static binary → ~/.local/bin) if missing/<0.45.1
  → provision python >=3.11 (standalone → ~/.local/share/lince/python) only if system is older
  → fetch prebuilt lince-dashboard.wasm from latest GH Release + sha256 verify
  → run module install scripts (non-interactive, idempotent — existing convention)
  → install `lince` launcher shim in ~/.local/bin (works in bash/fish/zsh)
```

Key architectural fact: wasm32-wasip1 bytecode is platform-independent — **one artifact serves all targets**.

## Current state pointers

- `docs/install` — existing curl wrapper: OS detect + prereq wall + clone to ~/.local/share/lince + delegate to quickstart.sh + cleanup clone
- `quickstart.sh` — module orchestration (interactive scenarios Mini/Full/Custom)
- `lince-dashboard/install.sh` ~lines 61-122 — rustup/cargo checks + source build (the path we bypass by default)
- `scripts/check-zellij.sh` — zellij >=0.45.1 version gate (duplicated in docs/install; keep in sync)
- `sandbox/install.sh:38` — python >=3.11 check
- No `.github/workflows` exists at all — the release pipeline subtask is the repo's first CI

## Out of scope

CLI unification (m-14 remnants stay parked), npm/brew channels, config-preserving merge (GH #108), WSL support (own subtask), voxcode changes (stays >=3.11).

## Public reconciliation pending

Epic #97 on GitHub and its sub-issues #98-#108 describe the npm channel this epic supersedes. Deciding how to reconcile them (close-as-superseded vs rewrite) is a maintainer decision on the public repo — tracked separately, not part of these tasks.
<!-- SECTION:DESCRIPTION:END -->
