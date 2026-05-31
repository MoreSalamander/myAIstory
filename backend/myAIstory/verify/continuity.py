"""continuity_verify — the first blocking episode gate (SPEC §3).

Pure-Python. Rejects an episode draft that contradicts the bible: an
unresolvable speaker, a dead character speaking, or a complete drift off the
established theme. This is the gate that makes "episode 7 still remembers
episode 1" a system property rather than a hope.
"""

from __future__ import annotations

from myAIstory.schemas.models import Bible, Episode
from myAIstory.verify.resolve import (
    NARRATOR,
    resolve_speaker,
    speaker_index,
    theme_markers,
)
from myAIstory.verify.result import VerifyResult, parse


def verify_continuity(raw: object, bible: Bible) -> VerifyResult:
    """Validate an episode draft against the bible's canon."""
    result = VerifyResult(gate="continuity_verify")

    result.add_check("schema")
    episode, viols = parse(Episode, raw)
    if episode is None:
        result.violations.extend(viols)
        return result

    index = speaker_index(bible)

    # Every speech speaker resolves to the narrator or a canon character, and a
    # character whose status is "dead" may not be speaking (a clear contradiction
    # of established canon). Narration/mention of the dead is allowed.
    result.add_check("speakers_resolve")
    result.add_check("no_dead_speaker")
    for i, line in enumerate(episode.lines):
        if not line.is_speech:
            continue
        kind, char = resolve_speaker(line.speaker, index)
        if kind is None:
            result.fail(
                "unresolved_speaker",
                f"line {i} speaker {line.speaker!r} is neither {NARRATOR!r} "
                "nor a canon character/alias",
                field=f"lines.{i}.speaker",
            )
            continue
        if kind == "character" and char is not None and char.status == "dead":
            result.fail(
                "dead_character_speaking",
                f"line {i}: {char.name!r} speaks but is marked dead in the bible",
                field=f"lines.{i}.speaker",
            )

    # Theme has not drifted: a known theme must leave at least one marker in the
    # episode text. Free-text themes skip this (deterministic, keyword-fenced).
    markers = theme_markers(bible.theme)
    if markers:
        result.add_check("theme_marker_present")
        haystack = " ".join(
            (line.text or "") for line in episode.lines if line.is_speech
        ).lower()
        if not any(m in haystack for m in markers):
            result.fail(
                "theme_drift",
                f"episode contains no marker of theme {bible.theme!r} "
                f"(expected one of: {', '.join(markers)})",
                field="lines",
            )

    return result
