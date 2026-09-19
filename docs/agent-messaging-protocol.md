# Terminal conversation transport

This replaces the former structured question/delegation mailbox protocol.

Agents use two authenticated Unix-socket operations: `peers` and `send`.
`send` takes `recipient`, `text` and optionally `conversation`. The host generates
sender identity from the credential; the client cannot choose a pane, process,
command, credential, or another sender. Names must resolve to one live peer in
the same host session. An explicit conversation reference must belong to the two
participants. No request ownership or task lifecycle is modeled.

The optional installation writes the agent skill and host opt-in configuration.
A host wrapper launches the original TUI, grants one per-instance credential,
renews a short lease and revokes it when the child exits. Disabled agent types
start normally without a communication credential. Existing sandbox integration
exposes only the public socket and the instance credential, not host credentials
or the Zellij control socket.

Delivery is serial, FIFO per recipient, with at most 32 pending messages and a
five-minute deadline. The worker checks the original live instance, supervised
process, original pane and existing dashboard idle signal. The status signal must
postdate registration and the preceding submission. Bob has a one-time host-side
observer for its initial empty composer because its native SessionStart is delayed
until the first input; subsequent readiness comes only from native hooks. It writes the envelope and
body as bracketed paste, waits 300 ms, and sends Enter using explicit Zellij pane
IDs. It does not focus or reveal the target. No shell evaluates peer text.
Terminal control characters in peer fields are rejected (newline/tab in the body
are allowed). Text is bounded to 16 KiB and socket frames/concurrency are bounded.

`submitted` means the terminal write commands returned successfully. It is not a
read receipt. A partial or timed-out write is `uncertain` and is never automatically
retried. The live log retains at most 200 messages; all state is session-local and
is lost on service restart. Legacy SQLite mailboxes are never opened or replayed.

Dashboard snapshots are host-only. They contain public identities and recent
messages, never credentials. Controller polls synchronize aliases using the
original pane and dashboard status ID; renaming preserves the instance ID and
conversation references, while updating name resolution and displayed names. The dashboard displays the last submitted sender
without asserting current work provenance. Skills teach reply routing and
conversation references; they do not perform polling or terminal scraping.

There is an unavoidable check/write race. Lifecycle events do not describe the
prompt editor's draft or every provider dialog. The implementation makes no claim
of atomic delivery with provider readiness, exactly-once execution, persistence,
or cancellation. The operator guide describes the opt-in and these limitations.
