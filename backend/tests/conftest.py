"""Shared fixtures for the verifier test suite.

Builders return valid objects; each test mutates one thing to drive a single
gate to FAIL, proving the gate catches exactly what SPEC says it must.
"""

from __future__ import annotations

import pytest

from myAIstory.schemas.models import (
    ArcBeat,
    Bible,
    CanonCharacter,
    CharacterSeed,
    Episode,
    Line,
    SeriesSeed,
    VoiceMap,
)

# Episodes are tested at a 1-minute target → spoken word band is 110–170.
TARGET_MINUTES = 1


def _words(n: int, *, marker: str = "dragon") -> str:
    """A block of n words that includes a theme marker (so continuity passes)."""
    body = [marker] + ["word"] * (n - 1)
    return " ".join(body)


@pytest.fixture
def seed() -> SeriesSeed:
    return SeriesSeed(
        title="The Ember Cycle",
        theme="dragons",
        characters=[
            CharacterSeed(name="Ember", role="protagonist"),
            CharacterSeed(name="Ash", role="rival"),
        ],
        plot_direction="Two dragons vie for a contested hoard.",
        episode_count=2,
        tone="epic",
        target_minutes=TARGET_MINUTES,
    )


@pytest.fixture
def bible() -> Bible:
    return Bible(
        series_id="the-ember-cycle",
        title="The Ember Cycle",
        theme="dragons",
        tone="epic",
        characters=[
            CanonCharacter(name="Ember", role="protagonist", status="alive",
                           aliases=["The Emberling"]),
            CanonCharacter(name="Ash", role="rival", status="alive"),
        ],
        arc=[
            ArcBeat(episode=1, summary="Ember discovers the hoard."),
            ArcBeat(episode=2, summary="Ash challenges Ember for it."),
        ],
        episode_count=2,
    )


@pytest.fixture
def voice_map() -> VoiceMap:
    return VoiceMap(
        narrator="narrator_v",
        by_character={"Ember": "voice_a", "Ash": "voice_b"},
    )


@pytest.fixture
def make_episode():
    """Factory for a valid episode; override fields via kwargs."""

    def _make(**overrides) -> Episode:
        data = dict(
            number=1,
            title="The Contested Hoard",
            summary="Ember finds the hoard and Ash arrives to contest it.",
            beats=["opening", "development", "resolution_or_hook"],
            lines=[
                Line(kind="narration", speaker="narrator", text=_words(120)),
                Line(kind="dialogue", speaker="Ember", text=_words(15)),
                Line(kind="dialogue", speaker="Ash", text=_words(15)),
            ],
            new_facts=[],
        )
        data.update(overrides)
        return Episode(**data)

    return _make
