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
