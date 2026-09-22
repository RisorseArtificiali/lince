---
id: LINCE-114
title: Rewrite quickstart.sh as npm bootstrap
status: To Do
assignee: []
created_date: '2026-05-11 15:00'
updated_date: '2026-09-19 13:35'
labels:
  - enhancement
  - epic-97
milestone: m-14
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/105'
  - 'https://github.com/RisorseArtificiali/lince/issues/97'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## TLDR

Rewrite the `quickstart.sh` served from `https://lince.sh/quickstart.sh` to be a short npm bootstrap: verify npm, set `npm config prefix` to `~/.local`, run `npm install -g @risorseartificiali/lince-cli@latest`, then exec the package's installer. Move today's interactive TUI logic into `dist/installer.sh` inside the npm package.

## Why

Once the npm package is published by CI, both install and update can flow through it — but only if the curl entry point points users at the package instead of cloning/copying the source directly. After this lands, the same `curl https://lince.sh/quickstart.sh | bash` one-liner works but goes through the npm channel internally.

## Implementation plan

1. Keep `quickstart.sh` as the curl-served file (URL is the user contract). Rename the existing interactive TUI to `installer.sh`.
2. New short `quickstart.sh` (~40 lines): verify `npm`, error to nodejs.org if missing; if `npm config get prefix` ∈ {/usr, /usr/local} then `npm config set prefix "$HOME/.local"`; warn if `~/.local/bin` not in PATH; `npm install -g @risorseartificiali/lince-cli@latest`; `exec lince-installer "$@"`.
3. Move today's quickstart.sh content to `installer.sh` (pure rename — logic unchanged).
4. Update `bin/lince-installer` (created in #103) so it execs `dist/installer.sh`.
5. Update release CI (#104) to stage `installer.sh` into `dist/` (not `quickstart.sh`).
6. Update `docs/` so the install snippet still uses the same URL — only the script body changes.
7. Audit repo grep for `quickstart.sh` — update READMEs, comments, scripts that referenced old interactive content.

## Dependencies

- Blocks: —
- Blocked by: #103, #104

## References

- Epic: #97
- Plan: `/home/maeste/.claude/plans/lince-unified-cli-npm.md` (section "Bootstrap")
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On a fresh VM with Node.js installed: `curl -fsSL https://lince.sh/quickstart.sh | bash` completes, walks the user through the interactive TUI, and ends with a working install.
- [ ] #2 On a fresh VM without Node.js: the same curl command fails with the documented 'npm not found' message and non-zero exit code, with no partial state on disk.
- [ ] #3 After install, `npm config get prefix` returns $HOME/.local (if previously system-wide) and ~/.local/bin/lince is present.
- [ ] #4 installer.sh runs standalone (from inside an unpacked npm package) and reproduces today's TUI flow.
- [ ] #5 The website's install instructions are unchanged in form (same URL).
- [ ] #6 No references to the old monolithic quickstart.sh content remain in the repo (grep returns only the new short bootstrap + history).
<!-- AC:END -->
