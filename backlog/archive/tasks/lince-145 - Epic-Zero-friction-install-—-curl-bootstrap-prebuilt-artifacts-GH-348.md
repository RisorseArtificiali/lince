---
id: LINCE-145
title: 'Epic: Zero-friction install — curl bootstrap + prebuilt artifacts (GH #348)'
status: To Do
assignee: []
created_date: '2026-09-19 13:37'
labels:
  - enhancement
  - epic
  - install-friction
milestone: m-18
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/348'
  - docs/install
  - quickstart.sh
  - scripts/check-zellij.sh
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

Installing lince today requires: Zellij >= 0.45.1, Python 3.11+, bubblewrap, git, jq, node, a C linker, rustup with the wasm32-wasip1 target, and a from-source WASM plugin build (~15-20 min, ~1GB toolchain). The existing curl entrypoint `docs/install` (served at https://lince.sh/install) checks all of these and **exits demanding manual installation**. This is the main adoption bottleneck identified in the 2026-09 herdr comparison.

## Locked decisions (2026-09-19, chat with Stefano)

1. **Channel**: curl one-liner + GitHub Releases artifacts. NOT npm (revises epic #97 / milestone m-14). npm/brew can be added later as extra channels on top of the same artifacts.
2. **Python**: floor stays **3.11** (tomllib in sandbox/agent-sandbox is the gate; 3.9 is EOL and ML deps already abandoned it). When system Python < 3.11 the installer **provisions a standalone CPython** (python-build-standalone style) — this removes the brew prerequisite on macOS and covers Ubuntu 22.04 (3.10). No changes to sandbox code.
3. **WSL**: deferred to its own low-priority spike subtask.
4. **Scope**: friction-killing core ONLY. The epic #97 CLI unification (lince-cli module, moving binaries off PATH, alias removal, `lince config` surface) is **out of scope** — parked in m-14.

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

## Public tracking (source of truth for PRs)

GH epic **#348** with sub-issues: #349 (CI release pipeline), #350 (bootstrap provisioning), #351 (prebuilt fetch + shim), #353 (lince update), #354 (lince-lab validation), #355 (docs), #356 (WSL spike). #97 was rescoped to CLI-unification-only and parked; #102-#107 closed as superseded.

## Current state pointers

- `docs/install` — existing curl wrapper: OS detect + prereq wall + clone to ~/.local/share/lince + delegate to quickstart.sh + cleanup clone
- `quickstart.sh` — module orchestration (interactive scenarios Mini/Full/Custom)
- `lince-dashboard/install.sh` ~lines 61-122 — rustup/cargo checks + source build (the path we bypass by default)
- `scripts/check-zellij.sh` — zellij >=0.45.1 version gate (duplicated in docs/install; keep in sync)
- `sandbox/install.sh:38` — python >=3.11 check
- No `.github/workflows` exists at all — the release pipeline subtask is the repo's first CI

## Note (2026-09-19)

This epic was previously created in backlog and was lost to a `git clean` during parallel branch operations (files were untracked). Recreated same day; GH tracking #348-356 was never affected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All subtasks closed via PRs targeting RisorseArtificiali/lince:main with `Closes #N` pointing at #349-#356
- [ ] #2 Epic-level DoD checklist on GH #348 completed
<!-- AC:END -->
