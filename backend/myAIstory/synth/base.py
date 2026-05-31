"""The synthesis interface.

Everything that drafts text implements `LLM.stream`. The pipeline depends only
on this protocol, never on Ollama directly, so a scripted fake can drive the
whole pipeline in tests with no model running (the same swap-the-backend
discipline as the pluggable TTS interface in phase 3).
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    def stream(self, *, role: str, system: str, prompt: str) -> Iterator[str]:
        """Yield response tokens for a prompt under a named role.

        `role` selects the model + sampling params (see synth/router.py). The
        concatenation of all yielded tokens is the full completion.
        """
        ...
