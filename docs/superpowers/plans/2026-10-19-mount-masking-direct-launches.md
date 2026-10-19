# Opt-in mount masking — Task 1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Direct `agent-sandbox run` and `learn` honor a global, opt-in list of masked mount-point paths while keeping the project writable and failing before agent execution when the requested view cannot be guaranteed.

**Architecture:** Read the mount list independently of the existing legacy config merge, before choosing a backend or starting auxiliary processes. Reuse one validated per-launch policy in both bwrap builders; place masks after automatic exposures and before the project bind, and reject any exposure that would undo the mask. Keep Config v2 precedence limited to this new key: existing non-mask `agent-sandbox` settings still use the existing legacy loader until a separate migration changes that contract.

**Tech Stack:** Python 3.11+ (`tomllib`, `pathlib`, `unittest`), bubblewrap, optional Landlock shim, JSON Schemas embedded in `lince-config`; Linux mount-namespace integration tests.

## Global Constraints

- Scope is **Phase 1 / Task 1** of the [versioned PRD](../../prd/2026-10-19-masking-opt-in-mount-lince.md) (Task 1, lines 108–147). Its [review dossier](../../history/2026-10-19-masking-opt-in-mount-lince-walkthrough.md) records the approved changes and unresolved assumptions.
- V2: `~/.config/lince/lince.toml`, `[filesystem].mask_mount_points`; legacy: `~/.agent-sandbox/config.toml`, `[sandbox].mask_mount_points`; both global-only, lists of absolute directory paths. Presence of global v2 selects its list even when empty; invalid v2 is fatal, with no legacy fallback.
- `run` checks local `.agent-sandbox/config.toml` **and** `.lince/lince.toml` at invocation directory and `-p` project directory; `learn` checks both at its working directory. A local definition, including `[]` in the non-selected format, is fatal. Never obtain this key from a merged/project or level-fragment dictionary.
- Without a list, preserve the existing view. A non-bwrap backend with a non-empty list is an explicit pre-launch error. Never claim dashboard launch protection in this phase.
- For every bwrap level including `learn`: hidden original siblings, writable ephemeral non-project path, traversable ancestors, persistent writable project. Reject unsafe overlaps before exec. Explicit experimental binds remain an accepted limitation; mention them rather than claiming an absolute guarantee.
- Reject exact `/`, `/proc`, `/dev`, `/run`; descendants of `/run` are not blanket-rejected. Reject nonexistent, symlink, and non-directory paths. Warn for existing paths not mounted, but still mask them.
- Follow `lince/CLAUDE.md`: Python ruff defaults, 119 columns; do not directly edit installed files; installations via module install/update/uninstall scripts. No dashboard WASI changes in Task 1.

## Deviation Protocol

If a step does not produce its stated expected result — a test fails for a different reason, a referenced symbol differs, or a bwrap/Landlock capability does not behave as hypothesized — STOP that task. Do not silently change the guarantee. Record step, expected versus observed, and the smallest question needed to proceed; revise this plan and obtain a decision before implementation resumes.

**Approved deviation (Task 1 intake tests, 2026-10-19):** The first GREEN run expected a passing newer-v2-version diagnostic test, but the new assertion looked for `version` while the existing `lince-config.check_version_contract` diagnostic says `newer lince` and `lince update`. The user approved changing that assertion to match the existing diagnostic and resuming focused tests, installed-copy verification, and implementation. No change to the version contract or masking guarantee.

**Approved deviation (Task 3 regression harnesses, 2026-10-19):** The prescribed regression scripts were expected to load `sandbox/agent-sandbox` after the new sibling-module import. In fact their `SourceFileLoader`/`exec_module` harnesses do not add `sandbox/` to `sys.path`, so both stopped at `ModuleNotFoundError: mount_masking` before collecting tests. The user approved updating `scripts/tests/test_sandbox_broker_bind.py` and `scripts/tests/test_policy_record.py` to expose that script directory while importing, then finishing the focused and regression tests. This only adjusts the test harnesses; no weakening of the runtime policy.

