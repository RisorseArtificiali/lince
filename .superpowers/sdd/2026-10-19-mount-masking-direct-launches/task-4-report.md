# Task 1, subtask 4 — stopped at Deviation Protocol

**Status: BLOCKED / NOT COMMITTED.** Base HEAD `362ec93` (`feat/mount-masking`), initially clean. Implementation and tests below are uncommitted and not accepted as complete.

## Step and deviation

The Task 4 real namespace integration gate was expected to report PASS after exercising a mounted and unmounted point, or SKIP with a printed reason if user/mount namespace or mount capabilities were unavailable. Command (twice):

```text
bash sandbox/tests/test-mount-masking.sh
bash: fork: Impossibile allocare memoria
```

Neither invocation reached the script's capability-specific `SKIP` message or the view checks. Earlier `unshare -Urmp -- true` and `unshare -Urmp -- mount -t tmpfs tmpfs /tmp` both exited successfully; an earlier `unshare -Urmp -- sh -c 'mount --make-rprivate / && mount -t tmpfs tmpfs /tmp && umount /tmp'` printed `sh: fork: Impossibile allocare memoria`. The failure may relate to subprocess creation in this environment; no capability conclusion or integration PASS can be drawn. Per the plan's Deviation Protocol, work stopped rather than relabeling this as a namespace-capability SKIP or weakening the test.

**Smallest question:** Should I treat this `fork`/`ENOMEM` result as an environmental blocker and resume Task 4 once subprocess creation is available (or use an approved isolated test environment), leaving the gate mandatory rather than marking it SKIP?

## Changes in worktree (uncommitted)

- `sandbox/agent-sandbox`: optional learn-builder mask argument, masks after writable home and before project; final exposure preflight; learn global/local intake and pre-launch error handling.
- `scripts/tests/test_mount_masking.py`: learn ordering, home overlap and late exposure, cwd-local early rejection, no-list parity; Landlock derived-target and late record-bind assertions.
- `sandbox/tests/mount_mask_probe.py`: disposable project probe as prescribed in the plan.
- `sandbox/tests/test-mount-masking.sh`: disposable HOME/config and two fixture directories, private mounted tmpfs, baseline-visible probe, per-level masked probe, Landlock on/off, learn marker checks. The gate has not run successfully and needs review in a capable environment.

`sandbox/mount_masking.py` was not changed.

## TDD evidence and remaining checks

RED: `python3 -m unittest scripts.tests.test_mount_masking -v`: `Ran 40 tests in 0.083s`, `FAILED (failures=1, errors=3)`; three learn tests rejected the missing `mask_mount_points` parameter, and cwd-local early rejection failed because backend resolution happened first. The 35 prior tests and new Landlock-target assertion passed.

After preliminary implementation, the same command produced `Ran 40 tests in 0.149s`, `FAILED (failures=1)`: the new test matched the earlier status-directory `--bind` instead of the later home `--bind`. That assertion was corrected, but the focused suite was **not rerun** after the correction because of the integration deviation. The Landlock exec gate (`bash sandbox/tests/test-landlock-exec.sh`), ABI 0 simulation, final self-review, and commit remain pending. No claim of actual agent execution, sibling hiding, ephemeral writes or host persistence is made from the unexecuted real-mount gate.

Backlog.md MCP workflow resource and tools are unavailable in this session (resource list and templates both empty); no tracking item was created.

## Resumption after approved `unshare --fork` deviation (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (new deviation).** The plan now records the approved namespace-harness correction: PID namespaces require `unshare --fork` for a multi-process test. Both `unshare -Urmp` invocations in `sandbox/tests/test-mount-masking.sh` were changed to `unshare -Urmpf`. No user configuration or installed files were changed.

### Focused unit result

`python3 -m unittest scripts.tests.test_mount_masking -v`: `Ran 40 tests in 0.089s` / `OK`. This includes the corrected home-bind test assertion.

### New integration deviation

Expected: `bash sandbox/tests/test-mount-masking.sh` passes the no-policy baseline (the disposable visible probe executes and observes the sibling), then exercises masked views for mounted/unmounted points and levels or prints a genuine capability SKIP.

