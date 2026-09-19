# Peer messaging in LINCE

Agents keep their original terminal interfaces. Messaging adds a host-owned
mailbox and the `lince-msg` command; it does not replace the TUI or use ACP.
Claude Code, Codex and Bob are the v1 adapters. Pi/OpenCode are follow-ups.

## Enable a group

Install/update the dashboard normally. Its shared installer installs the message
service, CLI and hooks while preserving existing agent settings and other hooks.
The standalone equivalent is `bash lince-messages/install.sh --configure-all`.
For Codex, review the new handlers in `/hooks`; installation does not bypass
Codex's trust policy. Start fresh agent panes so their supervisors issue fresh
instance credentials. Existing unsupervised panes cannot acquire identities by
claiming a pane name.

Open **Alt+d**, then **m** for Messages and tasks. Press **g**, create a group
with **n**, select it with **[**/**]**, and toggle membership with **Space**.
Membership is explicitly controlled by the human, including cross-project
sharing. New instances start without groups; replacing an agent does not inherit
its membership or pending assignments. Removing membership interrupts outstanding
work in that group and prevents further agent access to it.

The group view separately toggles automatic native intake with **a**. A capability
error explains when this is unavailable. Receiving a message never grants it
human authority or accepts the work on the recipient's behalf.

## Ask and delegate

Each agent receives collaboration instructions through its native startup hook.
It can use these commands from its own sandbox:

```sh
lince-msg peers
lince-msg ask INSTANCE_UUID --group GROUP_UUID --text 'Review this API change' --key review-1
lince-msg delegate INSTANCE_UUID --group GROUP_UUID --text 'Run the relevant regression checks' --key tests-1
lince-msg inbox
lince-msg get REQUEST_UUID
lince-msg accept REQUEST_UUID
lince-msg reply QUESTION_UUID --text 'Review result and evidence'
lince-msg complete TASK_UUID --text 'Test result and evidence'
lince-msg fail TASK_UUID --text 'What prevented completion'
```

`--stdin` and `--file PATH` supply longer text. The client reads files locally;
the host never opens an arbitrary path supplied in a message. Output is JSON.
`get` exposes full text and paginated events; follow its cursor with `--after`.
`inbox --after CURSOR` exposes updates and previews without accepting work.
`read REQUEST` acknowledges receipt; `accept REQUEST` claims ownership.

Use `--parent CURRENT_REQUEST` for a nested consultation. A caller can continue
independent work and check the inbox later, or `wait REQUEST --timeout 30`.
Waiting is bounded, does not block service for other clients, and rejects cyclic
blocking dependencies. Timeout never cancels a task or resends a prompt. Reuse the
same idempotency key and identical arguments for a retry after uncertain transport.

One inbound item may be active or paused per instance. Direct human input takes
precedence and pauses peer work when its origin is known; resumption is explicit.
Outgoing consultations retain the caller's original provenance. An idle terminal
or a completed model turn is not a completed task.

## Inspect and control

The status line reserves left row 1 for VoxCode, left row 2 for mailbox counts,
and the right column for `Alt+d details` and the focused agent's provenance.
`Mail` counts unread pending requests; `Work` counts read pending/active/paused
requests; `!` counts failed/interrupted requests and uncertain deliveries, without
counting an uncertain request twice. `●` marks human work and `←` accepted peer
work; unknown origin is unmarked. `[dashboard].messaging_ascii = true` uses ASCII
markers. An unavailable broker clears provenance rather than presenting stale
ownership as authoritative.

The `classic` preset retains its original Zellij bars; messaging is available
through Alt+d there. The three-area LINCE status line belongs to `minimal` and
`statusline`, including their existing Alt+b visibility modes.

Inside Messages and tasks:

| Key | Action |
| --- | --- |
| 1–6 | All, unread, waiting, active/paused, errors, completed/cancelled |
| j/k, arrows | Select a request or group member |
| Enter | Open the full request and its event history |
| Page Up / Page Down | Scroll long content |
| n / r | Older history or more thread events / refresh latest |
| c / p / u | Cancel / pause / explicitly resume |
| t / d | Retry an uncertain delivery with the same ID / reconcile it as delivered/read |
| s / f | Explicitly navigate to the original sender/recipient pane |
| g | Group membership and automatic-intake controls |
| D | Delete terminal history older than 30 days; retain live work and referenced parents |
| Escape | Back to list/groups, then back to the agent menu |

Thread views show delivery separately from work, parent linkage, timestamps,
results, and cancellation acknowledgement. Cancellation does not undo edits or
forcibly terminate a tool; the recipient uses `cancel-ack` at a safe point. Late
results remain visible for audit but cannot reopen cancelled work. Inspecting or
refreshing messages never changes the focused agent pane.

## Capabilities and platforms

The capability matrix is version-specific; see the [validation ledger](agent-messaging-validation.md)
for actual evidence and outstanding release gates. Claude 2.1.272 and Codex
0.154.0 have a documented native Stop continuation path. That is distinct from
externally waking a TUI which is already idle; no blind paste/Enter is used.
Unverified versions retain explicit inbox access with automatic intake disabled.
Bob 2.0.4 uses explicit inbox access and startup context because its documented
Stop hook ignores output. Its original TUI has been validated with SSO for
questions/tasks in both directions, startup context and human precedence.
Permission-dialog detection is unavailable: messages remain queued and automatic
intake cannot be enabled. `bob run` still requires an API key; SSO validation uses
`bob chat`. These limitations are visible in the group view.

Linux bwrap has a real transport test without Zellij IPC. Seatbelt has generated
profile checks only at this checkpoint: macOS runtime/UI support is not yet
validated. Nono is not enrolled by the dashboard messaging wrapper. Unsandboxed
agents lack filesystem isolation from other same-user host processes.

## Security, recovery and operations

The service stores plaintext history under `~/.local/state/lince-messages`,
outside project-controlled files. Per-instance credentials authenticate agents;
the separate host credential controls groups and dashboard operations. Sandboxes
receive only their own credential and the restricted mailbox socket. The API has
no host execution, arbitrary host-file access, permission approval or Zellij
control operation. Payload, queue, connection and rate limits bound usage.

The launch supervisor renews a short lease. Normal exit revokes immediately;
abrupt loss revokes within 15 seconds. A service restart preserves history,
marks active/paused work interrupted and attempted unacknowledged deliveries
uncertain, disables automatic intake, and never silently replays a prompt.
Inspect/reconcile in Alt+d. Reassigning work to a replacement requires a new
request. Deduplication does not promise exactly-once model execution.

Updating stops authenticated service processes before replacing their code;
the next dashboard poll or supervised launch starts the new version. Apply the
same recovery rules to outstanding work. Uninstall removes message handlers and
executables while retaining user settings, backups and history. Use the standalone
`lince-messages/uninstall.sh` if removing messaging independently.

If installation used a custom settings path, pass that path explicitly at removal:

```sh
bash lince-messages/install.sh --configure-claude /path/to/settings.json
bash lince-messages/uninstall.sh --settings claude /path/to/settings.json
```

Repeat `--settings AGENT PATH` for additional Claude, Codex or Bob files. Standard
settings paths are also cleaned. Other handlers/settings remain intact. If a
settings file cannot be parsed, fix it and retry; executables are retained until
hook removal succeeds.

If the mailbox is unavailable, check installation/PATH and the session's private
`service.log` under the state directory. For missing native events, verify hook
registration, Codex hook trust, the tested version and a fresh supervised pane.
Never publish credential files or full logs containing user prompts.

Messaging does not prevent conflicting edits to a shared workspace. “Read-only”
or “tests-only” peer scopes are agreements, not filesystem enforcement. This work
does not claim to repair unrelated findings in the sandbox security review.
