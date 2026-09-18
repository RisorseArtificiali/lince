# Agent messaging validation ledger

This is an implementation ledger, not a release certification. Unverified gates
remain required by #333/#343. Work is delivered as one PR with one commit per
sub-issue; subsequent corrections will be folded into the relevant commits.

## Recorded evidence

2026-09-18, Linux development host:

- Real bwrap client/server exchange in `test_sandbox_transport.py`: own credential
  works; administrative RPC is denied; administrative credential and Zellij socket
  are absent from the sandbox. This is a real transport check, not a model session.
- Service tests exercise group authorization/revocation, sender spoofing, control
  characters/frame bounds, rate/queue limits, concurrent retries, request ownership,
  explicit results, cancellations/late results, wait cycles and recovery.
- CLI tests exercise real service connections, stdin/local files, literal shell
  metacharacters, timeout exit code, duplicate retries and install/update/uninstall.
- Python mailbox suite: **54 passed**, including all ordered adapter pairs through
  the real CLI/service, maximum-size escaped request/results, a full 128-instance /
  64-group registry, and installed supervisor/update/restart/uninstall recovery.
  Ordered adapter pairs are deterministic fixtures, not live models.
- Dashboard Python regression suite: **33 passed**.
- Native intake tests cover permissions/questions/unknown, continuation limits,
  human interruption/resume, duplicate events, session replacement and expired
  supervisor leases. These are deterministic tests, not live TUI evidence.
- Claude Code **2.1.272**: a real `--print` session returned `LINCE_HOOK_PROBE` with
  SessionStart/UserPromptSubmit/Stop/SessionEnd payloads captured. The retained
  lifecycle-only fixture is `lince-messages/tests/fixtures/claude-2.1.272-lifecycle.json`.
  This establishes actual field names/session correlation, not question/delegation
  parity, permission-dialog handling or native Stop continuation.

## Capability evidence and remaining gates

| Agent / platform | Evidence | Still required |
| --- | --- | --- |
| Claude 2.1.272 / Linux | Actual lifecycle, native Stop continuation and bidirectional real question/task flows with Codex; deterministic adapter tests | Reviewed; declared limitations below |
| Codex 0.154.0 / Linux | Actual lifecycle, native Stop continuation and bidirectional real question/task flows with Claude; deterministic adapter tests | Reviewed; declared limitations below |
| Bob 2.0.4 (01dddf684) / Linux | Original SSO TUI: native startup context, both question/task roles with Claude, human precedence and conservative permission-dialog handling | No automatic wakeup or permission detection; headless mode still requires BOB_API_KEY |
| macOS / Seatbelt | Generated rules tested only | Real transport and UI validation before any macOS support claim |
| Dashboard | Status line and Alt+d mailbox implemented; WASI suite: 114 passed, one existing preview ignored | Reviewed; declared limitations below |

The documented Stop continuation contract for Claude/Codex does not establish a
safe external wakeup of an already idle TUI. Keep those capabilities separate.
Bob's documented Stop output is ignored; retain its original TUI and explicit
inbox path. ACP remains excluded.

Primary references consulted:

- https://code.claude.com/docs/en/hooks
- https://developers.openai.com/es-419/docs/hooks (official localized hook reference;
  the unlocalized `/docs/hooks` endpoint failed during this check)
- https://bob.ibm.com/docs/shell/configuration/lifecycle-hooks

## Reproduction

```sh
python3 -m unittest discover -s lince-messages/tests -v
python3 -m unittest discover -s scripts/tests -p 'test_x11_clipboard.py' -v
```

Basic native Claude capture command (temporary hook settings, no tools enabled):
`claude --settings SETTINGS --setting-sources '' -p --max-turns 1 --tools '' -- 'Reply exactly LINCE_HOOK_PROBE.'`
The temporary capture handler retained only event/session/source/permission/turn
metadata and called the messaging adapter; no prompt, transcript or credential
contents are included in the fixture.