Observed: the script reached the first `agent-sandbox run` in the private namespace but exited before its probe executed; bwrap printed:

```text
bwrap: Can't find source path /tmp/lince-mask-test.QVItPr/home/.agent-sandbox/claude-config: No such file or directory
```

The launcher banner identified `mask-probe (python3)`, project `/tmp/lince-mask-test.QVItPr/point/project`, `landlock off`, and the disposable global config. No baseline PASS, masked check, or capability SKIP printed. This is an unexpected baseline fixture/bwrap failure rather than evidence of a mask view, so the task stopped before the Landlock gate, ABI 0 simulation, self-review or commit. No assumption is made that a bwrap process beginning means agent execution.

**Smallest question:** May I make the disposable fixture's sandbox config directory exist (or set an equivalent test-only config setting) to satisfy this generated baseline bind, then rerun the full required gates? The correction would touch only `sandbox/tests/test-mount-masking.sh`, not production bind behavior or the masking guarantee.

## Resumption after approved disposable-home fixture correction (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (new deviation).** The plan now approves creating the disposable `home/.agent-sandbox/claude-config` directory. Changed only the fixture's `mkdir -p` line to create it; no real HOME, installed files, or production bind logic changed.

### New real-mount gate result

Command: `bash sandbox/tests/test-mount-masking.sh`.

Expected: the first no-list baseline executes `visible_probe.py`, verifies sibling visibility and writes `project/baseline-ran`; then the mounted/unmounted masking matrix runs or emits a genuine namespace/mount capability SKIP.

Observed: the test reached the first disposable `agent-sandbox run` but bwrap failed before probe exec with:

```text
bwrap: Can't mkdir /run/user/0: Read-only file system
```

The launcher identified `mask-probe (python3)` and project `/tmp/lince-mask-test.ChQ58T/point/project`, with `landlock off`. No baseline PASS, agent marker, masked-view assertion, or SKIP was printed. This is a different unexpected bwrap capability/view result than the approved missing-source fixture error. Per the plan's Deviation Protocol the task stopped here; the focused unit suite, Landlock exec gate, ABI 0 simulation, self-review, and commit were **not** run in this resumption. Previous focused-unit result remains `Ran 40 tests` / `OK` from the prior resumption, not a fresh verification after this fixture edit.

**Smallest question:** May I add a test-only writable `/run/user/0` parent in the private namespace (or otherwise provide that bwrap tmpfs destination in the disposable harness) and rerun the mandatory gates? This would not change production mount behavior, but the current baseline cannot reach agent exec without a decision on the private namespace's `/run` layout.

## Resumption after approved private runtime mount (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (actual view failure).** The plan now authorizes a private-namespace-only temporary mount for `/run/user/0` startup. Added `mount -t tmpfs tmpfs /run/user` and `mkdir -p /run/user/0` immediately after `mount --make-rprivate /` inside `unshare -Urmpf`; no host `/run/user`, real HOME or production mount policy was changed.

### Real-mount gate: first baseline assertion

Command: `bash sandbox/tests/test-mount-masking.sh`.

Expected: absent-policy baseline probe executes and reads the host-created sibling sentinel at `project.parent / 'sibling/secret'`, writes `project/baseline-ran`, then masked matrix tests execute. Actual: the probe **did execute**, but its sibling read raised:

```text
Traceback (most recent call last):
  File "/tmp/lince-mask-test.ptJrG6/point/project/visible_probe.py", line 3, in <module>
    assert (project.parent / 'sibling/secret').read_text() == 'secret'
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/lince-mask-test.ptJrG6/point/sibling/secret'
```

The `agent-sandbox` banner identified `landlock off`, `mask-probe (python3)`, and project `/tmp/lince-mask-test.ptJrG6/point/project`. The script printed no baseline PASS, no masked checks, and no capability SKIP. This is a view failure rather than an inability to spawn bwrap or execute the agent. The script's fixture resides below `/tmp`, and the default bwrap command has a `--tmpfs /tmp`; whether that is the entire explanation requires an explicit fixture/view decision, not a silent change to the guarantee. Per the plan and the user's instruction, stopped before Landlock/ABI 0, focused-unit rerun, self-review, or commit. The last focused run remains the prior `Ran 40 tests` / `OK` result, not a fresh result in this resumption.

