---
id: LINCE-145.7
title: >-
  Follow-up: WSL support spike — bubblewrap/userns probe + sandbox policy
  decision (GH #356)
status: To Do
assignee: []
created_date: '2026-09-19 13:38'
labels:
  - spike
  - install-friction
  - wsl
milestone: m-18
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/356'
  - sandbox/agent-sandbox
  - docs/install
parent_task_id: LINCE-145
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Findings go on GH #356 (epic #348). Deferred by Stefano on 2026-09-19: WSL is NOT part of the first zero-friction-install round — this task keeps the investigation from being lost.

## Context

The known risk: zellij and the WASM plugin are expected to work fine on WSL2, but **bubblewrap** — the core of the lince sandbox, our main differentiator — depends on unprivileged user namespaces, historically unreliable on Microsoft's WSL2 kernels (varies with kernel version, systemd on/off, apparmor).

## Scope (spike — findings, not code)

1. Probe matrix on WSL2 variants (systemd enabled/disabled, recent Microsoft kernels): `unshare -Ur true`, then bubblewrap from the distro package; note failures verbatim.
2. Determine whether paranoid/normal sandbox profiles can work at all; Landlock availability on the WSL kernel is part of the question.
3. If sandboxing cannot work: recommend a policy between (a) loud opt-in degraded mode — no sandbox, explicit consent + persistent warning in the dashboard status line — and (b) "unsupported on this kernel". Per project principle: NEVER run agents unsandboxed silently.
4. Ubuntu 22.04-on-WSL Python is already covered by the standalone-Python provisioning task — not re-investigated here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Findings documented as a kernel/systemd matrix with verbatim probe failures
- [ ] #2 Sandbox policy recommendation (loud opt-in degraded mode vs unsupported) recorded with rationale
- [ ] #3 Findings posted on GH #356
- [ ] #4 No production code changes included
<!-- AC:END -->
