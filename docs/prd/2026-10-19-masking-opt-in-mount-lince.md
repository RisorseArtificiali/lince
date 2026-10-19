# PRD: Opt-in mount-point masking in LINCE (v1)

**Problem:** LINCE includes the filesystem root as read-only in the bwrap sandbox. Filesystems mounted under `/`, such as `/run/media/alessio/Dati`, therefore remain readable by agents even outside the working directory, at every sandbox level. The existing home-directory mask does not extend to other mounts. Users working on a project located on a mounted disk need to keep the project accessible without exposing sibling directories through that mount path.

**Goal:** allow users to configure mount points to mask globally when launching LINCE agents, while keeping the working directory usable with the same high-level guarantees currently provided by home-directory masking.

**Non-goals:** automatically discover mounts to protect; identify a volume independently of its path; hide unconfigured bind aliases or equivalent source paths; prevent new mounts or aliases from propagating from the host during a session; prevent explicitly configured binds or experimental bwrap arguments from re-exposing content; make LINCE configuration or executables immutable for future launches.

**Success criteria:** on a host with `/run/media/alessio/Dati` configured and a working directory inside it, a bwrap agent can read and write within the project but cannot read a sibling directory through `/run/media/alessio/Dati` or the `/dati` symlink. Launches without the new configuration retain their current behavior. Invalid configurations or backends unable to enforce the rule do not launch the agent.

## Decisions

- V1 is opt-in and offers the same guarantee as home-directory masking — because the user explicitly separated stronger protection against aliases and future mounts from this feature.
- The list of directory mount points belongs in either global Config v2 or global legacy configuration. For direct `run` and `learn` launches, when global Config v2 exists, only its list is effective, including an empty list; invalid Config v2 fails rather than falling back to legacy. Otherwise the global legacy list is effective. A definition of the list in a project-local file is an error even when the list is empty or that file's format is not the effective global format. For direct `run`, check local configuration at both the invocation directory and the `-p` working directory; for `learn`, at its working directory; for dashboard launches, at both the dashboard launch directory and the selected agent working directory — because a project must not override the global choice.
- The global list uses `[filesystem].mask_mount_points` in Config v2 (`~/.config/lince/lince.toml`) and `[sandbox].mask_mount_points` in legacy configuration (`~/.agent-sandbox/config.toml`); both are lists of absolute directory paths. These keys are global-only and are rejected when present in the project-local files covered by the preceding decision.
- Users configure the real mount-point path, not a symlink such as `/dati` — because the mask applies at the mount path and symlinks must follow the resulting view.
- The rule applies to every bwrap agent at every sandbox level, including `learn`, whether launched directly or from the dashboard. A backend that cannot enforce the rule fails at launch — because silently ignoring an explicit policy would make an unprotected agent appear protected.
- Outside the working directory, the mask provides an empty, writable but ephemeral view; the working directory is re-exposed read/write and changes there persist — matching the chosen home-directory behavior.
- A working directory that spans the entire mount is allowed — because its breadth is an explicit user choice, even when it reduces the usefulness of the mask.
- A configured path that exists but is not mounted at launch produces an accurate warning and is still masked — because the policy concerns a path, not the identity of a volume.
- A configured path that does not exist causes an error and prevents launch — so a configuration mistake cannot be hidden behind an apparently protected launch.
- A path essential to the sandbox, including `/`, `/proc`, and `/dev`, is rejected before launch — so masking cannot break the agent's runtime environment.
- Configuration changes apply to new launches; already-running agents must be restarted — because the filesystem view is established when the sandbox starts.

## Phase 1: Masking for direct agent-sandbox launches

**Goal:** an agent launched directly through `agent-sandbox` applies a global mount-masking policy without losing access to its working directory.

**Scope:** read and validate the global list in both configuration formats; enforce it with the bwrap backend at every level, including `learn`; fail explicitly if the chosen backend cannot enforce it; handle unmounted points and invalid paths; verify behavior with a test mount and on the host that has `Dati`.

**Out of scope for this phase:** dashboard launch-path enforcement, verification, and its startup summary are covered in phase 2. Phase 1 may be released as an opt-in for direct `agent-sandbox` launches only; until phase 2 passes, dashboard launches must not be presented as protected by the mount-masking list.

**Depends on:** nothing.

**Acceptance criteria:**

