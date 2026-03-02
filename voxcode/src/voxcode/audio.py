"""Audio capture via sounddevice with automatic resampling."""

import queue

import numpy as np
import sounddevice as sd


class AudioCapture:
    """Captures audio from the microphone, resampling to target rate if needed."""

    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 30, device=None):
        self.target_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.device = device
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._native_rate: int = sample_rate
        self._resample_ratio: float = 1.0

    def _callback(self, indata, frames, time_info, status):
        mono = indata[:, 0].copy()
        if self._resample_ratio != 1.0:
            mono = self._resample(mono)
        self.audio_queue.put(mono)

    def _resample(self, audio: np.ndarray) -> np.ndarray:
        """Resample audio from native rate to target rate using linear interpolation."""
        target_len = int(len(audio) / self._resample_ratio)
        if target_len == len(audio):
            return audio
        indices = np.linspace(0, len(audio) - 1, target_len)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    def start(self):
        import ctypes
        import os

        # Determine native sample rate of the device
        device_info = sd.query_devices(self.device or sd.default.device[0], kind="input")
        self._native_rate = int(device_info["default_samplerate"])
        self._resample_ratio = self._native_rate / self.target_rate

        # Calculate block size at native rate to produce target frame duration
        native_block_size = int(self._native_rate * self.frame_duration_ms / 1000)

        # Suppress PortAudio stderr noise during sample rate probing
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        stderr_fd = os.dup(2)
        os.dup2(devnull_fd, 2)

        try:
            # Try target rate first (some devices/drivers support it)
            self._stream = sd.InputStream(
                samplerate=self.target_rate,
                channels=1,
                dtype="float32",
                blocksize=int(self.target_rate * self.frame_duration_ms / 1000),
                callback=self._callback,
                device=self.device,
            )
            self._stream.start()
            self._resample_ratio = 1.0
            self._native_rate = self.target_rate
        except sd.PortAudioError:
            # Fall back to native rate with resampling
            self._stream = sd.InputStream(
                samplerate=self._native_rate,
                channels=1,
                dtype="float32",
                blocksize=native_block_size,
                callback=self._callback,
                device=self.device,
            )
            self._stream.start()
        finally:
            # Restore stderr
            os.dup2(stderr_fd, 2)
            os.close(stderr_fd)
            os.close(devnull_fd)

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def get_frame(self, timeout: float = 0.1) -> np.ndarray:
        return self.audio_queue.get(timeout=timeout)

    @property
    def effective_rate(self) -> int:
        return self._native_rate

    @property
    def resampling(self) -> bool:
        return self._resample_ratio != 1.0

    @staticmethod
    def get_level(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame**2)))

    @staticmethod
    def list_devices() -> str:
        return str(sd.query_devices())
