# Dashboard enhancement (#312)

Implementation sequence (one commit per issue):

1. #312: discover viewport geometry from the owning tab's PaneManifest.
2. #294: independent UI palettes, including inherited Zellij styling.
3. #293: compact/full sidebar with the same agent IDs and navigation.
4. #295: passive attention bar and a statusline layout with an on-demand controller.
5. #313: dashboard-owned Zellij chrome and launch configuration.
6. #292: minimal fresh-install default, reversible presets and packaging.

Themes change colors. Views change placement/density. Presets combine those
choices. Agent lifecycle, state persistence and hook handling have one owner;
additional UI surfaces must not initialize a second controller.

A named `lince-viewport` terminal pane defines the agent overlay rectangle.
The controller scopes discovery to its own tab and repositions overlays only
when the rectangle changes. This also supports manual Zellij resizing and
removing the standard bars without percentage offsets in Rust.

#296 (mobile-specific navigation) remains deferred. Native Zellij fullscreen
can hide other panes; persistent attention is guaranteed in LINCE's managed
views, not when an external fullscreen command hides the bar itself.

Minimal and statusline share one managed layout and differ only in initial sidebar
visibility. Alt+s suppresses the sidebar/auxiliary pane and reapplies the shipped
swap layout to existing panes on restoration, preserving IDs and column geometry.
The swap tab inherits the attention row from `default_tab_template`; duplicating
that row misplaces the controller on alternate restores. Restoring columns briefly
focuses the tiled controller, which hides the floating layer; the active agent
(or dialog) regains focus after the swap so its overlay remains visible. While the controller is
suppressed, the visible attention plugin forwards pane manifests to it so agent
discovery and viewport geometry continue updating. The controller accepts these
messages only from its own registered attention plugin. Viewport changes resize
only visible agent panes: changing coordinates of suppressed panes can reveal
them and steal focus in Zellij. Hidden panes get their geometry on selection;
a pending correction waits for a manifest confirming that agent is focused and
unsuppressed, since showing a pane can restore its previous dimensions. The
correction is consumed once, avoiding stale resize requests during agent switches.
Popup lists are always full; the sidebar is always compact. All global dialogs
use a renderer-owned border so outlines survive pane_frames=false.

Minimal sidebars keep their geometry while dialogs are open. A passive floating
surface receives rendered frames and forwards keys to the same controller;
no second lifecycle/state machine is created. Surface updates are deferred through
plugin events to avoid nested message callbacks. CLI pipes are acknowledged using
their source IDs before routing, including messages ignored by passive surfaces.

Validation: the WASM suite covers viewport identity, narrow/Unicode rendering,
long-detail pagination, palette inheritance and attention. The optional
`lince-dashboard/tests/check-ui-session.py` checks real Zellij controller/popup
focus, two-row chrome, six sidebar toggles and exact agent/viewport geometry
in disposable sessions with three harmless sleep processes as fixture agents.
The manual checklist is `docs/design/dashboard-312-smoke-tests.md`.

Managed presets default to a 15% sidebar (configurable 10–60%). Alt+b cycles
hidden → left summary only → full. Both visible modes use two rows. Restoring
chrome first reconstructs the complete swap layout, then suppresses unwanted
surfaces and restores the selected overlay. With both bars suppressed, timer
messages query the live pane manifest through the session-scoped CLI because suppressed plugins do
not receive PaneUpdate events. Only the visible, focused agent is resized.
Alt+q persists an optional view (sidebar visibility and status bar mode) alongside
agents in the existing version 3 state file. Missing views retain preset defaults;
restoration waits until the controller has discovered its chrome panes.
Reasserting controller selectability after hiding chrome refreshes Zellij's
floating viewport, which otherwise retains the old fixed-bar bounds. All roles
request the same existing plugin permissions: Zellij caches them by WASM URL,
so different subsets would overwrite the controller's grant on the next launch.
Hidden-pane polls carry the current UI generation; results started before a
selection or chrome change are discarded. Current polls retry only the selected
visible agent after recomputing floating bounds. Native focus synchronization is
paused throughout chrome restoration, including the event that restores focus.
