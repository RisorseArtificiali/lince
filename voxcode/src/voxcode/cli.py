"""Main application entry point and orchestration."""

import argparse
import queue
import select
import sys
import termios
import threading
import tty

import numpy as np

from voxcode.audio import AudioCapture
from voxcode.commands import CommandType, parse_transcription
from voxcode.config import VoxCodeConfig, load_config
from voxcode.multiplexer import create_bridge
from voxcode.transcriber import TranscriptionResult, Transcriber
from voxcode.ui import VoxCodeUI
from voxcode.vad import EnergyVAD, VADState


class VoxCode:
    """Main application class coordinating audio → VAD → whisper → multiplexer pipeline."""

    def __init__(self, config: VoxCodeConfig):
        self.config = config
        self.running = False
        self.paused = False
        self.buffer = ""
        self.ptt_active = False

        self._result_queue: queue.Queue[TranscriptionResult] = queue.Queue()
        self._transcription_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._old_term_settings = None

        self.audio = AudioCapture(sample_rate=16000, device=config.audio.device)
        self.vad = EnergyVAD(
            threshold=config.vad.threshold,
            silence_duration=config.vad.silence_duration,
            pre_roll=config.vad.pre_roll,
        )
        self.transcriber = Transcriber(
            model_size=config.whisper.model,
            device=config.whisper.device,
            compute_type=config.whisper.compute_type,
        )
        self.bridge = create_bridge(config)
        self.ui = VoxCodeUI()

    def run(self):
        if not self._validate_environment():
            return

        self.running = True
        self._setup_terminal()

        try:
            target = self.bridge.get_target_pane()
            self.ui.mode = self.config.general.mode
            self.ui.target_pane = target
            self.ui.start()
            self.ui.update(status="loading")

            # Preload whisper model in background
            load_thread = threading.Thread(target=self._preload_model, daemon=True)
            load_thread.start()

            self.audio.start()

            # Transcription worker thread
            transcribe_thread = threading.Thread(target=self._transcription_worker, daemon=True)
            transcribe_thread.start()

            # Wait for model to load
            load_thread.join()
            self.ui.update(status="listening")

            self._main_loop()
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.audio.stop()
            self.ui.stop()
            self._restore_terminal()

    def _validate_environment(self) -> bool:
        console = self.ui.console
        try:
            self.bridge.validate()
        except RuntimeError as e:
            console.print(f"[red]Multiplexer error: {e}[/]")
            return False

        try:
            self.bridge.get_target_pane()
        except RuntimeError as e:
            console.print(f"[red]Claude Code not found: {e}[/]")
            return False

        try:
            import sounddevice as sd

            sd.query_devices(kind="input")
        except Exception as e:
            console.print(f"[red]Audio error: {e}[/]")
            return False

        return True

    def _preload_model(self):
        self.transcriber._ensure_model()

    def _setup_terminal(self):
        if sys.stdin.isatty():
            self._old_term_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())

    def _restore_terminal(self):
        if self._old_term_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term_settings)
            self._old_term_settings = None

    def _poll_keyboard(self) -> str | None:
        if not sys.stdin.isatty():
            return None
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def _main_loop(self):
        ptt_frames: list[np.ndarray] = []

        while self.running:
            # 1. Keyboard
            key = self._poll_keyboard()
            if key:
                self._handle_key(key, ptt_frames)

            # 2. Audio frame
            try:
                frame = self.audio.get_frame(timeout=0.05)
            except queue.Empty:
                self._check_results()
                continue

            level = AudioCapture.get_level(frame)
            self.ui.update(audio_level=min(level * 10, 1.0))

            if self.paused:
                continue

            # 3. Mode-specific processing
            if self.config.general.mode == "vad":
                self._process_vad(frame)
            else:
                self._process_ptt(frame, ptt_frames)

            # 4. Check transcription results
            self._check_results()

    def _process_vad(self, frame: np.ndarray):
        state_changed, speech_audio = self.vad.process_frame(frame)
        if not state_changed:
            return

        if self.vad.state == VADState.SPEECH:
            self.ui.update(status="recording")
        elif speech_audio is not None and len(speech_audio) > 0:
            self.ui.update(status="transcribing")
            self._transcription_queue.put(speech_audio)

    def _process_ptt(self, frame: np.ndarray, ptt_frames: list[np.ndarray]):
        if self.ptt_active:
            ptt_frames.append(frame)
        elif ptt_frames:
            audio = np.concatenate(ptt_frames)
            ptt_frames.clear()
            if len(audio) > 0:
                self.ui.update(status="transcribing")
                self._transcription_queue.put(audio)

    def _handle_key(self, key: str, ptt_frames: list[np.ndarray]):
        if key == "q":
            self.running = False
        elif key == "\n" or key == "\r":
            self._send_buffer()
        elif key == "c":
            self.buffer = ""
            self.ui.update(buffer="")
        elif key == " " and self.config.general.mode == "ptt":
            self.ptt_active = not self.ptt_active
            if self.ptt_active:
                ptt_frames.clear()
                self.ui.update(status="recording", ptt_active=True)
            else:
                self.ui.update(ptt_active=False)

    def _transcription_worker(self):
        while self.running:
            try:
                audio = self._transcription_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                result = self.transcriber.transcribe(audio, self.config.general.language)
                if result.text:
                    self._result_queue.put(result)
            except Exception:
                pass
            finally:
                self.ui.update(status="listening")

    def _check_results(self):
        try:
            result = self._result_queue.get_nowait()
        except queue.Empty:
            return

        self.ui.update(detected_language=result.language)

        parsed = parse_transcription(
            result.text,
            prefix=self.config.commands.prefix,
            enabled=self.config.commands.enabled,
        )

        if parsed.is_command:
            self._handle_command(parsed.command)
        else:
            self.buffer += (" " if self.buffer else "") + parsed.text
            self.ui.update(buffer=self.buffer, status="listening")

            if self.config.general.auto_send:
                self._send_buffer()

    def _handle_command(self, command: CommandType | None):
        if command == CommandType.CANCEL:
            self.buffer = ""
            self.ui.update(buffer="", status="listening")
        elif command == CommandType.SEND:
            self._send_buffer()
        elif command == CommandType.PAUSE:
            self.paused = True
            self.vad.reset()
            self.ui.update(status="paused")
        elif command == CommandType.RESUME:
            self.paused = False
            self.ui.update(status="listening")

    def _send_buffer(self):
        text = self.buffer.strip()
        if not text:
            return

        try:
            self.bridge.send_text(text)
            self.ui.update(last_sent=text, buffer="", status="listening")
        except Exception as e:
            self.ui.print_message(f"[red]Send failed: {e}[/]")

        self.buffer = ""