- [ ] Without a configured list, a direct launch retains the current visibility of mounts.
- [ ] A direct launch reads the list from global Config v2.
- [ ] A direct launch reads the list from global legacy configuration.
- [ ] When both global formats exist, the effective list follows LINCE's existing precedence.
- [ ] If project-local configuration defines the list, launch fails with an explicit error rather than ignoring or using it.
- [ ] A configured point that is a symlink is rejected with an explicit error.
- [ ] A configured point that is not a directory is rejected with an explicit error.
- [ ] A configured point that does not exist prevents launch with an explicit error.
- [ ] Configuring `/`, `/proc`, `/dev`, or `/run` as a point to mask prevents launch with an explicit error. A mount point beneath `/run`, such as `/run/media/alessio/Dati`, is not rejected solely because it is beneath `/run`.
- [ ] When a configured point is mounted, sibling directories of the working directory are not readable through that path in the bwrap sandbox.
- [ ] A symlink to the configured point presents the same masked view.
- [ ] The working directory within the configured point remains readable, and writes there persist on the host.
- [ ] Path components needed to reach the working directory remain traversable in the sandbox.
- [ ] Outside the working directory and the path components needed to reach it, original contents of the masked point are not visible.
- [ ] Writes outside the working directory within the masked path are allowed but do not persist on the host.
- [ ] When a configured point overlaps a path LINCE automatically re-exposes, including the writable home in `learn` or a temporary directory, original content outside the working directory remains unreadable and writes there remain ephemeral at every bwrap level; if LINCE cannot preserve both the mask and the agent's required runtime paths, launch fails before the agent starts with an explicit error.
- [ ] A working directory spanning the entire configured point is not rejected merely because of its breadth.
- [ ] If the configured point exists but is not mounted, launch warns that the point is not mounted without claiming that the physical volume is absent.
- [ ] If the configured point exists but is not mounted, the path is still masked.
- [ ] With the list enabled, a backend unable to enforce the rule prevents launch with an explicit error.
- [ ] The rule applies to bwrap launches at every sandbox level, including `learn`.
- [ ] Automated tests verify global list loading and precedence when global Config v2 is present with a non-empty list, with an empty list, or with invalid configuration (which fails without legacy fallback); they also verify rejection of a project-local definition—including an empty list in the non-selected format—at the invocation directory and `-p` working directory for `run`, and at the working directory for `learn`.
- [ ] Tests using a test mount verify the masked view, symlink behavior, persistence of writes in the working directory, and that writes outside the working directory succeed inside the sandbox but leave no file on the host after exit.
- [ ] Tests verify the unmounted-point case, invalid paths, and an incompatible backend.
- [ ] Tests verify masking at each available bwrap level, including `learn`. For a configured point overlapping the writable home in `learn`, tests verify that a pre-existing sibling is unreadable, a write outside the working directory leaves no host file after exit, and a working-directory write persists—or that launch fails explicitly before the agent starts if the required view cannot be provided.
- [ ] A check on the host with `Dati` records the views of the working directory and a sibling directory through `/run/media/alessio/Dati`.
- [ ] A check on the host with `Dati` records the view through `/dati`.
- [ ] A check on the host with `Dati` records that writes in the working directory persist.
- [ ] `agent-sandbox` documentation explains global configuration in both formats, behavior without the opt-in setting, and the direct-launch-only scope until dashboard integration passes phase 2.
- [ ] `agent-sandbox` documentation explains the unmounted-point case and the limits concerning aliases, configured binds, and new mounts from the host.

## Phase 2: Dashboard integration and policy visibility

**Goal:** the dashboard launches agents with the same policy as phase 1 and clearly communicates which mount view was requested.

**Scope:** the dashboard launch path, including levels and `learn` where available; a startup summary; messages for unmounted points, experimental overrides, and incompatible backends; verification that configuration changes apply to new launches.

**Out of scope for this phase:** finding or blocking aliases; changing the general rules for configurable binds.

**Depends on:** phase 1 — global-list semantics, validation, and masking in `agent-sandbox` launches.

**Acceptance criteria:**

