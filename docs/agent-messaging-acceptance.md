# Pane conversation acceptance record

This is the acceptance record for the skill-based replacement of PR #346.
The [original mailbox audit](history/agent-mailbox-acceptance.md) and its
[validation ledger](history/agent-mailbox-validation.md) are historical; their
native-model results do not validate the replacement transport.

| Accepted behavior | Implementation and evidence |
| --- | --- |
| Communication is optional and installs a skill per selected agent | Explicit install opt-in; all eight skill paths, updates, disable and ownership-preserving uninstall tested |
| Original agent TUIs exchange questions and replies | `peers` / `send`, authenticated instance identity, correlated references and recap instructions; real socket/CLI and Zellij terminal-fixture checks |
| Sender can continue independent work | Send returns without waiting; replies use the same transport; skill forbids polling and unnecessary acknowledgement loops |
| Groups, inboxes and delegated-task lifecycle are removed | Retired adapters/commands/tests removed; legacy hook handlers cleaned without deleting unrelated handlers; historical data retained but not loaded |
| Idle delivery does not change focus | FIFO transport checks original pane/process and fresh status; paste + Enter, bounded pending queue and timeout; Zellij smoke in three presets |
| Claude, Codex, Bob, Pi, OpenCode, Gemini, Amp and Goose have integration paths | Native dashboard hooks/plugins; Pi final-turn detection and unknown OpenCode state tested; Gemini/Goose contracts and Amp observable tested without provider calls |
| Claude idle and Bob first-prompt regressions are addressed | Real Claude hook filename regression; Bob one-time empty-composer observer with native-hook precedence and negative startup-screen tests |
| Rename updates messaging without breaking conversations | Host-authenticated name synchronization keyed by pane and status ID; name resolution/history/identity regression test |
| Status UI stays compact and describes only observed delivery | Last sender/reference on left second row, inline details/help after tabs, read-only Alt+d log; WASI rendering and Zellij smoke |
| Alt+Up/Down reaches the focused agent | Shipped focus bindings removed; migration preserves custom actions and is idempotent |

Definition of done for this replacement: implementation and shipped defaults agree;
operator guide, protocol and smoke instructions describe the final behavior;
automated checks and release build pass; tested capabilities are distinguished
from unverified native versions/platforms; the follow-up PR records migration and
remaining limits before merge.

See [validation](agent-messaging-validation.md) for commands and evidence. The
user confirmed the rename/status-bar smoke in this session. This does not certify
all eight native TUIs or macOS. Terminal injection still has a check/write race,
cannot protect an existing draft in the prompt editor, and is not a read receipt.
Bob startup detection depends on the known composer layout; narrow/changed UI
remains unknown. Gemini/Goose require newer versions than those installed locally;
Amp and macOS native runtime behavior remain unverified.
