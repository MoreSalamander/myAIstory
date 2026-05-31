"""A scripted TTS backend for tests and offline runs.

Renders deterministic *silent* clips whose length is proportional to the word
count, so the per-line render loop and the stitch concatenation can be
exercised with no audio engine installed. This is the audio-side counterpart
to synth/scripted.py's ScriptedLLM: the unreliable, heavyweight component is
replaced by something fast and predictable, leaving the orchestration under
test.
"""

from __future__ import annotations

from myAIstory.tts.base import Clip, Voice

# Mirrors voice.py's placeholder pool plus a dedicated narrator id, so the
# default casting policy resolves against this registry with no overrides.
DEFAULT_VOICE_IDS = ["narrator"] + [f"voice_{i:02d}" for i in range(8)]


class ScriptedTTS:
    """Yields silent PCM clips sized by word count; records every call.

    `words_per_second` controls the synthetic duration so stitched length is
    deterministic and assertable. `calls` is the (voice, text) audit trail, the
    same shape ScriptedLLM exposes.
    """

    def __init__(
        self,
        voice_ids: list[str] | None = None,
        *,
        sample_rate: int = 22050,
        words_per_second: float = 2.5,
    ) -> None:
        ids = voice_ids or DEFAULT_VOICE_IDS
        self._voices = [Voice(id=v, label=v.replace("_", " ").title()) for v in ids]
        self.sample_rate = sample_rate
        self.words_per_second = words_per_second
        self.calls: list[tuple[str, str]] = []

    def voices(self) -> list[Voice]:
        return list(self._voices)

    def synth(self, *, text: str, voice: str) -> Clip:
        self.calls.append((voice, text))
        words = max(1, len((text or "").split()))
        seconds = words / self.words_per_second
        n_frames = int(self.sample_rate * seconds)
        frames = b"\x00\x00" * n_frames  # 16-bit mono silence
        return Clip(frames=frames, sample_rate=self.sample_rate)
