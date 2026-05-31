"""Timeline mixing (phase 2): speech + resolved cues on one timeline.

Bolts onto the pipeline at the same call site as v1's plain `stitch`: when a
SoundLibrary is active and an episode carries resolved cues, `mix` places
one-shot sfx and ducks/fades looping beds beneath the speech. With no cues the
pipeline still uses the simple stitch — sound is purely additive.
"""

from myAIstory.mix.mixer import DUCK_DB, FADE_MS, mix

__all__ = ["mix", "DUCK_DB", "FADE_MS"]
