"""stitch — assemble per-line clips into one episode track (ARCHITECTURE.md).

v1 is deliberately the simplest thing that produces a listenable episode:
concatenate the line clips in script order, separated by a short silence so
speech does not run together. Phase 2 replaces this with a timeline `mix/`
(ducking, fades, cue placement) behind the same call site — stitch stays pure
and audio-library-free (stdlib `wave` only).
"""

from __future__ import annotations

from myAIstory.tts.base import Clip

DEFAULT_GAP_MS = 350  # silence between lines, for natural pacing


def silence(rate: int, ms: int, *, sample_width: int = 2, channels: int = 1) -> bytes:
    n_frames = int(rate * ms / 1000)
    return b"\x00" * (n_frames * sample_width * channels)


def stitch(clips: list[Clip], *, gap_ms: int = DEFAULT_GAP_MS) -> Clip:
    """Concatenate clips in order, inserting `gap_ms` of silence between them.

    All clips must share one PCM format (a single backend yields one rate);
    a mismatch is a programming error, raised rather than silently resampled.
    """
    if not clips:
        raise ValueError("stitch requires at least one clip")

    rate, width, channels = clips[0].format
    for c in clips:
        if c.format != (rate, width, channels):
            raise ValueError(
                f"cannot stitch clips with mismatched audio format: "
                f"{c.format} != {(rate, width, channels)}"
            )

    gap = silence(rate, gap_ms, sample_width=width, channels=channels)
    parts: list[bytes] = []
    for i, c in enumerate(clips):
        if i:
            parts.append(gap)
        parts.append(c.frames)

    return Clip(frames=b"".join(parts), sample_rate=rate,
                sample_width=width, channels=channels)