def _launch_tmux_session(command: str) -> None:
    """Launch a tmux session with the given command and VoxCode side by side."""
    import shutil
    import subprocess

    if not shutil.which("tmux"):
        print("Error: tmux is not installed.")
        sys.exit(1)

    session = "voxcode"

    # If session already exists, just attach
    result = subprocess.run(["tmux", "has-session", "-t", session], capture_output=True)
    if result.returncode == 0:
        print(f"Session '{session}' already exists. Attaching...")
        subprocess.run(["tmux", "attach-session", "-t", session])
        return

    # Resolve the full path to voxcode so it works from any directory
    voxcode_bin = shutil.which("voxcode")
    if voxcode_bin:
        voxcode_cmd = voxcode_bin
    else:
        voxcode_cmd = "uv run voxcode"

    # Create session with the user command in the first pane
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session],
        check=True,
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", f"{session}:0.0", command, "Enter"],
        check=True,
    )

    # Split and start voxcode in the second pane
    subprocess.run(
        ["tmux", "split-window", "-h", "-t", f"{session}:0"],
        check=True,
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", f"{session}:0.1", voxcode_cmd, "Enter"],
        check=True,
    )

    # Focus the voxcode pane
    subprocess.run(
        ["tmux", "select-pane", "-t", f"{session}:0.1"],
        check=True,
    )

    # Attach
    subprocess.run(["tmux", "attach-session", "-t", session])

