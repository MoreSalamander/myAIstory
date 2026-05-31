"""CLI: generate a verified series from a seed (text-only, phase 2).

    python -m myAIstory.cli                     # sample seed, persist to data/
    python -m myAIstory.cli --seed seed.json    # your own seed
    python -m myAIstory.cli --episodes 1        # just the first episode
    python -m myAIstory.cli --minutes 2         # ~2-minute episodes

Streams NDJSON events to stdout and (when persisting) appends them to the
series' events.ndjson. Requires a running Ollama server (`ollama serve`).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from myAIstory import store
from myAIstory.events import EventEmitter, stdout_sink
from myAIstory.pipeline.series import run_series
from myAIstory.synth import OllamaClient

SAMPLE_SEED = {
    "title": "The Ember Cycle",
    "theme": "dragons",
    "tone": "epic",
    "characters": [
        {"name": "Ember", "role": "protagonist"},
        {"name": "Ash", "role": "rival"},
    ],
    "plot_direction": "Two dragons contest an ancient hoard beneath a dying volcano.",
    "episode_count": 3,
    "target_minutes": 2,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a verified my-AI-story series.")
    parser.add_argument("--seed", help="path to a seed JSON file")
    parser.add_argument("--episodes", type=int, default=None,
                        help="cap the number of episodes generated")
    parser.add_argument("--minutes", type=int, default=None,
                        help="override target minutes per episode")
    parser.add_argument("--no-persist", action="store_true",
                        help="do not write any files (events still print)")
    args = parser.parse_args(argv)

    if args.seed:
        with open(args.seed, encoding="utf-8") as fh:
            seed = json.load(fh)
    else:
        seed = SAMPLE_SEED

    persist = not args.no_persist
    emit = EventEmitter([stdout_sink()])
    series_id = store.slugify(str(seed.get("title", "series")))
    if persist:
        emit.add_sink(store.event_sink(series_id))

    llm = OllamaClient()
    bible, episodes = run_series(
        seed, llm, emit,
        target_minutes=args.minutes,
        persist=persist,
        max_episodes=args.episodes,
    )

    if bible is None:
        print("series initialization failed — see events above", file=sys.stderr)
        return 1

    print(
        f"\n{len(episodes)}/{bible.episode_count} episodes verified for "
        f"'{bible.series_id}'"
        + (f" → backend/data/series/{bible.series_id}/" if persist else " (not persisted)"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
