---
id: LINCE-144.5
title: >-
  lince-lab recipes: zero-prereq clean-machine installs (Fedora/Ubuntu
  22.04+24.04/Debian/Arch) + migration oracle
status: To Do
assignee: []
created_date: '2026-09-19 13:24'
updated_date: '2026-09-19 13:25'
labels:
  - validation
  - install-friction
milestone: m-18
dependencies:
  - LINCE-144.1
  - LINCE-144.2
  - LINCE-144.3
references:
  - lince-lab/
  - docs/install
  - 'https://github.com/RisorseArtificiali/lince/issues/268'
parent_task_id: LINCE-144
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context

The m-18 install work must be validated on machines that have none of the prerequisites — that is the whole point. The repo has `lince-lab` for exactly this: disposable VMs driven by recipe TOMLs through the lince-lab CLI (broker over a unix socket). **Never** drive limactl/hypervisors directly; author a recipe and run it via the CLI.

## Scope

1. Recipes booting clean VMs and driving `curl -sSL https://lince.sh/install | bash -s -- --defaults`:
   - Fedora (latest)
   - Ubuntu 24.04
   - Ubuntu 22.04 — specifically exercises the standalone-Python provisioning path (system python 3.10)
   - Debian 12
   - Arch
2. Oracles per recipe:
   - install completes with zero manual prerequisites (bubblewrap pre-installed in the image or its documented one-liner is the only system package)
   - `lince` shim launches the zellij dashboard with the plugin loaded
   - `agent-sandbox` spawns an agent in the paranoid profile
   - idempotency: running the installer a second time succeeds
3. **Migration oracle**: a VM first installed via the OLD flow (clone + source build), then updated via the new flow, keeps a working `lince` (old alias still functional).
4. macOS: document a manual validation checklist (until lince-lab v2 Mac support, GH #268, is available).
5. Record results in the task notes / validation doc.

## Dependencies

Depends on the release pipeline, bootstrap provisioning, and prebuilt-plugin install tasks.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Recipes for Fedora, Ubuntu 24.04, Ubuntu 22.04, Debian 12, Arch run via the lince-lab CLI and all oracles are green
- [ ] #2 Ubuntu 22.04 recipe proves standalone-Python provisioning engaged (system python 3.10)
- [ ] #3 Migration oracle green: old source-built install upgraded via new flow, previous alias still functional
- [ ] #4 macOS manual validation checklist documented
- [ ] #5 Results recorded in the task notes / validation doc
<!-- AC:END -->
