---
id: LINCE-19
title: Implement OGG/Opus to numpy audio conversion for Telegram voice
status: To Do
assignee: []
created_date: '2026-03-03 14:35'
labels:
  - telebridge
  - voice
  - audio
milestone: m-5
dependencies:
  - LINCE-3
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create the audio conversion utility needed to transform Telegram voice messages (OGG/Opus format) into numpy arrays compatible with VoxCode's Whisper Transcriber.

**Problem**: Telegram voice messages are encoded as OGG/Opus. VoxCode's `Transcriber.transcribe()` expects `np.ndarray` float32 at 16kHz mono. We need a conversion bridge.

**Approach — ffmpeg subprocess** (preferred, no extra Python deps):
```python
async def ogg_to_numpy(ogg_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
    """Convert OGG/Opus bytes to float32 numpy array at target sample rate."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", "pipe:0",
        "-f", "f32le",           # raw float32 little-endian output
        "-acodec", "pcm_f32le",
        "-ar", str(sample_rate),  # resample to 16kHz
        "-ac", "1",               # mono
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate(input=ogg_bytes)
    return np.frombuffer(stdout, dtype=np.float32)
```

**Alternative — pydub** (if ffmpeg not available, adds dependency):
```python
from pydub import AudioSegment
import io

def ogg_to_numpy_pydub(ogg_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
    audio = AudioSegment.from_ogg(io.BytesIO(ogg_bytes))
    audio = audio.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    return samples / 32768.0  # normalize int16 to float32
```

**Recommendation**: Use ffmpeg subprocess as primary (it's a standard Linux tool, already required by many audio tools). Add pydub as optional fallback documented in README.

**Location**: `telebridge/src/telebridge/audio_convert.py`

**Validation**:
- Output must be float32 in range [-1.0, 1.0]
- Sample rate must be exactly 16000 Hz
- Must be mono (single channel)
- Empty input should return empty array, not crash
- Corrupt OGG should raise clear error

**System dependency**: Document `ffmpeg` as a required system package in README and config.example.toml.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Converts OGG/Opus bytes to float32 numpy array
- [ ] #2 Output is 16kHz mono
- [ ] #3 Uses async ffmpeg subprocess (non-blocking)
- [ ] #4 Handles empty input gracefully
- [ ] #5 Handles corrupt OGG with clear error message
- [ ] #6 ffmpeg documented as system requirement
<!-- AC:END -->
