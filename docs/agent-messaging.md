# Conversations between agent panes

LINCE optionally installs the `lince-converse` skill for agents with native skill discovery.
Agents exchange ordinary text prompts through their existing terminal panes.
There are no communication groups, inboxes, task ownership or completion commands.

## Enable and disable

Dashboard installation offers a separate opt-in for each supported agent when
run interactively. Noninteractive installation leaves communication disabled.
Updates preserve the existing choices; an old mailbox installation does not
implicitly opt in to terminal injection.

```sh
bash lince-messages/install.sh --enable claude codex bob pi opencode gemini amp goose
bash lince-messages/install.sh --disable bob
```

Enabling installs `skills/lince-converse/SKILL.md` in the selected agent's
personal skill directory. It permits opted-in agents in this LINCE session to
send text to each other. Start fresh agent panes after changing choices.
The host wrapper provisions credentials only for opted-in agent types.

Every `install.sh` / `update.sh` run — including a bare opt-in change — stops
the running messaging services first. Registrations live only in service
memory, so agent panes opened before the run keep failing with
`access_denied: Communication disabled or instance has closed` until each pane
is closed and launched again. Opt-ins and installed skills are unchanged; only
a relaunch re-provisions the per-pane credential.

| Agent | Default personal skill directory | Automatic reception in LINCE |
| --- | --- | --- |
| Claude | `~/.claude/skills` | Existing dashboard hooks |
| Codex | `~/.codex/skills` (or `$CODEX_HOME/skills`) | Existing dashboard hooks |
| Bob | `~/.bob/skills` | Existing dashboard hooks; dialog limitations below |
| [Pi](https://pi.dev/docs/latest/skills) | `~/.pi/agent/skills` (or `$PI_CODING_AGENT_DIR/skills`) | Existing extension, updated to write status files and distinguish tool turns from agent completion |
| [OpenCode](https://opencode.ai/docs/skills) | `~/.config/opencode/skills` | Existing dashboard plugin |
| [Gemini](https://geminicli.com/docs/cli/skills/) | `~/.gemini/skills` | [Native hooks](https://geminicli.com/docs/hooks/reference/): `SessionStart` / `AfterAgent` |
| [Amp](https://ampcode.com/docs/customize/skills) | `~/.config/amp/skills` | [Thread state plugin](https://ampcode.com/docs/plugin-api): `idle` |
| [Goose](https://github.com/block/goose/blob/main/documentation/docs/guides/context-engineering/using-skills.md) | `~/.config/goose/skills` (compatible config location) | [Open Plugins hooks](https://github.com/block/goose/blob/main/documentation/docs/guides/context-engineering/hooks.md): `SessionStart` / `Stop` |

All eight agents have dashboard lifecycle integrations. Use current agent versions
with the documented hook/plugin APIs; installing a skill alone does not provide
an idle signal. Gemini 0.1.7 and Goose 1.20.1 from the development machine predate
the integrations documented above; upgrade before testing these receivers.
Amp requires the plugin API with `ctx.thread.state`. Its first session signal may
arrive only after opening an existing thread or sending the first prompt.
Bob Shell emits its first `SessionStart` only when processing input. Lince
therefore observes the initial empty composer through Zellij once and emits
`bob.PromptReady`. This also updates the dashboard to I before the first prompt.
The observer runs outside the sandbox, stops at the first native hook, and
requires the known empty placeholder, borders and mode footer. Login/team/trust
dialogs, errors and busy screens do not qualify. Narrow panes or a changed Bob
UI may remain unknown; native hooks still work after manual interaction.
Messages remain pending and eventually expire if an integration is unavailable
or disabled. The one-time Bob composer check above is the only screen-based
readiness inference; subsequent states come from native lifecycle events.
The `~/.config` skill paths follow `XDG_CONFIG_HOME` when set. Native skill discovery
can expose compatible skills to other providers, but access remains gated by each
agent's own opt-in and per-instance credential.

No separate messaging hooks are installed. Delivery uses dashboard status
integrations, installed/refreshed by `lince-dashboard/install.sh` / `update.sh`:
Gemini settings handlers plus `~/.gemini/lince-status.py`, Amp's system plugin
`~/.config/amp/plugins/lince-status.js`, and Goose's
`~/.agents/plugins/lince-status/`. They only report state and do not approve tools
or change agent prompts. Existing disabled-hook/plugin settings are preserved.
Goose has no separate permission event in this integration: it stays non-idle
while a tool is pending rather than claiming a P badge. These hooks must be working. On Codex, review existing dashboard handlers
in `/hooks` if required by the installed version. Unsupported or unknown states
leave delivery pending rather than guessing readiness. Existing bwrap/Seatbelt
transport restrictions remain; other sandbox backends have no claimed support.

For agents without automatic skill selection, explicitly ask them to use the
`lince-converse` skill. The received prompt also identifies the skill and reply
command. No system prompt or general project instructions are rewritten.

## Conversation

```sh
lince-msg peers
lince-msg send reviewer --text 'Review the permission check in auth.py and reply to me.'
lince-msg send IMPLEMENTER_ID --conversation 12ab34cd --text 'Regarding auth.py: ...'
```

Use a live ID or a unique name returned by `peers`. Renaming with `Alt+r`
synchronizes that name with messaging; existing IDs and conversations stay valid. A new message gets an
eight-character conversation ID. Use `--conversation` to reply or follow up;
both peers must match the original exchange. Include a short recap in a reply.
`--file PATH` and `--stdin` support longer text, read locally by the client.

`send` returns after accepting the text for delivery, without waiting for an
answer. The receiving terminal gets the sender, conversation reference, reply
command and full body. The agent can continue independent work or end its turn;
a later reply becomes another prompt. Acknowledgements do not need replies.

A small delivery queue waits for an idle signal, up to five minutes. This is only
transport buffering: no read receipts, task states or inferred completion.
Pending messages fail if either original peer closes. Closed pane IDs are never
retargeted to a replacement agent.

## Dashboard

`Alt+d` → `m` opens recent exchanges. Enter shows full text and delivery details;
`s`/`f` explicitly navigate to the original sender/recipient; Escape goes back.
There are no group or automatic-intake controls.

- `pending`: waiting for an idle recipient.
- `submitted`: text and Enter were sent, not proof of reading or completion.
- `failed`: delivery was not attempted, or the destination/idle deadline expired.
- `uncertain`: a write may have been partial; inspect the pane before resending.

The second line of the left status area shows `← name #reference` for the
focused agent's last submitted peer message. `Alt+d details` and `Alt+h help`
follow the agent tabs, with no reserved right column.
This does not claim the agent is currently working on that message and is not
attached to its R/I/P state.

The service keeps the last 200 exchanges in memory for this session. It does not
replay pending messages after a service restart. If a conversation reference is
no longer available, start a new one with a recap. The terminal transcript remains
the visible conversation; this log is only a delivery aid.

## Limits and migration

Terminal injection is best effort. Existing hooks do not prove that the prompt
editor is empty or eliminate a process/permission transition between checking
readiness and writing. Do not leave partially typed prompts in enabled receiver
panes. Normal human instructions and native permission policy still apply.
Bob's dashboard hooks do not cover all permission/question transitions; this is
not a guarantee of safe input into every possible native dialog. Original TUIs
and their paste/Enter behavior must be checked on each platform/version.

Updates remove only the old `lince-msg-hook AGENT` handlers from standard settings;
unrelated hooks are preserved. Custom legacy settings can be cleaned with
`python3 lince-messages/hook_config.py AGENT PATH --remove`.
Old mailbox data is left untouched but is no longer loaded. Existing instances
must be restarted. Updating the communication runtime stops its services and
discards pending deliveries and the in-memory log; inspect pending/uncertain
messages before updating and resend intentionally after restarting panes.
Afterwards, panes opened before the update report
`access_denied — Communication disabled or instance has closed` on any
`lince-msg` command until they are closed and launched again: credentials are
provisioned per pane process at launch, and the restarted service knows no old
registrations. Relaunching the pane is enough — no reinstall or opt-in change
is needed.
Uninstall removes only unmodified LINCE-owned skills; locally
edited or unrelated files are preserved.

See [smoke instructions](../smoke.md) and [validation](agent-messaging-validation.md).
