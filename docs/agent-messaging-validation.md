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
| Claude 2.1.272 / Linux | Actual basic lifecycle payloads; deterministic adapter tests | Live questions/tasks in both directions; cross-agent flow; Stop continuation; TUI/bwrap and permission/human intervention checks |
| Codex 0.154.0 / Linux | Actual basic lifecycle payloads; deterministic adapter tests | Live questions/tasks and cross-agent flows; native continuation; TUI/bwrap checks |
| Bob 2.0.4 (01dddf684) / Linux | Installed version observed; current Shell documentation read | Adapter, actual payloads, explicit inbox/context intake and live flows |
| macOS / Seatbelt | Generated rules tested only | Real transport and UI validation before any macOS support claim |
| Dashboard | Existing architecture inspected | Status line, Alt+d, disposable Zellij smoke and regressions |

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
