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
from myAIstory.schemas.models import (
    Bible,
    CanonCharacter,
    DEFAULT_MINUTES,
    Episode,
    WorldFact,
)
from myAIstory.pipeline.audio import render_episode
from myAIstory.pipeline.retry import run_with_retry
from myAIstory.pipeline.speakers import augment_for_declared, salvage_speakers
from myAIstory.pipeline.voice import assign_voices
from myAIstory.synth.base import LLM
from myAIstory.synth.drafts import stream_collect
from myAIstory.synth.prompts import EPISODE_SYSTEM, build_episode_prompt
from myAIstory.sound.library import SoundLibrary
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
    library: Optional[SoundLibrary] = None,
    persist: bool = True,
    max_retries: int = 2,
) -> Optional[Episode]:
    """Generate and verify one episode; returns the persisted Episode or None.

    When `tts` is provided, the verified episode is rendered to audio and (if
    persisting) written to audio/NN.wav. With no engine the pipeline stops at
    the verified script — exactly the phase-2 behavior. When a `library` is also
    given, the model may emit sound cues; resolved cues are mixed under the
    speech (cue_verify is non-blocking — unresolved cues are dropped).
    """
    if bible is None:
        bible = store.read_bible(series_id)

    emit.run_start("episode", series_id, number=number)

    # --- context_load --------------------------------------------------------
    emit.step_start("context_load")
    priors = store.prior_summaries(series_id, number) if persist else []
    # Cast against the active TTS backend's real voices when one is present,
    # else the placeholder pool (voice_assign is pure either way). A real
    # backend has no voice literally named "narrator", so pin the narrator to a
    # concrete registry id rather than the placeholder default.
    pool = voices or ([v.id for v in tts.voices()] if tts is not None else None)
    narrator_voice = None
    if pool:
        narrator_voice = "narrator" if "narrator" in pool else pool[0]
    voice_map = assign_voices(bible, pool, narrator_voice)  # voice_assign
    emit.step_complete("context_load", summary=f"{len(priors)} prior episode(s)")

    # --- episode_draft → 3 gates (bounded retry) -----------------------------
    cue_tags = library.tags if library is not None else None

    def produce(feedback):
        return stream_collect(
            llm, emit,
            stage="episode_draft",
            role="episode_draft",
            system=EPISODE_SYSTEM,
            prompt=build_episode_prompt(bible, number, priors, target_minutes,
                                        feedback, cue_tags=cue_tags),
        )

    # speaker_salvage (pre-gate, deterministic): demote any undeclared, unknown
    # speaker to the narrator so the strict gates judge a sound draft instead of
    # skipping the whole episode over an invented incidental voice. Declared
    # newcomers are NOT demoted — an augmented bible/voice-map view lets the
    # gates accept them as a legitimate same-episode introduction, without
    # touching the persistent canon (that stays bible_update's sole job).
    def repair(o):
        salvage_speakers(o, bible, emit)

    def gate_continuity(o):
        view_bible, _ = augment_for_declared(o, bible, voice_map, pool, narrator_voice)
        return verify_continuity(o, view_bible)

    def gate_speaker(o):
        view_bible, view_map = augment_for_declared(o, bible, voice_map, pool,
                                                    narrator_voice)
        return verify_speaker(o, view_map, view_bible)

    gates = [
        gate_continuity,
        lambda o: verify_structure(o, number, target_minutes),
        gate_speaker,
    ]
    obj, _ = run_with_retry(produce, gates, emit, stage="episode_verify",
                            max_retries=max_retries, repair=repair)
    if obj is None:
        emit.done("episode", "skipped", number=number,
                  reason="episode failed verification")
        return None

    obj["number"] = number  # pin to the requested index
    episode = Episode.model_validate(obj)

    # --- tts_synth → cue_verify → stitch/mix (only with an engine) -----------
    # Render against a voice map that includes any declared newcomers, so a
    # legitimately-introduced character has a voice for this very episode.
    _, render_map = augment_for_declared(obj, bible, voice_map, pool, narrator_voice)
    clip = (render_episode(episode, render_map, tts, emit, library=library)
            if tts is not None else None)

    # --- episode_persist -----------------------------------------------------
    if persist:
        emit.step_start("episode_persist")
        path = store.write_episode(series_id, episode)
        if clip is not None:
            store.write_audio(series_id, number, clip.to_wav())
        emit.step_complete("episode_persist", summary=str(path))

        # --- bible_update (verified): grow canon from this episode -----------
        # The ONLY path by which prose-proposed canon enters the source of
        # truth. New world facts are appended; newly-introduced characters are
        # validated and promoted to CanonCharacter (so LATER episodes may
        # legally name them — closing the gap that made the cast unable to grow
        # with the story); deaths flip status (only this stage may). The draft
        # never writes canon directly — it proposes, this stage decides.
        if episode.new_facts or episode.new_characters or episode.deaths:
            emit.step_start("bible_update")
            known = {c.name.strip().lower() for c in bible.characters}
            known |= {a.strip().lower() for c in bible.characters for a in c.aliases}

            for i, fact in enumerate(episode.new_facts):
                bible.world_facts.append(
                    WorldFact(id=f"e{number}_{i}", statement=fact,
                              established_in_episode=number)
                )

            added: list[str] = []
            for nc in episode.new_characters:
                name = nc.name.strip()
                if not name or name.lower() in known:
                    continue  # empty or collides with existing canon/alias → skip
                bible.characters.append(
                    CanonCharacter(name=name, role=nc.role, status=nc.status)
                )
                known.add(name.lower())
                added.append(name)

            by_name = {c.name.strip().lower(): c for c in bible.characters}
            died: list[str] = []
            for dn in episode.deaths:
                c = by_name.get(dn.strip().lower())
                if c is not None and c.status != "dead":
                    c.status = "dead"
                    died.append(c.name)

            store.write_bible(bible)  # re-persist; Bible model re-validates
            parts = [f"+{len(episode.new_facts)} fact(s)"]
            if added:
                parts.append(f"+{len(added)} character(s): {', '.join(added)}")
            if died:
                parts.append(f"{len(died)} death(s): {', '.join(died)}")
            emit.step_complete("bible_update", summary="; ".join(parts))

    emit.done("episode", "ok", number=number)
    return episode
