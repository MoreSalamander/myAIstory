"""Deterministic speaker salvage — the speaker analog of cue_verify.

A small local model chronically under-uses ``"narrator"``: it invents one-off
speaker names for incidental voices (a guard, a blacksmith, a crowd) without
declaring them as canon. The strict ``speaker_verify`` / ``continuity_verify``
gates then reject the whole episode, and once the retry budget is spent the
episode is *skipped* — a gap in the series. (Observed live: episode 2 skipped
across three attempts, each failing only on an invented speaker.)

This module mirrors the cue_verify philosophy from ARCHITECTURE.md — "unresolved
cues are dropped, not failed" — for speakers. Rather than hard-fail a salvageable
draft, it cleans the draft deterministically *before* the gates run, so the
unchanged, strict gates then pass on a sound draft:

  * **promote-declared** — a speaker the draft explicitly lists in
    ``new_characters`` (validated, non-colliding) is a legitimate same-episode
    introduction. An *augmented* bible / voice-map view (``augment_for_declared``)
    lets the gates accept it. The persistent bible is never touched here — real
    canon growth stays the sole job of the verified ``bible_update`` stage.
  * **salvage-undeclared** — a dialogue line whose speaker is neither a canon
    name/alias, the narrator, nor a declared newcomer is demoted to narration
    (``salvage_speakers``): the line's text is preserved and the narrator
    delivers it, so the moment survives instead of sinking the episode.

Pure-Python, no LLM, no I/O. Trust isolation (CONSTITUTION.md) holds: prose
output is cleaned or demoted, never silently promoted into the source of truth.
A *dead* canon character who speaks is deliberately left untouched — that is a
real continuity contradiction, and ``continuity_verify`` must still reject it.
"""

from __future__ import annotations

from typing import Optional

from myAIstory.events import EventEmitter
from myAIstory.pipeline.voice import assign_voices
from myAIstory.schemas.models import Bible, CanonCharacter, VoiceMap
from myAIstory.verify.resolve import NARRATOR, speaker_index


def declared_new_canon(obj: dict, bible: Bible) -> list[CanonCharacter]:
    """Validated, non-colliding characters this draft declares in new_characters.

    A declared name that is empty, or collides (case-insensitive) with an
    existing canon name/alias or an earlier declaration in the same draft, is
    dropped — exactly the dedup rule ``bible_update`` applies when it promotes
    for real, so the gate's view and the eventual persisted canon agree.
    """
    known = {c.name.strip().lower() for c in bible.characters}
    known |= {a.strip().lower() for c in bible.characters for a in c.aliases}
    out: list[CanonCharacter] = []
    seen: set[str] = set()
    for nc in obj.get("new_characters") or []:
        if not isinstance(nc, dict):
            continue
        name = (nc.get("name") or "").strip()
        low = name.lower()
        if not name or low in known or low in seen:
            continue
        seen.add(low)
        out.append(
            CanonCharacter(name=name, role=nc.get("role"),
                           status=nc.get("status") or "alive")
        )
    return out


def augment_for_declared(
    obj: dict,
    bible: Bible,
    base_voice_map: VoiceMap,
    pool: Optional[list[str]],
    narrator_voice: Optional[str],
) -> tuple[Bible, VoiceMap]:
    """A per-draft *view* of (bible, voice_map) including declared newcomers.

    Returns the originals unchanged when the draft declares nothing. When it
    does, the newcomers are added to a deep copy of the bible and cast a voice
    deterministically (``assign_voices`` re-derives existing assignments
    identically, so only the new names gain entries). The persistent bible is
    never mutated — promotion into the source of truth remains the sole job of
    ``bible_update``.
    """
    declared = declared_new_canon(obj, bible)
    if not declared:
        return bible, base_voice_map
    view = bible.model_copy(deep=True)
    view.characters = list(bible.characters) + declared
    return view, assign_voices(view, pool, narrator_voice)


def salvage_speakers(obj: dict, bible: Bible, emit: EventEmitter) -> list[tuple[int, str]]:
    """Demote dialogue lines with an unknown, undeclared speaker to narration.

    "Unknown" means: not the narrator, not a canon name/alias, and not a
    character this same draft declares in ``new_characters``. The line's text is
    preserved; only ``kind`` → ``"narration"`` and ``speaker`` → ``"narrator"``
    change, so the narrator delivers the line instead of the episode failing.

    Mutates ``obj`` in place and returns the ``(line_index, original_speaker)``
    pairs demoted, for logging. Emits a ``speaker_salvage`` step when it acts.
    """
    legit = set(speaker_index(bible).keys()) | {NARRATOR}
    legit |= {c.name.strip().lower() for c in declared_new_canon(obj, bible)}

    demoted: list[tuple[int, str]] = []
    for i, line in enumerate(obj.get("lines") or []):
        if not isinstance(line, dict) or line.get("kind") != "dialogue":
            continue
        speaker = (line.get("speaker") or "").strip()
        if not speaker or speaker.lower() in legit:
            continue
        line["kind"] = "narration"
        line["speaker"] = NARRATOR
        demoted.append((i, speaker))

    if demoted:
        names = ", ".join(f"{sp!r}@line{i}" for i, sp in demoted)
        emit.step_complete(
            "speaker_salvage",
            summary=f"demoted {len(demoted)} incidental speaker(s) to narrator: {names}",
        )
    return demoted
