# Direct mount masking — `Dati` VM validation (user report)

On 2026-10-20 the user reported testing Task 1 on a purpose-built VM with a
mounted `/run/media/alessio/Dati` directory and the `/dati` symlink. The user
reported that the behavior matched their expectations. This is a report of the
user's real-host test, **not** a command transcript or an independently repeated
test by this review session; individual commands, exit codes, sandbox levels and
the precise views/writes observed were not supplied. The source-tree synthetic
mount matrix additionally checks sibling invisibility, symlink view, persistent
project writes and ephemeral outside-project writes at available bwrap levels.

The configured path is masked in the namespace. Hidden scripts or runtime
dependencies may fail only when used; that diagnostic timing does not make the
original data visible through the masked path. See the [PRD](https://github.com/RisorseArtificiali/lince/issues/400)
and [security model](../documentation/sandbox/security-model.md) for the
per-path scope and limitations.
