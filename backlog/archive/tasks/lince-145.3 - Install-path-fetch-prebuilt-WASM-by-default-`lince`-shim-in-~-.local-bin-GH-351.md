---
id: LINCE-145.3
title: >-
  Install path: fetch prebuilt WASM by default + `lince` shim in ~/.local/bin
  (GH #351)
status: To Do
assignee: []
created_date: '2026-09-19 13:38'
updated_date: '2026-09-19 13:39'
labels:
  - enhancement
  - install-friction
milestone: m-18
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/351'
  - lince-dashboard/install.sh
  - lince-dashboard/plugin/build.sh
  - quickstart.sh
parent_task_id: LINCE-145
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR closes GH #351 (epic #348). Depends on the release-pipeline task (GH #349) — there must be an artifact to fetch; develop against a manually-produced artifact if the pipeline lands later.

## Context

Today `lince-dashboard/install.sh` (around lines 61-122) checks rustup/cargo/wasm32-wasip1 and builds the plugin from source via `plugin/build.sh` — the single biggest install cost. Once the release pipeline publishes a prebuilt `lince-dashboard.wasm`, the default install path must use it and never require a Rust toolchain.

## Scope

1. **Prebuilt-first plugin install**: download `lince-dashboard.wasm` + `SHA256SUMS` from the latest GitHub Release of `RisorseArtificiali/lince`, verify checksum (abort with a clear error on mismatch), install to `~/.config/zellij/plugins/`. Wire into `lince-dashboard/install.sh` and quickstart flows as the default.
2. **`--build-from-source` fallback**: keep the entire current source-build path behind this flag; offer it explicitly when the download fails. Never silently fall back.
3. **`lince` launcher shim**: small launcher script in `~/.local/bin/lince` replicating what the current bashrc alias does (launch zellij with the lince layout). Rationale: the alias does not work in fish/zsh (lince ships fish/zsh agent registry entries). Do NOT remove or touch existing alias-based installs — alias removal is m-14 CLI-unification scope, explicitly parked (GH #100).
4. Existing source-built installs and the clone → quickstart → module-install flow must keep working unchanged (module install scripts still run from the cloned tree; the clone cleanup flow is untouched).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Fresh install on a machine without Rust ends with `lince` launching the dashboard (plugin loaded, rustup/cargo never invoked)
- [ ] #2 Checksum mismatch aborts with a clear error and no partial install
- [ ] #3 --build-from-source reproduces today's source-build behavior unchanged
- [ ] #4 Existing alias-based installs keep working untouched
- [ ] #5 `lince` shim works under bash, fish and zsh
<!-- AC:END -->
