"""voice_assign — deterministic casting (SPEC §4).

Pure logic, no audio. Runs in phase 2 already (it doesn't need a TTS engine —
only a list of voice ids) so that speaker_verify can gate episodes before phase
3 wires in real voices. The DEFAULT_VOICE_POOL is a placeholder registry that
phase 3 replaces with the active TTS backend's real voices.

Casting is deterministic: a stable hash of the character name picks the voice,
so re-running a series yields the same cast (SPEC §4 "Voice policy").
"""

from __future__ import annotations

import hashlib

from myAIstory.schemas.models import Bible, VoiceMap

# Placeholder until a TTS backend declares its real voices (phase 3).
DEFAULT_NARRATOR_VOICE = "narrator"
DEFAULT_VOICE_POOL = [f"voice_{i:02d}" for i in range(8)]


def _stable_index(name: str, modulo: int) -> int:
    digest = hashlib.md5(name.strip().lower().encode("utf-8")).hexdigest()
    return int(digest, 16) % modulo


def assign_voices(
    bible: Bible,
    voices: list[str] | None = None,
    narrator_voice: str | None = None,
) -> VoiceMap:
    """Cast every canon character to a voice, deterministically."""
    pool = list(voices) if voices else list(DEFAULT_VOICE_POOL)
    narrator = narrator_voice or DEFAULT_NARRATOR_VOICE

    # Reserve the narrator's voice from the character pool when possible, so the
    # narrator sounds distinct from the cast.
    char_pool = [v for v in pool if v != narrator] or pool

    by_character: dict[str, str] = {}
    for c in bible.characters:
        if c.voice and c.voice in pool:
            by_character[c.name] = c.voice            # honor an explicit choice
        else:
            idx = _stable_index(c.name, len(char_pool))
            by_character[c.name] = char_pool[idx]      # deterministic assignment

    return VoiceMap(narrator=narrator, by_character=by_character)
