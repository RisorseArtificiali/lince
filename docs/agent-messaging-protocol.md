# Agent messaging protocol v1

Implementation contract for #333–#343. The delivery is one PR with one commit
per sub-issue. Original agent TUIs remain in their panes; ACP and replacement
TUIs are out of scope. Pi/OpenCode are follow-ups.

## Trust and transport

The host supervisor owns a session UUID, a SQLite database and an administrative
credential outside project directories. It creates a fresh instance UUID and
256-bit random bearer credential for every agent process. Only credential hashes
are stored in the database. Agent aliases and pane IDs are display/routing metadata,
never authentication. Rename, reorder and focus cannot change an instance UUID.
An exited instance is revoked; its replacement requires an explicit new assignment.

The stdlib Python service uses newline-framed UTF-8 JSON over an AF_UNIX socket.
Each connection serves one request. The public socket exposes messaging only;
administrative operations additionally require the separate supervisor credential.
Neither endpoint executes commands, reads caller-selected host files, sends keys,
approves tools nor proxies Zellij. A connection must authenticate before accessing
any state. Same UID and socket permissions alone are insufficient authentication.

Sandbox launch exposes the public endpoint and that instance's credential only.
The database, administrative credential and other instances' credentials must be
inaccessible even where home directories would otherwise be exposed. On bwrap,
mount only the public endpoint and mask private messaging state; on Seatbelt,
deny private messaging state and allow only the public socket connection. No
messaging mount exposes the Zellij socket. This does not repair unrelated sandbox
escapes; same-UID unsandboxed processes are outside this isolation boundary.

Membership is host-controlled and initially empty. Agents discover/read/send only
within explicitly enabled groups. Cross-project sharing requires a human enabling
membership. Revocation invalidates access immediately, including existing history.
The supervisor can inspect all groups for the dashboard. Project configuration
cannot enable membership or select administrative credentials.

## Wire envelope and identifiers

Request: `{"v":1,"token":"…","op":"ask","args":{…}}`.
Success: `{"v":1,"ok":true,"result":{…}}`.
Error: `{"v":1,"ok":false,"error":{"code":"access_denied","message":"…"}}`.
Unknown versions, operations and fields fail explicitly. Errors never echo tokens.
The caller identity is resolved from the token, never a sender field supplied by
the client. The CLI is **lince-msg**, leaving the current `lince` launcher alias
and unified CLI epic #97 independent.

UUIDs identify sessions, instances, groups, requests, conversations and events.
Each request contains sender/recipient instance IDs, group, kind (`question` or
`task`), text, optional parent request, conversation, delivery/work states and
timestamps. Replies and results have their own immutable event IDs and reference
the request. The sender supplies an idempotency key; a retry with identical
arguments returns the same request, while changed arguments conflict. Parent
linkage requires participant access and preserves the caller's current provenance.

The v1 request view returned by send, get and state changes has this shape
(symbolic UUIDs below; timestamps are Unix seconds):

```json
{"id":"request-uuid","conversation":"conversation-uuid","parent":null,
 "group_id":"group-uuid","sender":"instance-a","recipient":"instance-b",
 "kind":"task","text":"Run the regression check","delivery":"read",
 "work":"active","cancel_ack":0,"created":1789756000.0,"updated":1789756001.0,
 "events":[{"seq":12,"id":"event-uuid","request":"request-uuid",
            "actor":"instance-b","type":"accepted","text":"","created":1789756001.0}],
 "cursor":12,"more":false}
```

IDs and text are strings; `parent` is a request ID or null; `cancel_ack` is
integer 0/1. `cursor`/event `seq` are nonnegative integers and `more` is boolean.
Get returns at most one full event per page, retaining the full request text;
pass `after=cursor` until `more=false`. Inbox instead returns
`{"events":[...],"cursor":12,"pending":[...]}`, with bounded text previews.
Preview reads do not change receipt or ownership. Peers returns
`{"instance":"own-uuid","peers":[...],"groups":[...]}`; peer capabilities are
JSON-encoded strings in v1, while group entries contain `id` and `name`.

Events share the request envelope's protocol version. Their actor is an instance
UUID or `host`. Types include `created`, `delivery_attempt`, `delivery`, `work`,
`cancel_ack`, `accepted`, `resumed`, `reply`, `complete`, `fail`, `late_reply`,
`late_complete`, `late_fail`, `human_intervention` and `unknown_interruption`.
State-change event text carries the new value; result events carry the answer.

## Operations

| Operation | Actor | Arguments/result |
| --- | --- | --- |
| peers | member | Visible live instances, aliases, capabilities and groups |
| ask / delegate | member | recipient, group, text, key, optional parent; returns request |
| inbox | member | Pending inbound requests and updates; reading alone changes nothing |
| read | recipient | request; acknowledges receipt without acceptance |
| accept | recipient | request; claims one active inbound item |
| reply | question recipient | request, text, key; records explicit answer |
| complete / fail | recipient | request, text, key; records terminal outcome |
| cancel | requester or human | request; terminal cancellation, recipient acknowledgement separate |
| cancel-ack | recipient | request; records acknowledgement of already-cancelled work |
| pause / resume | recipient or human | request; preserve ownership; resume must be explicit |
| get | participant | request with ordered thread, including late results |
| wait | participant | request, timeout; client polls without holding a service transaction |

Administration registers/revokes instances, configures group membership, toggles
automatic intake, obtains dashboard snapshots, and reconciles uncertain delivery.
It is unavailable with agent credentials. Retrying delivery uses the same request
ID and requires an explicit decision; it never reassigns an exited recipient.

## Independent state machines

Delivery: `queued → delivered → read`. Delivery attempts are durably recorded
before exposing an envelope. A crash after an attempt without acknowledgement
produces `uncertain`; reconciliation may return it to queued with the same ID.
Voluntary `read` can acknowledge queued/delivered/uncertain messages. Receiving or
reading a message never accepts work.