**Smallest question:** May I relocate only the disposable mount fixture to a private-namespace path outside bwrap's default `/tmp` tmpfs (keeping HOME/config disposable and the sibling visibility baseline mandatory), then rerun the full gates? If that is not the intended baseline view, what absent-policy visibility should the test assert for a fixture beneath `/tmp`?

## Resumption after approved private `/mnt` fixture relocation (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (Landlock shim launch failure).** The plan now approves placing only the synthetic fixture under `/mnt` tmpfs inside `unshare -Urmpf`. The disposable HOME/config remain under the temporary `/tmp` directory. The harness mounts `/mnt` after making propagation private, creates `point` and `plain` there, mounts its synthetic point under `/mnt`, and repoints the fixture alias for each case. No host `/mnt` or `/run` mount was changed.

### Real-mount gate: baseline PASS; first Landlock run fails before probe

Command: `bash sandbox/tests/test-mount-masking.sh`.

Expected: with the absent mask list, `visible_probe.py` runs, reads the sibling sentinel and writes `baseline-ran`; then with a mask and Landlock active at the normal level, `mount_mask_probe.py` runs, reads the project, finds neither original sibling nor alias, writes a persistent project marker and an ephemeral outside marker.

Observed: `PASS: point no-list baseline sees sibling`. The next launch displayed `landlock fs only (ABI 7)` but the Landlock shim exited before probe execution:

```text
Traceback (most recent call last):
  File "/tmp/.lince/agent-sandbox", line 39, in <module>
    from mount_masking import (MountMaskError, check_mount_exposures, load_mount_mask_points,
ModuleNotFoundError: No module named 'mount_masking'

During handling of the above exception, another exception occurred:
  File "/tmp/.lince/agent-sandbox", line 48, in <module>
    spec.loader.exec_module(module)
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/.lince/mount_masking.py'
```

There was no masked PASS, no persistence/ephemeral verification, and no capability SKIP; the first masked agent did not exec. The prescribed Landlock/ABI 0 and focused unit gates were not run in this resumption, and no self-review or commit followed. The previous focused result is `Ran 40 tests` / `OK`, not a fresh run.

**Smallest question:** May I update the opt-in bwrap Landlock shim packaging so `mount_masking.py` is available beside the shim at `/tmp/.lince/agent-sandbox` inside the namespace, with a regression assertion that the shim import succeeds, then rerun the full gates? This would repair an actual launcher failure without disabling Landlock or relaxing the masked-view checks.

## Resumption after approved Landlock shim module bind (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (new profile-fixture deviation).** The plan records approval to bind `mount_masking.py` beside the Landlock shim. Added an expected-red unit check for the `--ro-bind` of the shipped sibling module at `/tmp/.lince/mount_masking.py` for both empty and nonempty mask lists. Focused command `python3 -m unittest scripts.tests.test_mount_masking.TestMountMaskPlanning.test_landlock_shim_binds_sibling_module_with_and_without_mask -v` produced `Ran 1 test` / `FAILED (failures=2)`: both subtests lacked the mount triple. Builder now adds the module bind next to the shim bind when Landlock is active. No Landlock policy was disabled or broadened.

### Real-mount gate: actual masked normal view PASS, missing custom-agent profile

Command: `bash sandbox/tests/test-mount-masking.sh`.

Expected: point baseline sees sibling; every shipped bwrap level (normal, permissive, paranoid), with Landlock on/off, checks masked view, persistent project write and ephemeral outside write, then the unmounted fixture and learn repeat the checks.

Observed:

```text
PASS: point no-list baseline sees sibling
agent-sandbox: landlock fs only (ABI 7) — rw rules=11 connect=[] bind=[]
PASS: point normal landlock=true hides siblings, persists project, isolates write
Error: unknown sandbox level 'permissive' for agent 'mask-probe' (looked for mask-probe-permissive.toml then permissive.toml in ./.agent-sandbox/profiles/, ~/.agent-sandbox/profiles/, and alongside agent-sandbox).
```