**Approved baseline exceptions (Task 3 supplemental checks, 2026-10-19):** After the import fix, `test_x11_clipboard.py` expected X11 bind after every `--tmpfs` but found a late messaging tmpfs; `test_default_config.py` expected identical embedded/example text but found a pre-existing `LINCE_STATUS_DIR` difference. Both exact failures were reproduced in a temporary detached worktree at Task 3's base `db4445a`, before the uncommitted Task 3 changes. The user approved continuing Task 3, treating X11 as outside this mount-masking task and restoring embedded/example parity in Task 5 as already planned. A headless SSH session was suggested as a possible X11 factor; the failing assertion is specifically about generated mount order, so no cause is presumed beyond the reproduced baseline.

---

## Verified baseline (worktree `feat/mount-masking`, clean at `d52f0d9`)

- `sandbox/agent-sandbox:1248-1305`: `load_config()` merges legacy global and invocation-local only; it does not load v2 or inspect the `-p` local file. `cmd_run:4656-4705` resolves backend before validating the project; `cmd_learn:7967-8024` uses invocation cwd and a separate builder.
- `lince-config/lince-config:2038-2110` switches global v2/legacy, but `_load_toml_or_empty:1803-1813` converts malformed TOML into `{}` plus warning; its v2 resolver currently does not return `[filesystem]` in JSON (`2470-2487`). `2290-2339` handles only a subset of project overlays and cannot enforce the new global-only rule by itself. The v2 schema lacks the key (`291-300`); legacy schema lacks it (`436-469`).
- `build_bwrap_cmd:3144-3354` overlays root ro, home/tmpfs, writable home/cache/CLI binds, then final messaging mounts (`3496-3497`); the project bind is currently at `3227-3229`, **before** later re-exposures. `build_learn_bwrap_cmd:7683-7723` binds the real home rw. Neither builder may just insert `--tmpfs` adjacent to the current project bind without auditing subsequent binds.
- `bwrap_rw_targets:4121-4149` derives Landlock writable rules from bwrap argv; `landlock_plan:4279-4315` disables the shim in permissive, and ABI 0 at normal falls back to bwrap-only (`5441-5465`). `learn` does not currently inject Landlock. The masked tmpfs must be tested with Landlock on/off; do not assume a host `--rw` rule is meaningful inside the namespace.
- `sandbox/install.sh:98-108` and `sandbox/update.sh:20-30` install only the single-file script. A new import requires packaging in both paths and cleanup in `sandbox/uninstall.sh`. `scripts/tests/test_schemas.py`, `test_config_reference.py`, and `test_default_config.py` guard schema, generated reference, and byte-identical defaults respectively.

## File map and interface contract

| File | Responsibility |
|---|---|
| `sandbox/mount_masking.py` (new) | Standard-library-only, strict global/local loading, version check, validation/mount warning, overlap preflight, bwrap mask argv; no installation side effects on import. |
| `sandbox/agent-sandbox` | Call policy once per `run`/`learn` before backend startup; pass immutable paths to both builders; reject unsupported backend; preserve absence-of-list behavior. |
| `sandbox/install.sh`, `sandbox/update.sh`, `sandbox/uninstall.sh` | Ship/remove `mount_masking.py` beside installed `agent-sandbox`; never edit a user's config. |
| `lince-config/lince-config`; `schemas/lince.schema.json`, `schemas/sandbox-config.schema.json` | Declare both keys in their respective schemas with descriptions; regenerate, not hand-edit, JSON schemas. |
| `scripts/tests/test_mount_masking.py` (new) | Strict source selection, local rejection, path classification, backend gate, command order/overlaps, Landlock unit checks. |
| `sandbox/tests/test-mount-masking.sh` (new) | Real bwrap integration using an isolated test mount, exit-code and host-persistence assertions; skip explicitly if user namespaces or bwrap/mount privileges are unavailable. |
| `sandbox/tests/mount_mask_probe.py` (new) | Executed as the disposable test agent inside bwrap; checks sibling, alias, ancestor traversal, and two writes with observable exit status. |
| `sandbox/README.md`, `docs/documentation/sandbox/security-model.md`, `docs/examples/lince.toml.example`, `sandbox/config.toml.example`, embedded `_DEFAULT_CONFIG` | Human-facing direct-only semantics and opt-in examples; maintain byte identity of the last two. Generated `docs/documentation/configuration-keys.md` and skill reference updated only via `scripts/gen_config_reference.py`. |

