---
id: LINCE-112
title: Add npm package manifest + installer shim (@risorseartificiali/lince-cli)
status: To Do
assignee: []
created_date: '2026-05-11 15:00'
labels:
  - enhancement
  - epic-97
milestone: m-14
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/103'
  - 'https://github.com/RisorseArtificiali/lince/issues/97'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## TLDR

Create the npm package skeleton at the repo root: `package.json` declaring `@risorseartificiali/lince-cli`, a `bin/lince-installer` shim, and an `.npmignore` that restricts the published tarball to `dist/` + `bin/` + manifest. No publish yet — this issue just establishes the structure so the release CI workflow has something to publish.

## Why

`lince update` needs to install the package globally; the curl bootstrap needs to install it too. Both depend on the package existing with a stable name, scope, and layout. Doing the manifest/structure separately from the CI workflow keeps each PR small and reviewable, and lets local developers verify the layout (`npm pack --dry-run`) before any CI is wired up.

## Implementation plan

1. `package.json` at repo root with name `@risorseartificiali/lince-cli`, version `0.1.0`, license, homepage `https://lince.sh`, repo URL, `bin: {lince-installer: ./bin/lince-installer}`, `files: [bin, dist, README.md, LICENSE]`, `os: [linux]`, `engines: {node: >=18}`.
2. `bin/lince-installer` — bash shim that `exec bash "$PKG_ROOT/dist/installer.sh" "$@"`. Placeholder until #105 lands. chmod +x.
3. `.npmignore` — denylist-then-allowlist pattern: `*` then `!dist/`, `!dist/**`, `!bin/`, `!bin/**`, `!package.json`, `!README.md`, `!LICENSE`.
4. Root README (or `README.npm.md`) — brief install + update instructions for the npm package.
5. Local verification: `npm pack --dry-run` and confirm the file list contains only bin/, package.json, README.md, LICENSE (dist/ empty until CI).
6. Do NOT run `npm publish` here — publish is in #104.

## Dependencies

- Blocks: #102, #104, #105
- Blocked by: —

## References

- Epic: #97
- Plan: `/home/maeste/.claude/plans/lince-unified-cli-npm.md` (section "Distribution via npm")
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 package.json exists at repo root, validates with `npm pkg fix --dry-run`, and declares the scope @risorseartificiali.
- [ ] #2 bin/lince-installer is executable and runs without crashing (even if it just prints a placeholder message until #105 lands).
- [ ] #3 .npmignore correctly excludes source modules: `npm pack --dry-run` shows no sandbox/**, no lince-config/**, no lince-dashboard/**.
- [ ] #4 `npm pack` (not dry-run) produces a .tgz and `tar tzf <file>` shows only the intended paths.
- [ ] #5 package.json `os` field is `[linux]` so `npm install` on macOS/Windows errors with a clear unsupported-platform message.
- [ ] #6 The repo's existing build/lint commands still pass after the additions (no regressions).
<!-- AC:END -->
