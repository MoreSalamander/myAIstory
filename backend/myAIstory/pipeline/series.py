"""Run a whole series: init, then every episode in order.

A skipped episode (verification budget exhausted) does not abort the run — the
series continues, and the skip is in the event log. This is the bounded-retry-
then-skip policy at series scale: the system never force-persists bad work, and
never lets one bad episode kill the rest.
"""

from __future__ import annotations

from typing import Optional

from myAIstory.events import EventEmitter
from myAIstory.schemas.models import Bible, DEFAULT_MINUTES, Episode
from myAIstory.pipeline.episode import run_episode
from myAIstory.pipeline.init import run_init
from myAIstory.synth.base import LLM
from myAIstory.tts.base import TTSEngine


def run_series(
    seed_raw: dict,
    llm: LLM,
    emit: EventEmitter,
    *,
    target_minutes: Optional[int] = None,
    tts: Optional[TTSEngine] = None,
    persist: bool = True,
    max_retries: int = 2,
    max_episodes: Optional[int] = None,
) -> tuple[Optional[Bible], list[Episode]]:
    """Initialize a series and generate its episodes.

    Returns (bible, episodes). bible is None if init failed; episodes contains
    only the ones that passed verification (skips are omitted but logged).
    """
    bible = run_init(seed_raw, llm, emit, persist=persist, max_retries=max_retries)
    if bible is None:
        return None, []

    target = target_minutes or int(seed_raw.get("target_minutes", DEFAULT_MINUTES))
    count = bible.episode_count
    if max_episodes is not None:
        count = min(count, max_episodes)

    episodes: list[Episode] = []
    for number in range(1, count + 1):
        episode = run_episode(
            bible.series_id, number, llm, emit,
            bible=bible, target_minutes=target, tts=tts,
            persist=persist, max_retries=max_retries,
        )
        if episode is not None:
            episodes.append(episode)

    return bible, episodes
