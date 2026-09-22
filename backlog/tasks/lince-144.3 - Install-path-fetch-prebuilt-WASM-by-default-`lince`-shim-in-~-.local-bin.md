---
id: LINCE-144.3
title: 'Install path: fetch prebuilt WASM by default + `lince` shim in ~/.local/bin'
status: To Do
assignee: []
created_date: '2026-09-19 13:24'
updated_date: '2026-09-19 13:25'
labels:
  - enhancement
  - install-friction
milestone: m-18
dependencies:
  - LINCE-144.1
references:
  - lince-dashboard/install.sh
  - lince-dashboard/plugin/build.sh
  - quickstart.sh
parent_task_id: LINCE-144
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context

Today `lince-dashboard/install.sh` (around lines 61-122) checks rustup/cargo/wasm32-wasip1 and builds the plugin from source via `plugin/build.sh` — the single biggest install cost. Once the release pipeline (sibling task LINCE-144.1) publishes a prebuilt `lince-dashboard.wasm`, the default install path must use it and never require a Rust toolchain.

## Scope

1. **Prebuilt-first plugin install**: download `lince-dashboard.wasm` + `SHA256SUMS` from the latest GitHub Release of `RisorseArtificiali/lince`, verify checksum (abort with a clear error on mismatch), install to `~/.config/zellij/plugins/`. Wire this into `lince-dashboard/install.sh` and the quickstart flows as the default.
2. **`--build-from-source` fallback**: keep the entire current source-build path behind this flag; also offer it explicitly when the artifact download fails. Never silently fall back.
3. **`lince` launcher shim**: install a small launcher script in `~/.local/bin/lince` replicating what the current bashrc alias does (launch zellij with the lince layout). Rationale: the alias does not work in fish/zsh (lince even ships fish/zsh agent registry entries). Do NOT remove or touch existing alias-based installs — alias removal is m-14 CLI-unification scope, explicitly parked.
4. Existing source-built installs and the clone → quickstart → module-install flow must keep working unchanged (module install scripts still run from the cloned tree; the clone cleanup flow is untouched).

## Dependencies

Needs the release pipeline (sibling task LINCE-144.1) to exist so there is an artifact to fetch; develop against a manually-produced artifact if the pipeline lands later.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Fresh install on a machine without Rust ends with `lince` launching the dashboard (plugin loaded, rustup/cargo never invoked)
- [ ] #2 Checksum mismatch aborts with a clear error and no partial install
- [ ] #3 --build-from-source reproduces today's source-build behavior unchanged
- [ ] #4 Existing alias-based installs keep working untouched
- [ ] #5 `lince` shim works under bash, fish and zsh
<!-- AC:END -->
