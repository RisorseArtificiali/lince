# macOS verification report — VoxCode dashboard integration (#318)

Contributor report for [#318](https://github.com/RisorseArtificiali/lince/issues/318)
(dashboard side) and [voxcode#3](https://github.com/RisorseArtificiali/voxcode/issues/3)
(VoxCode side). One machine, Apple Silicon only. Checks that need a person at the
keyboard and microphone are listed as **not verified** at the end; everything
marked PASS below was reproduced with the commands shown.

## Environment

| Component | Value |
|---|---|
| macOS | 26.6 (build 25G72), Apple Silicon (M4, MacBook Air) |
| Terminal | Orca 1.4.199 (`TERM_PROGRAM=Orca`) |
| Package managers | Homebrew 6.0.21, uv 0.9.24 |
| Host `python3` | 3.14.6 (Homebrew) |
| VoxCode runtime | Python 3.13.11 in the `uv tool` environment |
| Zellij | 0.45.1 (`brew install zellij`) |
| VoxCode | 0.1.0, commit `9e3ac2d` (2026-04-01) |
| Audio/ASR stack | sounddevice 0.5.6 with bundled PortAudio 19.7.0 (CoreAudio), faster-whisper 1.2.1, ctranslate2 4.8.2 |
| Whisper | `tiny`, CPU, `int8`. Metal/MPS not covered |
| Rust | rustup `stable-aarch64-apple-darwin`; `wasm32-wasip1` added by `plugin/build.sh` |
| LINCE | branch of this PR, on top of `main` at `5eeca4d`; re-run after merging `main` at `b4b7b30` (mute/`Alt+m`, PTT `Alt+t`) |

`XDG_RUNTIME_DIR` is unset on macOS, so the voice worker socket lives in
`/tmp/lince-voice-<uid>/`. The macOS input-source shortcuts (Ctrl+Space) were
disabled on this machine.

## Setup steps and results

### 1. VoxCode installation — installer FAIL, manual `uv tool install` PASS

`bash install.sh` from a VoxCode clone stops at step 1/4:

```
Error: PortAudio library not found (required by sounddevice).
  Install it for your distro:
    Ubuntu/Debian:  sudo apt install libportaudio2
    ...
```

The check only knows `ldconfig`, `/usr/lib/libportaudio.so` and
`pkg-config portaudio-2.0`. On macOS no system library is needed: the
`sounddevice` wheel ships its own `libportaudio.dylib`. Working steps:

```bash
git clone https://github.com/RisorseArtificiali/voxcode.git
uv tool install --from ./voxcode voxcode      # installs ~/.local/bin/voxcode
mkdir -p ~/.config/voxcode
cp voxcode/config.example.toml ~/.config/voxcode/config.toml
voxcode --list-devices
```

`voxcode --list-devices` listed the CoreAudio inputs (built-in microphone, an
iPhone Continuity microphone, Microsoft Teams Audio) with the built-in
microphone as default. `~/.local/bin` must be on `PATH` before running the LINCE
installer, which enables the integration only when `voxcode` is found.

`quickstart.sh` clones VoxCode and runs the same `install.sh`, so on macOS it
prints `✗ VoxCode installation failed` and continues without voice; install
VoxCode manually as above and re-run `lince-dashboard/install.sh`.

Follow-up (VoxCode repository, scope of voxcode#3): skip or relax the PortAudio
check on Darwin. `brew install portaudio` plus `pkg-config` should also satisfy
the existing check but was not tested.

### 2. LINCE dashboard installation — PASS

```bash
brew install zellij
LINCE_DASHBOARD_PRESET=minimal LINCE_VOXCODE_ENABLED=true bash lince-dashboard/install.sh
```

Result: plugin built with the rustup toolchain (`build.sh` added the
`wasm32-wasip1` target itself), plugin permissions written to
`~/Library/Caches/org.Zellij-Contributors.Zellij/permissions.kdl`,
`Alt v` / `Alt x` / `Ctrl Space` bindings present in
`~/.config/lince-dashboard/zellij.kdl`, `voxcode_enabled = true` in
`~/.config/lince-dashboard/config.toml`, adapter at `~/.local/bin/lince-voice`,
Seatbelt detected as sandbox backend. No manual step was needed.

### 3. Automated tests on macOS — 2 failures found, both fixed in this PR

`python3 -m unittest lince-dashboard/tests/test_voice.py` initially reported two
errors:

- `ModuleNotFoundError: No module named 'numpy'` in the fake-audio test: a test
  dependency of the host interpreter, not a platform problem. Run with
  `uv run --no-project --with numpy python -m unittest lince-dashboard/tests/test_voice.py`.
- `{"error": "AF_UNIX path too long"}` from the socket worker test. macOS caps
  Unix socket paths at 104 bytes and the test places `XDG_RUNTIME_DIR` under the
  per-user temp dir (`/var/folders/.../T/...`, ~60 bytes) so the socket path
  overflowed. The adapter now falls back to `/tmp/lince-voice-<uid>/` when the
  runtime directory is too long; a regression test covers it. Production use
  was unaffected because `XDG_RUNTIME_DIR` is unset on macOS.

`lince-dashboard/tests/check-ui-session.py` (real Zellij, fixture adapter) timed
out at startup on macOS: it wrote plugin permissions under `XDG_CACHE_HOME`,
which Zellij ignores on macOS in favour of `~/Library/Caches`, so the plugin
never received `RunCommands`. The harness now redirects `HOME` to its
disposable directory and writes the macOS cache path there. After the fix both
presets pass on macOS:

```
statusline: voice controls and shell delivery, global popups, sidebar/status-bar combinations, agent geometry and save/quit OK
minimal: voice controls and shell delivery, global popups, sidebar/status-bar combinations, agent geometry and quit without save OK
```

This covers, with scripted key events and no audio: `Alt+v` popup, `s`/`a`/`m`/`x`,
`Ctrl+Space` (both the legacy NUL byte and the CSI-u encoding) starting a PTT
recording and `Alt+t` stopping it, insertion into the visible shell and into the
visible agent, locked mode (`Ctrl+l`), sidebar hidden, all `Alt+b` states,
save/quit with restart, and quit without saving agent state.

After merging `main` (`b4b7b30`, 2026-09-22) the same run first failed on
both platforms' code path, not on macOS: since #343 every agent pane is wrapped
by `lince-msg-host`, which the harness only installs with `--messaging`, so the
fixture panes died with `env: lince-msg-host: No such file or directory` and the
PTT insertion into the agent had no target. The harness now writes a
pass-through `lince-msg-host` stub for ordinary smoke runs. With the rebuilt
plugin both presets pass again on macOS (one run hit a 10 s `list-panes`
timeout right after the save/quit restart and passed on the next run).

`test_layout_launch.py`, `test_preset_install.py`, `test_clipboard_setup.py`,
`test_codex_hooks.py` and `test_plugin_install.py` pass. The Rust plugin tests
(`tests/run-plugin-tests.sh`) were not run: `wasmtime` is not installed here;
they run in the `plugin-ci.yml` workflow on the pull request.

### 4. Adapter with the real microphone, outside Zellij — PASS

The adapter was driven directly (`lince-voice --request '{"action": ...}'`) with a
scratch `HOME`, using the built-in microphone and macOS text-to-speech
(`say -v Alice`) through the speakers as the audio source.

| Check | Result |
|---|---|
| Worker spawned from the `voxcode` entry-point interpreter, socket in `/tmp/lince-voice-<uid>/` | PASS |
| `devices`: three CoreAudio inputs enumerated by name | PASS |
| Save by device name, `tiny`/CPU, language `it`; settings survive worker shutdown and restart, worker starts stopped | PASS |
| `start`: `loading` for ~9 s (first run includes the model download), then `listening` | PASS |
| Level meter: values 0–2 while speech played, 0 in silence | PASS |
| VAD transcription: "Ciao, questo è un test del riconoscimento vocale su macOS" → `Ciao, questo è un test del riconosimento vocale su mecoe.` (`tiny` quality) | PASS |
| Mute (`pause` at the time, now `mute`): microphone closed, a sentence spoken while muted never appeared, also after unmute | PASS |
| Unmute, `send`, event acknowledgement, `stop` | PASS |
| PTT: first `ptt` from stopped starts and arms, second `ptt` stops and transcribes | PASS |
| Raw capture sanity (`sounddevice.rec`, 3 s): non-zero samples on the default and the named device | PASS |

No new microphone permission prompt appeared; the terminal app already had
Microphone access. A fresh machine is expected to prompt the terminal app the
first time the worker opens the stream.

### 5. Real audio inside a Zellij session — PASS

A scripted session (same disposable setup as `check-ui-session.py`, but with the
real `lince-voice`, VoxCode on `PATH`, saved settings VAD/`tiny`/CPU/auto-insert)
ran `Alt+v`, `a`, `Esc`, then played a sentence through the speakers:

```
sh-3.2$ inserimento vocale nella scelle visibile del dashboard
```

The worker was spawned by the Zellij server process, captured the microphone,
transcribed on CPU, and the plugin inserted the text into the visible shell
without an Enter and without the clipboard. `x` stopped the worker and the
status bar returned to `VA-STOP`. The same run with the `statusline` preset
(sidebar hidden) delivered the text identically; no difference between
`minimal` and `statusline` with real audio.

One observation, not shown to be macOS-specific: when `Alt+v` was the very first
popup of a fresh session and the floating layer had never been shown, the
plugin did not remember a target and opened the popup with
`Error: Focus a visible agent or shell before inserting text`, keeping the
message. Focusing the shell and reopening `Alt+v` delivered it, as documented.
The problem did not occur once any popup had been opened and closed first.

## Not verified (needs a person at the keyboard)

- Terminal-specific Option-as-Meta handling: the scripted runs inject the
  `Esc`-prefixed / CSI-u sequences directly, so `Alt+v`, `Alt+t`, `Alt+m` and the other
  `Alt` shortcuts were not exercised through a physical Option key in Orca,
  Terminal.app, iTerm2, Ghostty, kitty or WezTerm.
- `Ctrl+Space` conflict with the macOS *Select the previous input source*
  shortcut when it is enabled (it was disabled on this machine).
- First-run microphone permission prompt for a terminal app without prior
  Microphone access, and the behaviour when access is denied (expected: level
  meter stays at zero, no text).
- Intel Macs and the `voxcode` standalone UI.

Metal/MPS is not a pending check but a stack limitation: VoxCode transcribes
only through faster-whisper/ctranslate2, and the ctranslate2 wheel installed on
macOS reports `unsupported device mps` / `unsupported device metal` and is not
compiled with CUDA (`ctranslate2.get_supported_compute_types`). CPU (`int8`,
`float32`) is the only option on macOS today; the adapter's CUDA choice does
nothing here.

## Follow-ups

1. VoxCode installer: Darwin-aware PortAudio check (voxcode#3 / voxcode#2).
2. `quickstart.sh`: on macOS it reports the VoxCode installer failure and moves
   on; once the VoxCode installer works on Darwin no change is needed here.
3. Optional: a Darwin note in the installer's *VoxCode not installed* hint, and
   `wasmtime` in the macOS toolchain notes for the Rust plugin tests.
