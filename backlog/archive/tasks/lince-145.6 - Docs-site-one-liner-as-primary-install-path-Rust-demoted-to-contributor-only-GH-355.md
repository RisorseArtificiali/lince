---
id: LINCE-145.6
title: >-
  Docs + site: one-liner as primary install path; Rust demoted to
  contributor-only (GH #355)
status: To Do
assignee: []
created_date: '2026-09-19 13:38'
updated_date: '2026-09-19 13:39'
labels:
  - documentation
  - install-friction
milestone: m-18
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/355'
  - README.md
  - QUICKSTART.md
  - docs/install
parent_task_id: LINCE-145
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR closes GH #355 (epic #348). Depends on the install-path task (GH #351, final UX) and `lince update` (GH #353, update docs).

## Context

Once the curl bootstrap provisions everything and the plugin ships prebuilt, the user-facing documentation is wrong in a key way: it presents rustup + wasm32-wasip1 + a source build as the normal install path.

## Scope

1. `README.md`: rewrite Prerequisites — user path needs only curl + git (+ bubblewrap on Linux, the one sudo'd package); macOS needs no brew. Move Rust/wasm32-wasip1 into a clearly-marked contributor / build-from-source section.
2. `QUICKSTART.md`: update scenarios to the new bootstrap behavior (--defaults, provisioning notes).
3. Website copy at lince.sh (the site serves `docs/install` as /install).
4. Document: checksum verification, manual/offline install, `--build-from-source`, standalone-Python provisioning behavior (~/.local/share/lince/python), WSL status (unsupported, spike tracked in GH #356), and `lince update` once it lands.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No user-facing doc instructs installing rustup for a normal install; Rust appears only in contributor / build-from-source sections
- [ ] #2 One-liner documented in both interactive and --defaults forms
- [ ] #3 Checksum verification, manual/offline install, --build-from-source, standalone-Python provisioning and WSL status are all documented
- [ ] #4 README and QUICKSTART match actual bootstrap behavior (verified against a real run)
<!-- AC:END -->