Codex basic native probe: `codex exec --skip-git-repo-check --ignore-user-config
--disable plugins --sandbox read-only`, with temporary inline hooks and a no-tools
prompt. The probe used `--dangerously-bypass-hook-trust` for that invocation only
after verifying that existing user hooks were exclusively LINCE status handlers;
plugins were disabled. Product installation does not bypass trust. The retained
fixture is `lince-messages/tests/fixtures/codex-0.154.0-lifecycle.json`.

Initial Bob runtime probe (before SSO became available): `bob run --disable-mcp --disable-subagents --max-turns 1
--trust` in a disposable workspace failed before hook execution with “Bob API key
is required”. A separate original-TUI `bob chat` probe remained in “Restoring
session…” and was interrupted. Neither counts as a successful model or hook
validation. The installed adapter accepts both documented `event` and bundled
`hook_event_name` payload spellings, and never attempts automatic wakeup.

The WASI toolchain was installed through `lince-dashboard/tests/setup-wasm-toolchain.sh`.
`bash lince-dashboard/tests/run-plugin-tests.sh` executes the Rust tests under
wasmtime (114 passed, one pre-existing preview ignored at this checkpoint).
This is stronger than a host `cargo check`; actual Zellij evidence follows below.

Alt+d mailbox implementation: `m` opens messages, `1`–`6` filter durable history,
Enter opens full paginated threads, and `g` opens host-controlled membership and
automatic-intake settings. Tests cover pinned IDs, stale asynchronous responses,
selection preservation, explicit navigation, cancellation acknowledgement, late
results and Unicode wrapping. Host API tests cover equal-timestamp pagination,
filter validation/authorization and deliberate uncertain-delivery reconciliation.

## Real terminal and continuation evidence

Zellij **0.45.1**, Linux: `check-ui-session.py --messaging` passed for both
statusline and minimal presets. The test installs an isolated real broker and
observes the actual PTY rendering with pyte, because Zellij's `dump-screen`
returns empty output for WASM panes. It exercises mailbox counts, accepting on a
hidden recipient without focus changes, focused-agent provenance, full threads,
pause/resume/cancel/acknowledgement, explicit navigation and group membership.
Existing voice controls/delivery, global popups, sidebar/status modes, geometry
and save/quit checks also passed. Agents in this smoke are harmless fixtures.
The classic preset was separately exercised with the real mailbox and Alt+d
controls; it retains its original Zellij chrome and has no LINCE attention bar.

```sh
bash lince-dashboard/tests/setup-ui-test-env.sh /tmp/lince-ui-test-venv
/tmp/lince-ui-test-venv/bin/python lince-dashboard/tests/check-ui-session.py \
  --zellij /path/to/zellij-0.45.1 --messaging
```

Claude **2.1.272** native intake: one request was queued before a real `--print`
run with tools disabled and automatic native intake enabled. The first Stop
returned a block reason containing the peer envelope; Claude continued and its
final response included `LINCE_NATIVE_DELIVERY`. Captured events show two Stop
events, first `stop_hook_active=false`, then `true`, followed by SessionEnd.
See `fixtures/claude-2.1.272-stop-continuation.json` under `lince-messages/tests`.
This establishes native continuation and delivery only: no CLI acceptance/reply
was performed, no automatic idle wakeup or full cross-agent completion is claimed.

Repeat the opt-in Claude continuation check using the configured model access:

```sh
python3 lince-messages/tests/probe-claude-intake.py --output /tmp/claude-intake-evidence.json
```

The probe disables agent tools, uses temporary hook settings without changing
user settings, and exports only lifecycle metadata and a bounded outcome.

Codex **0.154.0** native intake: a real `exec` session received the queued peer
envelope through Stop and continued with `stop_hook_active=true`; its final
response included `LINCE_NATIVE_DELIVERY`. The probe used the same temporary
inline hooks and reviewed, invocation-only trust bypass as the lifecycle probe.
It attempted `lince-msg --help`, which failed because this probe did not install
the CLI on PATH. Delivery was verified; acceptance/reply was not. Captured
lifecycle fields are in `fixtures/codex-0.154.0-stop-continuation.json`.

## Real Claude ↔ Codex questions and delegation

