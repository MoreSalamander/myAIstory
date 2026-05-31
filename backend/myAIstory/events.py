"""NDJSON event emitter (ARCHITECTURE.md "Event vocabulary").

Every pipeline stage emits newline-delimited JSON events on a shared
vocabulary so a run is observable three ways from one stream: live (web UI,
phase 4), replayable (events.ndjson), and auditable (every gate verdict and
skip is recorded). This module is the single source of that vocabulary.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Callable, TextIO

Sink = Callable[[dict], None]

# The shared vocabulary. verify_fail / retry / skip / cue_* are my-AI-story
# additions; the rest match the studio's existing pipelines.
EVENT_TYPES = frozenset({
    "run_start", "step_start", "token", "step_complete",
    "verify_pass", "verify_fail", "retry", "skip",
    "tts_line", "cue_place", "cue_drop",
    "done", "error",
})


def stdout_sink(stream: TextIO | None = None) -> Sink:
    """A sink that prints one compact JSON object per line."""
    out = stream or sys.stdout

    def _sink(event: dict) -> None:
        out.write(json.dumps(event, ensure_ascii=False) + "\n")
        out.flush()

    return _sink


class EventEmitter:
    """Fans one event out to many sinks (stdout, a file, a web queue…)."""

    def __init__(self, sinks: list[Sink] | None = None) -> None:
        self.sinks: list[Sink] = list(sinks or [])

    def add_sink(self, sink: Sink) -> None:
        self.sinks.append(sink)

    def emit(self, type_: str, **payload) -> dict:
        if type_ not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type_!r}")
        event = {"type": type_, "ts": round(time.time(), 3), **payload}
        for sink in self.sinks:
            sink(event)
        return event

    # --- convenience wrappers for the common events --------------------------

    def run_start(self, pipeline: str, series_id: str, **extra) -> dict:
        return self.emit("run_start", pipeline=pipeline, series_id=series_id, **extra)

    def step_start(self, stage: str, **extra) -> dict:
        return self.emit("step_start", stage=stage, **extra)

    def token(self, stage: str, text: str) -> dict:
        return self.emit("token", stage=stage, text=text)

    def step_complete(self, stage: str, summary: str = "", **extra) -> dict:
        return self.emit("step_complete", stage=stage, summary=summary, **extra)

    def verify_pass(self, stage: str, checks: list[str]) -> dict:
        return self.emit("verify_pass", stage=stage, checks=checks)

    def verify_fail(self, stage: str, violations: list[str], attempt: int) -> dict:
        return self.emit("verify_fail", stage=stage, violations=violations, attempt=attempt)

    def retry(self, stage: str, attempt: int, reason: str) -> dict:
        return self.emit("retry", stage=stage, attempt=attempt, reason=reason)

    def skip(self, stage: str, reason: str) -> dict:
        return self.emit("skip", stage=stage, reason=reason)

    def tts_line(self, speaker: str, voice: str, idx: int) -> dict:
        return self.emit("tts_line", speaker=speaker, voice=voice, idx=idx)

    def done(self, pipeline: str, result: str, **extra) -> dict:
        return self.emit("done", pipeline=pipeline, result=result, **extra)

    def error(self, stage: str, message: str) -> dict:
        return self.emit("error", stage=stage, message=message)
