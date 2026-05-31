"""tts_synth + stitch — the audio stages of pipeline B (ARCHITECTURE.md).

Runs only after an episode has passed every blocking gate, so by construction
every speech line is attributable and maps to a resolved voice (speaker_verify).
This stage therefore performs no verification — it renders. Cue lines are
ignored in v1 (the cue/under fields stay dormant until phase 2's mixer).
"""

from __future__ import annotations

from myAIstory.events import EventEmitter
from myAIstory.schemas.models import Episode, Line, VoiceMap
from myAIstory.tts.base import Clip, TTSEngine
from myAIstory.tts.stitch import DEFAULT_GAP_MS, stitch


def voice_for(line: Line, voice_map: VoiceMap) -> str:
    """Resolve a speech line to its voice id (narration → narrator)."""
    if line.kind == "dialogue" and line.speaker:
        return voice_map.by_character.get(line.speaker, voice_map.narrator)
    return voice_map.narrator


def render_episode(
    episode: Episode,
    voice_map: VoiceMap,
    engine: TTSEngine,
    emit: EventEmitter,
    *,
    gap_ms: int = DEFAULT_GAP_MS,
) -> Clip:
    """Render every speech line and stitch them into one episode clip."""
    emit.step_start("tts_synth")
    clips: list[Clip] = []
    for line in episode.lines:
        if not line.is_speech:
            continue  # cue lines: phase 2 mixer
        voice = voice_for(line, voice_map)
        clips.append(engine.synth(text=line.text or "", voice=voice))
        emit.tts_line(speaker=line.speaker or "narrator", voice=voice, idx=len(clips) - 1)
    emit.step_complete("tts_synth", summary=f"{len(clips)} line(s) rendered")

    emit.step_start("stitch")
    combined = stitch(clips, gap_ms=gap_ms)
    emit.step_complete("stitch", summary=f"{combined.duration:.1f}s")
    return combined
