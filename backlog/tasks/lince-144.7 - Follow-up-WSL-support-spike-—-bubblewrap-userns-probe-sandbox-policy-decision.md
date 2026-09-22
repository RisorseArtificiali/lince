---
id: LINCE-144.7
title: >-
  Follow-up: WSL support spike — bubblewrap/userns probe + sandbox policy
  decision
status: To Do
assignee: []
created_date: '2026-09-19 13:24'
updated_date: '2026-09-19 13:25'
labels:
  - spike
  - install-friction
  - wsl
milestone: m-18
dependencies: []
references:
  - sandbox/agent-sandbox
  - docs/install
parent_task_id: LINCE-144
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context

Deferred by Stefano on 2026-09-19: WSL is NOT part of the first zero-friction-install round. This task tracks the investigation so the deferral is not lost.

The known risk: zellij and the WASM plugin are expected to work fine on WSL2, but **bubblewrap** — the core of the lince sandbox, our main differentiator — depends on unprivileged user namespaces, which have historically been unreliable on Microsoft's WSL2 kernels (varies with kernel version, systemd on/off, apparmor).

## Scope (spike — findings, not code)

1. Probe matrix on WSL2 variants (systemd enabled/disabled, recent Microsoft kernels): `unshare -Ur true`, then bubblewrap from the distro package; note failures verbatim.
2. Determine whether paranoid/normal sandbox profiles can work at all; Landlock availability on the WSL kernel is part of the question.
3. If sandboxing cannot work: recommend a policy between (a) loud opt-in degraded mode — no sandbox, explicit consent + persistent warning in the dashboard status line — and (b) "unsupported on this kernel". Per project principle: NEVER run agents unsandboxed silently.
4. Ubuntu 22.04-on-WSL Python is already covered by the standalone-Python provisioning task — not re-investigated here.
5. Output: GitHub issue with the findings matrix + recommendation, linked back to this task.

## Acceptance

- Findings documented with kernel/systemd matrix
- Policy recommendation recorded
- No code changes required in this task
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Findings documented as a kernel/systemd matrix with verbatim probe failures
- [ ] #2 Sandbox policy recommendation (loud opt-in degraded mode vs unsupported) recorded with rationale
- [ ] #3 GitHub issue with findings opened and linked back to this task
- [ ] #4 No production code changes included
<!-- AC:END -->
