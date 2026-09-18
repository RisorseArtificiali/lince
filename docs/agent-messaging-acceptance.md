# Messaging release audit — epic #333

This audit maps the current implementation to the GitHub acceptance criteria.
It does not close issues or replace their criteria. All required implementation and declared-platform evidence has been reviewed.
The final closure action is merging the single PR and closing its required issues.

| Issue / criteria | Evidence | Outstanding |
| --- | --- | --- |
| #334, 1–7: contract, identities, states, scheduling, capabilities, recovery, boundary | [Protocol](agent-messaging-protocol.md), including exact request/event shapes and example operations; [operator guide](agent-messaging.md); [version/platform ledger](agent-messaging-validation.md) | Author review complete; merge pending |
| #335, 1–4: durable state, authentication, groups, restricted API | `store.py`, `service.py`; authorization, revocation, concurrent retry and transition tests in `test_service.py`; actual bwrap administrative-access rejection | Author review complete; merge pending |
| #335, 5: sandbox transport | `test_sandbox_transport.py` and retained Claude/Codex native bwrap outcomes | macOS runtime support is not claimed; generated Seatbelt rules alone are not runtime evidence |
| #335, 6–8: limits, deduplication, recovery, negative tests | Frame-bound/full-registry tests; rate/queue/cycle tests; restart/no-replay and deliberate reconciliation tests | Author review complete; merge pending |
| #336, 1–5 and 7: CLI, correlation, waits, instructions, transport tests | `lince-msg`, `instructions.md`, `test_cli.py`, native bidirectional Claude/Codex exchanges | Author review complete; merge pending |
| #336, 6: installation and removal | Installed supervisor/update/restart/uninstall test; configuration-preserving hook tests | Custom paths are removed with explicit, repeatable `--settings AGENT PATH`; regression covers all three adapters, preserved user handlers, repeated removal and invalid settings. Author review complete; merge pending |
| #337, 1–8: safe native intake, provenance, ownership, nested consultations, interruption, recovery | `test_delivery.py`, native Stop fixtures, original-TUI human/permission fixtures, service concurrency/cycle/cancellation tests | Native callback deduplication uses Codex turn IDs when present. The protocol documents why equal payloads without native identity cannot safely be assumed duplicates. Author review complete; merge pending |
| #338, 1–6: Claude adapter | Actual 2.1.272 lifecycle, continuation, human/permission TUI events, cross-agent questions/tasks and native bwrap task; deterministic adapter/config tests | Author review complete; merge pending |
| #339, 1–6: Codex adapter | Actual 0.154.0 lifecycle, continuation, human/permission TUI events, cross-agent questions/tasks and native bwrap task; deterministic adapter/config/turn-duplicate tests | Author review complete; merge pending |
| #340, 1–8: Bob adapter | Actual 2.0.4 SSO TUI: SessionStart context, emitted payload fixtures, real Bob/Claude questions/tasks in both directions, human precedence and native permission dialog retaining a queued message; 54-test suite includes captured Bob replay. No automatic wakeup/permission detection claimed | Author review complete; merge pending |
| #341, 1–6: status line | WASI rendering/snapshot tests; real Zellij statusline/minimal PTY checks; classic retains original bars; full visibility-mode regressions | Author review complete; merge pending |
| #342, 1–7: Alt+d | Browser model and host API tests; real Zellij thread/group/pause/resume/cancel/ack/navigation checks; pinned instance navigation and stale-response tests | Author review complete; merge pending |
| #343, 1: packaging/regressions | Installed update/uninstall test, 33 dashboard Python regressions, actual VoxCode/layout smoke | Custom-path removal and malformed-settings recovery verified; author review complete; merge pending |
| #343, 2: all ordered pairs | `test_agent_pairs.py`: all six directed v1 pairs, question/task results, nested consultation, human takeover | This is deterministic evidence, not real Bob execution |
| #343, 3: real agents/platforms | Real Claude/Codex exchanges, TUI checks and bwrap tasks; real Bob SSO TUI exchanges and intervention checks | Verified within the declared matrix; no Bob-inside-bwrap or macOS runtime claim |
| #343, 4–6: negative boundary, stable routing, documentation | Service/sandbox/browser tests, native preflight checks, operator/security/recovery guides | Author review complete; merge pending |
| #343, 7: integrated review demonstration | Actual Claude/Codex original TUIs in one real Zellij session: review request, independent work while pending, explicit acceptance/reply, correlated receipt, hidden-peer focus preservation, live status-line provenance and actual reply visible in Alt+d. Reproduction script and `claude-codex-2026-09-18-integrated-review.json` retained | Author review complete; merge pending |
| #343, 8 and #333 DoD | This audit and the validation ledger distinguish deterministic/live checks and unavailable platforms | Implementation/evidence audit complete; merge the single PR and close required issues. Pi #344 / OpenCode #345 remain outside the v1 closure gate |

