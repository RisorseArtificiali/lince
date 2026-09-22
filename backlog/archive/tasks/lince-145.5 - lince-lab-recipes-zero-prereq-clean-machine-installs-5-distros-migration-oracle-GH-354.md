---
id: LINCE-145.5
title: >-
  lince-lab recipes: zero-prereq clean-machine installs (5 distros) + migration
  oracle (GH #354)
status: To Do
assignee: []
created_date: '2026-09-19 13:38'
updated_date: '2026-09-19 13:39'
labels:
  - validation
  - install-friction
milestone: m-18
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/354'
  - lince-lab/
  - docs/install
  - 'https://github.com/RisorseArtificiali/lince/issues/268'
parent_task_id: LINCE-145
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR closes GH #354 (epic #348). Depends on the release pipeline (#349), bootstrap provisioning (#350) and prebuilt-plugin install (#351) tasks.

## Context

The m-18 install work must be validated on machines that have none of the prerequisites — that is the whole point. The repo has `lince-lab` for exactly this: disposable VMs driven by recipe TOMLs through the lince-lab CLI (broker over a unix socket). **Never** drive limactl/hypervisors directly; author a recipe and run it via the CLI.

## Scope

1. Recipes booting clean VMs and driving `curl -sSL https://lince.sh/install | bash -s -- --defaults`: Fedora (latest), Ubuntu 24.04, **Ubuntu 22.04** (exercises standalone-Python provisioning — system python 3.10), Debian 12, Arch.
2. Oracles per recipe: install completes with zero manual prerequisites (bubblewrap is the only system package); `lince` shim launches the zellij dashboard with the plugin loaded; `agent-sandbox` spawns an agent in the paranoid profile; idempotency: second installer run succeeds.
3. **Migration oracle**: a VM first installed via the OLD flow (clone + source build), then updated via the new flow, keeps a working `lince` (old alias still functional).
4. macOS: document a manual validation checklist (until lince-lab v2 Mac support, GH #268).
5. Record results in the task notes / validation doc.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Recipes for Fedora, Ubuntu 24.04, Ubuntu 22.04, Debian 12, Arch run via the lince-lab CLI and all oracles are green
- [ ] #2 Ubuntu 22.04 recipe proves standalone-Python provisioning engaged (system python 3.10)
- [ ] #3 Migration oracle green: old source-built install upgraded via new flow, previous alias still functional
- [ ] #4 macOS manual validation checklist documented
- [ ] #5 Results recorded in the task notes / validation doc
<!-- AC:END -->