Work: `pending → active` through explicit acceptance (the acceptance event is
persisted). `active → paused → active`; `active → completed/failed`;
`pending/active/paused → cancelled/interrupted`. A question's explicit `reply`
completes it; a delegated task requires `complete` or `fail`. There is at most one
active **or paused** inbound request per instance. Pausing never releases ownership.
Terminal states cannot reopen. Late results are retained as audit events without
changing terminal status. Cancelled work can be acknowledged by its recipient;
cancellation never promises undoing edits or stopping a running tool.

Human input pauses current peer work and sets human provenance when the adapter
can establish origin. Resume is explicit. Unknown origin stays unknown. Outgoing
consultations leave provenance unchanged. Only accepting/resuming establishes
peer provenance; queued/read messages and terminal R/I/P badges do not.

Waits are optional, bounded to 300 seconds, and do not cancel on timeout. The
service records expiring wait edges and rejects a cycle before registering an
edge. Clients remain able to read/reply while waiting. Responses distinguish
pending, paused, failed, cancelled and interrupted work from successful results.

## Delivery adapters

Capabilities are independently declared: instance correlation, native context
intake, safe wakeup, permission detection, question detection, human attribution,
and cancellation. `has_native_hooks` is not a safety capability. Unknown or
unsupported versions have automatic wakeup disabled with a visible reason.

Prefer bounded context delivery within a documented hook, which executes in the
actual recipient process and avoids the terminal check/write race. Never inject
text/Enter into an idle-looking pane: the foreground process may have exited or
the user may have partially typed a prompt. No delivery focuses/reveals a pane.
Permission/question/unknown/busy states queue messages; voluntary inbox reads
remain possible. A hook must not synchronously wait for peer work.

When Codex supplies `turn_id`, UserPromptSubmit and Stop callbacks use stable
keys scoped by native session, event, turn and continuation flag. The service
retains hook keys for 24 hours. Without a provider event/turn identity, identical
payloads can represent distinct human prompts; the adapter does not collapse
those by text equality. Work-operation idempotency, durable delivery state,
continuation flags and intake rate bounds still apply. These mechanisms do not
claim exactly-once native hook or model execution.

Claude, Codex and Bob retain their own TUI and get version-verified hooks plus
collaboration instructions. Bob may expose explicit inbox-only intake if no safe
automatic path is established. Any other missing capability must be reported and
tested, not hidden as apparent v1 parity. ACP is not an alternative path.

## Persistence and resource bounds

SQLite transactions atomically write state and its event, with foreign keys,
WAL and full synchronization. Service restart preserves identity/history, marks
in-progress work interrupted and unacknowledged attempts uncertain. Never replay
prompts automatically. Deduplication is not exactly-once model execution.

Limits: 64 KiB request frames; 2 MiB response frames; 16 KiB text; 128 pending inbound items per instance;
60 authenticated calls/second per instance; 64 simultaneous connections; 5-second
socket timeout; at most one envelope per hook invocation. Reject NUL, escape and
other terminal controls except LF/TAB; rendering must also sanitize legacy data.
Each session retains at most 128 registered instances (including exited ones)
and 64 groups. Reaching the instance limit requires a new session; old history
is preserved. These bounds also keep full registry snapshots within the response
frame limit.
Terminal history becomes eligible for pruning after 30 days; it is not deleted
automatically. Host-initiated pruning removes whole
terminal threads only, never active work or a parent still referenced by retained
work. Agent APIs cannot delete audit history. Messages are local plaintext.

## Example transcripts

All lines below omit the common `v`, credential and success envelope. IDs are
symbolic and responses are excerpts of the full request view above.

```json
{"op":"ask","args":{"group":"g","recipient":"reviewer","text":"Review API compatibility","key":"q1"}}
{"id":"q","kind":"question","delivery":"queued","work":"pending"}
{"op":"inbox","args":{}}
{"op":"read","args":{"request":"q"}}
{"op":"accept","args":{"request":"q"}}
{"op":"reply","args":{"request":"q","text":"The renamed flag breaks compatibility","key":"r1"}}
{"op":"wait","args":{"request":"q","timeout":10}}
{"id":"q","work":"completed"}
{"op":"delegate","args":{"group":"g","recipient":"coder","text":"Add a compatibility alias","key":"t1"}}
{"id":"t","kind":"task","work":"pending"}
{"op":"accept","args":{"request":"t"}}
{"op":"ask","args":{"group":"g","recipient":"reviewer","text":"Check this alias","parent":"t","key":"q2"}}
{"op":"complete","args":{"request":"t","text":"Alias added; regression check passes","key":"c1"}}
{"op":"fail","args":{"request":"another-task","text":"Required fixture unavailable","key":"f1"}}
{"op":"cancel","args":{"request":"queued-task"}}
```

## Evidence and release gate

Deterministic service/CLI/adapter tests and real-agent validation are separate.
Record exact agent versions, captured hook payloads, commands and observable
question/delegation outcomes in both directions for Claude/Codex/Bob, including
cross-agent and delayed replies after focus changes. Linux bwrap is a required
runtime gate. macOS/Seatbelt support requires actual transport/UI validation on
macOS; generation tests alone cannot establish that claim. Unavailable checks
remain unverified. UI validation includes a disposable Zellij session, narrow
and wide terminals, hidden/replaced panes and the three presentation presets.

The status line reserves left VoxCode/mailbox, center agent states with provenance,
and right `Alt+d details`/focused provenance. Alt+d exposes threads, filters,
membership, delivery suspension, cancellation, resume and reconciliation. Existing
VoxCode, Alt+N focus and manual agent actions remain regression gates.
