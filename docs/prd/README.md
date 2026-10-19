# Product requirements

PRDs in this directory are the versioned requirements for LINCE features. Implementation plans live in `docs/superpowers/plans/`; design decisions in `docs/design/`; completed reviews and experiment records in `docs/history/`. Use the repository copies below as the source of truth for future edits; the original workspace documents remain archival snapshots.

## Opt-in masking of mount points (2026-10-19)

- [PRD, both phases and task breakdown](2026-10-19-masking-opt-in-mount-lince.md)
- [Implementation plan — Phase 1 / Task 1, direct launches](../superpowers/plans/2026-10-19-mount-masking-direct-launches.md)
- [Approved v1 design agreement](../design/mount-visibility-v1.md) and [deferred questions](../design/mount-visibility-open-questions.md)
- [Synthetic bwrap spike](../history/mount-visibility-spike-2026-10-19.md) and [PRD walkthrough dossier](../history/2026-10-19-masking-opt-in-mount-lince-walkthrough.md)

The spike was run on a machine without `Dati`; the host acceptance checks in the PRD remain pending until performed. The implementation plan covers direct `agent-sandbox` launches; dashboard integration is Phase 2 of the PRD.
