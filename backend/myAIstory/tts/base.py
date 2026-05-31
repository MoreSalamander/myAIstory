"""The text-to-speech interface (ARCHITECTURE.md `tts/`).

The pipeline depends only on this protocol, never on a concrete backend, so a
scripted fake can render the whole audio path in tests with no audio engine —
the same swap-the-backend discipline the synth/ layer uses for the LLM.

A backend declares its `voices()` registry (consumed by voice_assign) and
renders one speech line at a time via `synth()`. Audio is carried between
stages as a `Clip`: raw little-endian PCM frames plus the format needed to
write a WAV. Keeping a uniform in-memory representation is what lets `stitch`
concatenate clips from any backend without caring how they were produced.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Voice:
    """One entry in a backend's voice registry (SPEC §4 available-voices)."""

    id: str
    label: str
    sample: Optional[str] = None  # optional path/url to a preview clip


@dataclass(frozen=True)
class Clip:
    """A rendered mono PCM audio clip.

    `frames` is raw signed PCM (little-endian) at `sample_rate` Hz, with
    `sample_width` bytes per sample. This is exactly what stdlib `wave` writes,
    so no third-party audio library is needed for v1.
    """

    frames: bytes
    sample_rate: int
    sample_width: int = 2  # 16-bit
    channels: int = 1

    @property
    def format(self) -> tuple[int, int, int]:
        return (self.sample_rate, self.sample_width, self.channels)

    @property
    def n_frames(self) -> int:
        return len(self.frames) // (self.sample_width * self.channels)

    @property
    def duration(self) -> float:
        return self.n_frames / self.sample_rate if self.sample_rate else 0.0

    def to_wav(self) -> bytes:
        """Encode to a WAV byte string (what store.write_audio persists)."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(self.sample_width)
            w.setframerate(self.sample_rate)
            w.writeframes(self.frames)
        return buf.getvalue()


@runtime_checkable
class TTSEngine(Protocol):
    def voices(self) -> list[Voice]:
        """The backend's available voices (drives deterministic casting)."""
        ...

    def synth(self, *, text: str, voice: str) -> Clip:
        """Render one line of text in the given voice id to a PCM clip."""
        ...
