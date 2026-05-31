"""Pipeline A — series initialization (ARCHITECTURE.md).

    seed_validate → bible_draft (frame) → arc_plan (one beat per episode)
       → bible_verify → series_persist → done

The arc is planned as a *map step* (one LLM call per episode beat), not asked
for all at once: small models reliably write one good beat per call but collapse
when told to emit all N in a single response. Each beat is individually gated
(arc_verify) before it joins the bible, and the fully assembled bible still
passes the unchanged blocking bible_verify gate at the boundary.
"""

from __future__ import annotations

from typing import Optional

from myAIstory import store
from myAIstory.events import EventEmitter
from myAIstory.schemas.models import Bible, SeriesSeed
from myAIstory.synth.base import LLM
from myAIstory.synth.drafts import stream_collect
from myAIstory.synth.prompts import (
    BIBLE_SYSTEM,
    build_arc_beat_prompt,
    build_bible_prompt,
)
from myAIstory.pipeline.retry import run_with_retry
from myAIstory.verify import verify_arc_beat, verify_bible, verify_seed


def run_init(
    seed_raw: dict,
    llm: LLM,
    emit: EventEmitter,
    *,
    persist: bool = True,
    max_retries: int = 2,
    available_voices: Optional[set[str]] = None,
) -> Optional[Bible]:
    """Initialize a series from a seed; returns the persisted Bible or None."""
    series_id = store.slugify(str(seed_raw.get("title", "series")))
    emit.run_start("init", series_id)

    # --- seed_validate (blocking) -------------------------------------------
    emit.step_start("seed_validate")
    seed_result = verify_seed(seed_raw, available_voices=available_voices)
    if not seed_result.passed:
        emit.verify_fail("seed_validate", [str(v) for v in seed_result.violations], 1)
        emit.done("init", "rejected", series_id=series_id, reason="invalid seed")
        return None
    emit.verify_pass("seed_validate", seed_result.checks)
    seed = SeriesSeed.model_validate(seed_raw)

    # --- bible_draft: the FRAME (cast + world, arc left empty) --------------
    def produce_frame(feedback):
        return stream_collect(
            llm, emit,
            stage="bible_draft",
            role="bible_draft",
            system=BIBLE_SYSTEM,
            prompt=build_bible_prompt(seed, feedback),
        )

    frame_obj, _ = run_with_retry(
        produce_frame,
        gates=[lambda o: verify_bible(o, seed, check_arc=False)],
        emit=emit,
        stage="bible_verify",
        max_retries=max_retries,
    )
    if frame_obj is None:
        emit.done("init", "skipped", series_id=series_id, reason="bible frame failed verification")
        return None

    # Pin the series_id to the deterministic slug so storage is predictable.
    frame_obj["series_id"] = series_id
    frame = Bible.model_validate({**frame_obj, "arc": []})

    # --- arc_plan: one verified beat per episode (the map step) -------------
    total = seed.episode_count
    prior: list[tuple[int, str]] = []
    arc: list[dict] = []
    for k in range(1, total + 1):
        def produce_beat(feedback, _k=k):
            return stream_collect(
                llm, emit,
                stage="arc_beat",
                role="arc_beat",
                system=BIBLE_SYSTEM,
                prompt=build_arc_beat_prompt(frame, _k, prior, total, feedback),
                index=_k, total=total,
            )

        beat_obj, _ = run_with_retry(
            produce_beat,
            gates=[lambda o, _k=k: verify_arc_beat(o, _k)],
            emit=emit,
            stage="arc_verify",
            max_retries=max_retries,
        )
        if beat_obj is None:
            # A gap in the arc means an incomplete bible — bounded-retry-then-
            # skip at beat granularity: abort the whole series, logged.
            emit.skip("arc_plan", reason=f"arc beat {k}/{total} failed verification")
            emit.done("init", "skipped", series_id=series_id,
                      reason=f"arc planning failed at episode {k}")
            return None
        beat = {"episode": k, "summary": str(beat_obj["summary"]).strip()}
        arc.append(beat)
        prior.append((k, beat["summary"]))

    # --- bible_verify: the assembled whole, unchanged blocking gate ---------
    assembled = {**frame_obj, "arc": arc}
    result = verify_bible(assembled, seed)  # check_arc=True (the real boundary)
    if not result.passed:
        emit.verify_fail("bible_verify", [str(v) for v in result.violations], 1)
        emit.done("init", "skipped", series_id=series_id, reason="assembled bible failed verification")
        return None
    emit.verify_pass("bible_verify", result.checks)
    bible = Bible.model_validate(assembled)

    # --- series_persist ------------------------------------------------------
    if persist:
        emit.step_start("series_persist")
        path = store.write_bible(bible)
        emit.step_complete("series_persist", summary=str(path))

    emit.done("init", "ok", series_id=series_id)
    return bible
