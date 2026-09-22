# Keyboard reference

This page follows the same order as the dashboard Help pane (`Alt+h`, `Alt+?`,
or `?` in the detailed list), with extra context for shortcuts that need it.
Letters are case-sensitive: `Alt+N` means `Alt+Shift+n`, and `Alt+Q` means
`Alt+Shift+q`. Global `Alt` shortcuts work while an agent pane is focused and in
Zellij locked mode; shortcuts without `Alt` apply to the detailed agent list or
the dialog currently open.

## Open views and voice controls

| Key | Help label | Details |
|-----|------------|---------|
| `Alt+d` | Detailed agent list | Opens the full controller from any pane. |
| `Alt+v` | VoxCode settings / start / mute / stop | Opens voice settings and controls. If voice input is disabled, LINCE explains which setting enables it. |
| `Alt+m` | Mute/unmute VoxCode | Toggles mute without opening the voice panel. |
| `Alt+t` / `Ctrl+Space` | PTT: insert / insert + Enter | `Alt+t` inserts the transcript; `Ctrl+Space` inserts it and submits it. |
| `Alt+i` / `Alt+h` / `Alt+?` | Info / help | `Alt+i` opens information for the focused agent. `Alt+h` and `Alt+?` open Help. |
| `Alt+s` | Toggle sidebar | Shows or hides the compact sidebar in `minimal` and `side-pane`. |
| `Alt+b` | Bar: hidden / left / full / right | Cycles the two-row attention bar through hidden, left summary, full, and agents-only modes. |

## Create agents

| Key | Help label | Details |
|-----|------------|---------|
| `Alt+n` / `n` | New agent wizard | Opens the full creation wizard. `Alt+n` works from any pane; `n` works in the detailed list. |
| `Alt+N` / `N` | New agent with defaults | Uses configured and session defaults, then asks only for the agent name. |

When no agents exist, the footer keeps these creation shortcuts and Messages on
the left, with `Alt+q` and `Alt+Q` aligned on the right; it does not repeat the
Messages command as a status label.

The wizard's Project Directory screen accepts a typed path and supports `Tab`
completion. Recent directories appear below the field: press `Down` to enter the
list, use `Up`/`Down` to move, and press `Enter` to select. Typing filters recent
directories and returns focus to the path field. See the [Usage Guide](usage-guide.md#agent-creation-wizard)
for every wizard step.

## Select and focus agents

| Key | Help label | Details |
|-----|------------|---------|
| `j` / `k`, arrows | Select agent | Moves selection in the detailed list without changing the focused pane. |
| `1`–`9`, `Enter` / `f` | Focus agent | Focuses the selected or numbered agent from the detailed list. |
| `Alt+1`–`Alt+9` | Switch from any pane | Jumps directly to the numbered agent globally. |
| `Alt+k` / `Alt+j`, `Alt+PageUp` / `Alt+PageDown` | Cycle agents | Moves to the previous or next agent in displayed order and wraps at the ends. |

## Manage agents and ordering

| Key | Help label | Details |
|-----|------------|---------|
| `Alt+r` | Rename focused agent | Opens the rename prompt for the focused agent from any pane. |
| `Alt+x` | Kill focused agent | Stops the focused agent, closes its pane, and focuses the next agent when available. |
| `i` | Info (PageUp/Down scroll) | Opens details for the selected agent; use `PageUp` and `PageDown` for long content. |
| `r` | Rename selected | Renames the selected agent in the detailed list. |
| `K` / `J` | Move selected up/down | Changes the saved display and navigation order, including across project groups. |
| `a` | Reset directory/name order | Restores sorting by project directory and agent name. |
| `x` | Kill selected | Stops the selected agent and closes its pane. |

## Relay conversations

| Key | Help label | Details |
|-----|------------|---------|
| `s` | Relay last message | Chooses a destination and sends the last conversation message. |
| `S` | Relay N messages | First asks how many recent messages to relay, then asks for the destination. |

## Exit and close dialogs

| Key | Help label | Details |
|-----|------------|---------|
| `Alt+q` | Save and quit | Saves agents, their order, sidebar visibility, and attention-bar mode to `.lince-dashboard`, then quits after the write succeeds. Works from any pane. |
| `Alt+Q` | Quit without saving | Quits from any pane without changing the last saved state. |
| `Esc` / `?` | Close help | Dismisses Help. `Esc` also cancels or closes the current dialog where applicable. |

Bare `q` and `Q` do not exit LINCE. This keeps typing in the detailed list safe
and makes the two session-wide exit commands consistent.
