#!/usr/bin/env python3
"""Interactive test: microphone → VAD → Whisper transcription.

No tmux required. Run this to validate your audio pipeline works.

Usage:
    uv run python test_interactive.py              # Full test (VAD + transcription)
    uv run python test_interactive.py --ptt        # Push-to-talk mode (Enter to toggle)
    uv run python test_interactive.py --devices    # List audio devices
    uv run python test_interactive.py --model small --device cpu  # Lighter model
"""

import argparse
import queue
import sys
import threading
import time

import numpy as np

from voxcode.audio import AudioCapture
from voxcode.commands import parse_transcription
from voxcode.transcriber import Transcriber
from voxcode.vad import EnergyVAD, VADState

# ANSI escape codes
CLEAR_LINE = "\033[2K\r"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def bar(level: float, width: int = 35) -> str:
    filled = int(level * width)
    if level < 0.3:
        color = GREEN
    elif level < 0.7:
        color = YELLOW
    else:
        color = RED
    return f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"


def print_header():
    print(f"\n{BOLD}╭──────────────────────────────────────╮{RESET}")
    print(f"{BOLD}│     VoxCode Interactive Audio Test    │{RESET}")
    print(f"{BOLD}╰──────────────────────────────────────╯{RESET}\n")


def test_devices():
    from voxcode.audio import AudioCapture

    print_header()
    print(AudioCapture.list_devices())
    print()
    import sounddevice as sd

    info = sd.query_devices(kind="input")
    print(f"{GREEN}Default input:{RESET} {info['name']}")
    print(f"  Channels: {info['max_input_channels']}")
    print(f"  Sample rate: {info['default_samplerate']} Hz")


def test_vad_transcription(model_size: str, device: str, compute_type: str, language: str, audio_device: int | None = None):
    print_header()
    print(f"  Model: {BOLD}{model_size}{RESET} on {BOLD}{device}{RESET} ({compute_type})")
    print(f"  Language: {BOLD}{language}{RESET}")
    print(f"  Mode: {BOLD}VAD (continuous){RESET} — speak naturally, pauses trigger transcription")
    print()

    # Load model
    print(f"  {YELLOW}Loading Whisper model...{RESET}", end="", flush=True)
    transcriber = Transcriber(model_size=model_size, device=device, compute_type=compute_type)
    transcriber._ensure_model()
    print(f"{CLEAR_LINE}  {GREEN}Model loaded.{RESET}")

    # Start audio
    capture = AudioCapture(sample_rate=16000, device=audio_device)
    capture.start()
    print(f"  Capture: {capture.effective_rate}Hz {'→ 16kHz resampled' if capture.resampling else 'native'}")
    if audio_device is not None:
        print(f"  Device:  {BOLD}#{audio_device}{RESET}")
    print()
    print(f"  {BOLD}Speak now! Say 'comando: invia' to test voice commands.{RESET}")
    print(f"  {DIM}Press Ctrl+C to stop.{RESET}")
    print()

    vad = EnergyVAD(threshold=0.015, silence_duration=1.5, pre_roll=0.3)
    transcription_queue: queue.Queue[np.ndarray] = queue.Queue()
    segment_count = 0

    def transcription_worker():
        nonlocal segment_count
        while True:
            try:
                audio = transcription_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if audio is None:
                break

            duration = len(audio) / 16000
            sys.stdout.write(f"{CLEAR_LINE}  {YELLOW}Transcribing {duration:.1f}s of audio...{RESET}")
            sys.stdout.flush()

            t0 = time.time()
            result = transcriber.transcribe(audio, language)
            elapsed = time.time() - t0
            segment_count += 1

            if result.text:
                parsed = parse_transcription(result.text)
                if parsed.is_command:
                    sys.stdout.write(
                        f"{CLEAR_LINE}  {RED}[CMD]{RESET} {parsed.command.value} "
                        f"{DIM}({result.language}, {elapsed:.1f}s){RESET}\n"
                    )
                else:
                    sys.stdout.write(
                        f"{CLEAR_LINE}  {GREEN}[{segment_count}]{RESET} {result.text} "
                        f"{DIM}({result.language}, {elapsed:.1f}s){RESET}\n"
                    )
            else:
                sys.stdout.write(f"{CLEAR_LINE}  {DIM}[{segment_count}] (no speech detected){RESET}\n")
            sys.stdout.flush()

    worker = threading.Thread(target=transcription_worker, daemon=True)
    worker.start()

    try:
        while True:
            try:
                frame = capture.get_frame(timeout=0.1)
            except queue.Empty:
                continue

            level = AudioCapture.get_level(frame)
            display_level = min(level * 10, 1.0)

            state_changed, speech_audio = vad.process_frame(frame)

            if vad.state == VADState.SPEECH:
                status = f"{RED}● REC{RESET}"
            else:
                status = f"{GREEN}● listening{RESET}"

            sys.stdout.write(f"{CLEAR_LINE}  {status}  {bar(display_level)} {level:.4f}")
            sys.stdout.flush()

            if state_changed and speech_audio is not None and len(speech_audio) > 0:
                transcription_queue.put(speech_audio)

    except KeyboardInterrupt:
        pass

    transcription_queue.put(None)
    capture.stop()
    print(f"\n\n  {DIM}Transcribed {segment_count} segments.{RESET}\n")