**Proposed Python boundary (lock signatures before coding):** `MountMaskError(ValueError)`; `load_mount_mask_points(invocation_dir: Path, project_dir: Path) -> tuple[Path, ...]`; `validate_mount_mask_points(paths: tuple[Path, ...]) -> tuple[Path, ...]`; `mask_mount_args(paths: tuple[Path, ...], project_dir: Path) -> list[str]`; `check_mount_exposures(argv: list[str], paths: tuple[Path, ...], project_dir: Path) -> None` (all in `sandbox/mount_masking.py`).

`load_mount_mask_points` rejects local definitions before returning global raw paths; `validate_mount_mask_points` rejects invalid paths and warns once for each existing, not-currently-mounted path; `mask_mount_args` creates `--tmpfs <point>` plus only required `--dir` ancestor components beneath that point, without host binds; `check_mount_exposures` inspects the **complete generated bwrap mount argv** and rejects later automatic binds that would uncover original contents outside the project. Raise `MountMaskError` with the offending config file/path or mount argv and remediation. Normalization and mount-detection details are decision gates below.

## Decisions to close before implementation

1. **Config v2/legacy ownership:** recommended: use strict `tomllib` in `mount_masking.py` for this key only, selecting global v2 by file presence, and enforce the same supported `version` window as `lince-config.check_version_contract` (currently native `2.0`); add parity tests for missing/newer/invalid version. Never reuse `build_resolved_view()` as-is: it swallows TOML errors and omits filesystem data. Decide whether to expose the selected list through resolver JSON now for future dashboard integration; if yes, update its validation and output **without** allowing project overlay to set this key. Confirm the direct runner's legacy settings may coexist with v2's **mask list only**, as proposed in the Architecture header. If full v2 settings migration is instead required, re-scope before Task 1.
2. **Path spelling and safety:** recommended reject `~`, relative paths, `..`, symlinks in **any component**, duplicates after lexical normalization, and unsafe ancestor mappings; allow harmless trailing slash after lexical normalization. Validate with `lstat()` component-by-component **before** `resolve()` (which would silently follow `/dati`), verify directory with `stat()`. Decide whether `/tmp`, `/var/tmp`, `$HOME`, and ancestors containing runtime paths are supported by suppression/relocation or rejected with an exact reason; no blanket rejection of all `/run/**`. Identify mounts from `/proc/self/mountinfo` by exact decoded mountpoint (including escaped spaces); `Path.is_mount()` alone may misclassify bind/mount-namespace cases. An inability to read mountinfo should not produce a false "not mounted" claim: fail diagnostic or explicit "status unknown" decision.
3. **Automatic exposure and `learn`:** decide how to preflight the exact final argv, including `ro_dirs`, `extra_rw`, PATH dirs, scratch, config, CLI `--rw/--ro`, status/messaging and experimental args. Recommended: reject *automatic* exposure to a masked ancestor/descendant outside the project unless it is replaced with ephemeral content; emit file+path error **before** `Popen`. For mask overlapping writable home in `learn`, insert the mask after home `--bind` and project `--bind` after mask, or reject early if runtime home outside project is required. Masking all of `$HOME` while also promising ordinary learn behavior needs a real integration probe; an early explicit refusal is permitted by the PRD. Configured binds and raw experimental bwrap args remain documented escape hatches, but do not accidentally let internally generated binds leak a sibling.
4. **Landlock:** if active, verify `bwrap_rw_targets()` includes each masked tmpfs and its project bind, and `__landlock-exec` grants write to the **final namespace path**. If Landlock denies ephemeral sibling writes, fix its derived rights or fail before agent exec; never disable Landlock silently for the mask. Run normal/permissive/paranoid with ABI supported and simulate ABI 0; preserve the existing paranoid I7 behavior. A `learn` overlap must be checked even though its builder currently has no shim.
5. **Multiple/overlapping points:** choose deterministic ancestor-first mount order for distinct configured points; reject nested paths only if a test proves they cannot both meet the guarantee. Document exact ordering/diagnostic and test `[parent, child]` plus reversed input; do not simply deduplicate silently.

