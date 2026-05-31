"""A scripted LLM for tests and offline runs.

Returns canned completions per role, in order, so the full pipeline — drafting,
gating, bounded retry, persistence — can be exercised deterministically with no
Ollama server. This is how the orchestration is tested without the unreliable
component actually being unreliable.
"""

from __future__ import annotations

from typing import Iterator


class ScriptedLLM:
    """Yields pre-written responses, one per call, keyed by role.

    Pass a dict of role -> list[str]. Each call to stream() pops the next
    response for that role and yields it word-by-word to mimic streaming. This
    lets a test script a first (bad) draft followed by a corrected one to drive
    the retry path.
    """

    def __init__(self, responses: dict[str, list[str]]) -> None:
        self._responses = {role: list(items) for role, items in responses.items()}
        self.calls: list[tuple[str, str]] = []  # (role, prompt) audit trail

    def stream(self, *, role: str, system: str, prompt: str) -> Iterator[str]:
        self.calls.append((role, prompt))
        queue = self._responses.get(role)
        if not queue:
            raise AssertionError(f"ScriptedLLM has no more responses for role {role!r}")
        text = queue.pop(0)
        for i, word in enumerate(text.split(" ")):
            yield (" " if i else "") + word