- [ ] With a globally configured point, a bwrap agent launched from the dashboard can access its working directory but cannot read a sibling directory through that point.
- [ ] Dashboard launches enforce the rule at every available level, including `learn` where available.
- [ ] When a global mount-masking list is enabled and a dashboard launch would use a backend that cannot enforce it, the agent process does not start; the dashboard identifies that launch as rejected, shows the reason to the user, and does not report it as spawned.
- [ ] With the rule enabled, the startup summary in the agent's runner pane lists the configured mount paths requested for masking; when experimental bwrap overrides are active, it does not claim those paths are hidden.
- [ ] With the rule enabled, the startup summary identifies the re-exposed working directory.
- [ ] With the rule enabled, the startup summary identifies configured points that were not mounted.
- [ ] With the rule enabled, the startup summary indicates the presence of experimental bwrap overrides when configured.
- [ ] The summary does not claim that unconfigured aliases of the same content are hidden.
- [ ] After the global mount-masking list changes, the next dashboard-managed agent start uses the updated list—or is rejected if its backend cannot enforce it. This applies to wizard and quick-spawn starts without restarting the dashboard, and to agents re-spawned from saved session state.
- [ ] Changing the global list does not change the view of an already-running agent.
- [ ] Integration tests cover the dashboard launch path, startup summary, rejection of an incompatible backend, and rejection of a project-local mount list—including an empty list—at the dashboard launch directory and selected agent working directory.
- [ ] Dashboard documentation explains the global opt-in setting, startup summary, the need to restart running agents, and the parity of limitations with home-directory masking.

## Out of scope for this PRD

- Strong guarantees for complete or partial bind aliases, ordinary source paths of bind mounts, nested mounts re-exposed by the working directory, or propagation of new mounts from the host. Any such enhancement should also consider the home-directory mask.
- Protecting LINCE configuration and executables against modifications that affect future launches, including in `learn` mode.
- Disk lifecycle after launch: unmounting or removing the disk while an agent is running.
- Changing access to copies of data already in the working directory or to data provided by external services.

## Analysis sources

- [V1 agreement (Italian)](../design/mount-visibility-v1.md)
- [bwrap spike and observed limitations (Italian)](../history/mount-visibility-spike-2026-10-19.md)
- [Questions deferred beyond v1 (Italian)](../design/mount-visibility-open-questions.md)

## Task breakdown

### Task 1: Enforce global mount masking for direct agent-sandbox launches

**Description:** LINCE currently exposes filesystems mounted under `/` as read-only to bwrap agents, even when those filesystems are outside the working directory. Add an opt-in global list of directory mount points in both supported configuration formats. For direct `agent-sandbox` launches, mask each configured path while keeping the working directory accessible and writable, with the same high-level visibility guarantees as the existing home-directory mask. Apply the rule at every bwrap level, including `learn`; reject project-local attempts to set the list, invalid paths, essential runtime mounts, and backends that cannot enforce the rule. An existing but unmounted path must still be masked with an accurate warning. Validate the behavior on a test mount and on the host with `Dati`.

**Depends on:** nothing.

**References:** [PRD](2026-10-19-masking-opt-in-mount-lince.md); [v1 design agreement](../design/mount-visibility-v1.md); [bwrap spike](../history/mount-visibility-spike-2026-10-19.md).

**Acceptance criteria:**