## Task 1: Strict policy intake and local-source rejection

**Files:** Create `sandbox/mount_masking.py`; test `scripts/tests/test_mount_masking.py`; modify `sandbox/install.sh:98-108`, `sandbox/update.sh:20-30`, `sandbox/uninstall.sh:24-34` to ship the import. **Consumes:** `tomllib`, `Path.home()` and explicit invocation/project directories. **Produces:** `MountMaskError`, `load_mount_mask_points(invocation_dir, project_dir) -> tuple[Path, ...]`. **Guardrails:** use the exact global source switch; do not let `load_config` merge determine global-only policy; no default behavior change.

- [ ] Write table-driven failing tests with isolated home and two local roots: global legacy `['/mount/old']`, global v2 nonempty `['/mount/new']`, v2 `[]`, malformed TOML, missing/newer v2 version; assert selected tuple or `MountMaskError`, never fallback. For each command root (`run` cwd plus `-p`, `learn` cwd), test both local file formats with `[]` and nonempty values, including the non-selected format. Example assertion (parameterize file/section and cwd):

  ```python
  (project / '.lince').mkdir()
  (project / '.lince/lince.toml').write_text('[filesystem]\nmask_mount_points = []\n')
  with self.assertRaisesRegex(mask.MountMaskError, r'project.*mask_mount_points'):
      mask.load_mount_mask_points(invocation, project)
  ```

- [ ] Run `python3 -m unittest scripts.tests.test_mount_masking -v`; expect missing module/function failures, not incidental host-config reads.
- [ ] Implement a narrow strict loader. Inspect `key in table` rather than truthiness (`[]` counts). Parse both local file types at each distinct root before global selection. Treat malformed selected global v2 as fatal; do not read the legacy list in that case. Match v2 `version` contract with parity tests. Errors name file and `[table].mask_mount_points`. Add module installation alongside script, and uninstall with the same confirmation as the command.
- [ ] Run `python3 -m unittest scripts.tests.test_mount_masking -v` and a temporary-`HOME` installed-copy `agent-sandbox --help`; expect PASS, no `ModuleNotFoundError`.
- [ ] Review and commit **only if implementing**: policy loader, focused tests and packaging scripts.

## Task 2: Path validation and mounted-state diagnostics

**Files:** Modify `sandbox/mount_masking.py`; test `scripts/tests/test_mount_masking.py`. **Consumes:** selected raw paths from Task 1. **Produces:** `validate_mount_mask_points(paths) -> tuple[Path, ...]`, warning per existing unmounted point. **Guardrails:** do not call `resolve()` before symlink checks; never create configured directories to make an invalid config appear valid.

- [ ] Add failing isolated-fixture cases: relative/`~`/`..`; final and intermediate symlink; ordinary file; missing point; `/`, `/proc`, `/dev`, `/run` exact; valid child of `/run` (fixture under a test root plus a mocked essential-path matcher); mounted and unmounted dirs; mountinfo escaped whitespace; duplicates and parent+child in both orders.
  Concrete assertions for the two most easily missed errors:

  ```python
  alias = fixture / 'alias'
  alias.symlink_to(fixture / 'real', target_is_directory=True)
  with self.assertRaisesRegex(mask.MountMaskError, 'symlink'):
      mask.validate_mount_mask_points((alias,))
  with self.assertRaisesRegex(mask.MountMaskError, 'does not exist'):
      mask.validate_mount_mask_points((fixture / 'missing',))
  ```
