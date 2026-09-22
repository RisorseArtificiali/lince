---
id: LINCE-144.1
title: 'CI: tag-triggered release pipeline with prebuilt WASM plugin + checksum'
status: To Do
assignee: []
created_date: '2026-09-19 13:24'
updated_date: '2026-09-19 13:25'
labels:
  - enhancement
  - install-friction
  - ci
milestone: m-18
dependencies: []
references:
  - lince-dashboard/plugin/
  - CLAUDE.md
parent_task_id: LINCE-144
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context

The lince repo has **no CI at all** (zero `.github/workflows`). Everything is validated locally + via lince-lab VMs. This task creates the repo's first workflows and the release artifact that the whole m-18 zero-friction-install epic depends on: the **prebuilt WASM dashboard plugin**.

Architectural fact: `wasm32-wasip1` bytecode is platform-independent — one artifact serves Linux x86_64/aarch64, macOS x86_64/arm64, WSL.

## Scope

1. **PR workflow** (`.github/workflows/plugin-ci.yml`):
   - Install rustup-managed stable toolchain + `wasm32-wasip1` target
   - Build the plugin: from `lince-dashboard/plugin/`, always with `PATH="$HOME/.cargo/bin:$PATH"` and the explicit cargo path — **never bare `cargo`** (system rustc lacks the wasm target; see project CLAUDE.md)
   - Run plugin unit tests with the wasmtime technique: `cargo test --target wasm32-wasip1 --no-run`, then `wasmtime run --preload zellij=<stub.wat> <test>.wasm` using a WAT stub exporting `host_run_plugin_command` (host `cargo test` cannot link zellij imports; technique proven during config v2 wave 2, June 2026)
2. **Release workflow** (tag-triggered, e.g. `.github/workflows/release.yml`):
   - Release-profile build of the plugin
   - Validate the artifact instantiates under wasmtime with the same zellij WAT preload stub before attaching
   - Produce `SHA256SUMS`
   - Create the GitHub Release on `RisorseArtificiali/lince` attaching `lince-dashboard.wasm` + `SHA256SUMS`

## Notes

- zellij pin: the plugin supports zellij >= 0.45.1 (Codex scrollback fixes #4941/#5357) — record the zellij version the artifact was smoke-tested against in the release notes so the installer can warn on mismatch later.
- Keep the WAT stub in-repo (versioned) so PR and release workflows share it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Tag push vX.Y.Z creates a GitHub Release on RisorseArtificiali/lince with lince-dashboard.wasm + SHA256SUMS attached
- [ ] #2 Release workflow validates the artifact under wasmtime (zellij WAT stub) before attaching; a broken artifact fails the release
- [ ] #3 PR workflow builds the plugin and runs plugin unit tests via the wasm32-wasip1 + wasmtime technique, green on a sample PR
- [ ] #4 No workflow step invokes bare `cargo` (always rustup PATH + explicit cargo path)
- [ ] #5 Release notes record the zellij version used for smoke testing
<!-- AC:END -->
