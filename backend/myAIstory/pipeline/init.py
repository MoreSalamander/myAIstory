"""Pipeline A — series initialization (ARCHITECTURE.md).

    seed_validate → bible_draft → bible_verify → series_persist → done
"""

from __future__ import annotations

from typing import Optional

from myAIstory import store
from myAIstory.events import EventEmitter
from myAIstory.schemas.models import Bible, SeriesSeed
from myAIstory.synth.base import LLM
from myAIstory.synth.drafts import stream_collect
from myAIstory.synth.prompts import BIBLE_SYSTEM, build_bible_prompt
from myAIstory.pipeline.retry import run_with_retry
from myAIstory.verify import verify_bible, verify_seed


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

    # --- bible_draft → bible_verify (bounded retry) -------------------------
    def produce(feedback):
        return stream_collect(
            llm, emit,
            stage="bible_draft",
            role="bible_draft",
            system=BIBLE_SYSTEM,
            prompt=build_bible_prompt(seed, feedback),
        )

    obj, _ = run_with_retry(
        produce,
        gates=[lambda o: verify_bible(o, seed)],
        emit=emit,
        stage="bible_verify",
        max_retries=max_retries,
    )
    if obj is None:
        emit.done("init", "skipped", series_id=series_id, reason="bible failed verification")
        return None

    # Pin the series_id to the deterministic slug so storage is predictable.
    obj["series_id"] = series_id
    bible = Bible.model_validate(obj)

    # --- series_persist ------------------------------------------------------
    if persist:
        emit.step_start("series_persist")
        path = store.write_bible(bible)
        emit.step_complete("series_persist", summary=str(path))

    emit.done("init", "ok", series_id=series_id)
    return bible
