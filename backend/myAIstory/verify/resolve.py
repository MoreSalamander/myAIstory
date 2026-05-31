"""Shared, pure helpers for resolving speakers against a bible.

Used by continuity_verify and speaker_verify so the two gates agree on what
"a known speaker" means. No LLM, no I/O.
"""

from __future__ import annotations

from myAIstory.schemas.models import Bible, CanonCharacter

NARRATOR = "narrator"


def speaker_index(bible: Bible) -> dict[str, CanonCharacter]:
    """Map every canon name and alias (lowercased) to its CanonCharacter."""
    index: dict[str, CanonCharacter] = {}
    for c in bible.characters:
        index[c.name.strip().lower()] = c
        for alias in c.aliases:
            key = alias.strip().lower()
            if key:
                index.setdefault(key, c)
    return index


def resolve_speaker(speaker: str | None, index: dict[str, CanonCharacter]):
    """Resolve a line's speaker.

    Returns:
        ("narrator", None)            if the speaker is the narrator,
        ("character", CanonCharacter) if it resolves to canon,
        (None, None)                  if it is unresolvable.
    """
    if speaker is None:
        return None, None
    key = speaker.strip().lower()
    if key == NARRATOR:
        return NARRATOR, None
    char = index.get(key)
    if char is not None:
        return "character", char
    return None, None


# Deterministic, keyword-fenced theme markers (SPEC §3: "heuristic / keyword,
# deterministic — not an LLM"). If a theme is known here, an on-theme episode is
# expected to surface at least one of its markers somewhere in its text. Unknown
# (free-text) themes skip the marker check rather than false-reject.
THEME_MARKERS: dict[str, tuple[str, ...]] = {
    "dragons": ("dragon", "wyrm", "drake", "scale", "wing", "fire", "hoard", "talon"),
    "werewolves": ("wolf", "werewolf", "moon", "howl", "fur", "pack", "fang", "lycan"),
    "vampires": ("vampire", "blood", "fang", "coffin", "night", "immortal", "stake"),
    "space-opera": ("ship", "star", "void", "orbit", "fleet", "planet", "hyperspace"),
    "noir": ("rain", "shadow", "detective", "smoke", "alley", "gun", "dame", "case"),
}


def theme_markers(theme: str) -> tuple[str, ...]:
    """Return the marker keywords for a theme, or () if the theme is free-text."""
    return THEME_MARKERS.get(theme.strip().lower(), ())
