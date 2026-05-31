"""Pipeline B — episode generation (ARCHITECTURE.md).

    context_load → episode_draft → continuity_verify → structure_verify
       → speaker_verify → voice_assign → (tts/stitch: phase 3)
       → episode_persist → bible_update → done

Phase 2 runs everything except TTS/stitch (phase 3). voice_assign runs here
already so speaker_verify can gate the draft; the resulting VoiceMap is what
phase 3's TTS stage will consume.
"""

from __future__ import annotations

from typing import Optional

from myAIstory import store
from myAIstory.events import EventEmitter
from myAIstory.schemas.models import Bible, DEFAULT_MINUTES, Episode, WorldFact
from myAIstory.pipeline.audio import render_episode
from myAIstory.pipeline.retry import run_with_retry
from myAIstory.pipeline.voice import assign_voices
from myAIstory.synth.base import LLM
from myAIstory.synth.drafts import stream_collect
from myAIstory.synth.prompts import EPISODE_SYSTEM, build_episode_prompt
from myAIstory.tts.base import TTSEngine
from myAIstory.verify import verify_continuity, verify_speaker, verify_structure


def run_episode(
    series_id: str,
    number: int,
    llm: LLM,
    emit: EventEmitter,
    *,
    bible: Optional[Bible] = None,
    target_minutes: int = DEFAULT_MINUTES,
    voices: Optional[list[str]] = None,
    tts: Optional[TTSEngine] = None,
    persist: bool = True,
    max_retries: int = 2,
) -> Optional[Episode]:
    """Generate and verify one episode; returns the persisted Episode or None.

    When `tts` is provided, the verified episode is rendered to audio and (if
    persisting) written to audio/NN.wav. With no engine the pipeline stops at
    the verified script — exactly the phase-2 behavior.
    """
    if bible is None:
        bible = store.read_bible(series_id)

    emit.run_start("episode", series_id, number=number)

    # --- context_load --------------------------------------------------------
    emit.step_start("context_load")
    priors = store.prior_summaries(series_id, number) if persist else []
    # Cast against the active TTS backend's real voices when one is present,
    # else the placeholder pool (voice_assign is pure either way).
    pool = voices or ([v.id for v in tts.voices()] if tts is not None else None)
    voice_map = assign_voices(bible, pool)  # voice_assign (deterministic)
    emit.step_complete("context_load", summary=f"{len(priors)} prior episode(s)")

    # --- episode_draft → 3 gates (bounded retry) -----------------------------
    def produce(feedback):
        return stream_collect(
            llm, emit,
            stage="episode_draft",
            role="episode_draft",
            system=EPISODE_SYSTEM,
            prompt=build_episode_prompt(bible, number, priors, target_minutes, feedback),
        )

    gates = [
        lambda o: verify_continuity(o, bible),
        lambda o: verify_structure(o, number, target_minutes),
        lambda o: verify_speaker(o, voice_map, bible),
    ]
    obj, _ = run_with_retry(produce, gates, emit, stage="episode_verify",
                            max_retries=max_retries)
    if obj is None:
        emit.done("episode", "skipped", number=number,
                  reason="episode failed verification")
        return None

    obj["number"] = number  # pin to the requested index
    episode = Episode.model_validate(obj)

    # --- tts_synth → stitch (phase 3, only with an engine) -------------------
    clip = render_episode(episode, voice_map, tts, emit) if tts is not None else None

    # --- episode_persist -----------------------------------------------------
    if persist:
        emit.step_start("episode_persist")
        path = store.write_episode(series_id, episode)
        if clip is not None:
            store.write_audio(series_id, number, clip.to_wav())
        emit.step_complete("episode_persist", summary=str(path))

        # --- bible_update (verified): append new canon facts -----------------
        if episode.new_facts:
            emit.step_start("bible_update")
            for i, fact in enumerate(episode.new_facts):
                bible.world_facts.append(
                    WorldFact(id=f"e{number}_{i}", statement=fact,
                              established_in_episode=number)
                )
            store.write_bible(bible)  # re-persist; Bible model re-validates
            emit.step_complete("bible_update", summary=f"+{len(episode.new_facts)} fact(s)")

    emit.done("episode", "ok", number=number)
    return episode