2026-09-18: concurrent Claude **2.1.272** `--print` and Codex **0.154.0** `exec`
sessions each sent a question and a task, accepted their peer's incoming work,
posted explicit replies/results, and read their outgoing result events. Both
processes exited 0. All four requests finished `completed` with `delivery=read`,
and the broker recorded the recipient's explicit acceptance and result for each.
Questions asked for 17 + 25 (42); tasks asked for the word count of “red green
blue” (3). The retained evidence is
`lince-messages/tests/fixtures/claude-codex-2026-09-18-exchanges.json`.

The native CLIs used temporary hooks and the actual restricted message CLI with
per-instance credentials. Claude allowed only Bash calls to that CLI and sleep;
Codex's inner sandbox was disabled for the probe, within the current development
environment. Therefore this is real model/CLI/broker evidence, **not** a claim of
an interactive TUI, permission-dialog or bwrap agent-session test. Automatic
intake was off: both agents used the explicit inbox workflow. No Bob parity is
inferred. Codex's invocation-only hook-trust bypass was preceded by verification
that all existing handlers were exactly `codex-status-hook.sh`, with plugins
disabled and user configuration ignored.

The opt-in reproduction script requires reviewing those handlers explicitly:

```sh
python3 lince-messages/tests/probe-native-pair.py --reviewed-hook-trust
```

This uses authenticated model access and retains artifacts in a private temporary
directory. It is not run by installers or the deterministic test suite.
The checked-in probe was also run successfully: both processes exited 0 and its
four-request completion assertions passed, independently reproducing the exchange.

## Original native TUIs: human precedence and permission dialogs

2026-09-18, Linux: the original Claude **2.1.272** and Codex **0.154.0** TUIs
were launched in separate PTYs, using the already-trusted LINCE workspace and
temporary message-hook settings. The fixture first accepted a delegated item
through the broker. A real initial human prompt, “Reply exactly
HUMAN_OVERRIDE_READY. Do not use tools.”, emitted UserPromptSubmit and paused
that item; the authoritative instance provenance became `human`. This verifies
a native human event interrupting fixture-owned work, not a claim that the
model itself accepted that particular item. Real model acceptance was verified
separately in the cross-agent run above.

After the fixture explicitly resumed/completed that item, the test typed a
request to create a disposable file with Bash. Both native TUIs displayed their
actual permission dialog and emitted PermissionRequest. A new peer question
was then queued: after two seconds of active terminal observation, readiness
remained `permission`, delivery remained `queued`, and the file did not exist.
The dialog was dismissed and the owned test process was terminated; no permission
was approved. Removing prior ownership before this phase ensures that the
permission assertion did not pass merely because an owned item also blocks intake.

Retained sanitized payloads and observations:

- `lince-messages/tests/fixtures/claude-2.1.272-tui-intervention.json`
- `lince-messages/tests/fixtures/codex-0.154.0-tui-intervention.json`

`test_native_evidence.py` replays those actual payloads against the broker; its
checks supplement, rather than replace, the live observations.

Native commands used the following options (TEMP_SETTINGS / HOOK_OVERRIDES
registered SessionStart, UserPromptSubmit, PreToolUse, PostToolUse,
PermissionRequest, Stop and SessionEnd with the captured adapter handler):

```sh
claude --settings TEMP_SETTINGS --setting-sources '' --permission-mode default \
  --tools Bash -- 'Reply exactly HUMAN_OVERRIDE_READY. Do not use tools.'
codex --no-alt-screen --disable plugins --dangerously-bypass-hook-trust \
  --sandbox read-only -a on-request HOOK_OVERRIDES \
  'Reply exactly HUMAN_OVERRIDE_READY. Do not use tools.'
```

For this Codex TUI probe, existing global handlers were checked to be exactly
`codex-status-hook.sh`, inline configuration contained hook state only, and each
configured MCP server was disabled by an invocation-only override. Hook trust
was bypassed only for the inspected test handlers; permission approval remained
interactive. The product adds neither bypass.

