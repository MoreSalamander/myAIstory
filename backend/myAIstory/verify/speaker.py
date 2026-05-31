"""speaker_verify — the third blocking episode gate (SPEC §3).

Pure-Python. The last gate before audio: every speech line must map to a
resolved TTS voice. An unattributable line must never reach the TTS stage —
there would be no voice to render it in.
"""

from __future__ import annotations

from typing import Optional

from myAIstory.schemas.models import Bible, Episode, VoiceMap
from myAIstory.verify.resolve import NARRATOR, resolve_speaker, speaker_index
from myAIstory.verify.result import VerifyResult, parse


def verify_speaker(
    raw: object,
    voice_map: VoiceMap,
    bible: Optional[Bible] = None,
) -> VerifyResult:
    """Validate that every speech line maps to a resolved voice.

    Args:
        raw: a dict (model draft) or an Episode instance.
        voice_map: the resolved narrator + per-character voice assignment.
        bible: optional; if given, aliases are resolved to canon names before
            the voice lookup, so an aliased speaker still validates.
    """
    result = VerifyResult(gate="speaker_verify")

    result.add_check("schema")
    episode, viols = parse(Episode, raw)
    if episode is None:
        result.violations.extend(viols)
        return result

    index = speaker_index(bible) if bible is not None else {}

    result.add_check("all_speech_lines_voiced")
    for i, line in enumerate(episode.lines):
        if not line.is_speech:
            continue

        speaker = line.speaker
        # Resolve aliases to canon names when a bible is available.
        if bible is not None:
            kind, char = resolve_speaker(speaker, index)
            if kind == NARRATOR:
                speaker = NARRATOR
            elif kind == "character" and char is not None:
                speaker = char.name

        if speaker is None:
            result.fail(
                "unvoiced_line",
                f"line {i} has no speaker to assign a voice to",
                field=f"lines.{i}.speaker",
            )
            continue

        if speaker.strip().lower() == NARRATOR:
            continue  # narrator always has a voice (VoiceMap.narrator)

        if speaker not in voice_map.by_character:
            result.fail(
                "no_voice_for_speaker",
                f"line {i} speaker {line.speaker!r} has no entry in the voice map",
                field=f"lines.{i}.speaker",
            )

    return result
