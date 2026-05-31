"""seed_validate — the first gate (SPEC §1).

Pure-Python. Checks the user's seed is well-formed before anything else runs.
Structural bounds (title length, episode/minute ranges, character count) are
enforced by the SeriesSeed model; this gate adds the cross-field semantics:
character-name uniqueness and voice-registry membership.
"""

from __future__ import annotations

from typing import Optional

from myAIstory.schemas.models import SeriesSeed
from myAIstory.verify.result import VerifyResult, parse


def verify_seed(
    raw: object,
    available_voices: Optional[set[str]] = None,
) -> VerifyResult:
    """Validate a series seed.

    Args:
        raw: a dict (from the web form) or a SeriesSeed instance.
        available_voices: the set of voice ids the active TTS backend offers.
            If None, the voice-registry check is skipped (no backend wired yet
            in phase 1). If provided, every seed-specified voice must exist.
    """
    result = VerifyResult(gate="seed_validate")

    result.add_check("schema")
    seed, viols = parse(SeriesSeed, raw)
    if seed is None:
        result.violations.extend(viols)
        return result

    # Character-name uniqueness, case-insensitive (SPEC §1).
    result.add_check("unique_character_names")
    seen: dict[str, str] = {}
    for c in seed.characters:
        key = c.name.strip().lower()
        if key in seen:
            result.fail(
                "duplicate_character_name",
                f"character name {c.name!r} duplicates {seen[key]!r} "
                "(names must be unique, case-insensitively)",
                field="characters",
            )
        else:
            seen[key] = c.name

    # Voice-registry membership (only when a backend has declared its voices).
    if available_voices is not None:
        result.add_check("voice_registry")
        for c in seed.characters:
            if c.voice and c.voice not in available_voices:
                result.fail(
                    "unknown_voice",
                    f"character {c.name!r} requests voice {c.voice!r}, "
                    "which is not in the available-voices registry",
                    field="characters",
                )

    return result