- [ ] Run `python3 -m unittest scripts.tests.test_mount_masking -v`; expect validation/mountinfo failures.
- [ ] Implement component-wise `lstat` and mountinfo exact-match decoder; normalize lexical paths without dereferencing symlinks. Raise before any bwrap/helper subprocess; report "path is not mounted at launch; masking the path anyway", never "volume absent". Do not reject descendants of essential paths on prefix alone; overlap with actual runtime mounts is Task 3's separate preflight.
- [ ] Rerun focused unit tests; expect PASS; review and commit path validation plus tests if implementing.

## Task 3: Mount planning, exposure preflight, and direct `run`

**Files:** Modify `sandbox/mount_masking.py`, `sandbox/agent-sandbox:4656-4705,3110-3354,3487-3527,5466-5478`; test `scripts/tests/test_mount_masking.py`. **Consumes:** validated tuple. **Produces:** `mask_mount_args(paths: tuple[Path, ...], project_dir: Path) -> list[str]`, `check_mount_exposures(argv: list[str], paths: tuple[Path, ...], project_dir: Path) -> None`, optional `mask_mount_points: tuple[Path, ...] = ()` on `build_bwrap_cmd`. **Guardrails:** no policy means unchanged argv, fail unsupported backend before starting proxy/agent, final order must be evaluated with messaging/experimental/Landlock options present.

- [ ] Add failing tests that assert ordered argv triples, not just membership: `--ro-bind / /` before `--tmpfs POINT`, followed by `--dir` components for a deep project, then `--bind PROJECT PROJECT`. A sibling bind generated later must cause an early error; a project-wide mask (`POINT == PROJECT`) is allowed. Test `--backend nono/seatbelt` preflight (mock backend availability) and absent/empty list keeps old argv and backend choice.
  Assert the central ordering with the existing builder test harness (`MIN_CONFIG`, `MIN_AGENT_CONFIG` from `scripts/tests/test_sandbox_broker_bind.py`):

  ```python
  argv = sandbox.build_bwrap_cmd(MIN_CONFIG, project, [],
                                 agent_config=MIN_AGENT_CONFIG,
                                 mask_mount_points=(mount_point,))
  root = argv.index('--ro-bind')
  mask_at = next(i for i in range(root + 1, len(argv) - 1)
                 if argv[i:i + 2] == ['--tmpfs', str(mount_point)])
  project_at = argv.index('--bind', mask_at + 1)
  self.assertLess(root, mask_at)
  self.assertLess(mask_at, project_at)
  self.assertEqual(argv[mask_at + 1], str(mount_point))
  self.assertEqual(argv[project_at + 1:project_at + 3], [str(project), str(project)])
  ```
- [ ] Run `python3 -m unittest scripts.tests.test_mount_masking -v`; expect ordering/backend failures.
- [ ] Integrate policy at the top of `cmd_run`, after resolving project path but before backend choice/helper side effects; choose backend, then reject if not bwrap and paths nonempty. In `build_bwrap_cmd`, **only on opt-in launches**, place the project bind after all generated baseline mounts, with the mask immediately before it; keep old argv ordering with no list. Explicitly inspect the **final** argv so later messaging and shim mounts cannot re-expose a hidden sibling. Distinguish explicit raw experimental overrides from automatic mounts; don't claim raw overrides are protected. If impossible to preserve required runtime paths, raise `MountMaskError` and print its actionable reason before agent `Popen`.
- [ ] Run focused tests plus `python3 scripts/tests/test_sandbox_broker_bind.py` and `python3 scripts/tests/test_policy_record.py`; expect PASS. Review and commit run wiring with tests if implementing.

## Task 4: `learn`, Landlock, and real namespace checks

