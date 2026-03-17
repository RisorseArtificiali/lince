"""Audio conversion utilities for Telegram voice messages.

Converts OGG/Opus voice messages from Telegram to numpy arrays
compatible with VoxCode's Whisper Transcriber (float32 @ 16kHz mono).
"""

from __future__ import annotations

import asyncio
import logging
import shutil

import numpy as np

logger = logging.getLogger(__name__)

# FFmpeg command path - cached after first check
_FFMPEG_AVAILABLE: bool | None = None
_FFMPEG_CMD = "ffmpeg"

# Whisper-specific audio format requirements
WHISPER_SAMPLE_RATE = 16000


class AudioConversionError(RuntimeError):
    """Raised when audio conversion fails."""

    pass


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system.

    Returns:
        True if ffmpeg is found, False otherwise
    """
    global _FFMPEG_AVAILABLE
    if _FFMPEG_AVAILABLE is not None:
        return _FFMPEG_AVAILABLE

    _FFMPEG_AVAILABLE = shutil.which(_FFMPEG_CMD) is not None
    if not _FFMPEG_AVAILABLE:
        logger.warning("ffmpeg not found - audio conversion unavailable")
    return _FFMPEG_AVAILABLE


async def ogg_to_numpy(
    ogg_bytes: bytes,
    sample_rate: int = WHISPER_SAMPLE_RATE,
    timeout: float = 30.0,
) -> np.ndarray:
    """Convert OGG/Opus bytes to float32 numpy array at target sample rate.

    Uses ffmpeg subprocess to decode OGG/Opus and resample to the required
    format for Whisper transcription (float32 @ 16kHz mono).

    Args:
        ogg_bytes: Raw OGG/Opus audio data from Telegram voice message
        sample_rate: Target sample rate in Hz (default: 16000 for Whisper)
        timeout: Maximum seconds to wait for ffmpeg to complete

    Returns:
        Float32 numpy array with normalized audio values in range [-1.0, 1.0]
        Shape: (num_samples,)

    Raises:
        AudioConversionError: If ffmpeg is not available or conversion fails
        ValueError: If input is empty or invalid

    Example:
        >>> voice = await update.message.voice.get_file()
        >>> ogg_bytes = await voice.download_as_bytearray()
        >>> audio = await ogg_to_numpy(ogg_bytes)
        >>> # audio is now ready for Transcriber.transcribe()
    """
    # Check for empty input
    if not ogg_bytes:
        raise ValueError("Empty audio data - cannot convert")

    # Check ffmpeg availability
    if not check_ffmpeg_available():
        raise AudioConversionError(
            "ffmpeg is not installed. "
            "Install with: sudo apt install ffmpeg  # Debian/Ubuntu"
        )

    # Build ffmpeg command for OGG/Opus -> float32 PCM conversion
    # -i pipe:0          - read from stdin
    # -f f32le           - output format: raw float32 little-endian
    # -acodec pcm_f32le  - audio codec: PCM 32-bit float little-endian
    # -ar 16000          - sample rate: 16kHz (Whisper requirement)
    # -ac 1              - audio channels: 1 (mono)
    # pipe:1             - write to stdout
    proc = await asyncio.create_subprocess_exec(
        _FFMPEG_CMD,
        "-i",
        "pipe:0",
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        # Send OGG data to ffmpeg, read PCM output
        stdout = await asyncio.wait_for(
            proc.communicate(input=ogg_bytes),
            timeout=timeout,
        )
        stdout = stdout[0]  # unpack tuple (stdout, stderr)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise AudioConversionError(f"ffmpeg conversion timed out after {timeout}s")

    # Check for errors
    if proc.returncode != 0:
        raise AudioConversionError(
            f"ffmpeg failed with exit code {proc.returncode} "
            f"(input may be corrupt or invalid format)"
        )

    # No output - this shouldn't happen with valid input
    if not stdout:
        raise AudioConversionError("ffmpeg produced no output - input may be corrupted")

    # Convert raw bytes to numpy array (float32 little-endian)
    try:
        audio = np.frombuffer(stdout, dtype=np.float32)
    except ValueError as e:
        raise AudioConversionError(f"Failed to decode ffmpeg output: {e}")

    # Validate output format
    if audio.size == 0:
        raise AudioConversionError("Converted audio is empty")

    # Check for NaN or Inf (corrupted data)
    if not np.all(np.isfinite(audio)):
        raise AudioConversionError("Converted audio contains NaN or Inf values")

    # Verify value range (float32 audio should be in [-1.0, 1.0])
    max_val = np.abs(audio).max()
    if max_val > 1.0:
        logger.warning(f"Audio values exceed [-1.0, 1.0] range (max: {max_val:.2f})")

    return audio


def ogg_to_numpy_sync(
    ogg_bytes: bytes,
    sample_rate: int = WHISPER_SAMPLE_RATE,
) -> np.ndarray:
    """Synchronous wrapper for ogg_to_numpy.

    Useful for testing or non-async contexts. Creates a new event loop
    if one doesn't exist.

    Args:
        ogg_bytes: Raw OGG/Opus audio data
        sample_rate: Target sample rate in Hz

    Returns:
        Float32 numpy array with normalized audio

    Raises:
        AudioConversionError: If conversion fails
        ValueError: If input is empty or invalid
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        ogg_to_numpy(ogg_bytes, sample_rate=sample_rate)
    )


__all__ = [
    "ogg_to_numpy",
    "ogg_to_numpy_sync",
    "AudioConversionError",
    "check_ffmpeg_available",
    "WHISPER_SAMPLE_RATE",
]
