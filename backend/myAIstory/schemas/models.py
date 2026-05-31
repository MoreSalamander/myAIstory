"""Typed data contracts for my-AI-story.

These Pydantic models are authoritative for *exact types* (per SPEC.md §1–4);
the SPEC field tables are authoritative for *intent*. The two must agree.

Doctrine note (CONSTITUTION.md): these models define structure only. They do
NOT decide whether a model proposal is trustworthy — that is the job of the
`verify/` package. Construction enforces intrinsic field constraints (lengths,
ranges, allowed values); cross-entity semantics (uniqueness, seed↔bible
consistency, continuity, speaker resolution) live in the verifiers so they can
be reported as structured violations rather than raised as exceptions.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Tunable constants (SPEC delegates "exact taxonomy / bands" to this module).
# ---------------------------------------------------------------------------

MAX_TITLE_LEN = 120
MAX_PLOT_LEN = 2000
MIN_EPISODES, MAX_EPISODES = 1, 50
MIN_MINUTES, MAX_MINUTES, DEFAULT_MINUTES = 1, 30, 5
MIN_CHARACTERS, MAX_CHARACTERS = 1, 12

# Word-count band for structure_verify, derived from target_minutes.
#
# Narrated fiction lands ~110–170 spoken words/minute, but matching audio
# runtime EXACTLY is not the goal: a complete-but-short episode is a story
# decision, not a defect — a tight arc beat may simply not need more words,
# and a small local model chronically under-writes against a strict floor.
# So the verifier band is deliberately WIDE: a lenient per-minute floor that
# only rejects genuine stubs, and a generous ceiling that only catches
# runaway repetition. The draft prompt still AIMS for a runtime-matched
# length (see WPM_AIM) so audio lands near the target — but falling short of
# that aim is guidance, not a gate.
WPM_MIN, WPM_MAX = 15, 240
# Absolute stub guard: no matter how short the target runtime, an episode
# below this many spoken words is not a real episode and is rejected.
MIN_SPOKEN_WORDS = 60
# What the *draft prompt* aims for (not enforced): a healthy runtime-matched
# length so the rendered audio lands near the requested minutes.
WPM_AIM = 150

# Episode beat taxonomy. `beats` is a list of these kind-labels; the three
# REQUIRED kinds must all be present (SPEC §3 "Required beat kinds").
BEAT_KINDS = (
    "opening",
    "development",
    "rising_action",
    "turn",
    "climax",
    "resolution_or_hook",
)
REQUIRED_BEATS = ("opening", "development", "resolution_or_hook")

# Line kinds. Speech kinds are rendered by TTS; cue kinds (phase 2) are mixed
# from the sound library. The cue/under fields exist now so phase 2 is not a
# schema break (SPEC §3, §6).
SPEECH_KINDS = ("narration", "dialogue")
CUE_KINDS = ("sfx", "ambience", "music")

CharacterStatus = Literal["alive", "dead", "unknown"]
LineKind = Literal["narration", "dialogue", "sfx", "ambience", "music"]


# ---------------------------------------------------------------------------
# 1. SeriesSeed — human-owned input
# ---------------------------------------------------------------------------

class CharacterSeed(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    role: Optional[str] = None
    voice: Optional[str] = None  # a TTS voice id; resolved later if omitted


class SeriesSeed(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=MAX_TITLE_LEN)
    theme: str = Field(min_length=1)
    characters: list[CharacterSeed] = Field(
        min_length=MIN_CHARACTERS, max_length=MAX_CHARACTERS
    )
    plot_direction: str = Field(default="", max_length=MAX_PLOT_LEN)
    episode_count: int = Field(ge=MIN_EPISODES, le=MAX_EPISODES)
    tone: Optional[str] = None
    target_minutes: int = Field(default=DEFAULT_MINUTES, ge=MIN_MINUTES, le=MAX_MINUTES)


# ---------------------------------------------------------------------------
# 2. Bible — the source of truth
# ---------------------------------------------------------------------------

class CanonCharacter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    role: Optional[str] = None
    voice: Optional[str] = None
    status: CharacterStatus = "alive"
    facts: list[str] = Field(default_factory=list)


class WorldFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    statement: str
    established_in_episode: Optional[int] = None


class ArcBeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    episode: int = Field(ge=1)
    summary: str


class Bible(BaseModel):
    model_config = ConfigDict(extra="ignore")

    series_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    theme: str = Field(min_length=1)
    tone: Optional[str] = None
    characters: list[CanonCharacter] = Field(min_length=1)
    world_facts: list[WorldFact] = Field(default_factory=list)
    arc: list[ArcBeat] = Field(default_factory=list)
    episode_count: int = Field(ge=MIN_EPISODES, le=MAX_EPISODES)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# 3. Episode
# ---------------------------------------------------------------------------

class Line(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: LineKind
    speaker: Optional[str] = None  # required for speech kinds (verifier-checked)
    text: Optional[str] = None     # required for speech kinds (verifier-checked)
    cue: Optional[str] = None      # phase 2: asset tag for cue kinds
    under: bool = False            # phase 2: bed plays under following speech

    @property
    def is_speech(self) -> bool:
        return self.kind in SPEECH_KINDS

    @property
    def is_cue(self) -> bool:
        return self.kind in CUE_KINDS


class Episode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int = Field(ge=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    beats: list[str] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    new_facts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. VoiceMap
# ---------------------------------------------------------------------------

class VoiceMap(BaseModel):
    model_config = ConfigDict(extra="ignore")

    narrator: str = Field(min_length=1)
    by_character: dict[str, str] = Field(default_factory=dict)
