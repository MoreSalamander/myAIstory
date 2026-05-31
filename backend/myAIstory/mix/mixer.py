"""Timeline mixer — replaces v1's plain stitch when cues are present (SPEC §4b).

Mix policy (deterministic):
- speech is the reference track; a cue's `gain_db` is relative to it.
- one-shot `sfx` are placed at their cue line's position in the timeline.
- `under` beds (ambience/music) loop to fill their span, fade in/out at the
  span boundaries, and take an additional fixed attenuation (ducking) so they
  sit beneath the narration rather than competing with it.

Pure numpy + stdlib. The mixer never drafts or verifies — by the time it runs,
the script has passed every blocking gate and the cues have been resolved
against the SoundLibrary.
"""

from __future__ import annotations

import numpy as np

from myAIstory.schemas.models import Episode
from myAIstory.sound.cue import CuePlan
from myAIstory.sound.library import SoundLibrary
from myAIstory.tts.base import Clip
from myAIstory.tts.stitch import DEFAULT_GAP_MS

DUCK_DB = -8.0      # extra attenuation applied to `under` beds beneath speech
FADE_MS = 400.0     # bed fade in/out at span boundaries


def _db_to_gain(db: float) -> float:
    return float(10 ** (db / 20))


def _to_float(clip: Clip) -> np.ndarray:
    return np.frombuffer(clip.frames, dtype="<i2").astype(np.float64) / 32768.0


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(x) == 0:
        return x
    n = int(round(len(x) * dst / src))
    return np.interp(np.linspace(0, len(x), n, endpoint=False),
                     np.arange(len(x)), x)


def _loop_to(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) == 0:
        return np.zeros(n)
    reps = int(np.ceil(n / len(x)))
    return np.tile(x, reps)[:n]


def _fade(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
    k = min(int(sr * ms / 1000), len(x) // 2)
    if k <= 0:
        return x
    env = np.ones(len(x))
    env[:k] = np.linspace(0, 1, k)
    env[-k:] = np.linspace(1, 0, k)
    return x * env


def mix(
    episode: Episode,
    speech_clips: list[Clip],
    plan: CuePlan,
    library: SoundLibrary,
    *,
    sample_rate: int,
    gap_ms: int = DEFAULT_GAP_MS,
    duck_db: float = DUCK_DB,
    fade_ms: float = FADE_MS,
) -> Clip:
    """Render the speech+cue timeline to one Clip."""
    sr = sample_rate
    gap = int(sr * gap_ms / 1000)

    # 1. Lay speech on the timeline, recording the frame offset reached at each
    #    line index (the anchor a cue at that index attaches to).
    speech = iter(speech_clips)
    segments: list[tuple[int, np.ndarray]] = []
    anchor: dict[int, int] = {}
    cursor = 0
    for i, line in enumerate(episode.lines):
        anchor[i] = cursor
        if line.is_speech:
            samples = _to_float(next(speech))
            segments.append((cursor, samples))
            cursor += len(samples) + gap
    total = max(cursor - gap, 1)  # drop the trailing gap

    buf = np.zeros(total, dtype=np.float64)
    for off, samples in segments:
        end = min(off + len(samples), total)
        buf[off:end] += samples[: end - off]

    # 2. Group placements: one-shot sfx vs per-kind bed chains.
    placements = sorted(plan.placements, key=lambda p: p.idx)
    bed_starts: dict[str, list[tuple[int, object, bool]]] = {}
    for p in placements:
        start = anchor.get(p.idx, total)
        if p.asset.loop:
            bed_starts.setdefault(p.asset.kind, []).append((start, p.asset, p.under))
        else:
            # one-shot: place at the cue's anchor, scaled by its gain.
            clip = library.load_clip(p.asset)
            s = _resample(_to_float(clip), clip.sample_rate, sr) * _db_to_gain(p.asset.gain_db)
            end = min(start + len(s), total)
            if end > start:
                buf[start:end] += s[: end - start]

    # 3. Beds: each runs until the next bed of the same kind, or to the end.
    for kind, starts in bed_starts.items():
        starts.sort(key=lambda t: t[0])
        for j, (start, asset, under) in enumerate(starts):
            end = starts[j + 1][0] if j + 1 < len(starts) else total
            span = end - start
            if span <= 0:
                continue
            clip = library.load_clip(asset)
            base = _resample(_to_float(clip), clip.sample_rate, sr)
            bed = _loop_to(base, span)
            gain = _db_to_gain(asset.gain_db + (duck_db if under else 0.0))
            bed = _fade(bed, sr, fade_ms) * gain
            buf[start:end] += bed

    # 4. Guard against clipping, then back to int16.
    peak = float(np.max(np.abs(buf))) if buf.size else 0.0
    if peak > 1.0:
        buf /= peak
    pcm = (np.clip(buf, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    return Clip(frames=pcm, sample_rate=sr)