def _launch_zellij_session(command: str) -> None:
    """Launch a Zellij session with the given command and VoxCode side by side."""
    import os
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("zellij"):
        print("Error: zellij is not installed.")
        sys.exit(1)

    session = "voxcode"

    # Check if session already exists
    result = subprocess.run(["zellij", "list-sessions"], capture_output=True, text=True)
    if result.returncode == 0 and session in result.stdout:
        print(f"Session '{session}' already exists. Attaching...")
        subprocess.run(["zellij", "attach", session])
        return

    # Resolve the full path to voxcode
    voxcode_bin = shutil.which("voxcode")
    voxcode_cmd = voxcode_bin if voxcode_bin else "uv run voxcode"

    # Create a temporary KDL layout file
    layout = (
        'layout {\n'
        '    pane split_direction="vertical" {\n'
        f'        pane command="bash" {{\n'
        f'            args "-c" "{command}"\n'
        '        }\n'
        f'        pane command="bash" {{\n'
        f'            args "-c" "{voxcode_cmd}"\n'
        '            focus true\n'
        '        }\n'
        '    }\n'
        '}\n'
    )

    fd, layout_path = tempfile.mkstemp(suffix=".kdl", prefix="voxcode-layout-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(layout)
        subprocess.run(["zellij", "--session", session, "--layout", layout_path])
    finally:
        os.unlink(layout_path)


def main():
    parser = argparse.ArgumentParser(description="VoxCode - Voice input for Claude Code")
    parser.add_argument("--config", "-c", help="Path to config.toml file")
    parser.add_argument("--mode", choices=["vad", "ptt"], help="Input mode override")
    parser.add_argument("--model", help="Whisper model size override")
    parser.add_argument("--device", choices=["cuda", "cpu"], help="Compute device override")
    parser.add_argument("--audio-device", type=int, help="Audio input device index (see --list-devices)")
    parser.add_argument("--language", help="Language override (auto, it, en)")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    parser.add_argument(
        "--launch", nargs="?", const="", default=None, metavar="COMMAND",
        help="Launch a tmux/Zellij session with COMMAND in one pane and VoxCode in the other "
             "(default command: claude, configurable in config.toml [multiplexer] launch_command)",
    )
    parser.add_argument(
        "--backend", choices=["auto", "tmux", "zellij"],
        help="Terminal multiplexer backend (default: auto-detect)",
    )
    args = parser.parse_args()

    if args.list_devices:
        print(AudioCapture.list_devices())
        return

    config = load_config(args.config)

    if args.backend:
        config.multiplexer.backend = args.backend

    if args.launch is not None:
        command = args.launch if args.launch else config.multiplexer.launch_command
        # Backward compat: fall back to [tmux] launch_command if [multiplexer] is default
        if not command:
            command = config.tmux.launch_command or "claude"

        backend = config.multiplexer.backend
        if backend == "auto":
            import os
            if os.environ.get("ZELLIJ") or os.environ.get("ZELLIJ_SESSION_NAME"):
                backend = "zellij"
            else:
                backend = "tmux"

        if backend == "zellij":
            _launch_zellij_session(command)
        else:
            _launch_tmux_session(command)
        return

    if args.mode:
        config.general.mode = args.mode
    if args.model:
        config.whisper.model = args.model
    if args.device:
        config.whisper.device = args.device
    if args.audio_device is not None:
        config.audio.device = args.audio_device
    if args.language:
        config.general.language = args.language

    app = VoxCode(config)
    app.run()