def test_ptt_transcription(model_size: str, device: str, compute_type: str, language: str, audio_device: int | None = None):
    print_header()
    print(f"  Model: {BOLD}{model_size}{RESET} on {BOLD}{device}{RESET} ({compute_type})")
    print(f"  Mode: {BOLD}PTT (push-to-talk){RESET} — press Enter to start/stop recording")
    print()

    # Load model
    print(f"  {YELLOW}Loading Whisper model...{RESET}", end="", flush=True)
    transcriber = Transcriber(model_size=model_size, device=device, compute_type=compute_type)
    transcriber._ensure_model()
    print(f"{CLEAR_LINE}  {GREEN}Model loaded.{RESET}")

    capture = AudioCapture(sample_rate=16000, device=audio_device)
    capture.start()
    print(f"  Capture: {capture.effective_rate}Hz {'→ 16kHz resampled' if capture.resampling else 'native'}")
    if audio_device is not None:
        print(f"  Device:  {BOLD}#{audio_device}{RESET}")
    print()

    segment_count = 0

    try:
        while True:
            input(f"  {DIM}Press Enter to start recording (Ctrl+C to quit)...{RESET}")
            print(f"  {RED}● Recording... press Enter to stop{RESET}")

            frames = []
            recording = True

            def collect_audio():
                while recording:
                    try:
                        frame = capture.get_frame(timeout=0.1)
                        frames.append(frame)
                    except queue.Empty:
                        pass

            collector = threading.Thread(target=collect_audio, daemon=True)
            collector.start()

            input()
            recording = False
            collector.join(timeout=2.0)

            if not frames:
                print(f"  {DIM}No audio captured.{RESET}")
                continue

            audio = np.concatenate(frames)
            duration = len(audio) / 16000
            print(f"  {YELLOW}Transcribing {duration:.1f}s...{RESET}", end="", flush=True)

            t0 = time.time()
            result = transcriber.transcribe(audio, language)
            elapsed = time.time() - t0
            segment_count += 1

            if result.text:
                print(f"{CLEAR_LINE}  {GREEN}[{segment_count}]{RESET} {result.text} "
                      f"{DIM}({result.language}, {elapsed:.1f}s){RESET}")
            else:
                print(f"{CLEAR_LINE}  {DIM}[{segment_count}] (no speech detected){RESET}")
            print()

    except KeyboardInterrupt:
        pass

    capture.stop()
    print(f"\n  {DIM}Transcribed {segment_count} segments.{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="VoxCode interactive audio test")
    parser.add_argument("--devices", action="store_true", help="List audio devices and exit")
    parser.add_argument("--ptt", action="store_true", help="Push-to-talk mode (Enter to toggle)")
    parser.add_argument("--model", default="large-v3", help="Whisper model (default: large-v3)")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="Compute device")
    parser.add_argument("--compute-type", default="float16", help="Compute type (float16, int8)")
    parser.add_argument("--language", default="auto", help="Language (auto, it, en)")
    parser.add_argument("--audio-device", type=int, default=None, help="Audio input device index (see --devices)")
    args = parser.parse_args()

    if args.devices:
        test_devices()
        return

    if args.ptt:
        test_ptt_transcription(args.model, args.device, args.compute_type, args.language, args.audio_device)
    else:
        test_vad_transcription(args.model, args.device, args.compute_type, args.language, args.audio_device)


if __name__ == "__main__":
    main()
