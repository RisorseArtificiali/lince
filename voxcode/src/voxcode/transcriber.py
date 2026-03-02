"""Whisper transcription wrapper using faster-whisper."""

from dataclasses import dataclass

import numpy as np


@dataclass
class TranscriptionResult:
    text: str
    language: str


class Transcriber:
    """Wraps faster-whisper with lazy model loading."""

    def __init__(self, model_size: str = "large-v3", device: str = "cuda", compute_type: str = "float16"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )

    def transcribe(self, audio: np.ndarray, language: str = "auto") -> TranscriptionResult:
        """Transcribe audio numpy array (float32, 16kHz mono) to text."""
        self._ensure_model()
        segments, info = self._model.transcribe(
            audio,
            language=language if language != "auto" else None,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments)
        return TranscriptionResult(text=text.strip(), language=info.language or "unknown")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
