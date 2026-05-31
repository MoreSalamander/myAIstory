"""tts_synth + cue_verify + stitch/mix — the audio stages of pipeline B.

Runs only after an episode has passed every blocking gate, so by construction
every speech line is attributable and maps to a resolved voice (speaker_verify).
This stage therefore performs no blocking verification — it renders.

Two modes, chosen by whether a SoundLibrary is supplied:
  - no library (v1): render speech lines, concatenate with `stitch`. Cue lines
    are ignored.
  - with a library (phase 2): additionally run cue_verify (the non-blocking
    gate) — resolved cues emit `cue_place`, unresolved ones emit `cue_drop` and
    are dropped — then `mix` the surviving cues under the speech timeline.
"""

from __future__ import annotations

from typing import Optional

from myAIstory.events import EventEmitter
from myAIstory.mix.mixer import mix
from myAIstory.schemas.models import Episode, Line, VoiceMap
from myAIstory.sound.cue import resolve_cues
from myAIstory.sound.library import SoundLibrary
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
    library: Optional[SoundLibrary] = None,
    gap_ms: int = DEFAULT_GAP_MS,
) -> Clip:
    """Render every speech line, then stitch (v1) or mix with cues (phase 2)."""
    emit.step_start("tts_synth")
    clips: list[Clip] = []
    for line in episode.lines:
        if not line.is_speech:
            continue  # cue lines handled in the mix stage
        voice = voice_for(line, voice_map)
        clips.append(engine.synth(text=line.text or "", voice=voice))
        emit.tts_line(speaker=line.speaker or "narrator", voice=voice, idx=len(clips) - 1)
    emit.step_complete("tts_synth", summary=f"{len(clips)} line(s) rendered")

    # --- cue_verify (non-blocking) + mix, only with a library ----------------
    if library is not None:
        emit.step_start("cue_verify")
        plan = resolve_cues(episode, library)
        for p in plan.placements:
            emit.cue_place(kind=p.asset.kind, cue=p.asset.tag, idx=p.idx, under=p.under)
        for d in plan.drops:
            emit.cue_drop(kind=d.kind, cue=d.cue or "", idx=d.idx)
        emit.step_complete(
            "cue_verify",
            summary=f"{len(plan.placements)} placed, {len(plan.drops)} dropped",
        )
        if plan.has_cues:
            emit.step_start("mix")
            combined = mix(episode, clips, plan, library,
                           sample_rate=clips[0].sample_rate, gap_ms=gap_ms)
            emit.step_complete("mix", summary=f"{combined.duration:.1f}s")
            return combined

    emit.step_start("stitch")
    combined = stitch(clips, gap_ms=gap_ms)
    emit.step_complete("stitch", summary=f"{combined.duration:.1f}s")
    return combined
