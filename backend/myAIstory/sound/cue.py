"""cue_verify — the one deliberately NON-blocking gate (CONSTITUTION.md).

Every other verifier blocks: a failure stops the episode. Cues are the
exception. "Sound is enhancement, continuity is the premise" — so a cue tag
the model emits that does not resolve in the SoundLibrary is *dropped*, not
failed. The verified script still becomes an episode; it just loses that one
unrecognized sound. This stage partitions the episode's cue lines into placed
vs dropped; it never raises and never rejects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from myAIstory.schemas.models import Episode
from myAIstory.sound.library import Asset, SoundLibrary


@dataclass(frozen=True)
class CuePlacement:
    idx: int          # position in episode.lines (timeline anchor)
    asset: Asset
    under: bool       # bed plays under following speech (ducked)


@dataclass(frozen=True)
class CueDrop:
    idx: int
    kind: str
    cue: str | None


@dataclass
class CuePlan:
    placements: list[CuePlacement] = field(default_factory=list)
    drops: list[CueDrop] = field(default_factory=list)

    @property
    def has_cues(self) -> bool:
        return bool(self.placements)


def resolve_cues(episode: Episode, library: SoundLibrary) -> CuePlan:
    """Resolve every cue line against the library (non-blocking)."""
    plan = CuePlan()
    for i, line in enumerate(episode.lines):
        if not line.is_cue:
            continue
        asset = library.resolve(line.cue)
        if asset is None:
            plan.drops.append(CueDrop(idx=i, kind=line.kind, cue=line.cue))
        else:
            plan.placements.append(CuePlacement(idx=i, asset=asset, under=line.under))
    return plan
