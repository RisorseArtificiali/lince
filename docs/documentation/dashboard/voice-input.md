# Voice input with VoxCode

VoxCode integrates with any LINCE preset. It runs without a dedicated pane:
`Alt+v` opens a bordered configuration/control popup; the first row of the left
status-bar section displays its state and microphone level.

Install [VoxCode](https://github.com/RisorseArtificiali/voxcode) with its installer.
LINCE reuses VoxCode's Python environment and audio/transcription components;
it does not download another copy of its dependencies. The supported launcher is
the Python entry point installed by pip/uv. VoxCode keeps its standalone interface.

The LINCE installer offers to enable the integration when VoxCode is installed.
Automated quickstart defaults enable it when available. To opt out, set:

```toml
[dashboard]
voxcode_enabled = false
```

For automated installation, `LINCE_VOXCODE_ENABLED=true` or `false` skips the
integration question. Installation alone never activates the microphone.

## Configure and start

Press `Alt+v`. Use Tab or arrow keys to select a field; left/right change choices,
and Enter edits the microphone, language or model text. Backspace deletes text.
Microphone choices include the system default and detected input device names;
names are saved so device enumeration changes do not silently select another mic.
`r` refreshes the device list. An unavailable saved device requires a new choice.

Select PTT or VAD (voice activated), microphone, language, Whisper model, CPU/CUDA,
and whether to insert transcriptions automatically. Settings initially reflect
`~/.config/voxcode/config.toml` where present. Whisper compute type follows CPU
(`int8`) or CUDA (`float16`). Newer VoxCode transcriber factories are reused when
available; backend-specific configuration remains in VoxCode's own config.

- `s`: save configuration.
- `a`: save changes and start listening; model loading is indicated separately.
- `m`: mute/unmute. Muting closes the microphone stream and discards unfinished
  speech and pending transcription results; the loaded model stays available.
- `x`: stop, release the microphone and model, clear the unsent buffer.
- `i`: insert the current transcription buffer into the target terminal.
- `c`: clear the buffer.
- Escape: close the popup, keeping the chosen listening/muted state.

Stop before editing settings. They are saved immediately and atomically in
`~/.config/lince-dashboard/voice.json`, independently of the project agent state.
Closing with `Alt+q`, or quitting without saving agent state, does not discard
saved voice settings. A new dashboard always starts VoxCode **configured but
stopped**. The microphone is opened only after an explicit start.

## Push-to-talk and voice activation

In PTT mode, `Alt+t` or `Ctrl+Space` starts recording and a second press stops it
for transcription. Both shortcuts control the same recording: you can start with
one and stop with the other. The closing shortcut determines delivery: `Ctrl+Space`
inserts the transcription followed by Enter; `Alt+t` inserts text without Enter.
PTT inserts automatically when transcription finishes. `Ctrl+Space` is reserved for PTT rather than being
forwarded to the application in the pane. When VoxCode is configured but stopped,
the first press starts it and arms recording; wait for model loading to complete before speaking.
Before configuration, the shortcut opens the settings popup instead.
These global shortcuts also work in Zellij locked mode.

VAD mode records speech automatically after starting VoxCode. Silence ends each
segment. The threshold and silence duration come from VoxCode's `[vad]` config.
`Alt+m` mutes or unmutes VoxCode from any pane. Reopen `Alt+v` at any time to
mute or stop it. While muted the microphone is closed, so unmute with `Alt+m`,
the popup, or a spoken command.

In VAD mode, text accumulates in the buffer unless auto-insert is enabled. Existing VoxCode
voice commands such as `comando: invia` and `comando: cancella` still send or clear
it. VAD and manual buffer insertion do not add an Enter keystroke. Clipboard PTT is not part of this
integration.

## macOS

Verified on Apple Silicon with Zellij 0.45.1 and Whisper on CPU; see the
[macOS verification report](https://github.com/RisorseArtificiali/lince/blob/main/docs/design/dashboard-318-macos-verification.md)
for the environment, the exact steps and what is still unverified.

- **Install VoxCode with uv.** Its `install.sh` currently stops at a Linux-only
  PortAudio check on macOS. No Homebrew library is needed, because the
  `sounddevice` wheel bundles PortAudio:

  ```bash
  git clone https://github.com/RisorseArtificiali/voxcode.git
  uv tool install --from ./voxcode voxcode
  mkdir -p ~/.config/voxcode && cp voxcode/config.example.toml ~/.config/voxcode/config.toml
  voxcode --list-devices
  ```

  Keep `~/.local/bin` on `PATH`, then run `lince-dashboard/install.sh` (or
  re-run it with `LINCE_VOXCODE_ENABLED=true`). `quickstart.sh` reports
  "VoxCode installation failed" on macOS for the same reason and continues
  without voice.
- **Microphone permission** belongs to the terminal application: System
  Settings → Privacy & Security → Microphone. If the level indicator never
  moves while you speak, check this permission first.
- **Alt shortcuts need Option as Meta.** Terminal.app: *Use Option as Meta key*;
  iTerm2: *Left Option key: Esc+*; Ghostty: `macos-option-as-alt = true`.
  Otherwise Option plus a letter types a special character instead.
- **Ctrl+Space** is also the macOS *Select the previous input source* shortcut
  when enabled (System Settings → Keyboard → Keyboard Shortcuts → Input
  Sources). Disable it or use `Alt+x`.
- **CPU only.** Select CPU in `Alt+v`; the CUDA choice does nothing on macOS and
  the ctranslate2 backend used by VoxCode has no Metal/MPS support.
- The worker socket lives in `/tmp/lince-voice-<uid>/` because
  `XDG_RUNTIME_DIR` is unset on macOS.

## Destination and indicator

PTT fixes the destination to the active terminal when recording stops. Switching
panes during transcription does not redirect the result: it is delivered to the
original pane even if that pane is now hidden, without changing focus. If that
pane closes, the result is retained with an error; it is not sent elsewhere.

For VAD and manual insertion, the destination is the last focused, visible
terminal. Opening the popup does not change it. Switching terminals before
delivery selects the new destination. If that target disappears or becomes suppressed,
LINCE retains the undelivered message and opens the popup with an error; focus a
visible terminal to deliver it. It never reveals a hidden agent just to insert text.
The standalone `voxcode-text` pipe retains its existing focused/selected-agent routing.

| Indicator | Meaning |
|---|---|
| `V-??????` | Installed, configuration not completed |
| `VP-STOP` / `VA-STOP` | Configured PTT/VAD, stopped |
| `VP-LOAD` / `VA-LOAD` | Loading the transcription model |
| `VP-###···` / `VA-###···` | Live microphone level, six fixed cells |
| `VP-...` / `VA-...` | Transcribing |
| `VP-MUTE` / `VA-MUTE` | Temporarily muted |
| `V-ERR` | Error; details are shown in the popup |

The left agent summary stays entirely on the second row. Green `R` alternates
with white `/` in place. `Alt+b` continues to control the bar: when hidden or
agents-only, the voice indicator is hidden too, while voice shortcuts still work.
Disabling voice integration or not installing VoxCode leaves the first row free.

Each dashboard controller owns a private local voice worker. Text delivery is
acknowledged to avoid duplication; audio/results queued before muting are
invalidated. Normal dashboard exit stops the worker; after an interrupted session
it expires when no dashboard polls it for 20 seconds. No microphone or model is
needed for the automated tests; real audio is verified with the smoke checklist.
