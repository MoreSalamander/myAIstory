"""Model routing (mirrors my-AI-stro's core/model_router.py).

Roles map to local Ollama models + sampling params. The bible role and the
episode role are separate trust domains (CONSTITUTION.md "Trust isolation"):
even sharing a base model today, bible writes only enter canon through the
verified update stage — prose drafting never silently edits the source of truth.

num_ctx is pinned to 8192 everywhere, matching the my-AI-stro convention that
avoids Ollama's silent-truncation bug at the default 2048.
"""

from __future__ import annotations

from dataclasses import dataclass

NUM_CTX = 8192  # my-AI-stro convention: never rely on the 2048 default


@dataclass(frozen=True)
class ModelSpec:
    model: str
    temperature: float
    num_predict: int
    num_ctx: int = NUM_CTX


# Role → model. Defaults chosen from the user's installed models:
#   llama3.1:8b — strongest instruction-following for structured JSON output.
ROLES: dict[str, ModelSpec] = {
    # World-building: lower temperature for consistent, schema-faithful canon.
    "bible_draft": ModelSpec(model="llama3.1:8b", temperature=0.6, num_predict=2048),
    # Arc planning (the map step): one short beat per call, so a small
    # num_predict is plenty. Same low temperature as the frame — this is canon,
    # not prose — and it shares the bible's trust domain.
    "arc_beat": ModelSpec(model="llama3.1:8b", temperature=0.6, num_predict=256),
    # Prose: a touch warmer for livelier episodes, still JSON-constrained.
    "episode_draft": ModelSpec(model="llama3.1:8b", temperature=0.85, num_predict=2560),
}


def spec_for(role: str) -> ModelSpec:
    try:
        return ROLES[role]
    except KeyError as exc:
        raise KeyError(f"no model routed for role {role!r}") from exc