Before the user completed SSO, Bob authentication was rechecked: no BOB_API_KEY; the local
`~/.bob/settings/auth-secrets.json` contained only a telemetry identifier.
The [official setup guide](https://bob.ibm.com/docs/shell/getting-started/install-and-setup)
distinguishes browser/SSO login for interactive use and API keys for automation.
After SSO completed, the original TUI authenticated and the checks below passed.
No credential values are retained in this ledger or requested in chat.

## Native models inside Linux bwrap

2026-09-18: Claude **2.1.272** `--print` and Codex **0.154.0** `exec` each ran
in a real bwrap namespace and completed an assigned task with result `42`.
Before each model started, a Python preflight asserted its instance identity,
verified that the administrative credential and `/run/user/UID/zellij` were
absent, and confirmed that `host.snapshot` was denied using the agent credential.
Each model performed get/accept/complete/get through the real CLI. Both exited 0;
broker events show explicit acceptance and completion, with delivery `read`.

The probe used the production `messaging_bwrap_args()` mount/credential helper
with a temporary HOME and private mailbox, a read-only root, private `/tmp` and
`/run/user/UID`, a PID namespace, fresh `/proc` and `/dev`, and a writable fixture
workspace. The agent's existing configuration/authentication directory was bound
for normal provider access. Claude used CLAUDE_CONFIG_DIR; Codex used CODEX_HOME,
ignored user configuration, disabled plugins, and used the already-reviewed
invocation-only hook-trust bypass. Its inner sandbox was disabled inside bwrap.
This verifies the messaging boundary with actual native models, not every
possible user policy/profile combination. Interactive TUI behavior was exercised
separately, as recorded above.

An initial minimal probe omitted the writable `/dev` used by normal sandbox
launches and Claude's Bun runtime aborted before model startup. Repeating with
that standard mount succeeded. Claude also emitted a configuration-path warning
under the temporary HOME; its model, hooks and complete CLI round trip succeeded.
Neither observation is represented as a messaging failure or a skipped success.

Retained broker outcomes and preflight assertions:

- `lince-messages/tests/fixtures/claude-2.1.272-bwrap-task.json`
- `lince-messages/tests/fixtures/codex-0.154.0-bwrap-task.json`

## Reproducing the integrated native review

2026-09-18, Linux, Zellij 0.45.1: **passed** with Claude 2.1.272 and Codex
0.154.0 in their original interactive TUIs. Claude requested a correctness
review, wrote the independent result `42` while the request was still pending,
and later wrote a receipt containing the exact request ID and Codex's finding.
Codex accepted, demonstrated that `inclusive_sum(1, 3)` returned `3` instead of
`6`, and replied through the mailbox. The hidden recipient did not steal focus;
the focused status line showed the requester, question and request ID, and
Alt+d displayed both the completed thread and the actual review reply.
Retained evidence: `lince-messages/tests/fixtures/claude-codex-2026-09-18-integrated-review.json`.
The harness cleaned up its native processes, Zellij session and broker.

An initial observation searched for a final-answer marker that scrolled outside
the viewport. The exchange succeeded but that observation timed out; it was not
counted as a passing run. The final harness uses model-written result files and
waits for every thread page before inspecting the reply in Alt+d. The ordinary
statusline/minimal/classic smoke suite and 33 dashboard Python tests also passed
after adding the opt-in mode.

This opt-in test uses existing authenticated Claude/Codex accounts and their
original TUIs. Review the installed Codex status hooks before enabling the
invocation-only hook trust bypass; no persistent trust settings are changed.

```sh
bash lince-dashboard/tests/setup-ui-test-env.sh /tmp/lince-ui-test-venv
/tmp/lince-ui-test-venv/bin/python lince-dashboard/tests/check-ui-session.py \
  --zellij /path/to/zellij-0.45.1 \
  --native-review-evidence /tmp/lince-review-evidence \
  --reviewed-hook-trust
```

The harness creates a disposable Zellij session and installs the messaging
module under an isolated HOME. Production supervision registers both agents.
The test driver acts as the human submitting prompts; automatic idle wakeup is
disabled. Claude requests a review, computes an independent result while the
request remains pending, and later reads the correlated reply. Codex explicitly
accepts and reviews the disposable Python file. Status-line observations verify
pending/active work, focused provenance and no focus stealing by the hidden peer;
Alt+d displays the completed thread. Evidence includes the full broker event
history and result files actually written by the model, so merely echoing a
prompt or scrolling a marker off screen cannot satisfy the exchange checks.

This is a native TUI/UI integration test, not a bwrap claim. Legacy status-hook
identity is unset in the native children to avoid modifying existing user pane
state. The real sandbox and lifecycle-badge checks are recorded separately.

## Acceptance audit

See [the criterion-by-criterion release audit](agent-messaging-acceptance.md).
Bob runtime validation is now recorded below; only the release/merge step remains.
The author code/evidence review is recorded in the acceptance audit; it found and
fixed the missing recovery event for uncertain deliveries. All 53 messaging tests
passed after that correction, including repeat-restart deduplication of the event.
The integrated real-agent review/UI demonstration is now recorded above.
Custom hook-path uninstall supports repeatable explicit settings paths,
preserves user handlers and keeps executables available if settings removal fails;
the packaging regression verifies all three adapters and idempotent removal.
Codex callbacks with native turn IDs now preserve stable deduplication keys;
regressions cover a delayed duplicate after explicit resume and a duplicate Stop
after the intake cooldown, plus distinct human prompts without native IDs.

## Bob Shell original TUI — completed native validation

2026-09-18, Linux, Bob Shell **2.0.4** (01dddf684), Claude **2.1.272**:

- With the user's SSO login, `bob chat` reached the model. `bob run` still rejected
  missing BOB_API_KEY; browser SSO does not establish headless API authentication.
- Actual payloads use `hook_event_name`, `session_id` and, for tool callbacks,
  `tool_name: execute_command`. SessionStart supplied a random verification code
  through stdout; Bob correctly returned it without the code being in the prompt.
- Bob's original TUI and a real Claude headless peer each sent one question and
  one delegation, explicitly accepted/replied/completed incoming work, and read
  outgoing results. All four correlated requests completed. The included opt-in
  reproduction also passed:

  ```sh
  /tmp/lince-ui-test-venv/bin/python lince-messages/tests/probe-bob-pair.py
  ```

  Use `lince-dashboard/tests/setup-ui-test-env.sh` to install the pinned test-only
  pyte dependency. Existing Bob SSO and Claude authentication are prerequisites.
  Only the disposable pair probe uses Bob `--auto-approve` for the prompt's
  authorized messaging CLI operations. It changes no production launch flags.
- A separate `bob chat --disable-mcp --disable-subagents --trust --workspace DIR`
  run without auto-approval verified human precedence: a real UserPromptSubmit
  paused fixture-owned work and set human provenance. Fixture ownership was then
  explicitly completed before testing permission behavior.
- Asking Bob to create `sample.txt` with `touch` produced the actual Execute
  Command / Approve Once dialog. With that dialog open, an incoming message
  stayed queued, enabling automatic intake returned `unsupported`, and no Enter
  or approval was sent. The file remained absent. Bob emitted PreToolUse but no
  PermissionRequest event: the adapter correctly keeps permission detection
  false and exposes an explicit inbox rather than guessing safe terminal input.

Retained evidence:

- `lince-messages/tests/fixtures/bob-claude-2026-09-18-exchanges.json`
- `lince-messages/tests/fixtures/bob-2.0.4-tui-intervention.json`

Captured Bob events are replayed in the deterministic native-evidence test; the
suite now has **54 passing messaging tests**. Live observations and deterministic
replay remain separate evidence. These Bob sessions were native Linux TUI checks,
not Bob-inside-bwrap or macOS claims; shared bwrap transport and native
Claude/Codex bwrap checks are recorded above. No ACP or replacement TUI is used.
An earlier human/permission probe was refused by the model before reaching tool
approval and was not counted as permission evidence. An initial pair harness
incorrectly reused an exited Claude token for a later fixture; that operation
was denied as intended. The corrected pair reproduction and separate intervention
probe both completed successfully, and their owned processes were cleaned up.