The actual agent probe executed in the Landlock-enabled masked normal case; the three named assertions passed. The `permissive` invocation failed at profile lookup for the disposable `mask-probe` agent, before any agent execution. No permissive/paranoid, no Landlock-off, no unmounted fixture, no learn view, no standalone Landlock/ABI 0 gates or full focused-unit rerun have been verified since the change. Per the Deviation Protocol stopped before self-review or commit.

**Smallest question:** May I add disposable `mask-probe` level fragments for `permissive` and `paranoid` under the temporary test HOME (mirroring the shipped level policy needed for each case), so the matrix can execute all three postures without changing installed profiles or weakening the mask checks? The required baseline and mask assertions would remain mandatory.

## Resumption after approved disposable level profiles (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (paranoid credential/proxy preflight).** The plan records approval to add temporary `mask-probe` profiles. The harness now copies the shipped `claude-permissive.toml` and `claude-paranoid.toml` verbatim into disposable `$HOME/.agent-sandbox/profiles/mask-probe-{permissive,paranoid}.toml`. No installed profile, user HOME, host credential or production policy was changed.

### Real-mount matrix result

Command: `bash sandbox/tests/test-mount-masking.sh`.

Expected: the no-list sibling-visible baseline and masked normal, permissive, paranoid cases execute the probe and assert hidden sibling (including alias), persistent project write, ephemeral outside write; continue through Landlock off, unmounted directory and learn.

Observed, in order:

```text
PASS: point no-list baseline sees sibling
agent-sandbox: landlock fs only (ABI 7) — rw rules=11 connect=[] bind=[]
PASS: point normal landlock=true hides siblings, persists project, isolates write
PASS: point permissive landlock=true hides siblings, persists project, isolates write
Error: [security] unshare_net = true requires at least one credential rule (e.g. ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN in [env.extra] or in the active provider's [providers.<name>.env] block), otherwise the proxy doesn't start and the sandbox has no path to any LLM API.
Quick fix: export ANTHROPIC_API_KEY (or another from ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) in your host shell — the paranoid fragment for agent 'mask-probe' auto-maps it via [env.extra].
```

Paranoid did not launch the probe; this is an explicit credential/proxy preflight required by the copied shipped policy, not a missing namespace capability or a verified masking regression. As instructed, stopped without injecting a host credential, editing the shipped profile, classifying this as SKIP, or proceeding to later matrix cells. The standalone Landlock script, ABI 0 simulation, full focused-unit rerun, self-review and commit have not run since this change. The prior focused unit result remains `Ran 40 tests` / `OK` before the new module-bind assertion.

**Smallest question:** May the private test harness supply a disposable, nonfunctional test-only Anthropic credential value to satisfy the shipped paranoid proxy preflight, with no real host credentials/config changed, and then rerun the matrix? If that would not support a faithful paranoid launch, should paranoid instead be reported as explicitly unavailable pending a credential-capable environment (not counted as PASS)?

## Resumption after approved fake paranoid credential (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (missing paranoid bridge tool).** The plan records approval to pass a nonfunctional test-only Anthropic credential to the paranoid fixture. For only the paranoid run, the harness now sets `ANTHROPIC_API_KEY=mask-probe-nonfunctional-test-only` and unsets two alternative Anthropic credential env vars. No real credential was read or API request made; the shipped policy and all filesystem assertions remain unchanged.

### Real-mount matrix result

Command: `bash sandbox/tests/test-mount-masking.sh`.

Expected: all normal, permissive and paranoid masked checks on the private mount (then Landlock-off, unmounted and learn checks), or a genuine namespace/mount capability SKIP.

Observed:

```text
PASS: point no-list baseline sees sibling
agent-sandbox: landlock fs only (ABI 7) — rw rules=11 connect=[] bind=[]
PASS: point normal landlock=true hides siblings, persists project, isolates write
PASS: point permissive landlock=true hides siblings, persists project, isolates write
Error: paranoid sandbox needs 'socat' on the host (it is bind-mounted into the sandbox to bridge TCP -> unix-socket). Install via your package manager (e.g. `dnf install socat` or `apt install socat`), or switch sandbox_backend to nono.
```

