---
id: LINCE-145.4
title: '`lince update`: self-update on the release channel (+ --check) (GH #353)'
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
  - 'https://github.com/RisorseArtificiali/lince/issues/353'
  - lince-dashboard/update.sh
  - lince-messages/update.sh
  - 'https://github.com/RisorseArtificiali/lince/issues/108'
parent_task_id: LINCE-145
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR closes GH #353 (epic #348). Depends on the prebuilt-plugin install path (GH #351) — the updater updates what that task installs.

## Context

Today "updating" lince means re-running the curl one-liner, which re-clones and re-runs everything. With a release channel in place (prebuilt wasm on GitHub Releases), a minimal `lince update` becomes cheap.

## Scope

1. `lince update`: re-fetch the latest release artifacts (wasm), then run each installed module's existing `update.sh` (idempotent by project convention). Keep the curl one-liner as a fully valid alternative path — update must also work after a one-liner install.
2. `lince update --check`: print installed version vs latest release, change nothing.
3. User configuration must survive updates by relying on the existing update.sh behavior. The deeper config-preserving merge problem is **GH #108 — explicitly out of scope here**; do not attempt to solve it.
4. No CLI unification: standalone updater, not the m-14 `lince` multiplexer CLI (no `lince run/sandbox/config` subcommands in this task).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `lince update` on a release-channel install updates wasm + modules and `lince` still launches afterwards
- [ ] #2 `lince update --check` performs zero writes
- [ ] #3 Update after a curl one-liner install works (both entry paths converge)
- [ ] #4 User configuration survives updates (existing update.sh behavior, no regressions)
<!-- AC:END -->