## Interpretation of the evidence

- Broker events prove explicit acceptance/results; neither an idle terminal nor a
  model's final chat message substitutes for them.
- Real TUI intervention tests started with fixture-accepted work; real model
  acceptance was demonstrated separately in the cross-agent and bwrap runs.
- Permission tests released prior ownership first, so a queued message could not
  appear protected solely by the one-owned-item rule.
- There is no claim of external idle wakeup, permission approval, exactly-once
  model execution, concurrent-edit prevention or remediation of unrelated
  sandbox review findings.

## Author review checkpoint — 2026-09-18

Reviewed the current GitHub criteria against the protocol, service/store,
CLI/instructions, supervisor, adapters, configuration/maintenance scripts,
sandbox transport, dashboard actions/rendering, deterministic test assertions,
and retained real-agent/UI evidence. This is the implementation author's code
and evidence review, not an independent reviewer approval or release sign-off.

The review found and fixed a recovery audit gap: changing `delivered` to
`uncertain` on restart now writes its host-authored delivery event in the same
transaction. The recovery regression proves that another restart neither repeats
that event nor redelivers the request. All 53 messaging tests passed after the
fix, including the actual bwrap transport test. The protocol now states the
existing lifetime instance/group limits as well as message/transport limits.

### Epic DoD closure audit

| DoD item | Current conclusion |
| --- | --- |
| 1. All ten issues implemented, reviewed, merged and accepted | Implementation, author review and required evidence complete; merge pending. Ten issue-specific commits are retained in one PR |
| 2. All three agents in both question/task roles, real versions/platforms | Verified: Claude/Codex and Bob/Claude real question/task exchanges in both directions, with explicit acceptance/results and tested versions |
| 3. Host group/identity enforcement and restricted transport | Reviewed and verified by negative service tests, real bwrap transport and native bwrap preflight evidence; unsandboxed same-UID processes remain outside the isolation claim |
| 4. Scheduling, human precedence, nesting, cycles, bounds and cancellation | Shared state-machine and adapter tests verified; original Claude/Codex/Bob human/permission behavior recorded; Bob permission detection is explicitly unsupported and automatic intake remains disabled |
| 5. Recovery, deduplication, uncertain/interrupted work and immutable identity | Reviewed; recovery transition now audited once, no automatic replay/reassignment; idempotency does not promise exactly-once model execution |
| 6. Three-area status line and Alt+d without focus stealing | WASI tests, all three real presentation smokes and integrated native review verified; stale/replaced identities remain pinned |
| 7. Original TUIs and honest capabilities | All three original TUIs verified; Bob uses explicit inbox and SSO, with limitations documented; no ACP introduced |
| 8. Packaging, instructions, help and existing behavior | Install/update/uninstall and custom settings checks verified; dashboard Python suite and real VoxCode/layout/manual-control smokes pass |
| 9. Deterministic and declared native/platform checks | 54 messaging + 33 dashboard Python tests and 114 WASI tests pass (one existing ignored preview). Claude/Codex bwrap and Bob native Linux TUI evidence recorded; macOS runtime support is not claimed |
| 10. No unrelated files or expanded security claims | Only scoped paths staged; unrelated workspace documents/artifacts remain untracked. Documentation expressly excludes workspace conflict prevention and unrelated sandbox fixes |

The user supplied Bob SSO access and both native checks now pass. The final
release review includes the actual Bob payloads, its returned startup-context
code, all four cross-agent results, and the unapproved native permission dialog.
The post-evidence messaging suite passes 54 tests. Merge/issue closure remains
explicitly separate from implementation evidence. Pi/OpenCode stay non-blocking.