The first paranoid invocation did not exec the agent because the shipped profile requires `socat`, which is unavailable on this host. This is a required-tool limitation, not a namespace/mount SKIP or evidence that the masked view fails. As required by the plan's Deviation Protocol, stopped before the remaining matrix, full focused unit suite, standalone Landlock/ABI 0 gates, self-review and commit. The previous focused run (`Ran 40 tests` / `OK`) predates the new shim-module assertion and must not be cited as post-change verification.

**Smallest question:** Can the required `socat` executable be made available via the project's approved installation workflow or a suitable test host so the shipped paranoid posture can run unmodified, then may I rerun the prescribed gates? If not, should paranoid remain explicitly unverified rather than counted as a capability SKIP for the whole matrix?

## Resumption after host `socat` installation (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (new bwrap namespace failure).** User installed `socat`; retried the full real-mount matrix without changing the fixture, profile or production code.

### Real-mount matrix result

Command: `bash sandbox/tests/test-mount-masking.sh`.

Expected: masked normal/permissive/paranoid cases run their probes and check sibling+alias invisibility, project host persistence, and ephemeral outside writes with Landlock on and off, then repeat for unmounted directory and learn.

Observed:

```text
PASS: point no-list baseline sees sibling
agent-sandbox: landlock fs only (ABI 7) — rw rules=11 connect=[] bind=[]
PASS: point normal landlock=true hides siblings, persists project, isolates write
PASS: point permissive landlock=true hides siblings, persists project, isolates write
agent-sandbox: landlock fs+net (ABI 7) — rw rules=10 connect=[8118] bind=[]
PASS: point paranoid landlock=true hides siblings, persists project, isolates write
bwrap: open /proc/50/ns/ns failed: No such file or directory
```

The last line occurred on the **next** matrix cell, `point normal landlock=false`. Its banner identified `landlock off`, `mask-probe (python3)` and the same project; the script printed no PASS for that cell. The agent probe did not execute there. This is a new bwrap/PID namespace failure rather than a sibling visibility or Landlock denial assertion; neither a passing result nor a genuine missing-user/mount-namespace SKIP was produced. The unmounted fixture, learn and remaining Landlock-off cells are unverified. Per the Deviation Protocol stopped before fresh focused unit, standalone Landlock and ABI 0 checks, self-review or commit.

**Smallest question:** May I investigate and correct a private-namespace test-harness `/proc`/PID lifecycle issue (if confirmed) without altering production bwrap or masking policy, then rerun the mandatory matrix? If it is a host bwrap capability limitation instead, should this cell remain explicitly unverified rather than counted as PASS/SKIP?

## Resumption after approved private `--mount-proc` fixture (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (ABI 0 gate expectation mismatch).** The plan now records the approved private test PID/proc fix. Added `--mount-proc` to the main `unshare -Urmpf` invocation only; the one-shot mount capability probe is unchanged. No host mount, production policy, level profile, or view assertion changed.

### Required gates and output

- `bash sandbox/tests/test-mount-masking.sh`: exit 0. `PASS: point no-list baseline sees sibling`; for **point and plain**, `PASS` for normal/permissive/paranoid with `landlock=true` and `landlock=false` (12 masked cases), plus `PASS` for learn at both points. Each masked probe asserted original sibling and alias hidden, project read and host-persistent write, and ephemeral outside write absent on namespace host after exit. Paranoid with Landlock enabled printed `landlock fs+net (ABI 7)`; normal printed `landlock fs only (ABI 7)`. Unmounted plain produced the expected `path is not mounted at launch; masking the path anyway` warning. No capability SKIP.
- `python3 -m unittest scripts.tests.test_mount_masking -v`: `Ran 41 tests in 0.140s` / `OK`, including shim-module binding with/without masking, writable Landlock mount targets and learn preflight tests.
- `bash sandbox/tests/test-landlock-exec.sh`: host `Landlock ABI: 7`, `LANDLOCK GATE: ALL 11 CHECKS PASSED`. This includes the script's own `ABI 0 graceful: agent still execs (bwrap-only containment)` and `ABI 0 + --fail-closed: refuses to exec (I7)` checks. The inheritance check printed `bash: riga 2: /dev/null: Permesso negato` and still passed its denial assertion.
- `LINCE_LANDLOCK_FORCE_ABI=0 bash sandbox/tests/test-landlock-exec.sh`: **exit 1**, `Landlock ABI: 7`, `LANDLOCK GATE: 5 FAILED, 6 passed`. It reported `fs: write outside rw path NOT denied (IN_OK / OUT_OK)`, `inherit: subprocess escaped the fence (CHILD_OUT_OK)`, `net: connect to other port NOT denied`, `net: bind NOT denied`, and `record: shim did not update the record` (`AssertionError` in the record assertion). Its built-in ABI 0 graceful and fail-closed checks still passed.

