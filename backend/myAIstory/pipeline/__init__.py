"""Pipeline orchestration: the named stages wired together (ARCHITECTURE.md).

The orchestrators emit NDJSON events and route the model's proposals through the
verifier gates with bounded-retry-then-skip. They depend on the synth/ layer via
the LLM protocol, so a scripted fake can drive them with no model running.
"""

from myAIstory.pipeline.audio import render_episode
from myAIstory.pipeline.episode import run_episode
from myAIstory.pipeline.init import run_init
from myAIstory.pipeline.retry import run_with_retry
from myAIstory.pipeline.series import run_series
from myAIstory.pipeline.voice import assign_voices

__all__ = [
    "run_episode",
    "run_init",
    "run_series",
    "run_with_retry",
    "assign_voices",
    "render_episode",
]