**Files:** Modify `sandbox/agent-sandbox:7655-7725,7967-8024`, `sandbox/mount_masking.py`; test `scripts/tests/test_mount_masking.py`; create `sandbox/tests/test-mount-masking.sh`. **Consumes:** shared validated paths and exposure preflight. **Produces:** optional `mask_mount_points` argument on `build_learn_bwrap_cmd`, validated `learn` launch or pre-launch error. **Guardrails:** `learn`'s home is host-rw by default; do not expose siblings merely to preserve learn observability. Do not conflate a bwrap process starting with agent exec success.

- [ ] Add failing unit tests for learn's cwd-local rejection, home-overlap case, and mount order. Add real integration script creating a private test mount in an `unshare -Urmp` namespace when allowed, with `project/inside`, `sibling/secret`, an alias symlink at the test root, and `outside` under the mounted point. Copy `mount_mask_probe.py` into the project and configure a disposable global `[agents.mask-probe]` with `command = "python3"` and `default_args = ["/absolute/path/to/project/mount_mask_probe.py"]`, substituting the fixture's actual path; use `agent-sandbox run -p "$PROJECT" --agent mask-probe` (no appended `--` program). Probe body:

  ```python
  from pathlib import Path

  project = Path(__file__).resolve().parent
  point = project.parent
  alias = point.parent / 'alias'
  assert (project / 'inside').read_text() == 'project'
  assert not (point / 'sibling/secret').exists()
  assert not (alias / 'sibling/secret').exists()
  assert point.is_dir() and project.is_dir()
  (project / 'persisted').write_text('yes')
  (point / 'ephemeral').write_text('yes')
  ```

  After the agent exits but **before** leaving the private mount namespace, assert `project/persisted` exists and `ephemeral` does not on the namespace host. For absent-policy baseline use a distinct probe that asserts the sibling **is** visible; repeat masked checks for an unmounted existing directory, each shipped bwrap level and `learn`. For `learn`, use the same disposable agent or `--duration` and verify result outside/inside or explicit **pre-agent-exec** refusal. Skip only when environment lacks the required namespace/mount capability, with printed reason.
- [ ] Run `python3 -m unittest scripts.tests.test_mount_masking -v`; expect learn/overlap failures. Run `bash sandbox/tests/test-mount-masking.sh`; initially expect the view checks to fail if namespace setup succeeds, or a documented SKIP.
- [ ] Implement learn mask injection after host-home bind and before project bind, plus preflight of late exposures. For active Landlock, assert via `bwrap_rw_targets()` that tmpfs and project are writable; probe actual outside ephemeral write and host persistence with ABI available and with `[security] landlock=false`. If rights fail, repair derived rights without broadening host binds or stop per Deviation Protocol.
- [ ] Rerun integration + `bash sandbox/tests/test-landlock-exec.sh`, with ABI 0 simulated via `LINCE_LANDLOCK_FORCE_ABI=0`; expect PASS (or capability SKIP), no agent exec after a rejected overlap. Review and commit learn/integration work if implementing.

## Task 5: Config metadata, docs, and host acceptance

**Files:** Modify `lince-config/lince-config:291-300,436-469`, `docs/examples/lince.toml.example`, `sandbox/config.toml.example` and `sandbox/agent-sandbox:_DEFAULT_CONFIG`, `sandbox/README.md`, `docs/documentation/sandbox/security-model.md`; regenerate `schemas/{lince,sandbox-config}.schema.json`, `docs/documentation/configuration-keys.md`, `lince-dashboard/skills/lince-configure/references/sandbox-config.md`. Test `scripts/tests/{test_schemas,test_config_reference,test_default_config,test_mount_masking}.py`. **Consumes:** policy semantics verified in Tasks 1–4. **Produces:** documented user contract and reproducible host acceptance transcript. **Guardrails:** generated refs/schemas only via generators; docs say direct-only, no dashboard claim.

