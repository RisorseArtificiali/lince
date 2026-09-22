---
id: LINCE-145.1
title: >-
  CI: tag-triggered release pipeline with prebuilt WASM plugin + checksum (GH
  #349)
status: To Do
assignee: []
created_date: '2026-09-19 13:37'
labels:
  - enhancement
  - install-friction
  - ci
milestone: m-18
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/349'
  - lince-dashboard/plugin/
  - CLAUDE.md
parent_task_id: LINCE-145
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR closes GH #349 (epic #348).

## Context

The repo has **no CI at all** (zero `.github/workflows`). Everything is validated locally + via lince-lab VMs. This task creates the repo's first workflows and the release artifact the whole m-18 epic depends on: the **prebuilt WASM dashboard plugin**. Architectural fact: `wasm32-wasip1` bytecode is platform-independent — one artifact serves Linux x86_64/aarch64, macOS x86_64/arm64, WSL.

## Scope

1. **PR workflow** (`.github/workflows/plugin-ci.yml`): rustup-managed stable toolchain + `wasm32-wasip1` target; build from `lince-dashboard/plugin/` — always `PATH="$HOME/.cargo/bin:$PATH"` + explicit cargo path, **never bare `cargo`** (system rustc lacks the wasm target; see project CLAUDE.md). Run plugin unit tests via `cargo test --target wasm32-wasip1 --no-run` then `wasmtime run --preload zellij=<stub.wat> <test>.wasm` with a WAT stub exporting `host_run_plugin_command` (host `cargo test` cannot link zellij imports; technique proven June 2026, config v2 wave 2).
2. **Release workflow** (tag-triggered `.github/workflows/release.yml`): release-profile build; validate the artifact instantiates under wasmtime with the same WAT preload stub BEFORE attaching; produce SHA256SUMS; create the GH Release attaching `lince-dashboard.wasm` + `SHA256SUMS`. Record the smoke-tested zellij version in release notes (plugin supports zellij >= 0.45.1 — Codex scrollback fixes zellij#4941/#5357).
3. Keep the WAT stub in-repo, shared by both workflows.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Tag push vX.Y.Z creates a GitHub Release on RisorseArtificiali/lince with lince-dashboard.wasm + SHA256SUMS attached
- [ ] #2 Release workflow validates the artifact under wasmtime (zellij WAT stub) before attaching; a broken artifact fails the release
- [ ] #3 PR workflow builds the plugin and runs plugin unit tests via the wasm32-wasip1 + wasmtime technique, green on a sample PR
- [ ] #4 No workflow step invokes bare `cargo` (always rustup PATH + explicit cargo path)
- [ ] #5 Release notes record the zellij version used for smoke testing
<!-- AC:END -->