- [ ] Without a configured list, a direct launch retains the current visibility of mounts.
- [ ] A direct launch reads the list from global Config v2.
- [ ] A direct launch reads the list from global legacy configuration.
- [ ] When both global formats exist, the effective list follows LINCE's existing precedence.
- [ ] If project-local configuration defines the list, launch fails with an explicit error rather than ignoring or using it.
- [ ] A configured point that is a symlink is rejected with an explicit error.
- [ ] A configured point that is not a directory is rejected with an explicit error.
- [ ] A configured point that does not exist prevents launch with an explicit error.
- [ ] Configuring `/`, `/proc`, `/dev`, or `/run` as a point to mask prevents launch with an explicit error. A mount point beneath `/run`, such as `/run/media/alessio/Dati`, is not rejected solely because it is beneath `/run`.
- [ ] When a configured point is mounted, sibling directories of the working directory are not readable through that path in the bwrap sandbox.
- [ ] A symlink to the configured point presents the same masked view.
- [ ] The working directory within the configured point remains readable, and writes there persist on the host.
- [ ] Path components needed to reach the working directory remain traversable in the sandbox.
- [ ] Outside the working directory and the path components needed to reach it, original contents of the masked point are not visible.
- [ ] Writes outside the working directory within the masked path are allowed but do not persist on the host.
- [ ] When a configured point overlaps a path LINCE automatically re-exposes, including the writable home in `learn` or a temporary directory, original content outside the working directory remains unreadable and writes there remain ephemeral at every bwrap level; if LINCE cannot preserve both the mask and the agent's required runtime paths, launch fails before the agent starts with an explicit error.
- [ ] A working directory spanning the entire configured point is not rejected merely because of its breadth.
- [ ] If the configured point exists but is not mounted, launch warns that the point is not mounted without claiming that the physical volume is absent.
- [ ] If the configured point exists but is not mounted, the path is still masked.
- [ ] With the list enabled, a backend unable to enforce the rule prevents launch with an explicit error.
- [ ] The rule applies to bwrap launches at every sandbox level, including `learn`.
- [ ] Automated tests verify global list loading and precedence when global Config v2 is present with a non-empty list, with an empty list, or with invalid configuration (which fails without legacy fallback); they also verify rejection of a project-local definition—including an empty list in the non-selected format—at the invocation directory and `-p` working directory for `run`, and at the working directory for `learn`.
- [ ] Tests using a test mount verify the masked view, symlink behavior, persistence of writes in the working directory, and that writes outside the working directory succeed inside the sandbox but leave no file on the host after exit.
- [ ] Tests verify the unmounted-point case, invalid paths, and an incompatible backend.
- [ ] Tests verify masking at each available bwrap level, including `learn`. For a configured point overlapping the writable home in `learn`, tests verify that a pre-existing sibling is unreadable, a write outside the working directory leaves no host file after exit, and a working-directory write persists—or that launch fails explicitly before the agent starts if the required view cannot be provided.
- [ ] A check on the host with `Dati` records the views of the working directory and a sibling directory through `/run/media/alessio/Dati`.
- [ ] A check on the host with `Dati` records the view through `/dati`.
- [ ] A check on the host with `Dati` records that writes in the working directory persist.
- [ ] `agent-sandbox` documentation explains global configuration in both formats, behavior without the opt-in setting, and the direct-launch-only scope until dashboard integration passes phase 2.
- [ ] `agent-sandbox` documentation explains the unmounted-point case and the limits concerning aliases, configured binds, and new mounts from the host.

### Task 2: Apply mount masking and show policy status in dashboard launches

**Description:** LINCE dashboard launches must enforce the opt-in global mount-masking policy established for direct `agent-sandbox` launches. Ensure dashboard-started bwrap agents can access and write to their working directory without seeing sibling directories through the configured mount path. Surface unsupported-backend errors and summarize masked paths, the re-exposed working directory, unmounted configured paths, and experimental overrides at startup. Changes to global configuration must affect subsequent launches without changing already-running agents. Document the dashboard behavior and the same limits as home-directory masking.

**Depends on:** Task 1 — its global-list semantics, validation, and masking for direct `agent-sandbox` launches.

**References:** [PRD](2026-10-19-masking-opt-in-mount-lince.md); [v1 design agreement](../design/mount-visibility-v1.md); [deferred limitations](../design/mount-visibility-open-questions.md).

**Acceptance criteria:**

- [ ] With a globally configured point, a bwrap agent launched from the dashboard can access its working directory but cannot read a sibling directory through that point.
- [ ] Dashboard launches enforce the rule at every available level, including `learn` where available.
- [ ] When a global mount-masking list is enabled and a dashboard launch would use a backend that cannot enforce it, the agent process does not start; the dashboard identifies that launch as rejected, shows the reason to the user, and does not report it as spawned.
- [ ] With the rule enabled, the startup summary in the agent's runner pane lists the configured mount paths requested for masking; when experimental bwrap overrides are active, it does not claim those paths are hidden.
- [ ] With the rule enabled, the startup summary identifies the re-exposed working directory.
- [ ] With the rule enabled, the startup summary identifies configured points that were not mounted.
- [ ] With the rule enabled, the startup summary indicates the presence of experimental bwrap overrides when configured.
- [ ] The summary does not claim that unconfigured aliases of the same content are hidden.
- [ ] After the global mount-masking list changes, the next dashboard-managed agent start uses the updated list—or is rejected if its backend cannot enforce it. This applies to wizard and quick-spawn starts without restarting the dashboard, and to agents re-spawned from saved session state.
- [ ] Changing the global list does not change the view of an already-running agent.
- [ ] Integration tests cover the dashboard launch path, startup summary, rejection of an incompatible backend, and rejection of a project-local mount list—including an empty list—at the dashboard launch directory and selected agent working directory.
- [ ] Dashboard documentation explains the global opt-in setting, startup summary, the need to restart running agents, and the parity of limitations with home-directory masking.
