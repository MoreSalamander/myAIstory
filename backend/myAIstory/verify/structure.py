"""structure_verify — the second blocking episode gate (SPEC §3).

Pure-Python. Rejects an episode whose shape is wrong: misnumbered, missing a
required beat kind, the wrong length for its target runtime, or carrying empty
speech lines.
"""

from __future__ import annotations

from myAIstory.schemas.models import (
    BEAT_KINDS,
    DEFAULT_MINUTES,
    Episode,
    MIN_SPOKEN_WORDS,
    REQUIRED_BEATS,
    WPM_MAX,
    WPM_MIN,
)
from myAIstory.verify.result import VerifyResult, parse


def _word_count(text: str) -> int:
    return len(text.split())


def verify_structure(
    raw: object,
    expected_number: int,
    target_minutes: int = DEFAULT_MINUTES,
) -> VerifyResult:
    """Validate an episode's structure.

    Args:
        raw: a dict (model draft) or an Episode instance.
        expected_number: the episode index this draft is meant to be.
        target_minutes: the per-episode runtime target; sets the word band.
    """
    result = VerifyResult(gate="structure_verify")

    result.add_check("schema")
    episode, viols = parse(Episode, raw)
    if episode is None:
        result.violations.extend(viols)
        return result

    # Episode is the one we asked for.
    result.add_check("number_match")
    if episode.number != expected_number:
        result.fail(
            "episode_number_mismatch",
            f"episode number {episode.number} != expected {expected_number}",
            field="number",
        )

    # Required beat kinds all present (extra/optional kinds are allowed).
    result.add_check("required_beats_present")
    beats_lower = {b.strip().lower() for b in episode.beats}
    unknown = beats_lower - set(BEAT_KINDS)
    if unknown:
        result.fail(
            "unknown_beat_kind",
            f"unknown beat kind(s): {', '.join(sorted(unknown))} "
            f"(allowed: {', '.join(BEAT_KINDS)})",
            field="beats",
        )
    missing = [b for b in REQUIRED_BEATS if b not in beats_lower]
    if missing:
        result.fail(
            "missing_required_beat",
            f"missing required beat kind(s): {', '.join(missing)}",
            field="beats",
        )

    # Lines present and every speech line carries non-empty text.
    result.add_check("lines_nonempty")
    if not episode.lines:
        result.fail("no_lines", "episode has no lines", field="lines")
    for i, line in enumerate(episode.lines):
        if line.is_speech and not (line.text and line.text.strip()):
            result.fail(
                "empty_speech_text",
                f"line {i} is a {line.kind} line with empty text",
                field=f"lines.{i}.text",
            )

    # Spoken length within the (deliberately wide) band derived from
    # target_minutes. The floor is lenient — it only rejects genuine stubs,
    # not complete-but-short episodes (see models.py WPM_MIN rationale).
    result.add_check("word_count_band")
    spoken = sum(
        _word_count(line.text) for line in episode.lines if line.is_speech and line.text
    )
    low = max(MIN_SPOKEN_WORDS, target_minutes * WPM_MIN)
    high = target_minutes * WPM_MAX
    if spoken < low:
        result.fail(
            "too_short",
            f"{spoken} spoken words is below the {low}-word floor for "
            f"{target_minutes} min",
            field="lines",
        )
    elif spoken > high:
        result.fail(
            "too_long",
            f"{spoken} spoken words exceeds the {high}-word ceiling for "
            f"{target_minutes} min",
            field="lines",
        )

    return result
