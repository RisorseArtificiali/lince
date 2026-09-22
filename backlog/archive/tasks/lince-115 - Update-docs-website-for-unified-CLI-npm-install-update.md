---
id: LINCE-115
title: Update docs + website for unified CLI + npm install/update
status: To Do
assignee: []
created_date: '2026-05-11 15:00'
updated_date: '2026-09-19 13:35'
labels:
  - documentation
  - epic-97
milestone: m-14
dependencies:
  - LINCE-107
  - LINCE-108
  - LINCE-109
  - LINCE-110
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/106'
  - 'https://github.com/RisorseArtificiali/lince/issues/97'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## TLDR

Update all user-facing documentation to reflect the new install/update story: Node.js + npm prereq, single `lince <sub>` CLI, `lince update` command, removal of the `lince-config` / `agent-sandbox` standalone names from PATH.

## Why

The implementation changes the user contract: install prereqs, command names users learn, and the upgrade path. If docs lag, every install attempt becomes a support ticket. Mechanical but high-impact — the last public-facing piece before the validation issue.

## Implementation plan

1. `docs/` (website, deployed to lince.sh): mention Node.js prereq (link to nodejs.org); replace `lince-config <verb>` → `lince config <verb>`; replace `agent-sandbox` as a user command with `lince sandbox` (keep mentions where the binary path matters); add an "Updating" subsection for `lince update` / `lince update --check`.
2. Top-level README.md: same edits; refresh command table if one exists; add an "Updating" section near "Installation".
3. `lince-cli/README.md` (created in #98): expand into full user-facing docs — every subcommand, every flag, exit codes, where things live on disk.
4. `sandbox/README.md`, `lince-config/README.md`, `lince-dashboard/README.md`: refresh user-facing examples to use `lince <sub>`. Internal/developer docs can keep the old names where clearly marked as internal.
5. CLAUDE.md (project guidelines): note the new architecture briefly; Installation Conventions section still rules per-module, but the user-facing entry is `lince`.
6. Memory/skill files documenting command shapes (besides lince-configure which is #101) — search and update.
7. CHANGELOG.md (create if missing): add an entry referencing this epic and milestone.

## Dependencies

- Blocks: #107
- Blocked by: #98, #99, #100, #101, #102, #103, #104, #105

## References

- Epic: #97
- Plan: `/home/maeste/.claude/plans/lince-unified-cli-npm.md` (docs portion)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Fresh-eyes read-through of the website install page makes the new flow obvious without referencing any other doc.
- [ ] #2 `grep -rn 'lince-config ' docs/ README.md` returns zero hits with trailing space (only path-form hits remain).
- [ ] #3 `lince --help` output matches what the docs claim (subcommands, flags, defaults).
- [ ] #4 CHANGELOG entry references this epic (#97) and the milestone.
- [ ] #5 Internal docs (CLAUDE.md, per-module READMEs) are consistent with each other.
- [ ] #6 No broken internal links in the docs site after rebuild.
<!-- AC:END -->
