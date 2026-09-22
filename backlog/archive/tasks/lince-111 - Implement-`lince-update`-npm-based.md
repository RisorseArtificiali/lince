---
id: LINCE-111
title: Implement `lince update` (npm-based)
status: To Do
assignee: []
created_date: '2026-05-11 14:59'
updated_date: '2026-05-11 19:12'
labels:
  - enhancement
  - epic-97
milestone: m-14
dependencies:
  - LINCE-107
  - LINCE-112
  - LINCE-117
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/102'
  - 'https://github.com/RisorseArtificiali/lince/issues/97'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## TLDR

Implement the real `lince update` subcommand. It checks `npm` is available, runs `npm install -g @risorseartificiali/lince-cli@latest`, detects which modules are installed, and runs each module's existing `update.sh` from the freshly installed npm package tree.

## Why

This is the headline feature of the epic: replace the "re-run the curl one-liner to upgrade" UX with a single `lince update` command that's discoverable, predictable, and safe. By delegating to each module's existing `update.sh`, we avoid duplicating any install logic. By going through npm, we get version pinning, prebuilt artifacts (no `cargo`/`rustup` on user machines), and a real distribution channel.

## Implementation plan

1. Replace the `cmd_update` stub in `lince-cli/lince` with the real implementation.
2. Pre-flight: `shutil.which("npm")` — if missing, print clear error pointing at https://nodejs.org/, exit non-zero.
3. `--check` mode: `npm view @risorseartificiali/lince-cli version`, compare to embedded `__version__`. Report 'up to date' or 'X → Y'. No mutations.
4. Update flow: `npm install -g @risorseartificiali/lince-cli@latest` (streamed stdout, raise on non-zero). Resolve `npm root -g` → `<root>/@risorseartificiali/lince-cli/dist/`.
5. Module detection (filesystem-based): sandbox = `~/.local/share/lince/bin/agent-sandbox` exists; voxcode = `shutil.which("voxcode")`; dashboard = `~/.config/lince-dashboard/config.toml` exists; lince-cli/lince-config = always.
6. If `--module <name>` repeatable, restrict to that set; else update all detected.
7. Run updates in order: sandbox → voxcode → lince-dashboard → lince-config → lince-cli. Each `subprocess.run(["bash", str(dist_path/module/"update.sh")], check=True)` with streamed output. Stop on first failure with module name + stderr.
8. Self-update safety: lince-cli is last; overwriting `~/.local/bin/lince` while the running interpreter holds the file is safe on Linux. No re-exec.
9. `--version` flag on top-level parser prints `__version__`.

## Dependencies

- Blocks: #107
- Blocked by: #98, #103

## References

- Epic: #97
- Plan: `/home/maeste/.claude/plans/lince-unified-cli-npm.md` (section "`lince update` behaviour")
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On a machine without npm, `lince update` fails with the documented error message and non-zero exit code.
- [ ] #2 On a machine with npm, `lince update --check` reports current vs latest without mutating anything (verify via mtime on ~/.local/bin/lince).
- [ ] #3 `lince update` on an up-to-date install completes successfully and is essentially a no-op (running each update.sh idempotently).
- [ ] #4 `lince update` after publishing a new version actually moves the installed binaries to the new version.
- [ ] #5 `lince update --module lince-cli` does not touch ~/.config/lince-dashboard/config.toml (verify mtime).
- [ ] #6 If lince-dashboard/update.sh is artificially broken to exit 1, `lince update` stops at that module and prints a clear error; subsequent modules (lince-config, lince-cli) are not touched.
- [ ] #7 `lince --version` prints the embedded __version__.
<!-- AC:END -->
