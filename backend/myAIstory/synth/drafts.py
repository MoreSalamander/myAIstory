"""Draft stages: stream a completion while emitting token events.

These functions are the only place the model's output enters the pipeline. The
text they return is an untrusted proposal — the caller parses and gates it.
"""

from __future__ import annotations

from myAIstory.events import EventEmitter
from myAIstory.synth.base import LLM


def stream_collect(
    llm: LLM,
    emit: EventEmitter,
    *,
    stage: str,
    role: str,
    system: str,
    prompt: str,
    **step_extra,
) -> str:
    """Run one draft, emitting `token` events, and return the full completion.

    Any ``step_extra`` (e.g. index/total for a map step) is attached to the
    step_start/step_complete events so a UI can show progress through a loop.
    """
    emit.step_start(stage, **step_extra)
    parts: list[str] = []
    for chunk in llm.stream(role=role, system=system, prompt=prompt):
        parts.append(chunk)
        emit.token(stage, chunk)
    text = "".join(parts)
    emit.step_complete(stage, summary=f"{len(text)} chars", **step_extra)
    return text
