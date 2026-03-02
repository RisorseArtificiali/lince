# VoxCode Roadmap

Items currently out of scope, with notes on how they could be implemented as extensions.

---

## 1. Audio File Processing

**Priority**: Medium
**Effort**: Low-Medium

Process pre-recorded audio files (.wav, .mp3, .flac) instead of live microphone input.

### Implementation approach

- Add a `--file <path>` CLI argument that bypasses the audio capture and VAD pipeline
- Use `soundfile` or `pydub` to load the audio, resample to 16kHz mono
- Feed directly to `Transcriber.transcribe()` — faster-whisper already handles long audio via its internal VAD segmentation
- For large files, use faster-whisper's `vad_filter=True` to auto-segment
- Output modes: (a) print to stdout, (b) send to Claude Code via tmux, (c) copy to clipboard

### Key code changes

```
cli.py:  add --file arg → load audio → transcribe → output
audio.py: add FileAudioSource class alongside AudioCapture
```

### Dependencies

- `soundfile` for reading audio formats (already a faster-whisper dependency)

---

## 2. TTS — Text-to-Speech for Claude Code Responses

**Priority**: Medium
**Effort**: Medium

Read Claude Code responses (or selected portions) aloud using a local TTS model.

### Implementation approach

- **Model options** (all local, no API needed):
  - `piper-tts`: Very fast, lightweight, good quality. Runs on CPU. Multiple voices per language. Best choice for low latency.
  - `coqui-tts` / `XTTS-v2`: Higher quality, GPU-accelerated, supports voice cloning. Heavier.
  - `bark`: Very natural, but slow even on GPU. Not ideal for real-time.
- **Response capture**: Monitor the Claude Code tmux pane output using `tmux capture-pane -p` to grab the latest response text
- **Selective reading**: Parse the response to skip code blocks, read only prose sections. User could configure what to read (full response, summary only, first paragraph, etc.)
- **Audio output**: Use `sounddevice` for playback (already a dependency)
- **Activation**: Voice command "comando: leggi" / "comando: read", or automatic after each response

### Architecture

```
tmux capture-pane → text extraction → piper-tts → sounddevice playback
                                         │
                          config: voice, speed, skip_code_blocks
```

### Key code changes

```
New module: tts.py          — TTS model wrapper (piper-tts)
New module: response_monitor.py — tmux pane output monitoring
cli.py:    add TTS toggle, "leggi" voice command
config.toml: [tts] section with voice, speed, auto_read settings
```

### Dependencies

- `piper-tts` (recommended) or `coqui-tts`
- Possibly `piper-phonemize` for text preprocessing

---

## 3. Claude Code MCP/Hook Integration

**Priority**: Low
**Effort**: Medium-High

Deeper integration with Claude Code beyond tmux send-keys.

### Implementation approach

- **As MCP server**: VoxCode registers as an MCP server that Claude Code connects to. This allows:
  - Claude Code to request voice input ("ask user by voice")
  - VoxCode to receive structured responses instead of scraping tmux
  - Bidirectional communication channel
- **As Hook**: Use Claude Code's hook system to trigger VoxCode actions on events (e.g., auto-read responses after each tool execution)
- **Protocol**: Implement the MCP stdio transport. VoxCode exposes tools like `voice_input`, `read_aloud`

### Architecture

```
Claude Code ←→ MCP stdio ←→ VoxCode MCP Server
                                 │
                    tools: voice_input(prompt) → text
                           read_aloud(text) → audio
```

### Key code changes

```
New module: mcp_server.py  — MCP protocol handler
New module: mcp_tools.py   — Tool definitions (voice_input, read_aloud)
cli.py:    add --mcp flag to start in MCP server mode
```

### Dependencies

- `mcp` Python SDK for MCP server implementation

---

## 4. Non-tmux Support

**Priority**: Low
**Effort**: Medium

Support usage without tmux (direct terminal, Wayland/X11 input injection).

### Implementation approach

- **Wayland**: Use `wtype` for keystroke injection (Wayland-native, similar to xdotool)
- **X11**: Use `xdotool type` for keystroke injection
- **Clipboard mode**: Copy transcription to clipboard via `wl-copy` (Wayland) or `xclip` (X11), user pastes manually
- **Auto-detect**: Check `$XDG_SESSION_TYPE` to determine Wayland vs X11, fall back to clipboard

### Key code changes

```
New module: input_bridge.py  — abstract interface with tmux/wayland/x11/clipboard backends
tmux_bridge.py: refactor as one backend of input_bridge
config.toml: [output] section with method = "tmux" | "wayland" | "x11" | "clipboard"
```

### Dependencies

- `wtype` (Wayland) or `xdotool` (X11) as system packages

---

## 5. Silero VAD Upgrade

**Priority**: Low
**Effort**: Low

Replace or supplement energy-based VAD with Silero VAD for better accuracy.

### Implementation approach

- Use `silero-vad` PyPI package (ONNX-based, no torch dependency)
- Implement as a second VAD backend selectable via config
- Silero VAD works on 30ms frames at 16kHz — same as current setup
- Better accuracy in noisy environments, fewer false triggers

### Key code changes

```
vad.py: add SileroVAD class implementing same interface as EnergyVAD
config.toml: [vad] engine = "energy" | "silero"
```

### Dependencies

- `silero-vad` (uses `onnxruntime` internally)

---

## 6. Noise Suppression

**Priority**: Low
**Effort**: Low

Pre-process audio to remove background noise before transcription.

### Implementation approach

- Use `noisereduce` library (numpy-based, lightweight) or RNNoise (via `rnnoise-python`)
- Apply noise reduction to each speech segment before sending to Whisper
- Configurable: on/off, aggressiveness level

### Key code changes

```
New module: noise.py  — noise reduction wrapper
cli.py: integrate between VAD output and transcriber input
config.toml: [noise] enabled = true, method = "rnnoise" | "noisereduce"
```