### Deviation: expected versus observed

Expected from the prescribed ABI 0 simulation gate: a PASS or legitimate capability SKIP, with graceful bwrap-only fallback and paranoid fail-closed preserved. Observed: running the **whole standalone script** under forced ABI 0 makes its earlier ABI-7 enforcement checks assert that Landlock denies filesystem/network operations, while the shim intentionally degrades them (the script's kernel-ABI probe prints 7 even though `LINCE_LANDLOCK_FORCE_ABI=0` controls shim operation). Five assertions failed. This is an unexpected test-gate mismatch, not evidence that ABI 0 should enforce ABI 7 rights; no test assertion or Landlock policy was weakened. Per the Deviation Protocol, stopped before self-review and commit.

**Smallest question:** May I treat the existing script's built-in ABI 0 graceful/fail-closed checks as the required ABI 0 simulation evidence, rather than requiring the entire ABI-7 enforcement suite to pass with `LINCE_LANDLOCK_FORCE_ABI=0` exported globally? Alternatively, should the script's ABI probe be made force-aware so it skips only ABI-unavailable enforcement checks in that mode, then rerun it? Either choice would retain the paranoid fail-closed assertion.

## Resumption after approved ABI 0 gate interpretation (2026-10-19)

**Status: BLOCKED / NOT COMMITTED (learn + HOME overlap gate gap discovered during self-review).** The plan now approves using the dedicated ABI 0 graceful and fail-closed checks from the standard 11/11 standalone Landlock run. The globally forced-ABI-0 invocation remains an explicitly failed, inapplicable whole-script run; it is **not** marked PASS. No production or test files were changed in this resumption.

Self-review commands: `git diff --check` (exit 0, no output); `git diff -- docs/superpowers/plans/2026-10-19-mount-masking-direct-launches.md sandbox/agent-sandbox scripts/tests/test_mount_masking.py`; read both new integration files; `git status --short --branch` showed the intended five tracked/untracked scoped files and the approved plan note. Reviewed the masked learn builder, module bind order, and real-mount matrix. The real matrix's learn cases set `HOME` under the disposable `/tmp` root while masking `/mnt/.../point` or `/mnt/.../plain`. The unit case `test_learn_mask_after_writable_home_and_before_project` does mock `Path.home()` as the mask point and asserts mount order, and another unit case rejects a late re-exposing bind; neither launches a real agent with the learn home bind overlapping the mask point. The code does not explicitly refuse this overlap before agent exec. Thus the Task 4 guarantee that a learn HOME overlap cannot expose original siblings outside the project is **not yet established** by the required real view test or by a pre-agent rejection.

The last verified results remain: real matrix PASS for 2 fixtures × 3 levels × Landlock on/off plus two learn cases with nonoverlapping HOME; focused suite `Ran 41 tests` / `OK`; standard Landlock script `ALL 11 CHECKS PASSED` including dedicated ABI 0 graceful/fail-closed; globally forced whole-script run `5 FAILED, 6 passed` (not a supported PASS). No new tests were run after the gap was identified, and no commit was made.

**Deviation: expected versus observed:** Expected at self-review: no remaining Task 4 gate gaps, including learn when the writable HOME overlaps the masked point (real probe or explicit refusal before agent execution). Observed: only argv-order/unit preflight tests for this overlap; integration learn probes use nonoverlapping HOME and never exercise or refuse the overlap. Per the plan's Deviation Protocol stopped before final review/commit rather than inferring real isolation from argv.

**Smallest question:** May I add one dedicated private-namespace learn case with disposable HOME equal to a masked point and the existing probe project beneath it, require either the same sibling/alias invisibility + ephemeral/project persistence markers or a demonstrable pre-agent-exec overlap refusal, and rerun the relevant gates? No real HOME/config or production mount policy would change.

## Final resumption — required learn/HOME overlap (2026-10-19)

**Status: VERIFIED / ready for scoped commit.** The approved PRD and Task 4 plan already require this case; no new product decision was needed. Added a real private-namespace learn invocation with `HOME` equal to the synthetic mounted mask point and project within it. The home config is copied into that disposable point, never into a real user directory. Success requires the existing probe to complete (project read, original sibling and alias absent, project marker persisted, outside write ephemeral); refusal is accepted only when stderr explicitly identifies a masked overlap and there is no project or outside marker. This run took the successful-agent path. Added a focused pre-agent-exec test for a late re-exposing bind under overlapping learn HOME: preflight errors before `mkstemp` or `Popen`.

### Final verification commands and results

- `bash sandbox/tests/test-mount-masking.sh` — exit 0; both baseline lines `PASS: point/plain no-list baseline sees sibling`; **12 masked run cases** (point/plain × normal/permissive/paranoid × Landlock true/false) printed `PASS ... hides siblings, persists project, isolates write`; both non-overlap learn cases printed `PASS`; additionally `PASS: learn HOME overlap hides sibling, persists project, isolates write`. This proves agent execution and host-side persistence/absence assertions, rather than treating bwrap startup as success. Mounted point shows ABI 7 Landlock fs-only for normal, fs+net for paranoid; unmounted directory prints the expected warning.
- `python3 -m unittest scripts.tests.test_mount_masking -v` — `Ran 42 tests in 0.115s` / `OK`, including learn HOME ordering/late exposure, launch-level early rejection (no `Popen` or trace), no-list parity, shim module bind with and without masking, and writable Landlock targets.
- `bash sandbox/tests/test-landlock-exec.sh` — `Landlock ABI: 7`, `LANDLOCK GATE: ALL 11 CHECKS PASSED`; specifically `ABI 0 graceful: agent still execs (bwrap-only containment)` and `ABI 0 + --fail-closed: refuses to exec (I7)` PASS. The earlier global `LINCE_LANDLOCK_FORCE_ABI=0 bash sandbox/tests/test-landlock-exec.sh` failed 5 ABI-7 enforcement assertions and is **not** marked a pass, as the user-approved plan note explains.
- `python3 scripts/tests/test_policy_record.py` — `Ran 14 tests in 0.006s` / `OK`; `python3 scripts/tests/test_sandbox_broker_bind.py` — `Ran 3 tests in 0.047s` / `OK`; `python3 sandbox/agent-sandbox --help` — exit 0, usage printed; `bash -n sandbox/tests/test-mount-masking.sh && git diff --check` — exit 0, no output.

### Self-review and scope

Reviewed the production diff and new files, including the final bwrap preflight order, learn intake before backend/helper/startup, and the opt-in Landlock shim's sibling-module bind (also needed for the no-list shim). The private test namespace uses `unshare -Urmpf --mount-proc`, makes mount propagation private, and mounts `/run/user` and `/mnt` only there; real HOME/config and installed files are untouched. Baseline and masked checks use the same disposable agent config without appended CLI program; fake credential exists only for paranoid fixture process preflight. The copied shipped level profiles are not weakened. `sandbox/mount_masking.py` needed no Task 4 edit; Task 3 automatic-bind preflight remains active, and raw experimental overrides remain the approved limitation. Further host-specific Dati acceptance is Task 5, not established here.

The record above retains each stopped attempt and its approved resolution. No further Task 4 view or Landlock gate gap was found after the real learn/HOME overlap case passed.
