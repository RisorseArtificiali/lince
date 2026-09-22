---
id: LINCE-116
title: End-to-end migration validation for unified CLI + npm
status: To Do
assignee: []
created_date: '2026-05-11 15:00'
updated_date: '2026-09-19 13:35'
labels:
  - testing
  - epic-97
milestone: m-14
dependencies:
  - LINCE-107
  - LINCE-108
  - LINCE-109
  - LINCE-110
  - LINCE-117
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/107'
  - 'https://github.com/RisorseArtificiali/lince/issues/97'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## TLDR

End-to-end validation of the unified-CLI + npm architecture: fresh-install path, update path, migration from the old curl flow, no-npm failure mode, passthrough subcommand parity, partial-failure recovery. The final gate before merging the epic branch into `main`.

## Why

Every previous sub-issue ships a slice with its own acceptance criteria, but the interactions between slices are where real users break. A dedicated validation pass — ideally on a real (or VM) clean Linux box — is the only thing that catches issues like "fresh install works but updating from an old install leaves stale state".

## Implementation plan (scenarios to execute and document)

1. **Fresh install on clean VM with Node.js**: `curl -fsSL https://lince.sh/quickstart.sh | bash` → TUI → modules install → only ~/.local/bin/lince on PATH, internal copies at ~/.local/share/lince/bin/, no legacy aliases in rc files.
2. **Fresh install without Node.js**: curl exits non-zero with documented "npm not found"; no partial state on disk.
3. **Update from old curl-installed state**: simulate legacy install (binaries at ~/.local/bin/{agent-sandbox,lince-config}, alias lines in ~/.bashrc); manually `npm install -g @risorseartificiali/lince-cli@latest` and `lince update` → stale removed, internal present, aliases stripped; subsequent `lince update --check` reports up-to-date.
4. **Passthrough parity**: `lince config list` ≡ direct binary; `lince sandbox --help` ≡ direct binary; `lince config set <key> <val> -q` ≡ direct (verify by reading the file).
5. **Selective update**: touch dashboard config; `lince update --module lince-cli`; verify dashboard config mtime unchanged.
6. **Partial-failure**: break dashboard/update.sh to exit 1 in the npm-installed copy; run `lince update`; verify sandbox + voxcode updated, dashboard fails clearly, lince-config + lince-cli not touched.
7. **WASM prebuild**: on a VM without cargo/rustup, `lince update` updates the dashboard plugin successfully (WASM ships prebuilt).
8. **lince-configure skill exercise**: representative skill flow (e.g. "switch to paranoid mode") works against the new `lince config` surface.
9. **Documentation accuracy**: follow only the website install page — reach a working install.
10. **Write validation report** at `docs/validation-m14.md` (or similar), link from the epic issue.

## Dependencies

- Blocks: —
- Blocked by: #98, #99, #100, #101, #102, #103, #104, #105, #106

## References

- Epic: #97
- Plan: `/home/maeste/.claude/plans/lince-unified-cli-npm.md` (section "Verification plan")
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Scenarios 1–9 all pass on at least one clean Linux VM (e.g. Fedora 40 per CLAUDE.md target).
- [ ] #2 Validation report committed to the repo (or attached to the epic issue) with per-scenario outcomes.
- [ ] #3 No regressions observed in lince-configure skill operations.
- [ ] #4 All scenario-specific commands behave as documented in their respective sub-issue acceptance criteria — no behavioural drift.
- [ ] #5 Epic issue (#97) checklist updated to reflect validation completion.
- [ ] #6 Scenario 11 passes: with a customized value AND a user-invented key in ~/.config/lince-dashboard/config.toml, `lince update` (without --reset-config) preserves the custom value, reports the orphan key in the 'Unrecognized config keys' notice, adds any new default keys, and leaves a .bak.* backup alongside.
<!-- AC:END -->
