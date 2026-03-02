"""Voice Activity Detection using energy threshold."""

from collections import deque
from enum import Enum

import numpy as np


class VADState(Enum):
    SILENCE = "silence"
    SPEECH = "speech"


class EnergyVAD:
    """Simple energy-based VAD with pre-roll buffer for capturing speech onset."""

    def __init__(
        self,
        threshold: float = 0.015,
        silence_duration: float = 1.5,
        pre_roll: float = 0.3,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
    ):
        self.threshold = threshold
        frames_per_second = 1000 / frame_duration_ms
        self.silence_frames = int(silence_duration * frames_per_second)
        pre_roll_count = int(pre_roll * frames_per_second)

        self.state = VADState.SILENCE
        self.silence_count = 0
        self.speech_frames: list[np.ndarray] = []
        self.pre_roll: deque[np.ndarray] = deque(maxlen=max(pre_roll_count, 1))

    def process_frame(self, frame: np.ndarray) -> tuple[bool, np.ndarray | None]:
        """Process a single audio frame.

        Returns:
            (state_changed, speech_audio_or_none)
            - When speech ends: (True, concatenated_speech_audio)
            - When speech starts: (True, None)
            - No change: (False, None)
        """
        energy = float(np.sqrt(np.mean(frame**2)))

        if self.state == VADState.SILENCE:
            self.pre_roll.append(frame)
            if energy > self.threshold:
                self.state = VADState.SPEECH
                self.silence_count = 0
                self.speech_frames = list(self.pre_roll)
                self.pre_roll.clear()
                return True, None
            return False, None

        # SPEECH state
        self.speech_frames.append(frame)
        if energy > self.threshold:
            self.silence_count = 0
            return False, None

        self.silence_count += 1
        if self.silence_count >= self.silence_frames:
            self.state = VADState.SILENCE
            # Trim trailing silence frames from the speech audio
            trim_count = min(self.silence_count, len(self.speech_frames))
            speech = self.speech_frames[:-trim_count] if trim_count > 0 else self.speech_frames
            audio = np.concatenate(speech) if speech else np.array([], dtype=np.float32)
            self.speech_frames = []
            return True, audio

        return False, None

    def reset(self):
        self.state = VADState.SILENCE
        self.silence_count = 0
        self.speech_frames = []
        self.pre_roll.clear()
