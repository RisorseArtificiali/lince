# Product requirements

Feature requirements and implementation plans are tracked in GitHub issues. Design decisions live in `docs/design/`; completed reviews and experiment records in `docs/history/`.

## Opt-in masking of mount points (2026-10-19)

- [PRD, both phases and task breakdown — issue #400](https://github.com/RisorseArtificiali/lince/issues/400)
- [Implementation plan — Phase 1 / Task 1, direct launches — issue #400 comment](https://github.com/RisorseArtificiali/lince/issues/400#issuecomment-6303656755)
- [Approved v1 design agreement](../design/mount-visibility-v1.md) and [deferred questions](../design/mount-visibility-open-questions.md)
- [Synthetic bwrap spike](../history/mount-visibility-spike-2026-10-19.md) and [PRD walkthrough dossier](../history/2026-10-19-masking-opt-in-mount-lince-walkthrough.md)

The spike was run on a machine without `Dati`; the later [VM validation report](../history/mount-masking-dati-validation.md) records the user's host test. Issue #400 and the implementation plan cover direct `agent-sandbox` launches; dashboard integration is Phase 2 of the PRD and remains follow-up work.