- [ ] Add schema assertions that both addresses validate with an array of strings and reject wrong element types; no local authorization implied by JSON Schema (runtime source checks are authoritative). Add examples with `[]` off-by-default and a real absolute mount path; keep `_DEFAULT_CONFIG` byte-identical to `sandbox/config.toml.example`.
- [ ] Run `python3 scripts/tests/test_schemas.py` and `python3 scripts/tests/test_config_reference.py`; expect stale-output failures before regeneration.
- [ ] Update schema descriptions and narrative docs: both global addresses; empty/absent list retains old view; errors and unmounted warning; restart for new view; direct-only until Task 2; limits for unconfigured aliases, explicit binds, experimental overrides, later host mounts. Run `python3 lince-config/lince-config schema --write schemas/` and `python3 scripts/gen_config_reference.py`; regenerate copied default by matching the exact embedded text (guard test below).
- [ ] Run `python3 scripts/tests/test_schemas.py`, `python3 scripts/tests/test_config_reference.py`, `python3 scripts/tests/test_default_config.py`, `python3 scripts/tests/test_resolve.py`, `python3 -m unittest scripts.tests.test_mount_masking -v`, `bash sandbox/tests/test-mount-masking.sh`, `python3 sandbox/agent-sandbox --help`, and any lint used by the repo. Expected: all locally supported checks PASS, explicit capability skips only for real mount checks.
- [ ] On the actual `Dati` host, in a disposable project under `/run/media/alessio/Dati`, use a **test-only** sentinel sibling and a test-only file in the project; enable `[filesystem].mask_mount_points = ["/run/media/alessio/Dati"]` (or legacy), launch direct bwrap and record: project read/write with host persistence; sibling invisible through the mount path; `/dati` symlink shows the same view; outside-project write in the masked path is ephemeral. Repeat at available levels/learn, recording any explicit unsupported-overlap refusal. Do not mutate the real global config by hand during this task: use disposable `HOME`/installer workflows or a user-approved host validation procedure. Store an anonymized transcript in `docs/history/mount-masking-dati-validation.md` when actually run, otherwise state "Dati acceptance pending" (do not mark accepted).
- [ ] Review and commit docs/metadata plus evidence **only if implementing**; run `git status --short` to confirm no generated or installed-file drift.

## Acceptance mapping and release gate

| PRD Task 1 criteria (lines 118–147) | Verification |
|---|---|
| 118–122, 139 (opt-in, two globals, precedence, local both roots/formats) | Task 1 unit matrix + Task 3/4 no-list and backend launches |
| 123–126, 135–137, 141 (path errors, essential paths, unmounted, backend) | Task 2 fixtures + Task 3 backend gate + Task 4 unmounted real view |
| 127–134, 138, 140, 142 (siblings, symlink, traversability, persistence, overlap/learn, all levels) | Task 3 argv/preflight; Task 4 bwrap namespace matrix and Landlock probes |
| 143–145 (`Dati`, `/dati`, host writes) | Task 5 host transcript; cannot be certified from synthetic mount alone |
| 146–147 (global doc, direct-only, warning and limitations) | Task 5 docs + schema/reference consistency checks |

Release Phase 1 as **direct-launch-only** only after the real namespace matrix and `Dati` checks pass. If host verification cannot run, mark its acceptance pending rather than treating the phase as completed. Phase 2 dashboard spawn, refresh and summary are separate work.

## Document locations and provenance

- [PRD](../../prd/2026-10-19-masking-opt-in-mount-lince.md) is the normative scope; this plan at `docs/superpowers/plans/2026-10-19-mount-masking-direct-launches.md` is the execution checklist for Task 1 only. The [PRD index](../../prd/README.md) connects the two phases to their source material.
- [V1 agreement](../../design/mount-visibility-v1.md) and [deferred questions](../../design/mount-visibility-open-questions.md) live in `docs/design/`; the [synthetic spike](../../history/mount-visibility-spike-2026-10-19.md) and [review dossier](../../history/2026-10-19-masking-opt-in-mount-lince-walkthrough.md) are dated evidence under `docs/history/`. The originals outside Git are retained as an archive; update the copies in this repository for subsequent revisions.
