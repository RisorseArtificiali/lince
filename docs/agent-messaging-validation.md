# Terminal conversation validation

The previous mailbox validation is [historical](history/agent-mailbox-validation.md)
and does not establish correctness of the new terminal transport.

Verified on Linux, 2026-09-19: 20 communication Python tests, 41 dashboard
Python tests, 108 WASI tests passed (one pre-existing ignored test), release build
passed, and real Zellij 0.45.1 conversation smoke passed in statusline, minimal
and classic presets. The smoke uses fixtures as described below.

Run:

```sh
python3 -m unittest discover -s lince-messages/tests -v
bash lince-dashboard/tests/run-plugin-tests.sh
python3 lince-dashboard/tests/check-ui-session.py --conversations-only
```

The Python suite checks correlation and authenticated peer identity, rejection of
legacy task operations and control characters, FIFO delivery while busy, lease
expiry, closed/replaced peers, uncertain writes without replay, the real socket
and CLI, optional skill installation/update/removal, preservation of unrelated
hooks/edited skills, real Linux bwrap transport and generated Seatbelt rules.

The Zellij smoke uses terminal fixtures. It sends an actual multiline bracketed
paste and Enter to a hidden pane, receives an asynchronous answer in the original
sender pane after it becomes idle, and checks the shared reference, unchanged
focus, delivery log and last-sender UI. It is not a real-model behavioral test.

The Rust suite checks the read-only browser, stale responses, original-instance
navigation and existing dashboard behavior. Skill metadata is validated with
the skill-creator validator.

Pi and OpenCode extension callbacks are exercised under Node: status files work
without a Zellij socket, tool-turn completion does not enable Pi intake, and
unknown OpenCode status is not treated as idle. All eight skill destinations are
checked through installation, update and removal.

Manual real-agent (all eight providers) and macOS TUI checks remain required for native paste and
skill behavior. Follow [smoke.md](../smoke.md). No results from the retired Stop
hook continuation tests are presented as validation of this implementation.

Gemini/Goose hook stdin/stdout contracts and lifecycle status files are tested
without provider calls. Amp's real plugin callbacks are tested with a simulated
state observable: permission/error/unknown states, thread switching, stale
asynchronous reads and disposal. Installer tests verify idempotence, preservation
of unrelated settings and modified files, and uninstall. Registry/event-map
checks cover the new adapters. Local Gemini 0.1.7 and Goose 1.20.1 are older than
the documented hook implementations; Amp is not installed. These checks do not
constitute live validation of those three native TUIs.
The real Zellij fixture smoke also passes for Gemini, Amp and Goose event names
in all three presets, including queued delivery, asynchronous replies and focus
preservation.

The Claude regression test invokes the shipped shell hook and checks its prefixed
status filename, including permission/tool states overriding a generic idle file
and rejection of an idle signal predating the last submission.

The Bob regression invokes the shipped hook for SessionStart, UserPromptSubmit,
PreToolUse, PostToolUse and Stop. It verifies idle recognition and distinct
missing-file, stale-instance, busy-event and previous-delivery diagnostics.

Bob startup observer tests cover the empty composer, rejection of busy/auth/error
screens, one-time publication, and a native hook arriving during screen capture.
A real Bob startup was also checked without sending model prompts: its folder
trust dialog was correctly rejected as not ready. Authenticated startup-to-I
remains a manual smoke check.
